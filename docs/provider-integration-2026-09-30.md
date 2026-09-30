# 多渠道模型接入核对与测试策略 · 2026-09-30

这次把模型档案从9项扩展为79项，覆盖火山方舟、阿里百炼、腾讯TokenHub、MiniMax原厂、可灵原厂、Vidu原厂。每个档案保存渠道、实际模型ID、素材类型、输入模式、时长/分辨率、价格规则与官方链接。档案在config/models.json；接口构造在app/contracts.py，素材校验在app/capabilities.py，计价在app/pricing.py。

接口契约通过不代表账号已开通，也不代表视频还原质量已通过。没有进行付费生成；报价不能承诺供应商费用上限。官方限时折扣与企业优惠单独展示，预算使用刊例参考。上游更新后需重新核对。

## 视频输入的关键区别

| 渠道/型号 | 已实现的入口 | 限制与测试意义 |
|---|---|---|
| 腾讯/原厂 Hailuo 2.3、Fast | 文字（Fast除外）或1张首帧 | 768P 6/10秒；1080P仅6秒。不能把多件衣服当多图直接输入 |
| 腾讯 MiniMax H3 | 文字、首帧、尾帧、首尾帧；参考模式9图+3视频+3音频 | 总素材12，视频总15秒、音频总15秒；首尾帧与参考模式互斥 |
| 腾讯 MiniMax H3-Max | 文字、首帧、尾帧、首尾帧 | 当前渠道没有原厂Max的多模态参考入口 |
| MiniMax原厂 H3 / Max | 上述帧模式、多模态参考 | 原厂Max可参考9图3视频3音频；已有文件可用mm_file://ID |
| 腾讯/原厂 可灵 V3、2.6、2.5Turbo | 文字、首帧、首尾帧 | 首尾帧不等于任意多图。2.6有声仅1080p |
| 腾讯/原厂 可灵 V3 Omni、O1 | 多图、首尾帧、特征视频、原视频编辑、多图元素ID | 普通参考图/元素合计7；带视频最多4图/元素。特征视频与原视频用途不同 |
| 腾讯/原厂 可灵 Motion | 1人物图+1动作驱动视频 | 动作和输出时长跟随输入视频；不是普通参考视频 |
| 百炼 万相3.0 / Prime | 文字、首帧/首尾帧；参考模式10图5视频5音频；1文档或1网页 | 视频总15秒、音频总15秒，输入+输出视频≤30秒；文档与网页互斥；需要北京工作空间端点 |
| 百炼 万相2.7 R2V | 参考图+参考视频合计5，可另选首帧；逐素材绑定reference_voice | 音色不是独立reference_audio。含参考视频输出最长10秒 |
| 百炼 万相2.7 I2V | 首/尾帧+驱动音频；first_clip视频续写 | duration是续写的最终总时长，不是追加长度 |
| 百炼 万相2.7 Video Edit | 1原视频+最多4参考图 | 默认duration=0保持原时长；只计输出，输入免费；可保留原声 |
| 百炼 万相2.2 Animate Move | 人物图+动作视频 | 没有提示词字段；不能假装提示词约束在该接口生效 |
| 方舟 Seedance2.0、Fast、Mini | 文字、首尾帧、9图3视频3音频 | 参考总12，视频/音频总15秒；真人需可信流程 |
| 方舟 Seedance2.5 | 文字、首尾帧、30图10视频10音频 | 总素材50，视频/音频总30秒；按Token计费，不是固定每条1.5元 |
| 腾讯 PixVerse V6、5.6、C1 | 文字、首帧、首尾帧、最多7图参考 | 图的subject/background和引用名分别构造；5.6的1080p不支持10秒 |
| 腾讯 WAND Vega Video Lite | 文字、帧模式、多图/视频/音频参考 | 只接受公网URL；9图3视频3音频/总12按官方建议作保守限制 |
| 腾讯 混元Video1.5 | 文字或单图 | 固定5秒720p |
| 腾讯 优图Video2.0 | 单图+文字 | API无自选时长；按次计费；状态查询是POST，但属于读操作 |
| 腾讯 优图HumanActor | 人物图+驱动音频 | 音频决定输出时长；按秒计费 |
| 腾讯/原厂 Vidu Q3、Q2家族 | 按型号提供文字、首帧、首尾帧、参考、主体分组 | 仅Q2-Pro接参考视频；普通参考最多7图，带视频最多4图；主体每组1～3图或1段≤5秒视频 |
| 原厂 Vidu Q3Mix、2.0 | 参考图 | Q3Mix不提供subjects；2.0支持7图、4秒360p/720p |

## 真人素材：目前可以怎样测

