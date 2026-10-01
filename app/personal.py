"""Reusable personal reference settings; generation remains a normal metered job."""
import json
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from . import db

HAIRSTYLES = {
 "photo": ("跟随照片", "保留参考照片中的发型、长度、分缝和发色"),
 "long-straight": ("黑长直", "黑色顺直长发，柔顺自然，简洁发丝"),
 "side-wave": ("大偏分卷发", "大侧分长卷发，自然蓬松，柔和大波浪"),
 "feather": ("羽毛层中长发", "中长发，轻盈羽毛层次，自然外翻发尾"),
 "retro-short": ("复古短卷发", "短卷发，小卷纹理，蓬松复古层次"),
 "low-bun": ("低盘发", "后脑低位盘发，自然干净，露出颈部"),
 "wispy-bun": ("龙须刘海盘发", "盘发，两侧少量龙须碎发刘海，自然轻盈"),
 "twin-tail": ("双马尾", "左右对称双马尾，自然刘海，不增加发饰"),
 "wet-look": ("半湿发造型", "半湿发质感，自然后梳，清晰发丝"),
 "shoulder-wave": ("微卷齐肩发", "齐肩中短发，发尾轻微柔和卷曲"),
 "water-wave": ("水波纹长发", "长发，连续柔和水波纹，自然卷度"),
 "collarbone": ("韩系锁骨发", "锁骨长度中发，发尾内扣，轻薄刘海"),
 "low-tail": ("碎刘海低马尾", "低马尾，轻薄碎刘海，少量自然碎发"),
 "ear-short": ("耳下短发", "耳下长度短发，轮廓干练，自然顺滑"),
 "high-bun": ("云朵丸子头", "高位丸子头，轻柔蓬松，少量碎发"),
 "wood-wave": ("木马卷", "均匀自然的大卷长发，蓬松发量，柔和卷曲"),
 "hime": ("公主切长直发", "长直发，脸颊两侧整齐公主切层次，自然齐刘海"),
 "side-braid": ("侧编发披发", "一侧自然编发，另一侧披发，不增加装饰"),
 "highlight": ("挂耳染长发", "自然长发，耳侧局部挑染，其余发色自然"),
 "layer-long": ("高层次长卷发", "长卷发，清晰高层次，自然蓬松发根"),
 "loose-low": ("慵懒低扎发", "后脑低扎发，留少量碎发，自然松弛"),
 "curtain": ("八字刘海直发", "顺直长发，八字刘海，自然修饰额头"),
 "flip": ("齐肩外翘发", "齐肩短发，发尾轻微外翘，自然层次"),
 "claw": ("鲨鱼夹盘发", "后脑鲨鱼夹夹起长发，松弛自然，简洁夹子"),
 "high-tail": ("高马尾", "高位马尾，自然蓬松发根，清爽发丝"),
 "bob": ("法式波波头", "短波波头，轻微波浪，简洁自然刘海"),
 "half-up": ("半扎公主头", "上半部分头发束起，下半部分自然披发"),
 "side-soft": ("侧分微卷长发", "侧分长发，发尾自然微卷，柔和层次"),
 "short-clean": ("清爽短发", "清爽自然短发，两侧整洁，顶部保留自然层次"),
 "custom": ("自定义发型", "")
}

