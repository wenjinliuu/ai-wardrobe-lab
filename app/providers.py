"""Request builders are pure; transport has no automatic POST retry."""
import base64
import json
from . import contracts
from urllib.parse import quote
import httpx
from . import config, db
from .security import signed_asset

class AmbiguousSubmission(Exception):
    pass

class ProviderFailure(Exception):
    pass

def asset_uri(ref, inline=False):
    if ref.get("vendor_asset_id"):
        return "asset://"+ref["vendor_asset_id"] if ref.get("provider")=="ark" else ref["vendor_asset_id"]
    if ref.get("url"):return ref["url"]
    a=db.get_asset(ref["asset_id"])
    if inline and a["kind"]=="image" and not config.PUBLIC_BASE.startswith("https://"):
        return f"data:{a['mime']};base64,"+base64.b64encode((config.DATA/"assets"/a["path"]).read_bytes()).decode()
    if not config.PUBLIC_BASE:
        raise ValueError("该接口需要公网素材链接，请先配置 LAB_PUBLIC_BASE_URL")
    return signed_asset(a["id"])

def build_request(m,b,preview=False):
    def uri(r, inline=False):
        if r.get("vendor_asset_id"):return "asset://"+r["vendor_asset_id"] if m["provider"]=="ark" else r["vendor_asset_id"]
        if r.get("url"):return r["url"]
        return f"asset://{r['asset_id']}" if preview else asset_uri(r,inline)
    request=contracts.build(m,b,uri)
    if request:return request
    images=[r for r in b["refs"] if r["role"]!="motion"]
    motions=[r for r in b["refs"] if r["role"]=="motion"]
    prompt=b["compiled_prompt"]
    common={"model":m["model"]}
    adapter=m["adapter"]
    headers={"Content-Type":"application/json"}
    if adapter=="wan":
        path="/api/v1/services/aigc/video-generation/video-synthesis"
        headers["X-DashScope-Async"]="enable"
        common.update(input={"img_url":uri(images[0],True),"prompt":prompt},parameters={"resolution":b["resolution"],"duration":b["duration"],"audio":b.get("audio_mode","off")=="native","prompt_extend":False,"shot_type":"single","watermark":True,"seed":b["seed"]})
    elif adapter=="wan_animate":
        path="/api/v1/services/aigc/image2video/video-synthesis"
        headers["X-DashScope-Async"]="enable"
        common.update(input={"image_url":uri(images[0]),"video_url":uri(motions[0]),"watermark":True},parameters={"mode":b["resolution"],"check_image":True})
    else:
        raise ValueError("适配器不存在")
    return {"method":"POST","url":config.PROVIDERS[m["provider"]]["base"].rstrip("/")+path,"headers":headers,"body":common}

def normalize(m,data,submit=False):
    a=m["adapter"]
    newer=normalize_extra(m,data,submit)
    if newer is not None:return newer
    urls=[];task=None;status="pending"
    error=None
    if a=="seedream":
        if data.get("error"): error="图像生成被拒绝"
        urls=[x["url"] for x in data.get("data",[]) if x.get("url")]
        status="succeeded" if urls else "failed"
    elif a=="qwen":
        urls=[c["image"] for x in data.get("output",{}).get("choices",[]) for c in x.get("message",{}).get("content",[]) if c.get("image")]
        status="succeeded" if urls else "failed"
    elif a in ("wan","wan_animate","wan3","wan_media"):
        o=data.get("output",{});task=o.get("task_id");status=o.get("task_status","UNKNOWN").lower()
        results=o.get("results",{})
        if o.get("video_url"): urls=[o["video_url"]]
        elif isinstance(results,dict) and results.get("video_url"):urls=[results["video_url"]]
        if data.get("code") or o.get("code"):error="万相返回错误，请按 request_id 核对控制台"
    elif a in ("kling","kling_motion","kling_omni","native_kling_standard"):
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
    usage=data.get("tokenhub_usage") or data.get("usage") or data.get("task",{}).get("usage") or {}
    if a=="vidu":usage={"credits":data.get("credits")}
    return dict(status=status,task_id=task,urls=urls,usage=usage,request_id=data.get("request_id",""),error=error)

