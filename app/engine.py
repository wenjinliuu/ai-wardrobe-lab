import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from . import assets, catalog, config, db, providers
from .security import redact

def seed_templates():
    items=json.loads((config.ROOT/"config/templates.json").read_text())
    with db.connection() as conn:
        for t in items:
            conn.execute("INSERT OR IGNORE INTO templates VALUES(?,?,?,?)",(t["id"],t["version"],json.dumps(t,ensure_ascii=False),db.now()))

def templates():
    with db.connection() as conn:
        return [json.loads(r["body"]) for r in conn.execute("SELECT t.* FROM templates t JOIN (SELECT id,MAX(version) v FROM templates GROUP BY id) m ON m.id=t.id AND m.v=t.version ORDER BY t.created")]

def template(id,version):
    with db.connection() as conn:
        row=conn.execute("SELECT body FROM templates WHERE id=? AND version=?",(id,version)).fetchone()
    if not row:raise ValueError("模板版本不存在")
    return json.loads(row["body"])

def validate(b):
    m=catalog.model(b["model_id"])
    t=template(b["template_id"],b["template_version"])
    if t["kind"]!=b["kind"] or (m["kind"]=="image")!=(b["kind"]=="image"):
        raise ValueError("模板、模型与生成类型不匹配")
    if not b["refs"] or len(b["refs"])>12:raise ValueError("请提供1～12个素材引用")
    if len({r["asset_id"] for r in b["refs"]})!=len(b["refs"]):raise ValueError("同一张素材不能重复引用，请明确唯一角色")
    roles=[r["role"] for r in b["refs"]]
    for r in b["refs"]:
        if r["role"] not in catalog.ROLES:raise ValueError("未知素材角色")
        a=db.get_asset(r["asset_id"])
        expected="video" if r["role"]=="motion" else "image"
        if a["kind"]!=expected:raise ValueError("动作需要视频，其余角色需要图片")
        if expected=="image":
            if a["width"]<m["min_side"] or a["height"]<m["min_side"] or max(a["width"],a["height"])>m["max_side"] or a["size"]>m["max_mb"]*1024*1024:raise ValueError(f"{a['name']}不符合模型尺寸或大小限制")
            if m["adapter"] in {"kling","kling_motion","h3"} and not .4<=a["width"]/a["height"]<=2.5:raise ValueError("该模型要求图片宽高比在0.4～2.5之间")
        else:
            if not m.get("video_min") or not m["video_min"]<=a["duration"]<=m["video_max"]:raise ValueError("动作视频时长不符合该模型要求")
            if a["size"]>m["video_mb"]*1024*1024 or min(a["width"],a["height"])<m["video_side_min"] or max(a["width"],a["height"])>m["video_side_max"]:raise ValueError("动作视频尺寸或大小超出限制")
    if "identity" in roles and not b["identity_consent"]:raise ValueError("本人参考需要明确确认素材授权")
    if b["kind"]=="image":
        if b["person_mode"]=="self" and "identity" not in roles:
            raise ValueError("本人模式需要人物参考图；不使用自拍请选择默认模特")
        if any(r in roles for r in ("motion","look")):raise ValueError("生图请使用人物、姿势和衣服参考，不使用动作或完整Look角色")
        if t["category"]=="garment_present" and len(roles)!=1:raise ValueError("商品图整理请只选择一件衣物")
        if t["category"]=="outfit_image" and not any(r in roles for r in ("upper","lower","shoes")):raise ValueError("穿搭图至少需要一件服装参考")
    else:
        if roles.count("look")!=1:raise ValueError("视频必须选择一张完整穿搭图")
        if not b["image_confirmed"]:raise ValueError("请先确认穿搭图，再生成视频")
        a=db.get_asset(next(r["asset_id"] for r in b["refs"] if r["role"]=="look"))
        parent=db.get_job(a["source"])
        if parent:
            review=json.loads(parent["review"] or "{}")
            if review.get("verdict")!="pass":raise ValueError("生成图需在任务详情中评为合格后才可做视频")
            if b["mode"]=="live" and json.loads(parent["body"])["mode"]=="mock":raise ValueError("模拟结果不能作为真实视频生成输入")
        if m["kind"]=="motion" and roles.count("motion")!=1:raise ValueError("动作迁移模型需要一段动作参考视频")
        if roles.count("motion")>1:raise ValueError("首版每次只支持一段动作参考")
        if m["adapter"] not in ("h3",) and m["kind"]!="motion" and "motion" in roles:raise ValueError("当前模型不支持动作参考视频")
        if m["kind"] in ("video","motion") and any(r not in ("look","motion") for r in roles):raise ValueError("普通视频接口只接收完整穿搭图；其他素材应先合成图片")
        if m["adapter"]=="h3" and b["video_mode"]=="first_frame" and (len(roles)>1):raise ValueError("H3 首帧与多素材参考模式互斥，请选择参考模式")
        if m.get("restricted_identity"):
            inherited=parent and any(r["role"]=="identity" for r in json.loads(parent["body"])["refs"])
            if b["person_mode"]=="self" or inherited:raise ValueError("Seedance 真人授权资产录入尚未接入，当前仅开放默认模特模式")
    count=sum(r!="motion" for r in roles)
    if not b["reference_board"] and count>m["max_images"]:raise ValueError(f"该模型最多接收{m['max_images']}张图片，可换模型或在生图中试验参考板")
    if b["reference_board"] and b["kind"]!="image":raise ValueError("参考板只能用于图像对照，不能直接作为视频首帧")
    if b["resolution"] not in m["resolutions"]:raise ValueError("清晰度或服务模式不支持")
    if m["durations"] and b["duration"] not in m["durations"]:raise ValueError("时长不支持")
    if b["mode"]=="live":
        if not config.LIVE or not config.key(m["provider"]):raise ValueError("真实调用未开启或服务器尚未配置该平台Key")
        if not b["paid_confirmed"]:raise ValueError("请明确确认本次真实付费调用")
        if b["max_cost"]<=0:raise ValueError("真实调用需填写预算预占金额")
        if not config.PUBLIC_BASE.startswith("https://") and sum(a["size"] for a in [db.get_asset(r["asset_id"]) for r in b["refs"]])>32*1024*1024:
            raise ValueError("内联素材合计超过32MB，请配置HTTPS素材地址或减少素材大小")
        if m["kind"]=="motion" or (m["adapter"]=="h3" and "motion" in roles):
            u=urlsplit(config.PUBLIC_BASE)
            if u.scheme!="https" or not u.hostname:raise ValueError("动作视频输入需要部署后的 HTTPS 公网地址")
    prompt=b["prompt_override"] or t["prompt"]
    if t.get("negative_prompt"):
        prompt += "\n避免："+t["negative_prompt"]
    if m["prompt_max"]:
        mapping="\n参考顺序："+"；".join(f"图{i+1}={catalog.ROLES[r['role']]}" for i,r in enumerate(b["refs"]) if r["role"]!="motion")
        if b["reference_board"]:mapping+="。素材在一张参考板内按编号排列；输出应为完整单人照片，不能包含参考板或编号。"
        b["compiled_prompt"]=prompt+mapping
        if len(b["compiled_prompt"])>m["prompt_max"]:raise ValueError(f"提示词与角色说明合计超过{m['prompt_max']}字符")
    else:b["compiled_prompt"]="" # Wan Animate takes only image + motion; no ignored prompt
    b["template_snapshot"]=t
    b["model_snapshot"]=m.copy()
    b["workflow_version"]="1.0.0"
    b["prompt_version"]=f"{t['id']}@{t['version']}"+("+override" if b["prompt_override"] else "")
    b["asset_snapshot"]=[{k:db.get_asset(r["asset_id"])[k] for k in ("id","sha256","width","height","duration","size")} | {"role":r["role"]} for r in b["refs"]]
    return b

