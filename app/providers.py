"""Request builders are pure; transport has no automatic POST retry."""
import base64
from urllib.parse import quote
import httpx
from . import config, db
from .security import signed_asset

class AmbiguousSubmission(Exception):
    pass

class ProviderFailure(Exception):
    pass

def asset_uri(ref, inline=False):
    a=db.get_asset(ref["asset_id"])
    if inline and a["kind"]=="image" and not config.PUBLIC_BASE.startswith("https://"):
        return f"data:{a['mime']};base64,"+base64.b64encode((config.DATA/"assets"/a["path"]).read_bytes()).decode()
    if not config.PUBLIC_BASE:
        raise ValueError("该接口需要公网素材链接，请先配置 LAB_PUBLIC_BASE_URL")
    return signed_asset(a["id"])

def build_request(m,b,preview=False):
    def uri(r, inline=False):
        return f"asset://{r['asset_id']}" if preview else asset_uri(r,inline)
    images=[r for r in b["refs"] if r["role"]!="motion"]
    motions=[r for r in b["refs"] if r["role"]=="motion"]
    prompt=b["compiled_prompt"]
    common={"model":m["model"]}
    adapter=m["adapter"]
    headers={"Content-Type":"application/json"}
    if adapter=="seedream":
        path="/images/generations"
        common.update(prompt=prompt,image=[uri(r,True) for r in images],size=b["resolution"],response_format="url",watermark=True,sequential_image_generation="disabled")
    elif adapter=="qwen":
        path="/api/v1/services/aigc/multimodal-generation/generation"
        common.update(input={"messages":[{"role":"user","content":[*[{"image":uri(r,True)} for r in images],{"text":prompt}]}]},parameters={"n":1,"size":b["resolution"],"watermark":True,"prompt_extend":False})
    elif adapter=="wan":
        path="/api/v1/services/aigc/video-generation/video-synthesis"
        headers["X-DashScope-Async"]="enable"
        common.update(input={"img_url":uri(images[0],True),"prompt":prompt},parameters={"resolution":b["resolution"],"duration":b["duration"],"audio":False,"prompt_extend":True,"shot_type":"single","watermark":True,"seed":b["seed"]})
    elif adapter=="wan_animate":
        path="/api/v1/services/aigc/image2video/video-synthesis"
        headers["X-DashScope-Async"]="enable"
        common.update(input={"image_url":uri(images[0]),"video_url":uri(motions[0]),"watermark":True},parameters={"mode":b["resolution"],"check_image":True})
    elif adapter in ("kling","kling_motion"):
        path="/v1/wand/kling/"+("motion-control" if adapter=="kling_motion" else "image-to-video")
        contents=[{"type":"prompt","text":prompt},{"type":"image" if adapter=="kling_motion" else "first_frame","url":uri(images[0],True)}]
        settings={"resolution":b["resolution"],"audio":"off"}
        if adapter=="kling_motion":
            contents.append({"type":"video","url":uri(motions[0])});settings["character_orientation"]="video"
        else:
            settings.update(duration=b["duration"],multi_shot=False)
        common.update(contents=contents,settings=settings,options={"external_task_id":b["job_id"],"watermark_info":{"enabled":True}})
    elif adapter=="h3":
        path="/v1/wand/minimax-video-v2/generation"
        reference=b["video_mode"]=="reference"
        content=[{"type":"text","text":prompt}]
        content += [{"type":"image_url","image_url":{"url":uri(r,True)},"role":"reference_image" if reference else "first_frame"} for r in images]
        content += [{"type":"video_url","video_url":{"url":uri(r)},"role":"reference_video"} for r in motions]
        common.update(content=content,resolution=b["resolution"],duration=b["duration"],ratio="adaptive",aigc_watermark=True)
    elif adapter=="vidu":
        path="/ent/v2/reference2video"
        common.update(images=[uri(r,True) for r in images],prompt=prompt,duration=b["duration"],resolution=b["resolution"],seed=b["seed"],aspect_ratio=b["ratio"],movement_amplitude="small")
    elif adapter=="seedance":
        path="/contents/generations/tasks"
        common.update(content=[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":uri(images[0],True)},"role":"first_frame"}],resolution=b["resolution"],duration=b["duration"],ratio="adaptive",generate_audio=False,watermark=True,seed=b["seed"])
    else:
        raise ValueError("适配器不存在")
    return {"method":"POST","url":config.PROVIDERS[m["provider"]]["base"].rstrip("/")+path,"headers":headers,"body":common}

def normalize(m,data,submit=False):
    a=m["adapter"]
    urls=[];task=None;status="pending"
    error=None
    if a=="seedream":
        if data.get("error"): error="图像生成被拒绝"
        urls=[x["url"] for x in data.get("data",[]) if x.get("url")]
        status="succeeded" if urls else "failed"
    elif a=="qwen":
        urls=[c["image"] for x in data.get("output",{}).get("choices",[]) for c in x.get("message",{}).get("content",[]) if c.get("image")]
        status="succeeded" if urls else "failed"
    elif a in ("wan","wan_animate"):
        o=data.get("output",{});task=o.get("task_id");status=o.get("task_status","UNKNOWN").lower()
        results=o.get("results",{})
        if o.get("video_url"): urls=[o["video_url"]]
        elif isinstance(results,dict) and results.get("video_url"):urls=[results["video_url"]]
        if data.get("code") or o.get("code"):error="万相返回错误，请按 request_id 核对控制台"
    elif a in ("kling","kling_motion"):
        if data.get("code",0)!=0:error="TokenHub 可灵请求被拒绝"
        d=data.get("data",{})
        if isinstance(d,list):d=d[0] if d else {}
        task=d.get("id");status=d.get("status","unknown").lower()
        urls=[x["url"] for x in d.get("outputs",[]) if x.get("type")=="video" and x.get("url")]
    elif a=="h3":
        task=data.get("task_id")
        d=data.get("task",{})
        status=d.get("status","queued" if task else "unknown").lower()
        if d.get("content",{}).get("url"):urls=[d["content"]["url"]]
        task=task or d.get("id")
    elif a=="vidu":
        task=data.get("task_id") or data.get("id");status=data.get("state","unknown").lower()
        urls=[x["url"] for x in data.get("creations",[]) if x.get("url")]
    elif a=="seedance":
        task=data.get("id");status=data.get("status","queued" if submit and task else "unknown").lower()
        if data.get("content",{}).get("video_url"):urls=[data["content"]["video_url"]]
    if status in {"success","succeed","succeeded"}:status="succeeded"
    elif status in {"failed","fail","canceled","cancelled"}:status="failed"
    elif status in {"unknown"}:status="unknown"
    else:status="pending"
    if error:status="failed"
    usage=data.get("usage") or data.get("task",{}).get("usage") or data.get("tokenhub_usage") or {}
    if a=="vidu":usage={"credits":data.get("credits")}
    return dict(status=status,task_id=task,urls=urls,usage=usage,request_id=data.get("request_id",""),error=error)

def query_path(m,task_id):
    tid=quote(task_id,safe="")
    a=m["adapter"]
    if a in ("wan","wan_animate"):return "/api/v1/tasks/"+tid
    if a in ("kling","kling_motion"):return "/v1/wand/kling/tasks/"+tid
    if a=="h3":return "/v1/wand/minimax-video-v2/tasks/"+tid
    if a=="vidu":return "/ent/v2/tasks/"+tid+"/creations"
    if a=="seedance":return "/contents/generations/tasks/"+tid
    raise ValueError("该模型为同步生成，不提供任务查询")

def transport(m,body=None,task_id=None,client=None):
    request=build_request(m,body) if body else {"method":"GET","url":config.PROVIDERS[m["provider"]]["base"].rstrip("/")+query_path(m,task_id),"headers":{}}
    request["headers"]["Authorization"]=("Token " if m["provider"]=="vidu" else "Bearer ")+config.key(m["provider"])
    own=client is None
    client=client or httpx.Client(timeout=httpx.Timeout(300,connect=15),follow_redirects=False,trust_env=False)
    try:
        response=client.request(request["method"],request["url"],headers=request["headers"],json=request.get("body"))
        if response.status_code>=500 and body:
            raise AmbiguousSubmission("供应商提交响应异常；可能已受理，请先核对控制台，禁止自动重提")
        if response.status_code>=400:
            raise ProviderFailure(f"供应商 HTTP {response.status_code}；请核对权限、余额和参数")
        try:
            data=response.json()
        except ValueError as e:
            if body:raise AmbiguousSubmission("提交响应无法解析，需核对是否已创建任务") from e
            raise ProviderFailure("查询响应无法解析") from e
        result=normalize(m,data,submit=bool(body))
        if body and not result["task_id"] and not result["urls"] and result["status"] not in {"failed"}:
            raise AmbiguousSubmission("响应未包含任务编号或结果，需人工核对")
        return result
    except httpx.TransportError as e:
        if body:raise AmbiguousSubmission("提交网络中断，结果不确定；不会自动重新生成") from e
        raise ProviderFailure("查询网络暂时不可用") from e
    finally:
        if own:client.close()