def query_path(m,task_id):
    tid=quote(task_id,safe="")
    a=m["adapter"]
    if a in ("wan","wan_animate","wan3","wan_media"):return "/api/v1/tasks/"+tid
    if a in ("kling","kling_motion","kling_omni"):return "/v1/wand/kling/tasks/"+tid
    if a=="h3":return "/v2/query/video_generation/"+tid if m["provider"]=="minimax" else "/v1/wand/minimax-video-v2/tasks/"+tid
    if a=="vidu":return "/ent/v2/tasks/"+tid+"/creations"
    if a=="seedance":return "/contents/generations/tasks/"+tid
    paths={'tx_vidu':'/v1/wand/vidu/tasks/','tx_wand_video':'/v1/wand/vega-videos/tasks/','tx_pixverse':'/v1/wand/pixverse/tasks/','tx_hy_video':'/v1/wand/hunyuan-video/tasks/','tx_wand_image':'/v1/wand/vega-images/tasks/','tx_vidu_image':'/v1/wand/vidu-image/tasks/','tx_kling_image':'/v1/wand/kling-image/tasks/'}
    if a in paths:return paths[a]+tid
    if a=='native_kling_standard':return '/tasks?task_ids='+tid
    if a=='native_kling_legacy':return '/v1/videos/'+('text2video' if m.get('query_mode')=='text' else 'image2video')+'/'+tid
    if a=='native_kling_omni':return '/v1/videos/omni-video/'+tid
    if a=='native_kling_motion':return '/v1/videos/motion-control/'+tid
    if a=='native_kling_image':return '/v1/images/'+('generations' if m.get('native_single') else 'omni-image')+'/'+tid
    if a=='mini_old':return '/v1/query/video_generation?task_id='+tid if m['provider']=='minimax' else '/v1/wand/minimax-video/tasks/'+tid
    if a=='tx_yt':return '/v1/api/video/query'
    raise ValueError("该模型为同步生成，不提供任务查询")

def transport(m,body=None,task_id=None,client=None):
    request=build_request(m,body) if body else {"method":"GET","url":config.PROVIDERS[m["provider"]]["base"].rstrip("/")+query_path(m,task_id),"headers":{}}
    if task_id and m['adapter']=='tx_yt':request.update(method='POST',body={'model':m['model'],'id':task_id})
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
            if m['adapter']=='tx_hy35' and 'text/event-stream' in response.headers.get('content-type',''):
                frames=[json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith('data:') and line[5:].strip() not in ('','[DONE]')]
                data=next((f for f in reversed(frames) if any(c.get('delta',{}).get('image',{}).get('url') for c in f.get('choices',[]))),frames[-1] if frames else {})
            else:data=response.json()
        except ValueError as e:
            if body:raise AmbiguousSubmission("提交响应无法解析，需核对是否已创建任务") from e
            raise ProviderFailure("查询响应无法解析") from e
        result=normalize(m,data,submit=bool(body))
        if not body and m['adapter']=='mini_old' and m['provider']=='minimax' and data.get('file_id') and result['status']=='succeeded':
            response=client.get(config.PROVIDERS['minimax']['base']+'/v1/files/retrieve',params={'file_id':data['file_id']},headers=request['headers'])
            response.raise_for_status();file=response.json().get('file',{})
            result['urls']=[file['download_url']] if file.get('download_url') else []
        if body and not result["task_id"] and not result["urls"] and result["status"] not in {"failed"}:
            raise AmbiguousSubmission("响应未包含任务编号或结果，需人工核对")
        return result
    except httpx.TransportError as e:
        if body:raise AmbiguousSubmission("提交网络中断，结果不确定；不会自动重新生成") from e
        raise ProviderFailure("查询网络暂时不可用") from e
    finally:
        if own:client.close()