class Settings(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(default="我的个人形象",min_length=1,max_length=80)
    face_asset_id:str|None=Field(default=None,pattern=r"^[a-f0-9]{32}$")
    body_asset_id:str|None=Field(default=None,pattern=r"^[a-f0-9]{32}$")
    face_mode:Literal["photo","description"]="photo"
    appearance:str=Field(default="",max_length=500)
    hair_mode:Literal["photo","template"]="photo"
    hairstyle:str="long-straight"
    hair_details:str=Field(default="",max_length=300)
    body_mode:Literal["photo","values"]="values"
    height:int=Field(default=165,ge=120,le=220)
    weight:int=Field(default=55,ge=30,le=200)
    build:Literal["natural","slim","athletic","full"]="natural"
    consent:bool=False

def check(settings):
    p=Settings.model_validate(settings).model_dump()
    if p['hairstyle'] not in HAIRSTYLES:raise ValueError("未知发型模板")
    for k in ('face_asset_id','body_asset_id'):
        if p[k] and db.get_asset(p[k])['kind']!='image':raise ValueError("个人参考须为图片")
    if p['face_mode']=='photo' and not (p['face_asset_id'] or p['body_asset_id']):raise ValueError("跟随外貌需要脸部或全身参考照")
    if p['face_mode']=='description' and not p['appearance'].strip():raise ValueError("请填写外貌描述")
    if p['hair_mode']=='photo' and not (p['face_asset_id'] or p['body_asset_id']):raise ValueError("跟随发型需要参考照片")
    if p['hair_mode']=='template' and p['hairstyle']=='custom' and not p['hair_details'].strip():raise ValueError("请填写自定义发型")
    if p['body_mode']=='photo' and not p['body_asset_id']:raise ValueError("跟随体型需要完整全身照")
    if (p['face_asset_id'] or p['body_asset_id']) and not p['consent']:raise ValueError("请确认本人参考素材授权")
    return p

def prompt(p):
    parts=["任务是重新生成一张完整成人的全身标准形象照，不是抠出头像或把原照片缩小贴到白色画布。输出一个完整的人，从头顶、肩膀、胸部、腰部、臀部、膝盖、小腿一直到脚部与鞋子全部可见。单人正面自然站立、双手放松不遮挡身体。背景和地面统一纯白色#FFFFFF，均匀柔和光，无室内场景、杂物、舞台光和文字。固定水平镜头，人物居中，头顶到鞋底占画面高度82%–86%，目标84%；头顶和鞋底分别保留约8%白边。人物不能只占画面一小块，不能只出现头部、胸像、半身或悬浮人脸。固定水平全身机位，头发、手脚和鞋子完整入镜。穿素色合身基础T恤、素色长裤和简洁平底鞋，衣服不宽大、不遮挡身体轮廓，不添加包、首饰或其他配饰。"]
    parts.append("身份参考：使用脸部照片中的成人五官和脸型；若没有独立脸部照则从全身照参考身份。脸部或半身输入只用于五官参考，不继承它的裁切、脸部尺寸、身体姿势、服装或背景。无论输入是否包含身体，输出都必须是完整成人全身；保留身份，不只复制参考图中的人脸。" if p['face_mode']=='photo' else "外貌描述："+p['appearance'])
    parts.append("发型："+("以脸部参考照为优先，无脸部照则跟随全身照的发型。" if p['hair_mode']=='photo' else HAIRSTYLES[p['hairstyle']][1]+"。"+p['hair_details']))
    if p['body_mode']=='photo':parts.append("体型与身材比例只跟随全身参考照，忽略照片的服装、背景和构图。")
    else:parts.append(f"体型参考：身高{p['height']}厘米、体重{p['weight']}公斤；体态{ {'natural':'自然匀称','slim':'偏纤细','athletic':'运动结实','full':'偏丰满'}[p['build']] }，保持自然人体比例，不夸张拉长腿。按这些视觉体型描述生成完整躯干、四肢、双脚及自然人体比例；参考自拍中未拍到的身体部分也需要合理生成。数值用于视觉体型参考。")
    return "\n".join(parts)

def refs(p):
    selected=[]
    if p['face_asset_id'] and (p['face_mode']=='photo' or p['hair_mode']=='photo'):selected.append(dict(asset_id=p['face_asset_id'],role='identity'))
    if p['body_asset_id'] and (p['body_mode']=='photo' or not p['face_asset_id'] and (p['face_mode']=='photo' or p['hair_mode']=='photo')):
        if not selected or selected[0]['asset_id']!=p['body_asset_id']:selected.append(dict(asset_id=p['body_asset_id'],role='body'))
    return selected

def get(pid):
    with db.connection() as c:r=c.execute('SELECT body FROM personal_profiles WHERE id=?',(pid,)).fetchone()
    if not r:raise ValueError("个人形象不存在")
    return json.loads(r['body'])

def listing():
    with db.connection() as c:return [json.loads(r['body']) for r in c.execute('SELECT body FROM personal_profiles ORDER BY updated DESC')]

def save(p, pid=None):
    pid=pid or uuid.uuid4().hex
    p=dict(p,id=pid)
    with db.connection() as c:c.execute('INSERT INTO personal_profiles VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,updated=excluded.updated',(pid,json.dumps(p,ensure_ascii=False),db.now(),db.now()))
    return p
