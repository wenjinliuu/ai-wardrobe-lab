import hashlib
import io
import json
import subprocess
import uuid
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
import httpx
from . import config, db
from .security import public_url

MAX_FILE = 200*1024*1024
Image.MAX_IMAGE_PIXELS = 40_000_000

def probe_video(path):
    try:
        result=subprocess.run(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(path)],capture_output=True,timeout=20,check=True)
        p=json.loads(result.stdout)
        s=next(s for s in p["streams"] if s.get("codec_type")=="video")
        return int(s["width"]),int(s["height"]),float(p["format"]["duration"])
    except (OSError,ValueError,KeyError,StopIteration,subprocess.SubprocessError) as e:
        raise ValueError("视频无法验证，请上传有效 MP4 / MOV；服务器需安装 ffprobe") from e

def save_bytes(content, name, source="upload", expected=None):
    if not content or len(content)>MAX_FILE:
        raise ValueError("文件为空或超过200MB")
    aid=uuid.uuid4().hex
    duration=None
    if content[4:8]==b"ftyp":
        kind,mime,ext="video","video/mp4",".mp4"
        path=config.DATA/"assets"/(aid+ext)
        path.write_bytes(content)
        try:
            width,height,duration=probe_video(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    else:
        try:
            with Image.open(io.BytesIO(content)) as img:
                if img.format not in {"PNG","JPEG","WEBP"}:
                    raise ValueError("仅支持 JPG、PNG、WebP 或 MP4 / MOV")
                img.load()
                img=ImageOps.exif_transpose(img).convert("RGB")
                width,height=img.size
                if width<64 or height<64 or width*height>40_000_000:
                    raise ValueError("图片尺寸不合适")
                buffer=io.BytesIO()
                img.save(buffer,format="PNG") # strip metadata and alpha without changing source pixels
                content=buffer.getvalue()
                if len(content)>MAX_FILE:
                    raise ValueError("图片解码后超过大小限制")
        except (OSError,Image.DecompressionBombError) as e:
            raise ValueError("无法读取图片；仅支持 JPG、PNG、WebP") from e
        kind,mime,ext="image","image/png",".png"
        path=config.DATA/"assets"/(aid+ext)
        path.write_bytes(content)
    if expected and kind!=expected:
        path.unlink(missing_ok=True)
        raise ValueError("供应商结果类型与请求不符")
    normalized_name=(Path(name).stem+ext)[:120]
    meta=dict(id=aid,name=normalized_name,kind=kind,mime=mime,path=path.name,sha256=hashlib.sha256(content).hexdigest(),width=width,height=height,duration=duration,size=len(content),source=source,created=db.now())
    with db.connection() as conn:
        conn.execute("INSERT INTO assets("+",".join(meta)+") VALUES("+",".join("?" for _ in meta)+")",list(meta.values()))
    return meta

def download_result(url,kind,job_id,index):
    url=public_url(url)
    # Each redirect checked before connecting. Do not forward credentials to artifact hosts.
    with httpx.Client(timeout=120,follow_redirects=False,trust_env=False) as client:
        for _ in range(4):
            with client.stream("GET",url) as response:
                if response.is_redirect:
                    from urllib.parse import urljoin
                    url=public_url(urljoin(url,response.headers["location"]))
                    continue
                response.raise_for_status()
                chunks=[]
                size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>MAX_FILE:
                        raise ValueError("结果文件超过200MB")
                    chunks.append(chunk)
                return save_bytes(b"".join(chunks),f"{job_id}-{index}.{'mp4' if kind=='video' else 'png'}",job_id,kind)
    raise ValueError("结果跳转次数过多")

def reference_board(refs):
    # Deterministic contact sheet, only for image editing experiments.
    count=len(refs)
    cols=2 if count<=4 else 3
    rows=(count+cols-1)//cols
    board=Image.new("RGB",(cols*768,rows*896),"white")
    draw=ImageDraw.Draw(board)
    for i,ref in enumerate(refs):
        a=db.get_asset(ref["asset_id"])
        x=(i%cols)*768;y=(i//cols)*896
        with Image.open(config.DATA/"assets"/a["path"]) as img:
            image=ImageOps.contain(img,(720,800))
            board.paste(image,(x+(768-image.width)//2,y+55+(800-image.height)//2))
        draw.text((x+28,y+20),f"IMAGE {i+1}: {ref['role']}",fill="#32363c",font_size=24)
    buffer=io.BytesIO();board.save(buffer,format="PNG")
    return save_bytes(buffer.getvalue(),"reference-board.png","reference_board")

def mock_result(job):
    body=json.loads(job["body"])
    if body["kind"]=="image":
        image=Image.new("RGB",(768,1152),"#f4f5f7")
        draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((120,110,648,1042),30,fill="white",outline="#d9dee8",width=2)
        draw.text((175,145),"WORKFLOW TEST",fill="#718096",font_size=28)
        draw.text((175,190),"Mock output / no AI",fill="#2e3b50",font_size=26)
        for i,ref in enumerate(body["refs"][:4]):
            a=db.get_asset(ref["asset_id"])
            if a["kind"]=="image":
                with Image.open(config.DATA/"assets"/a["path"]) as source:
                    thumb=ImageOps.contain(source,(380,170))
                    image.paste(thumb,((768-thumb.width)//2,280+i*185))
        buffer=io.BytesIO();image.save(buffer,format="PNG")
        return save_bytes(buffer.getvalue(),"mock-look.png",job["id"],"image")
    aid=next(r["asset_id"] for r in body["refs"] if r["role"]=="look")
    a=db.get_asset(aid)
    target=config.DATA/"assets"/(uuid.uuid4().hex+".mp4")
    try:
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-loop","1","-i",str(config.DATA/"assets"/a["path"]),"-t",str(body["duration"]),"-vf","scale=480:640:force_original_aspect_ratio=decrease,pad=480:640:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p","-r","24","-c:v","libx264","-movflags","+faststart",str(target)],check=True,timeout=45,capture_output=True)
        return save_bytes(target.read_bytes(),"mock-static-video.mp4",job["id"],"video")
    finally:
        target.unlink(missing_ok=True)