def normalize_extra(m,data,submit=False):
    a=m['adapter'];d=data.get('data',{});task=None;urls=[];status='pending';error=None
    if a in ('qwen','wan_image'):
        urls=[c['image'] for x in data.get('output',{}).get('choices',[]) for c in x.get('message',{}).get('content',[]) if c.get('image')]
        status='succeeded' if urls else 'failed'
    elif a in ('tx_seedream','tx_hy_image'):
        urls=[x['url'] for x in data.get('data',[]) if x.get('url')];status='succeeded' if urls else 'failed'
    elif a=='tx_hy35':
        urls=[c['delta']['image']['url'] for c in data.get('choices',[]) if c.get('delta',{}).get('image',{}).get('url')];status='succeeded' if urls else 'failed'
    elif a=='mini_image':
        urls=d.get('image_urls',[]) if isinstance(d,dict) else [];status='succeeded' if urls else 'failed'
    elif a=='mini_old':
        task=data.get('task_id');status=data.get('status','pending').lower()
        if m['provider']=='tokenhub':
            obj=data.get('task',data);task=task or obj.get('id');status=obj.get('status',status).lower()
            if obj.get('content',{}).get('url'):urls=[obj['content']['url']]
    elif a.startswith('native_kling') and a!='native_kling_standard':
        d=d[0] if isinstance(d,list) and d else d
        task=d.get('task_id');status=d.get('task_status','pending').lower()
        urls=[x['url'] for key in ('videos','images') for x in d.get('task_result',{}).get(key,[]) if x.get('url')]
    elif a in ('tx_vidu','tx_vidu_image'):
        task=data.get('task_id') or data.get('id');status=data.get('state','pending').lower()
        urls=[x['url'] for x in data.get('creations',[]) if x.get('url')]
    elif a in ('tx_wand_image','tx_wand_video'):
        task=data.get('task_id') or data.get('id');status=data.get('status','pending').lower()
        urls=[x['url'] for x in data.get('data',[]) if x.get('url')]
        if data.get('content',{}).get('video_url') or data.get('content',{}).get('url'):urls=[data['content'].get('video_url') or data['content']['url']]
    elif a=='tx_kling_image':
        d=d[0] if isinstance(d,list) and d else d
        task=d.get('task_id') or d.get('id');status=d.get('task_status',d.get('status','pending')).lower()
        urls=[x['url'] for x in d.get('task_result',{}).get('images',[]) if x.get('url')]
        urls += [x['url'] for x in d.get('outputs',[]) if x.get('url')]
    elif a=='tx_pixverse':
        d=data.get('Resp',{});task=d.get('video_id');v=d.get('status');status={1:'succeeded',5:'pending',6:'failed',7:'failed',8:'failed'}.get(v,'pending')
        if d.get('url'):urls=[d['url']]
    elif a=='tx_hy_video':
        task=data.get('task_id');status=data.get('status','pending').lower();urls=[x['url'] for x in data.get('videos',[]) if x.get('url')]
    elif a=='tx_yt':
        task=data.get('id') or (d.get('id') if isinstance(d,dict) else None);status=data.get('status',d.get('status','pending') if isinstance(d,dict) else 'pending').lower()
        if isinstance(d,dict) and d.get('url'):urls=[d['url']]
    else:return None
    if status in ('success','succeed','succeeded','completed','done'):status='succeeded'
    elif status in ('fail','failed','canceled','cancelled'):status='failed'
    elif status=='unknown':status='unknown'
    else:status='pending'
    if data.get('error') or data.get('code',0) not in (0,None) or data.get('base_resp',{}).get('status_code',0)!=0 or data.get('ErrCode',0)!=0:status='failed';error='供应商返回错误，请核对请求编号与控制台'
    return dict(task_id=task,status=status,urls=urls,usage=data.get('tokenhub_usage') or data.get('usage') or {},request_id=data.get('request_id',''),error=error)
