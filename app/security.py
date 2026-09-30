import hashlib
import hmac
import ipaddress
import secrets
import socket
import time
from urllib.parse import urlsplit
from fastapi import HTTPException, Request
from . import config

DEV_SECRET = secrets.token_hex(32)

def sign(value):
    return hmac.new((config.SECRET or DEV_SECRET).encode(), value.encode(), hashlib.sha256).hexdigest()

def session():
    token = f"{int(time.time())+43200}.{secrets.token_hex(16)}"
    return token + "." + sign(token)

def valid_session(token):
    try:
        expiry, nonce, mac = token.split(".")
        return int(expiry) >= time.time() and hmac.compare_digest(mac,sign(expiry+"."+nonce))
    except (ValueError,AttributeError):
        return False

def require_auth(request: Request):
    if config.DEV and not config.PASSWORD and request.client.host in ("127.0.0.1","::1","testclient"):
        return "dev"
    token = request.cookies.get("lab_session", "")
    if not valid_session(token):
        raise HTTPException(401, "请先登录测试平台")
    return token

def require_write(request: Request):
    token = require_auth(request)
    if not hmac.compare_digest(request.headers.get("x-lab-csrf", ""), sign("csrf:"+token)):
        raise HTTPException(403,"请求验证失败，请刷新页面")
    check_origin(request)
    return token

def check_origin(request):
    origin = request.headers.get("origin")
    if origin:
        expected = config.PUBLIC_BASE or str(request.base_url).rstrip("/")
        if origin.rstrip("/") != expected:
            raise HTTPException(403,"拒绝跨站请求")

def signed_asset(asset_id):
    expiry = int(time.time())+config.ASSET_TTL
    return f"{config.PUBLIC_BASE}/media/{asset_id}?expires={expiry}&sig={sign(f'{asset_id}:{expiry}')}"

def validate_asset_signature(asset_id, expires, sig):
    return expires >= time.time() and hmac.compare_digest(sig,sign(f"{asset_id}:{expires}"))

def public_url(url):
    """Reject SSRF and unsafe redirects. Only used on official model output links."""
    u = urlsplit(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None,443):
        raise ValueError("结果地址必须为公网 HTTPS 链接")
    try:
        addresses = socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError("结果域名无法解析") from e
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("拒绝访问内网结果地址")
    return url

def redact(value):
    if isinstance(value,dict):
        return {k:("[redacted]" if any(t in k.lower() for t in ("authorization","api_key","secret","signature")) else redact(v)) for k,v in value.items()}
    if isinstance(value,list):
        return [redact(v) for v in value]
    if isinstance(value,str):
        if value.startswith("data:"):
            return "[inline asset omitted]"
        if value.startswith(("http://","https://")):
            u=urlsplit(value)
            return f"{u.scheme}://{u.netloc}{u.path}" # strip signed query
        for p in config.PROVIDERS:
            if config.key(p):
                value=value.replace(config.key(p),"[redacted]")
    return value