def estimate(b):
    m=b["model_snapshot"]
    rate=m.get("prices",{}).get(b["resolution"])
    duration=b["duration"]
    if m["kind"]=="motion":duration=next(a["duration"] for a in b["asset_snapshot"] if a["role"]=="motion")
    cost=round(rate*duration,4) if rate is not None else None
    return dict(estimated_cny=0 if b["mode"]=="mock" else cost,reference_cny=cost,price_date=m.get("price_date"),source="官方参考价格" if rate else "待核对账单",note="预算预占仅限制本站新增任务，不是供应商硬性费用上限；实际账单需核对。")

def create_job(b,idem):
    # Model/profile/template frozen per job; later switching never changes existing tasks.
    b=validate(b)
    expected=estimate(b)["estimated_cny"]
    if b["mode"]=="live" and expected is not None and expected>b["max_cost"]:raise ValueError("预占预算低于官方参考成本")
    canonical=json.dumps(b,sort_keys=True,ensure_ascii=False)
    digest=hashlib.sha256(canonical.encode()).hexdigest()
    jid=uuid.uuid4().hex
    b["job_id"]=jid
    with db.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing=conn.execute("SELECT * FROM jobs WHERE idem=?",(idem,)).fetchone()
        if existing:
            if existing["request_hash"]!=digest:raise ValueError("同一幂等编号不能用于不同请求")
            return db.decode_job(existing)
        if conn.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','submitting','polling','saving')").fetchone()[0]>=24:raise ValueError("任务队列已满，请稍后提交")
        if b["mode"]=="live":
            shanghai=timezone(timedelta(hours=8));n=datetime.now(shanghai)
            start=n.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            count,total=conn.execute("SELECT COUNT(*),COALESCE(SUM(COALESCE(actual,reserved)),0) FROM jobs WHERE created>=? AND json_extract(body,'$.mode')='live'",(start,)).fetchone()
            if count>=config.DAILY_CALLS or total+b["max_cost"]>config.DAILY_BUDGET:raise ValueError("超过今日调用次数或预算预占上限")
        conn.execute("INSERT INTO jobs(id,idem,request_hash,body,state,created,updated,reserved) VALUES(?,?,?,?,?,?,?,?)",(jid,idem,digest,json.dumps(b,ensure_ascii=False),"queued",db.now(),db.now(),0 if b["mode"]=="mock" else b["max_cost"]))
        row=conn.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone()
    db.event(jid,"input_validate","素材、模板与预算校验完成；任务已排队")
    return db.decode_job(row)

