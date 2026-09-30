"""Conservative model profiles; account availability and fidelity require live testing."""
import os

def profile(id, name, provider, adapter, kind, model, max_images, durations=(), resolutions=(), **extra):
    return dict(id=id,name=name,provider=provider,adapter=adapter,kind=kind,model=model,max_images=max_images,
                durations=list(durations),resolutions=list(resolutions),verified="contract_tested",live_tested=False,**extra)

MODELS = [
    profile("seedream", "Seedream 5.0 Pro · 多图合成", "ark", "seedream", "image", os.getenv("ARK_IMAGE_MODEL","doubao-seedream-5-0-pro-260628"),10, resolutions=["2K","3K"], min_side=256,max_side=8000,max_mb=20,prompt_max=3000,docs="https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh",note="模型 ID 可在服务器配置；默认限制为10张，账号可用性待实测。"),
    profile("qwen-edit", "Qwen Image Edit Plus · 图像编辑", "dashscope", "qwen", "image", "qwen-image-edit-plus",3,resolutions=["1024*1536","1536*1024","1024*1024"], min_side=256,max_side=8000,max_mb=10,prompt_max=1500,docs="https://help.aliyun.com/zh/model-studio/qwen-image-edit-api",note="最多3张图；多件服装可测试参考板，不能默认等价原生多图。"),
    profile("wan-flash", "万相 2.6 Flash · 图生视频", "dashscope", "wan", "video", "wan2.6-i2v-flash",1,range(2,16),["720P","1080P"],min_side=240,max_side=8000,max_mb=20,prompt_max=1500,prices={"720P":.15,"1080P":.25},price_unit="second",price_date="2026-09-30",docs="https://help.aliyun.com/zh/model-studio/legacy-image-to-video-api-reference/",note="明确关闭音频；单张完整穿搭图作为首帧。"),
    profile("wan-animate", "万相 Animate · 动作迁移", "dashscope", "wan_animate", "motion", "wan2.2-animate-move",1,[],["wan-std","wan-pro"],min_side=200,max_side=4096,max_mb=5,prompt_max=0,prices={"wan-std":.4,"wan-pro":.6},price_unit="second",price_date="2026-09-30",video_min=2,video_max=30,video_mb=200,video_side_min=200,video_side_max=2048,docs="https://help.aliyun.com/zh/model-studio/wan-animate-move-api",note="API不接收提示词；动作和输出时长由参考视频驱动。"),
    profile("kling-i2v", "可灵 V3 · 图生视频", "tokenhub", "kling", "video", "kling-video-v3",1,range(3,16),["720p","1080p","4k"],min_side=300,max_side=8000,max_mb=50,prompt_max=2500,docs="https://cloud.tencent.com/document/product/1823/135742",note="单镜头、关闭音频；价格需按账号账单核对。"),
    profile("kling-motion", "可灵 V3 · 动作控制", "tokenhub", "kling_motion", "motion", "kling-video-motion-control-v3.0",1,[],["720p","1080p"],min_side=300,max_side=8000,max_mb=50,prompt_max=2500,video_min=3,video_max=30,video_mb=100,video_side_min=340,video_side_max=3850,docs="https://cloud.tencent.com/document/product/1823/135742",note="人物朝向跟随视频，输出时长跟随动作参考。"),
    profile("minimax-h3", "MiniMax H3 · 多模态参考", "tokenhub", "h3", "reference_video", "minimax-video-h3",9,range(4,16),["768P","2K"],min_side=256,max_side=5760,max_mb=30,prompt_max=2000,video_min=2,video_max=15,video_mb=50,video_side_min=256,video_side_max=5760,docs="https://cloud.tencent.com/document/product/1823/135737",note="首帧模式和参考模式互斥；首轮仅支持一段动作参考。"),
    profile("vidu-ref", "Vidu 2.0 · 参考生视频", "vidu", "vidu", "reference_video", "vidu2.0",3,[4],["720p"],min_side=256,max_side=8000,max_mb=20,prompt_max=1500,docs="https://docs.platform.vidu.cn/331842775e0",note="采用已核对的保守2.0配置；新模型应新增能力档案再开放。"),
    profile("seedance", "Seedance 2.0 · 图生视频", "ark", "seedance", "video", os.getenv("ARK_VIDEO_MODEL","doubao-seedance-2-0-260128"),1,range(4,16),["720p","1080p"],min_side=300,max_side=6000,max_mb=20,prompt_max=1500,restricted_identity=True,docs="https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh",note="真人授权资产录入未实现，当前拒绝本人模式；先用授权默认模特验证。"),
]

def model(id):
    for m in MODELS:
        if m["id"] == id:
            return m
    raise ValueError("未知模型配置")

ROLES = {"pose":"姿势模板","identity":"本人参考","upper":"上衣","lower":"下装","shoes":"鞋子","accessory":"配饰","background":"背景","look":"完整穿搭图","motion":"动作参考"}
SKILLS = [
 {"id":"input_validate","name":"素材与权限校验","ai":False,"description":"检查角色、数量、尺寸、真人授权、模型能力与预算。"},
 {"id":"garment_present","name":"商品图整理","ai":True,"description":"保留颜色、印花、轮廓，整理背景；保留原图。"},
 {"id":"outfit_image","name":"多图穿搭合成","ai":True,"description":"按素材角色一次合成人物、姿势与服装；不默认逐件多次调用。"},
 {"id":"reference_board","name":"参考板对照","ai":False,"description":"确定性拼图，仅供图像模型对照实验，绝不直接作为普通视频首帧。"},
 {"id":"human_review","name":"人工确认与评分","ai":False,"description":"领口、图案、层次、鞋子、身份和动作评分；API成功不等于可交付。"},
 {"id":"outfit_video","name":"动态展示","ai":True,"description":"复用已确认穿搭图；普通首帧或动作视频驱动。"},
 {"id":"asset_finalize","name":"保存与导出","ai":False,"description":"转存结果、文件校验、来源追踪和账单记录。保存失败只重新保存。"},
 {"id":"garment_extract","name":"自拍拆衣（后续）","ai":True,"deferred":True,"description":"区分可见区域分割与生成补全；未接入首版。"},
 {"id":"outfit_3d","name":"真实3D（后续）","ai":True,"deferred":True,"description":"多视图与模型生成独立付费，不混同视频拖动。"},
]