Seedance的本人测试可以进行，但先要完成方舟可信素材流程：个人/企业账号认证与模型开通 → 体验中心/我的/真人/管理素材 → 创建授权资产组 → 演员本人扫码登录和认证、上传素材并授权 → 取得Active Asset ID → 在本站“授权ID/公网URL”入口录入ID、类型并确认授权。

已知公开规则允许同账号近30天、指定Seedance模型原始产物，以及指定Seedream5文生图原始产物进入可信路径。真人编辑图不能因为由AI生成就绕过授权。不要下载后重新编码再冒充原始可信URL；本站上传图片会转PNG并去掉元数据。本站只能记录用户确认，供应商仍判断授权、权限、资产状态和信任条件。

默认模特、非真人素材可先做普通调用。普通真实自拍URL可能被Seedance拦截，不能为了测试成功而改称无真人。可灵/MiniMax的审核、身份授权仍由各平台执行。

## 价格与规格的读法

价格是模型与渠道的属性。腾讯订阅/Token Plan可能折算套餐额度，原厂报价可能按人民币、积分或Token；不能比较一张“每条视频”价格而忽略时长、清晰度、有声、输入视频和输入图。完整档案与价格来源见后面的逐模型表。

示例：万相3.0标准版刊例480/720/1080P为0.3/0.6/1.2元/秒，输入视频和输出视频都收费。720P输出5秒、参考视频4秒，刊例参考5.4元；页面限时7折另列，最终看账户折扣。H3标准768P/2K为0.5/0.8元/秒，输入视频另计、超过5张参考图每张0.2元。原厂H3-Max输入视频和输出视频单价不同、超过2张图另计，不能复制H3标准规则。

可灵静音与有声不同；带参考视频的Omni与无视频不同。Vidu Q2部分模式按首秒与后续秒分段；图像Q2按参考图数量分档。Seedance按百万Token，实际输出像素、输入视频最低Token计量影响账单；本站标记近似或下界，不能把它称为完整固定报价。若某新型号尚无公开价格，明确显示“待核对”，不会填0。

## 工作流与收费

素材上传、确定性拼图、输入校验、预览请求、人工评分、转存/下载不调用AI。商品图优化、多图穿搭合成、视频生成各自是明确选中的生成任务，单次只提交一次生成POST，不默认逐件衣服多次AI加工。图片确认与视频生成之间保留人工质量检查。

原生多图模型直接发送分开的图片；参考板仅作为生图对照实验，默认关闭，免费普通图片处理。多图参考不等于精确替换衣服，素材角色标签、提示词和模板只能帮助约束，质量与还原需真实对比。

## 接入前配置与可测试边界

- Key只保存在服务器.env，分别为ARK_API_KEY、DASHSCOPE_API_KEY、TOKENHUB_API_KEY、MINIMAX_API_KEY、KLING_API_KEY、VIDU_API_KEY。新增原厂渠道不自动开启真实调用。
- 百炼新模型使用https://工作空间ID.cn-beijing.maas.aliyuncs.com；设置DASHSCOPE_BASE_URL。没有工作空间端点时可预览/模拟，真实调用会明确阻止。
- 本地图片按接口支持内联或转签名URL；视频/音频一般转公网签名URL，URL过期、审核、网络与账号权限需真实验证。外部HTTPSURL也有入口；外部时长须人工填写用于限制/计价，元数据最终由供应商验证。
- 上传支持PNG/JPEG/WebP、MP4/MOV、MP3/PCM WAV、PDF/TXT/MD/DOCX/XLSX/PPTX。不是每个模型都接受所有类型。文档页数/内容格式等由上游进一步检验；本站单文件200MB，模型自身上限另行限制。
- 公开腾讯目录还出现优图FX，但TokenHub文档没有给出独立model ID及完整包装参数契约；没有用猜测字段暴露可执行入口，后续得到接口说明再接入。专用服饰试穿、真实3D和自拍拆衣仍为后续。
- 各模型不是已付费效果验收。输入尺寸、格式或账号额度可能比公开档案更严格；不确定参数会保守限制并说明，而不把所有家族型号当作一样。

## 建议真实对照

固定授权模特/本人素材、上衣/下装/鞋子与一个动作视频，先预览原生分图请求；再测试首帧路线和多模态参考路线。比较服装纹理/颜色/层次、身份、动作、背景、耗时和实际费用。首尾帧、自由参考视频、严格动作控制分别成组，不混同“上传了动作视频就能精准复现动作”。每组先单次调用，记录失败也可能产生的费用，再决定增加样本。

## 逐模型档案

