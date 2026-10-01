import asyncio
import hashlib
import json
import time
import uuid
from urllib.parse import urlsplit
from . import assets, catalog, config, db, providers, personal
from .security import redact

def seed_templates():
    items=json.loads((config.ROOT/"config/templates.json").read_text())
    with db.connection() as conn:
        for t in items:
            if t.get('builtin_revision'):
                previous = conn.execute("SELECT version,body FROM templates WHERE id=?", (t['id'],)).fetchall()
                if any(json.loads(r['body']).get('builtin_revision') == t['builtin_revision'] for r in previous):
                    continue
                t = dict(t, version=max(t['version'], max((r['version'] for r in previous), default=0)+1))
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
    from .capabilities import validate as check
    m=catalog.model(b['model_id']);t=template(b['template_id'],b['template_version'])
    if t['kind']!=b['kind'] or (m['kind']=='image')!=(b['kind']=='image'):raise ValueError('模板、模型与生成类型不匹配')
    if b.get('personal_settings'):
        if b['kind']!='image' or b['template_id']!='personal-image' or b.get('personal_profile_id'):raise ValueError('个人形象生成须使用个人形象图片模板')
        p=personal.check(b['personal_settings']);b['personal_settings']=p
        b['refs']=personal.refs(p);b['prompt_override']=personal.prompt(p)
        b['video_mode']='reference' if b['refs'] else 'text'
        b['person_mode']='self' if b['refs'] else 'default';b['identity_consent']=p['consent']
    elif b['template_id']=='personal-image':raise ValueError('个人形象模板需要形象设置')
    if b.get('personal_profile_id'):
        p=personal.get(b['personal_profile_id'])
        if b['kind']!='image':raise ValueError('个人形象先用于穿搭生图；视频请使用完整穿搭首帧')
        if not any(r.get('asset_id')==p['asset_id'] and r['role']=='body' for r in b['refs']):raise ValueError('请选择个人形象全身参考图')
        if b['mode']=='live' and p['mode']=='mock':raise ValueError('模拟形象不能用于真实穿搭，请先建立真实形象')
        b['personal_profile_snapshot']=p
        b['person_mode']='self'
        b['prompt_override']=(b['prompt_override'] or t['prompt'])+'\n个人形象全身图提供脸部、体型、身材比例与已确认发型；独立脸部图若提供只补充五官细节。保持个人形象体型与发型，基础T恤和长裤必须替换为指定商品服装；不要沿用形象图的基础服装。姿势与构图遵循当前展示模板。'
    checked=check(b,m,t)
    from .billing import context
    checked['billing_snapshot']=context(checked)
    return checked

def estimate(b):
    from .pricing import estimate as quote
    return quote(b)


def create_job(b,idem):
    # Model/profile/template frozen per job; later switching never changes existing tasks.
    b=validate(b)
    expected=estimate(b)["estimated_cny"]
    if b["mode"]=="live" and expected is not None and expected>b["max_cost"]:raise ValueError("预占预算低于官方参考成本")
    canonical=json.dumps(b,sort_keys=True,ensure_ascii=False)
    digest=hashlib.sha256(canonical.encode()).hexdigest()
    jid=uuid.uuid4().hex
    b["job_id"]=jid
    request=providers.build_request(b["model_snapshot"],b,True)
    b["request_endpoint"]={"method":request["method"],"url":request["url"]}
    with db.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing=conn.execute("SELECT * FROM jobs WHERE idem=?",(idem,)).fetchone()
        if existing:
            if existing["request_hash"]!=digest:raise ValueError("同一幂等编号不能用于不同请求")
            return db.decode_job(existing)
        if conn.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','submitting','polling','saving')").fetchone()[0]>=24:raise ValueError("任务队列已满，请稍后提交")
        conn.execute("INSERT INTO jobs(id,idem,request_hash,body,state,created,updated,reserved) VALUES(?,?,?,?,?,?,?,?)",(jid,idem,digest,json.dumps(b,ensure_ascii=False),"queued",db.now(),db.now(),0 if b["mode"]=="mock" else b["max_cost"]))
        row=conn.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone()
    db.event(jid,"input_validate","素材、模板与预算校验完成；任务已排队")
    return db.decode_job(row)

def handle_result(job,result):
    # Query responses carry cumulative usage. Preserve it when later responses omit it.
    previous=json.loads(job.get('result') or '{}')
    result=dict(result)
    old_usage=previous.get('usage');new_usage=result.get('usage')
    result['usage']={**(old_usage if isinstance(old_usage,dict) else {}), **(new_usage if isinstance(new_usage,dict) else {})}
    from .billing import automatic
    bill=automatic(json.loads(job['body']), result['usage']) or previous.get('auto_billing')
    if bill:
        result['auto_billing']=bill
        review=json.loads(job.get('review') or '{}')
        if review.get('billing',{}).get('cost_source') not in ('receipt','units_calculated'):
            db.update_job(job['id'],actual=bill['actual_cny'])
    db.update_job(job['id'],result=json.dumps(result))
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
    # Recalculate previously persisted provider usage using each job's frozen tariff.
    from .billing import automatic
    with db.connection() as conn:
        rows=conn.execute("SELECT * FROM jobs WHERE result IS NOT NULL").fetchall()
        for row in rows:
            j=dict(row);result=json.loads(j['result'] or '{}')
            bill=automatic(json.loads(j['body']),result.get('usage') or {})
            if not bill:continue
            result['auto_billing']=bill
            review=json.loads(j['review'] or '{}')
            actual=j['actual'] if review.get('billing',{}).get('cost_source') in ('receipt','units_calculated') else bill['actual_cny']
            conn.execute('UPDATE jobs SET result=?,actual=? WHERE id=?',(json.dumps(result),actual,j['id']))
    with db.connection() as conn:
        conn.execute("UPDATE jobs SET state='uncertain',error='服务重启时提交结果尚未落盘，请核对供应商控制台，不自动重提' WHERE state='submitting'")