def handle_result(job,result):
    if result.get("task_id"):
        db.update_job(job["id"],provider_task_id=str(result["task_id"]))
    db.update_job(job["id"],request_id=result.get("request_id", ""))
    if result["status"]=="succeeded":
        if not result["urls"]:raise ValueError("供应商报告成功但没有返回文件地址")
        db.update_job(job["id"],result=json.dumps(result),state="saving",next_poll=0)
        db.event(job["id"],"asset_finalize","模型生成完成，开始保存文件；账单金额仍需核对")
    elif result["status"]=="failed":
        db.update_job(job["id"],state="failed",error=result.get("error") or "供应商生成失败，请按任务编号核对控制台",result=json.dumps(result))
        db.event(job["id"],"failed","供应商报告失败；不会自动重新生成，费用待账单核对")
    elif result["status"]=="unknown":
        db.update_job(job["id"],state="paused",error="供应商任务状态未知，请核对控制台后恢复查询")
    else:
        if not result.get("task_id") and not job.get("provider_task_id"):raise providers.AmbiguousSubmission("缺少任务编号，无法自动续查")
        db.update_job(job["id"],state="polling",next_poll=db.now()+config.POLL_INTERVAL)

def step(job):
    b=json.loads(job["body"]);m=b["model_snapshot"];jid=job["id"]
    if job["state"]=="queued":
        db.update_job(jid,state="submitting")
        db.event(jid,"generation","模拟流程开始" if b["mode"]=="mock" else "提交一次生成请求，提交异常不会自动重提")
        if b["mode"]=="mock":
            if b["mock_failure"]=="submit_unknown":raise providers.AmbiguousSubmission("模拟：提交后网络中断，禁止自动重提")
            db.update_job(jid,provider_task_id="mock-"+jid,state="polling",next_poll=db.now()+1)
        else:
            if b["reference_board"]:
                board=assets.reference_board(b["refs"])
                b["refs"]=[{"asset_id":board["id"],"role":"pose"}]
            handle_result(job,providers.transport(m,body=b))
    elif job["state"]=="polling":
        if b["mode"]=="mock":
            if b["mock_failure"]=="generation":
                handle_result(job,dict(status="failed",task_id=job["provider_task_id"],urls=[],error="模拟：模型生成失败"))
            else:
                db.update_job(jid,state="saving",result=json.dumps({"mock":True,"usage":{"calls":0}}),next_poll=0)
        else:
            handle_result(job,providers.transport(m,task_id=job["provider_task_id"]))
    elif job["state"]=="saving":
        result=json.loads(job["result"])
        if b["mock_failure"]=="save_once" and job["attempt"]==0:
            db.update_job(jid,state="save_failed",error="模拟：文件保存失败，可仅重试保存",attempt=1)
            return
        outputs=json.loads(job["outputs"])
        if result.get("mock"):
            if not outputs:outputs.append(assets.mock_result(job)["id"])
        else:
            for i,url in enumerate(result["urls"]):
                if i<len(outputs):continue
                outputs.append(assets.download_result(url,b["kind"],jid,i)["id"])
                db.update_job(jid,outputs=json.dumps(outputs)) # resume partial downloads, no model call
        db.update_job(jid,outputs=json.dumps(outputs),state="succeeded",error="",actual=0 if b["mode"]=="mock" else job["actual"])
        db.event(jid,"human_review","结果已保存，可以下载并进行人工评分；不代表服装还原已通过")