|渠道 / 模型ID|模式与容量|规格|刊例规则|官方来源|
|---|---|---|---|---|
|ark / `doubao-seedream-5-0-pro-260628`|纯文字:文字；多素材参考:参考图片≤10|1K/1.5K/2K；由输入/上游决定|`{"type":"image","rates":{"1K":0.3,"1.5K":0.3,"2K":0.6},"free_images":1,"extra_image":0.02}`|[API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh) · [价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh)|
|dashscope / `qwen-image-edit-plus`|多素材参考:参考图片≤3|1024*1536/1536*1024/1024*1024；由输入/上游决定|`{"type":"image","flat":0.2}`|[API](https://help.aliyun.com/zh/model-studio/qwen-image-edit-api) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|dashscope / `qwen-image-3.0`|纯文字:文字；多素材参考:参考图片≤3|1024*1024/1024*1536/2048*2048；由输入/上游决定|`{"type":"image","rates":{"1024*1024":0.18,"1024*1536":0.18,"2048*2048":0.18},"free_images":0,"extra_image":0.02}`|[API](https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|dashscope / `qwen-image-3.0-pro`|纯文字:文字；多素材参考:参考图片≤3|1024*1024/1024*1536/2048*2048；由输入/上游决定|`{"type":"image","rates":{"1024*1024":0.25,"1024*1536":0.25,"2048*2048":0.5},"free_images":0,"extra_image":0.02}`|[API](https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|dashscope / `wan2.7-image`|纯文字:文字；多素材参考:参考图片≤9|1K/2K；由输入/上游决定|`{"type":"image","flat":0.2}`|[API](https://help.aliyun.com/zh/model-studio/wan-image-generation-and-editing-api-reference) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|dashscope / `wan2.7-image-pro`|纯文字:文字；多素材参考:参考图片≤9|1K/2K/4K；由输入/上游决定|`{"type":"image","flat":0.5}`|[API](https://help.aliyun.com/zh/model-studio/wan-image-generation-and-editing-api-reference) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|tokenhub / `hy-image-v3`|纯文字:文字；多素材参考:参考图片≤3|1024x1024/768x1024/1024x768；由输入/上游决定|`{"type":"image","flat":0.2}`|[API](https://cloud.tencent.com/document/product/1823/135745) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `hy-image-v3.5-preview`|纯文字:文字；多素材参考:参考图片≤20|1K/2K/4K；由输入/上游决定|`{"type":"image","rates":{"1K":0.15,"2K":0.15,"4K":0.2}}`|[API](https://cloud.tencent.com/document/product/1823/135745) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `wand-vega-image-lite`|纯文字:文字；多素材参考:参考图片≤10|1K/2K/4K；由输入/上游决定|`{"type":"image","rates":{"1K":0.135,"2K":0.135,"4K":0.18}}`|[API](https://cloud.tencent.com/document/product/1823/137203) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `wand-vega-image-flash`|纯文字:文字；多素材参考:参考图片≤10|1K/2K/4K；由输入/上游决定|`{"type":"image","rates":{"1K":0.45,"2K":0.675,"4K":1.008}}`|[API](https://cloud.tencent.com/document/product/1823/137203) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `wand-vega-image-pro`|纯文字:文字；多素材参考:参考图片≤10|1K/2K/4K；由输入/上游决定|`{"type":"image","rates":{"1K":0.95,"2K":0.95,"4K":1.71},"free_images":3,"extra_image":0.1}`|[API](https://cloud.tencent.com/document/product/1823/137203) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `vidu-image-q2`|纯文字:文字；多素材参考:参考图片≤7|1080p/2K/4K；由输入/上游决定|`{"type":"image_tiers","tiers":[[0,{"1080p":0.1875,"2K":0.25,"4K":0.3125}],[3,{"1080p":0.25,"2K":0.375,"4K":0.625}],[7,{"1080p":0.3125,"2K":0.5,"4K":0.9375}]]}`|[API](https://cloud.tencent.com/document/product/1823/135746) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `seedream-image-v5.0-pro`|纯文字:文字；多素材参考:参考图片≤10|1K/1.5K/2K；由输入/上游决定|`{"type":"image","rates":{"1K":0.3,"1.5K":0.3,"2K":0.6},"free_images":1,"extra_image":0.02}`|[API](https://cloud.tencent.com/document/product/1823/136609) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `seedream-image-v5.0-lite`|纯文字:文字；多素材参考:参考图片≤10|2K/3K/4K；由输入/上游决定|`{"type":"image","flat":0.22}`|[API](https://cloud.tencent.com/document/product/1823/136609) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-image-v3`|纯文字:文字；多素材参考:参考图片≤1/可灵多图元素 ID≤10|1K/2K；由输入/上游决定|`{"type":"image","rates":{"1K":0.2,"2K":0.2,"4K":0.4}}`|[API](https://cloud.tencent.com/document/product/1823/138803) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-image-o1`|纯文字:文字；多素材参考:参考图片≤10/可灵多图元素 ID≤10|1K/2K；由输入/上游决定|`{"type":"image","rates":{"1K":0.2,"2K":0.2,"4K":0.4}}`|[API](https://cloud.tencent.com/document/product/1823/138803) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-image-v3-omni`|纯文字:文字；多素材参考:参考图片≤10/可灵多图元素 ID≤10|1K/2K/4K；由输入/上游决定|`{"type":"image","rates":{"1K":0.2,"2K":0.2,"4K":0.4}}`|[API](https://cloud.tencent.com/document/product/1823/138803) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|kling / `kling-image-v3`|纯文字:文字；多素材参考:参考图片≤1/可灵多图元素 ID≤10|1K/2K；由输入/上游决定|`{"type":"image","rates":{"1K":0.2,"2K":0.2,"4K":0.4}}`|[API](https://kling.ai/document-api/api/image/3-0-omni/image-omni) · [价格](https://kling.ai/document-api/pricing/base/image)|
|kling / `kling-image-o1`|纯文字:文字；多素材参考:参考图片≤10/可灵多图元素 ID≤10|1K/2K；由输入/上游决定|`{"type":"image","rates":{"1K":0.2,"2K":0.2,"4K":0.4}}`|[API](https://kling.ai/document-api/api/image/3-0-omni/image-omni) · [价格](https://kling.ai/document-api/pricing/base/image)|
|kling / `kling-image-v3-omni`|纯文字:文字；多素材参考:参考图片≤10/可灵多图元素 ID≤10|1K/2K/4K；由输入/上游决定|`{"type":"image","rates":{"1K":0.2,"2K":0.2,"4K":0.4}}`|[API](https://kling.ai/document-api/api/image/3-0-omni/image-omni) · [价格](https://kling.ai/document-api/pricing/base/image)|
|minimax / `image-01`|纯文字:文字；多素材参考:参考图片≤1|1024；由输入/上游决定|`{"type":"image","flat":0.025}`|[API](https://platform.minimaxi.com/docs/api-reference/image-generation-i2i) · [价格](https://platform.minimaxi.com/docs/guides/pricing-pay-as-you-go)|
|minimax / `image-01-live`|纯文字:文字；多素材参考:参考图片≤1|1024；由输入/上游决定|`{"type":"image","flat":0.025}`|[API](https://platform.minimaxi.com/docs/api-reference/image-generation-i2i) · [价格](https://platform.minimaxi.com/docs/guides/pricing-pay-as-you-go)|
|dashscope / `wan2.6-i2v-flash`|首帧:首帧图片≤1|720P/1080P；2～15秒|`{"type":"second","rates":{"720P":0.15,"1080P":0.25},"audio_rates":{"720P":0.3,"1080P":0.5}}`|[API](https://help.aliyun.com/zh/model-studio/legacy-image-to-video-api-reference/) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|dashscope / `wan3.0-video`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤10/参考视频≤5/参考音频≤5/参考文档≤1/参考网页≤1|480P/720P/1080P；2～30秒|`{"type":"second","rates":{"480P":0.3,"720P":0.6,"1080P":1.2},"input_video":true}`|[API](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|dashscope / `wan3.0-video-prime`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤10/参考视频≤5/参考音频≤5/参考文档≤1/参考网页≤1|480P/720P/1080P；2～30秒|`{"type":"second","rates":{"480P":0.45,"720P":0.9,"1080P":1.8},"input_video":true}`|[API](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|dashscope / `wan2.7-r2v-2026-06-12`|多素材参考:参考图片≤5/参考视频≤3/首帧图片≤1|720P/1080P；2～15秒|`{"type":"second","rates":{"720P":0.6,"1080P":1},"input_video":true,"input_cap":5}`|[API](https://help.aliyun.com/zh/model-studio/wan-video-to-video-api-reference) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|dashscope / `wan2.7-i2v`|首帧:首帧图片≤1/驱动音频≤1；首尾帧:首帧图片≤1/尾帧图片≤1/驱动音频≤1；视频续写:续写原视频≤1/驱动音频≤1|720P/1080P；2～15秒|`{"type":"second","rates":{"720P":0.6,"1080P":1},"input_video":false,"input_cap":null}`|[API](https://help.aliyun.com/zh/model-studio/image-to-video-general-api-reference) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|dashscope / `wan2.2-animate-move`|动作驱动:首帧图片≤1/驱动动作视频≤1|wan-std/wan-pro；由输入/上游决定|`{"type":"second","rates":{"wan-std":0.4,"wan-pro":0.6}}`|[API](https://help.aliyun.com/zh/model-studio/wan-animate-move-api) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|tokenhub / `minimax-video-h3`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤9/参考视频≤3/参考音频≤3；仅尾帧:尾帧图片≤1|768P/2K；4～15秒|`{"type":"second","rates":{"768P":0.5,"2K":0.8},"input_video":true,"input_rates":{"768P":0.5,"2K":0.8},"free_images":5,"extra_image":0.2}`|[API](https://cloud.tencent.com/document/product/1823/135737) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `minimax-video-h3-max`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；仅尾帧:尾帧图片≤1|480P/768P；5～15秒|`{"type":"second","rates":{"480P":0.33,"768P":0.5},"input_video":true,"input_rates":{"480P":0.33,"768P":0.5},"free_images":2,"extra_image":0.5}`|[API](https://cloud.tencent.com/document/product/1823/135737) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `minimax-video-v2.3`|纯文字:文字；首帧:首帧图片≤1|768P/1080P；6～10秒|`{"type":"job","rates":{"768P:6":2,"768P:10":4,"1080P:6":3.5}}`|[API](https://cloud.tencent.com/document/product/1823/135737) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `minimax-video-v2.3-fast`|首帧:首帧图片≤1|768P/1080P；6～10秒|`{"type":"job","rates":{"768P:6":1.35,"768P:10":2.25,"1080P:6":2.31}}`|[API](https://cloud.tencent.com/document/product/1823/135737) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|minimax / `MiniMax-H3`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤9/参考视频≤3/参考音频≤3；仅尾帧:尾帧图片≤1|768P/2K；4～15秒|`{"type":"second","rates":{"768P":0.5,"2K":0.8},"input_video":true,"input_rates":{"768P":0.5,"2K":0.8},"free_images":5,"extra_image":0.2}`|[API](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create) · [价格](https://platform.minimaxi.com/docs/guides/pricing-pay-as-you-go)|
|minimax / `MiniMax-H3-Max`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤9/参考视频≤3/参考音频≤3；仅尾帧:尾帧图片≤1|480P/768P；5～15秒|`{"type":"second","rates":{"480P":0.33,"768P":0.5},"input_video":true,"input_rates":{"480P":0.37,"768P":0.97},"free_images":2,"extra_image":0.5}`|[API](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create) · [价格](https://platform.minimaxi.com/docs/guides/pricing-pay-as-you-go)|
|minimax / `MiniMax-Hailuo-2.3`|纯文字:文字；首帧:首帧图片≤1|768P/1080P；6～10秒|`{"type":"job","rates":{"768P:6":2,"768P:10":4,"1080P:6":3.5}}`|[API](https://platform.minimaxi.com/docs/api-reference/video-generation-i2v) · [价格](https://platform.minimaxi.com/docs/guides/pricing-pay-as-you-go)|
|minimax / `MiniMax-Hailuo-2.3-Fast`|首帧:首帧图片≤1|768P/1080P；6～10秒|`{"type":"job","rates":{"768P:6":1.35,"768P:10":2.25,"1080P:6":2.31}}`|[API](https://platform.minimaxi.com/docs/api-reference/video-generation-i2v) · [价格](https://platform.minimaxi.com/docs/guides/pricing-pay-as-you-go)|
|tokenhub / `wand-vega-video-1.0-lite`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤9/参考视频≤3/参考音频≤3|768P/1080P/2K/4K；4～15秒|`{"type":"second","rates":{"768P":0.375,"1080P":0.5,"2K":0.625,"4K":0.75},"input_video":true,"free_images":5,"extra_image":0.15}`|[API](https://cloud.tencent.com/document/product/1823/138195) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `pixverse-video-v6.0`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7|360p/540p/720p/1080p；1～15秒|`{"type":"second","rates":{"360p":0.14665,"540p":0.20531,"720p":0.26397,"1080p":0.52794},"audio_rates":{"360p":0.20531,"540p":0.26397,"720p":0.35196,"1080p":0.67459}}`|[API](https://cloud.tencent.com/document/product/1823/135325) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `pixverse-video-v5.6`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7|360p/540p/720p/1080p；5～10秒|`{"type":"second","rates":{"360p":0.20531,"540p":0.20531,"720p":0.26397,"1080p":0.43995},"audio_rates":{"360p":0.46928,"540p":0.46928,"720p":0.52794,"1080p":0.8799}}`|[API](https://cloud.tencent.com/document/product/1823/135325) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `pixverse-video-c1`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7|360p/540p/720p/1080p；1～15秒|`{"type":"second","rates":{"360p":0.17598,"540p":0.23464,"720p":0.2933,"1080p":0.55727},"audio_rates":{"360p":0.23464,"540p":0.2933,"720p":0.38129,"1080p":0.70392}}`|[API](https://cloud.tencent.com/document/product/1823/135325) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `hy-video-v1.5`|纯文字:文字；首帧:首帧图片≤1|720p；5～5秒|`{"type":"second","flat":0.3}`|[API](https://cloud.tencent.com/document/product/1823/137202) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `yt-video-2.0`|首帧:首帧图片≤1|480p/720p/1080p；由输入/上游决定|`{"type":"job","rates":{"480p":2,"720p":5,"1080p":5}}`|[API](https://cloud.tencent.com/document/product/1823/135716) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `yt-video-humanactor`|音频驱动人像:首帧图片≤1/驱动音频≤1|720p/1080p；由输入/上游决定|`{"type":"second","rates":{"720p":1,"1080p":2}}`|[API](https://cloud.tencent.com/document/product/1823/135716) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-video-v3`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|720p/1080p/4k；3～15秒|`{"type":"second","rates":{"720p":0.6,"1080p":0.8,"4k":3},"audio_rates":{"720p":0.9,"1080p":1.2,"4k":3}}`|[API](https://cloud.tencent.com/document/product/1823/135742) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-video-v3-turbo`|纯文字:文字；首帧:首帧图片≤1|720p/1080p；3～15秒|`{"type":"second","rates":{"720p":0.8,"1080p":1},"audio_rates":{"720p":0.0,"1080p":1}}`|[API](https://cloud.tencent.com/document/product/1823/135742) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-video-v2.6`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|720p/1080p；5～10秒|`{"type":"second","rates":{"720p":0.3,"1080p":0.5},"audio_rates":{"720p":0.0,"1080p":1}}`|[API](https://cloud.tencent.com/document/product/1823/135742) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-video-v2.5-turbo`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|720p/1080p；5～10秒|`{"type":"second","rates":{"720p":0.3,"1080p":0.5},"audio_rates":{"720p":0.0,"1080p":1}}`|[API](https://cloud.tencent.com/document/product/1823/135742) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-video-v3-omni`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7/可灵多图元素 ID≤7；特征视频参考:特征参考视频≤1/参考图片≤4/可灵多图元素 ID≤4；编辑原视频:待编辑原视频≤1/参考图片≤4/可灵多图元素 ID≤4|720p/1080p/4k；3～15秒|`{"type":"second","rates":{"720p":0.6,"1080p":0.8,"4k":3},"audio_rates":{"720p":0.8,"1080p":1,"4k":3},"video_rates":{"720p":0.9,"1080p":1.2,"4k":3}}`|[API](https://cloud.tencent.com/document/product/1823/135742) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-video-o1`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7/可灵多图元素 ID≤7；特征视频参考:特征参考视频≤1/参考图片≤4/可灵多图元素 ID≤4；编辑原视频:待编辑原视频≤1/参考图片≤4/可灵多图元素 ID≤4|720p/1080p；3～10秒|`{"type":"second","rates":{"720p":0.6,"1080p":0.8,"4k":3},"audio_rates":{"720p":0.8,"1080p":1,"4k":3},"video_rates":{"720p":0.9,"1080p":1.2,"4k":3}}`|[API](https://cloud.tencent.com/document/product/1823/135742) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-video-motion-control-v3.0`|动作驱动:首帧图片≤1/驱动动作视频≤1|720p/1080p；由输入/上游决定|`{"type":"second","rates":{"720p":0.9,"1080p":1.2}}`|[API](https://cloud.tencent.com/document/product/1823/135742) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `kling-video-motion-control-v2.6`|动作驱动:首帧图片≤1/驱动动作视频≤1|720p/1080p；由输入/上游决定|`{"type":"second","rates":{"720p":0.5,"1080p":0.8}}`|[API](https://cloud.tencent.com/document/product/1823/135742) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|kling / `kling-v3`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|720p/1080p/4k；3～15秒|`{"type":"second","rates":{"720p":0.6,"1080p":0.8,"4k":3},"audio_rates":{"720p":0.9,"1080p":1.2,"4k":3}}`|[API](https://kling.ai/document-api/api/video/3-0-omni/image-to-video/legacy) · [价格](https://kling.ai/document-api/pricing/base/video)|
|kling / `kling-v3-turbo`|首帧:首帧图片≤1|720p/1080p；3～15秒|`{"type":"second","rates":{"720p":0.8,"1080p":1},"audio_rates":{"720p":0.0,"1080p":1}}`|[API](https://kling.ai/document-api/api/video/3-0-omni/image-to-video/legacy) · [价格](https://kling.ai/document-api/pricing/base/video)|
|kling / `kling-v2-6`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|720p/1080p；5～10秒|`{"type":"second","rates":{"720p":0.3,"1080p":0.5},"audio_rates":{"720p":0.0,"1080p":1}}`|[API](https://kling.ai/document-api/api/video/3-0-omni/image-to-video/legacy) · [价格](https://kling.ai/document-api/pricing/base/video)|
|kling / `kling-v2-5-turbo`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|720p/1080p；5～10秒|`{"type":"second","rates":{"720p":0.3,"1080p":0.5},"audio_rates":{"720p":0.0,"1080p":1}}`|[API](https://kling.ai/document-api/api/video/3-0-omni/image-to-video/legacy) · [价格](https://kling.ai/document-api/pricing/base/video)|
|kling / `kling-v3-omni`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7/可灵多图元素 ID≤7；特征视频参考:特征参考视频≤1/参考图片≤4/可灵多图元素 ID≤4；编辑原视频:待编辑原视频≤1/参考图片≤4/可灵多图元素 ID≤4|720p/1080p/4k；3～15秒|`{"type":"second","rates":{"720p":0.6,"1080p":0.8,"4k":3},"audio_rates":{"720p":0.8,"1080p":1,"4k":3},"video_rates":{"720p":0.9,"1080p":1.2,"4k":3}}`|[API](https://kling.ai/document-api/api/video/o1/video-omni/legacy) · [价格](https://kling.ai/document-api/pricing/base/video)|
|kling / `kling-video-o1`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7/可灵多图元素 ID≤7；特征视频参考:特征参考视频≤1/参考图片≤4/可灵多图元素 ID≤4；编辑原视频:待编辑原视频≤1/参考图片≤4/可灵多图元素 ID≤4|720p/1080p；3～10秒|`{"type":"second","rates":{"720p":0.6,"1080p":0.8,"4k":3},"audio_rates":{"720p":0.8,"1080p":1,"4k":3},"video_rates":{"720p":0.9,"1080p":1.2,"4k":3}}`|[API](https://kling.ai/document-api/api/video/o1/video-omni/legacy) · [价格](https://kling.ai/document-api/pricing/base/video)|
|kling / `kling-v3`|动作驱动:首帧图片≤1/驱动动作视频≤1|720p/1080p；由输入/上游决定|`{"type":"second","rates":{"720p":0.9,"1080p":1.2}}`|[API](https://kling.ai/document-api/api/video/motion-control/legacy) · [价格](https://kling.ai/document-api/pricing/base/video)|
|kling / `kling-v2-6`|动作驱动:首帧图片≤1/驱动动作视频≤1|720p/1080p；由输入/上游决定|`{"type":"second","rates":{"720p":0.5,"1080p":0.8}}`|[API](https://kling.ai/document-api/api/video/motion-control/legacy) · [价格](https://kling.ai/document-api/pricing/base/video)|
|tokenhub / `vidu-video-q3-pro`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|540p/720p/1080p；1～16秒|`{"type":"second","rates":{"540p":0.28125,"720p":0.625,"1080p":0.75}}`|[API](https://cloud.tencent.com/document/product/1823/135756) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `vidu-video-q3-turbo`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7；主体分组参考:主体图片（分组）≤21|540p/720p/1080p；1～16秒|`{"type":"second","rates":{"540p":0.21875,"720p":0.375,"1080p":0.40625},"mode_rates":{"reference":{"540p":0.125,"720p":0.3125,"1080p":0.40625},"subjects":{"540p":0.125,"720p":0.3125,"1080p":0.40625}}}`|[API](https://cloud.tencent.com/document/product/1823/135756) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `vidu-video-q3`|多素材参考:参考图片≤7；主体分组参考:主体图片（分组）≤21|540p/720p/1080p；1～16秒|`{"type":"second","rates":{"540p":0.21875,"720p":0.375,"1080p":0.46875}}`|[API](https://cloud.tencent.com/document/product/1823/135756) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `vidu-video-q2-pro`|首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7/参考视频≤2；主体分组参考:主体图片（分组）≤12/主体视频（分组）≤1|540p/720p/1080p；1～10秒|`{"type":"vidu_q2","version":"q2-pro"}`|[API](https://cloud.tencent.com/document/product/1823/135756) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `vidu-video-q2-turbo`|首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|540p/720p/1080p；1～10秒|`{"type":"vidu_q2","version":"q2-turbo"}`|[API](https://cloud.tencent.com/document/product/1823/135756) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|tokenhub / `vidu-video-q2`|纯文字:文字；多素材参考:参考图片≤7；主体分组参考:主体图片（分组）≤21|540p/720p/1080p；1～10秒|`{"type":"vidu_q2","version":"q2"}`|[API](https://cloud.tencent.com/document/product/1823/135756) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
|vidu / `viduq3-pro`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|540p/720p/1080p；1～16秒|`{"type":"second","rates":{"540p":0.28125,"720p":0.625,"1080p":0.75}}`|[API](https://docs.platform.vidu.cn/331842775e0) · [价格](https://docs.platform.vidu.cn/1227169m0)|
|vidu / `viduq3-turbo`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7；主体分组参考:主体图片（分组）≤21|540p/720p/1080p；1～16秒|`{"type":"second","rates":{"540p":0.21875,"720p":0.375,"1080p":0.40625},"mode_rates":{"reference":{"540p":0.125,"720p":0.3125,"1080p":0.40625},"subjects":{"540p":0.125,"720p":0.3125,"1080p":0.40625}}}`|[API](https://docs.platform.vidu.cn/331842775e0) · [价格](https://docs.platform.vidu.cn/1227169m0)|
|vidu / `viduq3`|多素材参考:参考图片≤7；主体分组参考:主体图片（分组）≤21|540p/720p/1080p；1～16秒|`{"type":"second","rates":{"540p":0.21875,"720p":0.375,"1080p":0.46875}}`|[API](https://docs.platform.vidu.cn/331842775e0) · [价格](https://docs.platform.vidu.cn/1227169m0)|
|vidu / `viduq2-pro`|首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤7/参考视频≤2；主体分组参考:主体图片（分组）≤12/主体视频（分组）≤1|540p/720p/1080p；1～10秒|`{"type":"vidu_q2","version":"q2-pro"}`|[API](https://docs.platform.vidu.cn/331842775e0) · [价格](https://docs.platform.vidu.cn/1227169m0)|
|vidu / `viduq2-turbo`|首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1|540p/720p/1080p；1～10秒|`{"type":"vidu_q2","version":"q2-turbo"}`|[API](https://docs.platform.vidu.cn/331842775e0) · [价格](https://docs.platform.vidu.cn/1227169m0)|
|vidu / `viduq2`|纯文字:文字；多素材参考:参考图片≤7；主体分组参考:主体图片（分组）≤21|540p/720p/1080p；1～10秒|`{"type":"vidu_q2","version":"q2"}`|[API](https://docs.platform.vidu.cn/331842775e0) · [价格](https://docs.platform.vidu.cn/1227169m0)|
|vidu / `viduq3-mix`|多素材参考:参考图片≤7|720p/1080p；1～16秒|`{"type":"second","rates":{"720p":0.75,"1080p":0.90625}}`|[API](https://docs.platform.vidu.cn/331842775e0) · [价格](https://docs.platform.vidu.cn/1227169m0)|
|vidu / `vidu2.0`|多素材参考:参考图片≤7；主体分组参考:主体图片（分组）≤21|360p/720p；4～4秒|`{"type":"job","flat":2.5}`|[API](https://docs.platform.vidu.cn/331842775e0) · [价格](https://docs.platform.vidu.cn/1227169m0)|
|ark / `doubao-seedance-2-0-260128`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤9/参考视频≤3/参考音频≤3|480p/720p/1080p；4～15秒|`{"type":"token","rates_million":{"480p":46,"720p":46,"1080p":51},"video_rates_million":{"480p":28,"720p":28,"1080p":31}}`|[API](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh&redirect=1) · [价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh)|
|ark / `doubao-seedance-2-0-fast-260128`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤9/参考视频≤3/参考音频≤3|480p/720p；4～15秒|`{"type":"token","rates_million":{"480p":37,"720p":37,"1080p":37},"video_rates_million":{"480p":22,"720p":22,"1080p":22}}`|[API](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh&redirect=1) · [价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh)|
|ark / `doubao-seedance-2-0-mini-260615`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤9/参考视频≤3/参考音频≤3|480p/720p；4～15秒|`{"type":"token","rates_million":{"480p":23,"720p":23,"1080p":23},"video_rates_million":{"480p":14,"720p":14,"1080p":14}}`|[API](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh&redirect=1) · [价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh)|
|ark / `doubao-seedance-2-5-260628`|纯文字:文字；首帧:首帧图片≤1；首尾帧:首帧图片≤1/尾帧图片≤1；多素材参考:参考图片≤30/参考视频≤10/参考音频≤10|480p/720p/1080p；4～30秒|`{"type":"token","rates_million":{"480p":70,"720p":70,"1080p":77},"video_rates_million":{"480p":42,"720p":42,"1080p":46}}`|[API](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh&redirect=1) · [价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh)|
|dashscope / `wan2.7-videoedit`|编辑原视频:待编辑原视频≤1/参考图片≤4|720P/1080P；2～10秒|`{"type":"second","rates":{"720P":0.6,"1080P":1}}`|[API](https://help.aliyun.com/zh/model-studio/wan-video-edit-api-reference) · [价格](https://help.aliyun.com/zh/model-studio/model-pricing-by-model)|
|tokenhub / `wand-vega-image-1.5-pro`|纯文字:文字；多素材参考:参考图片≤10|1K/2K/4K；由输入/上游决定|`{"type":"unknown"}`|[API](https://cloud.tencent.com/document/product/1823/137203) · [价格](https://cloud.tencent.com/document/product/1823/130055)|
