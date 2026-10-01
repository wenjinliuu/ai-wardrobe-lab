import json
from math import isfinite
import sqlite3
import time
from contextlib import contextmanager
from . import config

def now():
    return time.time()

@contextmanager
def connection():
    db = sqlite3.connect(config.DATA / "lab.sqlite3", timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init():
    config.DATA.mkdir(parents=True, exist_ok=True)
    (config.DATA / "assets").mkdir(exist_ok=True)
    with connection() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,mime TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,width INTEGER,height INTEGER,duration REAL,size INTEGER,source TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS templates(id TEXT,version INTEGER,body TEXT NOT NULL,created REAL,PRIMARY KEY(id,version));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,idem TEXT UNIQUE,request_hash TEXT,body TEXT NOT NULL,state TEXT,provider_task_id TEXT,result TEXT,outputs TEXT DEFAULT '[]',error TEXT DEFAULT '',attempt INTEGER DEFAULT 0,next_poll REAL DEFAULT 0,created REAL,updated REAL,reserved REAL DEFAULT 0,actual REAL,review TEXT,request_id TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT,stage TEXT,message TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT,created REAL);
        """)
        if 'details' not in {r['name'] for r in db.execute('PRAGMA table_info(assets)')}:
            db.execute("ALTER TABLE assets ADD COLUMN details TEXT DEFAULT '{}'")


def event(job_id, stage, message):
    with connection() as db:
        db.execute("INSERT INTO events(job_id,stage,message,created) VALUES(?,?,?,?)", (job_id,stage,message,now()))

def get_job(job_id):
    with connection() as db:
        r = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(r) if r else None

def update_job(job_id, **values):
    allowed = {"state","provider_task_id","result","outputs","error","attempt","next_poll","actual","review","request_id"}
    if not values.keys() <= allowed:
        raise ValueError("Invalid job fields")
    with connection() as db:
        db.execute("UPDATE jobs SET " + ",".join(f"{k}=?" for k in values) + ",updated=? WHERE id=?", [*values.values(),now(),job_id])

def list_assets():
    with connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM assets ORDER BY created DESC")]

def get_asset(asset_id):
    with connection() as db:
        r = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if not r:
        raise ValueError("素材不存在或已删除")
    return dict(r)

def reported_usage(result):
    usage = json.loads(result or '{}').get('usage') or {}
    return {k:v for k,v in usage.items() if k in ('total_tokens','input_tokens','output_tokens','prompt_tokens','completion_tokens','credits','generated_images') and isinstance(v,(int,float)) and not isinstance(v,bool) and isfinite(v) and v>=0} if isinstance(usage,dict) else {}

def decode_job(r):
    d = dict(r)
    d['reported_usage'] = reported_usage(d.get('result'))
    d['auto_billing'] = json.loads(d.get('result') or '{}').get('auto_billing')
    for k in ("body","outputs","review"):
        d[k] = json.loads(d[k]) if d[k] else None
    d.pop("result", None) # provider links are private; export contains asset IDs only
    d.pop("idem", None)
    d.pop("request_hash", None)
    return d