def tick():
    with db.connection() as conn:
        row=conn.execute("SELECT * FROM jobs WHERE state IN ('queued','polling','saving') AND next_poll<=? ORDER BY CASE WHEN state='queued' THEN 1 ELSE 0 END,created LIMIT 1",(db.now(),)).fetchone()
    if not row:return
    job=dict(row)
    if job["state"]=="polling" and db.now()-job["created"]>7200:
        db.update_job(job["id"],state="paused",error="等待超过2小时；可恢复查询，不重新生成")
        return
    try:
        step(job)
    except providers.AmbiguousSubmission as e:
        db.update_job(job["id"],state="uncertain",error=str(e))
        db.event(job["id"],"uncertain","提交结果不确定；需人工核对供应商任务编号")
    except providers.ProviderFailure as e:
        if job["state"]=="polling":
            db.update_job(job["id"],next_poll=db.now()+max(30,config.POLL_INTERVAL),error=str(e))
        else:db.update_job(job["id"],state="failed",error=str(e))
    except Exception as e:
        message=str(redact(str(e)))[:300]
        if job["state"]=="saving":
            db.update_job(job["id"],state="save_failed",error="结果保存失败，可重试保存；"+type(e).__name__)
        elif job["state"]=="queued" and json.loads(job["body"])["mode"]=="live":
            db.update_job(job["id"],state="uncertain",error="提交处理异常，请核对供应商控制台；"+type(e).__name__)
        else:db.update_job(job["id"],state="failed",error=message)

async def worker():
    # Exactly one worker process. Persist-before-submit avoids hidden repeat charges.
    while True:
        await asyncio.to_thread(tick)
        await asyncio.sleep(.5)

def recover():
    with db.connection() as conn:
        conn.execute("UPDATE jobs SET state='uncertain',error='服务重启时提交结果尚未落盘，请核对供应商控制台，不自动重提' WHERE state='submitting'")
