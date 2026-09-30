"""Conservative model profiles; account availability and fidelity require live testing."""
import os

def profile(id, name, provider, adapter, kind, model, max_images, durations=(), resolutions=(), **extra):
    return dict(id=id,name=name,provider=provider,adapter=adapter,kind=kind,model=model,max_images=max_images,
                durations=list(durations),resolutions=list(resolutions),verified="contract_tested",live_tested=False,**extra)

import json
from .config import ROOT
MODELS = json.loads((ROOT/'config/models.json').read_text())
USAGES = {'auto':'自动（按当前模式）','first_frame':'首帧图片','last_frame':'尾帧图片','reference_image':'参考图片','reference_video':'参考视频','reference_audio':'参考音频','driving_video':'驱动动作视频','driving_audio':'驱动音频','base_video':'待编辑原视频','feature_video':'特征参考视频','first_video':'续写原视频','subject_image':'主体图片（分组）','subject_video':'主体视频（分组）','element':'可灵多图元素 ID','voice':'可灵音色 ID','file':'参考文档','link':'参考网页'}

def model(id):
    for m in MODELS:
        if m["id"] == id:
            return m
    raise ValueError("未知模型配置")

ROLES = {"pose":"姿势模板","identity":"本人参考","upper":"上衣","lower":"下装","shoes":"鞋子","accessory":"配饰","background":"背景","look":"完整穿搭图","motion":"动作参考","audio":"声音参考","document":"文档参考"}
SKILLS = [
 {"id":"input_validate","name":"素材与权限校验","ai":False,"description":"检查角色、数量、尺寸、真人授权、模型能力与预算。"},
 {"id":"garment_present","name":"商品图整理","ai":True,"description":"保留颜色、印花、轮廓，整理背景；保留原图。"},
 {"id":"outfit_image","name":"多图穿搭合成","ai":True,"description":"按素材角色一次合成人物、姿势与服装；不默认逐件多次调用。"},
 {"id":"reference_board","name":"参考板对照","ai":False,"description":"确定性拼图，可选普通拼图对照，不消耗AI；原生多图保持分开输入，不把拼图当普通视频首帧。"},
 {"id":"human_review","name":"人工确认与评分","ai":False,"description":"领口、图案、层次、鞋子、身份和动作评分；API成功不等于可交付。"},
 {"id":"outfit_video","name":"动态展示","ai":True,"description":"复用已确认穿搭图；普通首帧或动作视频驱动。"},
 {"id":"asset_finalize","name":"保存与导出","ai":False,"description":"转存结果、文件校验、来源追踪和账单记录。保存失败只重新保存。"},
 {"id":"garment_extract","name":"自拍拆衣（后续）","ai":True,"deferred":True,"description":"区分可见区域分割与生成补全；未接入首版。"},
 {"id":"outfit_3d","name":"真实3D（后续）","ai":True,"deferred":True,"description":"多视图与模型生成独立付费，不混同视频拖动。"},
]
