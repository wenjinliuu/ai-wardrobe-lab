# 最新接入核对

2026-09-30多渠道扩展详见[79模型输入规格、价格与接入说明](provider-integration-2026-09-30.md)。以下保留首版调研记录，型号与能力以最新档案为准。

# 国内 API 接入清单

核对日期：2026-09-30。所有适配代码仅完成官方参数映射与本地模拟契约验证，没有宣称账号端点已实测。默认型号为保守档案，可在 `app/catalog.py` 添加新的型号和边界，避免只改模型字符串却沿用错误限制。

|服务|鉴权/端点组|素材与结果|接入前检查|
|---|---|---|---|
|Seedream|Ark Bearer，`/images/generations`|多张参考，同步返回图片URL|账号模型ID、分辨率、图像输入限制；`ARK_IMAGE_MODEL`可替换|
|Qwen Image Edit Plus|DashScope Bearer，多模态generation|消息数组含图片和指令，同步返回image|该档案最多3图；复杂穿搭比较参考板与其他模型|
|万相Flash|DashScope异步视频synthesis|完整Look首帧，任务查询返回视频|明确audio=false；2～15秒；北京Key与域名匹配|
|万相Animate|DashScope异步image2video|image_url、video_url；不接收prompt|2～30秒参考视频；wan-std/wan-pro；公网素材|
|可灵|TokenHub Bearer，kling端点组|contents与settings；data.id查询|普通首帧与motion-control分开；查询data为数组|
|MiniMax H3|TokenHub Bearer，minimax-video-v2端点组|content数组；查询task对象|首帧/参考互斥；仅H3支持多模态参考，不能替换为H3-Max|
|Vidu|国内api.vidu.cn，Token鉴权|reference2video，tasks/{id}/creations|2.0保守配置3图/4秒；新模型单独增加档案|
|Seedance|Ark Bearer，contents/generations/tasks|首帧role；异步查询|当前不支持本人模式；真人授权asset录入尚未实现|

各家返回URL仅为临时交付地址，保存后统一变成本站 asset_id。任务不暴露厂商原始临时链接。Seedance Key 与 Seedream 可共享 Ark 配置，仍需分别开通对应模型。

## 官方依据

- [Seedream 图像生成](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)
- [方舟型号退役与替换说明](https://docs.volcengine.com/docs/ark/model-deprecation-notice?lang=zh)
- [Seedance 视频任务](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)
- [Seedance 人像授权资产](https://docs.volcengine.com/docs/ark/seedance-portrait-asset-guide?lang=zh)
- [Qwen 图像编辑](https://help.aliyun.com/zh/model-studio/qwen-image-edit-api)
- [万相首帧视频](https://help.aliyun.com/zh/model-studio/legacy-image-to-video-api-reference/)
- [万相图生动作](https://help.aliyun.com/zh/model-studio/wan-animate-move-api)
- [百炼模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)
- [TokenHub 可灵](https://cloud.tencent.com/document/product/1823/135742)
- [TokenHub MiniMax](https://cloud.tencent.com/document/product/1823/135737)
- [TokenHub 价格](https://cloud.tencent.cn/document/product/1823/130055)
- [Vidu 国内参考生视频](https://docs.platform.vidu.cn/331842775e0)
- [Vidu 查询](https://docs.platform.vidu.cn/331854699e0)

## 后续接口

阿里 Aidge 专用虚拟试穿、服饰分割、腾讯混元3D和托管Agent工作流留作下一阶段适配。它们存在独立开通、鉴权或素材要求，不能用现有Key推定可用。固定按钮流程目前不需要任何厂商Skill托管；`config/templates.json`与工作流模块就是我们可管理的技能配置。

新增供应商时需补充：国内域名白名单、服务器凭证变量、模型能力档案、请求构造、状态/结果解析、查询路径、真实价格核对和契约测试。网页不提供任意URL代理，防止误把Key发送到陌生端点。
