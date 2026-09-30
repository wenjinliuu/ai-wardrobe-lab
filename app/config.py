"""Server-only credentials and domestic endpoints. Never serialize secrets."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("LAB_DATA_DIR", str(ROOT / "data")))
PUBLIC_BASE = os.getenv("LAB_PUBLIC_BASE_URL", "").rstrip("/")
PASSWORD = os.getenv("LAB_PASSWORD", "")
SECRET = os.getenv("LAB_SESSION_SECRET", "")
DEV = os.getenv("LAB_DEV_MODE", "false").lower() == "true"
LIVE = os.getenv("LAB_LIVE_ENABLED", "false").lower() == "true"
DAILY_BUDGET = float(os.getenv("LAB_DAILY_BUDGET_CNY", "30"))
DAILY_CALLS = int(os.getenv("LAB_DAILY_CALL_LIMIT", "20"))
POLL_INTERVAL = float(os.getenv("LAB_POLL_SECONDS", "15"))
ASSET_TTL = int(os.getenv("LAB_ASSET_TTL_SECONDS", "21600"))
PROVIDERS = {
    "ark": {"name": "火山方舟", "base": os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"), "key_env": "ARK_API_KEY"},
    "dashscope": {"name": "阿里百炼", "base": os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com"), "key_env": "DASHSCOPE_API_KEY"},
    "tokenhub": {"name": "腾讯 TokenHub", "base": "https://tokenhub.tencentmaas.com", "key_env": "TOKENHUB_API_KEY"},
    "minimax": {"name":"MiniMax 原厂国内", "base":"https://api.minimax.cn", "key_env":"MINIMAX_API_KEY"},
    "kling": {"name":"可灵原厂国内", "base":"https://api-beijing.klingai.com", "key_env":"KLING_API_KEY"},
    "vidu": {"name": "Vidu 国内", "base": "https://api.vidu.cn", "key_env": "VIDU_API_KEY"},
}

def key(provider):
    return os.getenv(PROVIDERS[provider]["key_env"], "")

def validate_config():
    if not DEV and (len(PASSWORD) < 12 or len(SECRET) < 32):
        raise RuntimeError("请设置至少12位 LAB_PASSWORD 和至少32位 LAB_SESSION_SECRET；本地开发可使用 LAB_DEV_MODE=true")
    for name, provider in PROVIDERS.items():
        from urllib.parse import urlsplit
        u = urlsplit(provider["base"])
        valid = {"ark": u.hostname == "ark.cn-beijing.volces.com",
                 "dashscope": u.hostname == "dashscope.aliyuncs.com" or (u.hostname or "").endswith(".cn-beijing.maas.aliyuncs.com"),
                 "minimax": u.hostname == "api.minimax.cn", "kling": u.hostname == "api-beijing.klingai.com",
                 "tokenhub": u.hostname == "tokenhub.tencentmaas.com", "vidu": u.hostname == "api.vidu.cn"}[name]
        if u.scheme != "https" or not valid or u.username or u.password or u.query or u.fragment or u.port not in (None,443):
            raise RuntimeError("只允许已核对的国内官方 API 域名")
