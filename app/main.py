import asyncio
import csv
import io
import json
import secrets
import time
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from . import assets, catalog, config, db, engine
from .security import check_origin, require_auth, require_write, session, sign, validate_asset_signature

@asynccontextmanager
async def lifespan(app):
    config.validate_config();db.init();engine.seed_templates();engine.recover()
    task=asyncio.create_task(engine.worker())
    app.state.worker=task
    yield
    task.cancel()
    try:await task
    except asyncio.CancelledError:pass

app=FastAPI(title="AI Wardrobe Lab",version="0.1.0",lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware("http")
async def headers(request,call_next):
    response=await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="no-referrer"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith(("/api","/media")):response.headers["Cache-Control"]="no-store"
    return response

@app.exception_handler(ValueError)
async def validation_error(request,exc):
    return JSONResponse({"detail":str(exc)},status_code=422)

class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid")

class Login(Strict):
    password:str=Field(max_length=256)

@app.get("/healthz")
def health(request:Request):
    task=getattr(request.app.state,"worker",None)
    if task is not None and task.done():
        raise HTTPException(503,"后台任务调度器已停止")
    return {"status":"ok","version":"0.1.0"}

@app.post("/api/login")
def login(data:Login,request:Request):
    check_origin(request)
    ip=request.client.host
    with db.connection() as conn:
        conn.execute("DELETE FROM login_attempts WHERE created<?",(time.time()-600,))
        count=conn.execute("SELECT COUNT(*) FROM login_attempts WHERE ip=?",(ip,)).fetchone()[0]
        if count>=10:raise HTTPException(429,"登录尝试过多，请10分钟后重试")
        if not config.PASSWORD or not secrets.compare_digest(data.password,config.PASSWORD):
            conn.execute("INSERT INTO login_attempts VALUES(?,?)",(ip,time.time()))
            # commit before returning; HTTPException would roll back the attempt
            return JSONResponse({"detail":"访问密码不正确"},status_code=401)
    token=session()
    response=JSONResponse({"csrf":sign("csrf:"+token)})
    response.set_cookie("lab_session",token,max_age=43200,httponly=True,secure=config.PUBLIC_BASE.startswith("https://"),samesite="strict")
    return response

@app.post("/api/logout",dependencies=[Depends(require_write)])
def logout():
    r=JSONResponse({"ok":True});r.delete_cookie("lab_session");return r

@app.get("/api/bootstrap")
def bootstrap(token=Depends(require_auth)):
    return {"csrf":sign("csrf:"+token),"models":catalog.MODELS,"templates":engine.templates(),"roles":catalog.ROLES,"skills":catalog.SKILLS,"usages":catalog.USAGES,"live_enabled":config.LIVE,"dev_mode":config.DEV,"daily_budget":None,"daily_call_limit":None,
            "providers":[dict(id=k,name=v["name"],base=v["base"],key_env=v["key_env"],configured=bool(config.key(k))) for k,v in config.PROVIDERS.items()]}

def public_asset(a, job_sources=None):
    j=job_sources.get(a['source']) if job_sources is not None else db.get_job(a['source']) if a['source'] else None
    provenance={'type':'demo' if a['source']=='demo' else 'upload' if a['source']=='upload' else 'unknown'}
    if provenance['type']=='upload':
        provenance['upload_origin']=json.loads(a.get('details') or '{}').get('upload_origin','unknown')
    if j:
        b=json.loads(j['body']);m=b['model_snapshot'];r=json.loads(j['review'] or '{}')
        provenance=dict(type='mock_generated' if b['mode']=='mock' else 'generated',job_id=j['id'],
                        provider=m['provider'],model=m['model'],model_name=m['name'],label=b.get('label'),
                        resolution=b['resolution'],duration=b['duration'] if b['kind']=='video' else None,
                        ratio=b['ratio'],audio_mode=b.get('audio_mode','off'),input_mode=b['video_mode'],
                        template_id=b['template_id'],template_version=b['template_version'],
                        actual_cny=j['actual'],billing=r.get('billing'),auto_billing=json.loads(j.get('result') or '{}').get('auto_billing'),reported_usage=db.reported_usage(j.get('result')),created=j['created'])
    return {k:v for k,v in a.items() if k!="path"} | {"url":"/api/assets/"+a["id"]+"/file","download_url":"/api/assets/"+a["id"]+"/download",'provenance':provenance}

@app.get("/api/assets",dependencies=[Depends(require_auth)])
def get_assets():
    with db.connection() as conn:
        sources={r['id']:dict(r) for r in conn.execute('SELECT id,body,review,actual,created,result FROM jobs')}
    return [public_asset(a,sources) for a in db.list_assets()]

@app.post("/api/assets",dependencies=[Depends(require_write)])
async def upload(file:UploadFile=File(...),origin:Literal['self','user']=Form('self')):
    data=bytearray()
    while chunk:=await file.read(1024*1024):
        data.extend(chunk)
        if len(data)>assets.MAX_FILE:raise HTTPException(413,"文件超过200MB")
    await file.close()
    a=await asyncio.to_thread(assets.save_bytes,bytes(data),file.filename or "upload",upload_origin=origin)
    return public_asset(a)

def file_response(a,download=False):
    return FileResponse(config.DATA/"assets"/a["path"],media_type=a["mime"],filename=a["name"] if download else None)

@app.get("/api/assets/{aid}/file",dependencies=[Depends(require_auth)])
def asset_file(aid:str):return file_response(db.get_asset(aid))

@app.get("/api/assets/{aid}/download",dependencies=[Depends(require_auth)])
def asset_download(aid:str):return file_response(db.get_asset(aid),True)

@app.get("/media/{aid}")
def media(aid:str,expires:int,sig:str):
    if not validate_asset_signature(aid,expires,sig):raise HTTPException(403,"素材链接已过期或签名无效")
    return file_response(db.get_asset(aid))

@app.delete("/api/assets/{aid}",dependencies=[Depends(require_write)])
def delete_asset(aid:str):
    a=db.get_asset(aid)
    with db.connection() as conn:
        for r in conn.execute("SELECT body,outputs FROM jobs"):
            b=json.loads(r["body"])
            if aid in json.loads(r["outputs"]) or any(x.get("asset_id")==aid for x in b["refs"]):raise ValueError("素材已被测试记录引用；请先删除相关任务记录")
        conn.execute("DELETE FROM assets WHERE id=?",(aid,))
    (config.DATA/"assets"/a["path"]).unlink(missing_ok=True)
    return {"ok":True}

class Ref(Strict):
    asset_id:str|None=Field(default=None,pattern=r"^[a-f0-9]{32}$")
    role:str
    usage:str="auto"
    vendor_asset_id:str|None=Field(default=None,pattern=r"^[A-Za-z0-9_.:/-]{1,200}$")
    vendor_kind:Literal["image","video","audio","element","voice","file","link"]="image"
    url:str|None=Field(default=None,max_length=3000)
    vendor_active:bool=False
    trusted_original:bool=False
    duration:float|None=Field(default=None,ge=0,le=120,allow_inf_nan=False)
    subject_name:str=Field(default="",max_length=50,pattern=r"^[\w -]*$")
    voice_url:str=Field(default="",max_length=3000)
    voice_id:str=Field(default="",max_length=100,pattern=r"^[A-Za-z0-9_.:-]*$")

class JobInput(Strict):
    kind:Literal["image","video"]="image"
    model_id:str
    template_id:str
    template_version:int=Field(ge=1)
    refs:list[Ref]=Field(default_factory=list,max_length=50)
    mode:Literal["mock","live"]="mock"
    resolution:str
    duration:int=Field(default=3,ge=1,le=30)
    ratio:str="9:16"
    seed:int=Field(default=42,ge=0,le=2147483647)
    prompt_override:str=Field(default="",max_length=20000)
    person_mode:Literal["default","self"]="default"
    identity_consent:bool=False
    image_confirmed:bool=False
    paid_confirmed:bool=False
    reference_board:bool=False
    video_mode:str="auto"
    audio_mode:Literal["off","native","original"]="off"
    max_cost:float=Field(default=3,ge=0,le=1000,allow_inf_nan=False)
    label:str=Field(default="",max_length=100)
    group:str=Field(default="",max_length=100)
    mock_failure:Literal["none","generation","submit_unknown","save_once"]="none"

@app.post("/api/preview",dependencies=[Depends(require_write)])
def preview(data:JobInput):
    from .providers import build_request
    b=engine.validate(data.model_dump())
    b["job_id"]="preview"
    req=build_request(b["model_snapshot"],b,True)
    if b["reference_board"]:
        # Preview must match effective API shape: one board, not many inputs.
        req_b=b.copy();req_b["refs"]=[{"asset_id":"reference-board","role":"pose"}]
        req=build_request(b["model_snapshot"],req_b,True)
    return {"request":req,"prompt":b["compiled_prompt"],"estimate":engine.estimate(b),"stages":b["template_snapshot"]["workflow"],"warnings":["真人授权、账号权限、质量与实际账单仍需实测。","模拟视频为静态帧，用于验证播放下载和调度。" if b["mode"]=="mock" else "真实调用会产生费用；不自动重提生成请求。"]}

@app.post("/api/jobs",dependencies=[Depends(require_write)],status_code=202)
def new_job(data:JobInput,request:Request):
    idem=request.headers.get("Idempotency-Key", "")
    if not 8<=len(idem)<=128:raise ValueError("请提供8～128字符的幂等编号")
    return engine.create_job(data.model_dump(),idem)

@app.get("/api/jobs",dependencies=[Depends(require_auth)])
def jobs():
    with db.connection() as conn:return [db.decode_job(r) for r in conn.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 500")]

@app.get("/api/jobs/{jid}",dependencies=[Depends(require_auth)])
def job_detail(jid:str):
    j=db.get_job(jid)
    if not j:raise HTTPException(404,"任务不存在")
    d=db.decode_job(j)
    with db.connection() as conn:d["events"]=[dict(r) for r in conn.execute("SELECT stage,message,created FROM events WHERE job_id=? ORDER BY id",(jid,))]
    result=json.loads(j["result"] or "{}")
    d["usage"]=result.get("usage",{})
    from .billing import context
    d['billing_context']=d['body'].get('billing_snapshot') or context(d['body'])
    return d

class Receipt(Strict):
    actual_cny:float|None=Field(default=None,ge=0,le=10000,allow_inf_nan=False)
    billing_mode:Literal['amount','units','both']='amount'
    billing_unit:Literal['tokens','credits']|None=None
    billed_units:float|None=Field(default=None,ge=0,le=1e12,allow_inf_nan=False)
    rate_override:float|None=Field(default=None,gt=0,le=1e6,allow_inf_nan=False)
    rate_note:str=Field(default='',max_length=300)
    bill_reference:str=Field(default='',max_length=200)

@app.post('/api/jobs/{jid}/billing-preview',dependencies=[Depends(require_write)])
def billing_preview(jid:str,data:Receipt):
    j=db.get_job(jid)
    if not j:raise HTTPException(404,'任务不存在')
    from .billing import reconcile
    return reconcile(json.loads(j['body']),data.model_dump())

class Review(Receipt):
    verdict:Literal["pass","fail","pending"]
    clothing:int=Field(ge=1,le=5)
    identity:int=Field(ge=1,le=5)
    motion:int|None=Field(default=None,ge=1,le=5)
    issues:list[str]=Field(default_factory=list,max_length=12)
    notes:str=Field(default="",max_length=1000)
    background:int|None=Field(default=None,ge=1,le=5)
    framing:int|None=Field(default=None,ge=1,le=5)
    detail:int|None=Field(default=None,ge=1,le=5)

@app.post("/api/jobs/{jid}/review",dependencies=[Depends(require_write)])
def review(jid:str,data:Review):
    j=db.get_job(jid)
    if not j:raise HTTPException(404,"任务不存在")
    if data.verdict=="pass" and j["state"]!="succeeded":raise ValueError("只有保存成功的结果才能评为合格")
    body=json.loads(j["body"])
    from .billing import reconcile
    bill=reconcile(body,data.model_dump())
    d=data.model_dump();d["reviewed_at"]=db.now();d['billing']=bill
    db.update_job(jid,review=json.dumps(d,ensure_ascii=False),actual=bill['actual_cny'] if bill['actual_cny'] is not None else (json.loads(j.get('result') or '{}').get('auto_billing') or {}).get('actual_cny'))
    return {"ok":True}

class Resume(Strict):
    provider_task_id:str=Field(default="",max_length=200,pattern=r"^[a-zA-Z0-9_.:-]*$")

@app.post("/api/jobs/{jid}/resume",dependencies=[Depends(require_write)])
def resume(jid:str,data:Resume):
    j=db.get_job(jid)
    if not j:raise HTTPException(404,"任务不存在")
    if j["state"]=="save_failed":
        db.update_job(jid,state="saving",next_poll=0,error="")
    elif j["state"] in ("uncertain","paused"):
        tid=data.provider_task_id or j["provider_task_id"]
        if not tid:raise ValueError("需从供应商控制台取得任务编号；禁止盲目重提")
        from .providers import query_path
        query_path(json.loads(j["body"])["model_snapshot"],tid)
        db.update_job(jid,provider_task_id=tid,state="polling",next_poll=0,error="")
    else:raise ValueError("当前任务无需恢复；失败后重新生成属于新付费任务")
    db.event(jid,"resume","仅恢复查询或保存，不重新提交生成")
    return {"ok":True}

@app.delete("/api/jobs/{jid}",dependencies=[Depends(require_write)])
def delete_job(jid:str):
    j=db.get_job(jid)
    if not j:raise HTTPException(404,"任务不存在")
    if j["state"] in ("queued","submitting","polling","saving","uncertain","paused","save_failed"):raise ValueError("未结束或待核对任务不能删除")
    if json.loads(j["body"])["mode"]=="live":raise ValueError("真实费用记录保留用于预算与对账；可删除输出素材的功能后续单独实现")
    with db.connection() as conn:
        conn.execute("DELETE FROM events WHERE job_id=?",(jid,));conn.execute("DELETE FROM jobs WHERE id=?",(jid,))
    return {"ok":True}

class TemplateInput(Strict):
    id:str=Field(pattern=r"^[a-z][a-z0-9-]{2,60}$")
    name:str=Field(min_length=1,max_length=100)
    kind:Literal["image","video"]
    category:Literal["outfit_image","garment_present","outfit_video"]
    description:str=Field(default="",max_length=500)
    prompt:str=Field(min_length=1,max_length=3000)
    negative_prompt:str=Field(default="",max_length=500)
    criteria:list[str]=Field(default_factory=list,max_length=12)

@app.post("/api/templates",dependencies=[Depends(require_write)])
def save_template(data:TemplateInput):
    if (data.category=="outfit_video")!=(data.kind=="video"):raise ValueError("模板类型与技能不一致")
    body=data.model_dump();body["workflow"]=["input_validate",data.category,"asset_finalize","human_review"]
    with db.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        v=conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM templates WHERE id=?",(data.id,)).fetchone()[0]
        body["version"]=v
        conn.execute("INSERT INTO templates VALUES(?,?,?,?)",(data.id,v,json.dumps(body,ensure_ascii=False),db.now()))
    return body

@app.get("/api/export",dependencies=[Depends(require_auth)])
def export(format:Literal["json","csv"]="json"):
    data=jobs()
    if format=="json":return Response(json.dumps({"schema_version":"1.1","exported_at":db.now(),"jobs":data,"assets":get_assets()},ensure_ascii=False,indent=2),media_type="application/json",headers={"Content-Disposition":"attachment; filename=wardrobe-experiments.json"})
    out=io.StringIO();w=csv.writer(out)
    w.writerow(["任务","组别","模型","模式","状态","服装评分","人工结论","预占预算CNY","账单核对CNY","创建时间","渠道","上游模型","选定清晰度","选定时长秒","画幅","声音","输入模式","模板版本","实际计费用量","反推计费用量","计费单位","单价","单价基数","费用来源","账单差额CNY","背景评分","构图评分","细节评分","输出文件规格","供应商回传用量（未对账）"])
    def safe(x):
        s=str(x if x is not None else "")
        return "'"+s if s.startswith(("=","+","-","@","\t","\r")) else s
    for j in data:
        r=j["review"] or {};b=j["body"]
        manual=r.get('billing') or {}
        bill=manual if manual.get('actual_cny') is not None else (j.get('auto_billing') or manual)
        w.writerow([safe(x) for x in [j["id"],b["group"],b["model_id"],b["mode"],j["state"],r.get("clothing"),r.get("verdict"),j["reserved"],j["actual"],j["created"],b["model_snapshot"]["provider"],b["model_snapshot"]["model"],b["resolution"],b["duration"] if b["kind"]=="video" else None,b["ratio"],b.get("audio_mode"),b["video_mode"],b["template_version"],bill.get("actual_units"),bill.get("inferred_units"),bill.get("unit"),bill.get("rate"),bill.get("rate_basis"),bill.get("cost_source"),bill.get("difference_cny"),r.get("background"),r.get("framing"),r.get("detail"),json.dumps([{k:a.get(k) for k in ("id","width","height","duration","size")} for aid in j["outputs"] or [] for a in [db.get_asset(aid)]],ensure_ascii=False),json.dumps(j.get('reported_usage',{}),ensure_ascii=False)]])
    return Response("\ufeff"+out.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=wardrobe-experiments.csv"})

@app.post("/api/demo",dependencies=[Depends(require_write)])
def demo_assets():
    from PIL import Image,ImageDraw
    generated=[]
    for role,color in [("upper","#94a7c0"),("lower","#d6c6af"),("shoes","#323d4f")]:
        name="demo-"+role+".png"
        existing=next((a for a in db.list_assets() if a["name"]==name and a["source"]=="demo"),None)
        if existing:a=existing
        else:
            img=Image.new("RGB",(768,1024),"#f8f7f5");d=ImageDraw.Draw(img)
            if role=="upper":d.polygon([(190,260),(300,210),(340,250),(430,250),(465,210),(578,260),(650,460),(540,500),(500,390),(510,740),(260,740),(270,390),(230,500),(118,460)],fill=color)
            elif role=="lower":d.polygon([(245,240),(523,240),(560,770),(425,790),(380,460),(343,790),(208,770)],fill=color)
            else:
                d.rounded_rectangle((135,460,400,580),50,fill=color);d.rounded_rectangle((368,615,635,735),50,fill=color)
            d.text((200,890),"DEMO / illustration",fill="#87909e",font_size=28)
            buf=io.BytesIO();img.save(buf,format="PNG");a=assets.save_bytes(buf.getvalue(),name,"demo")
        generated.append({"role":role,"asset":public_asset(a)})
    return generated

app.mount("/static",StaticFiles(directory=config.ROOT/"web"),name="static")
@app.get("/")
def index():return FileResponse(config.ROOT/"web/index.html")
