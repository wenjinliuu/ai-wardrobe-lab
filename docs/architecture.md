# 冻结时技术架构与代码交接

日期：2026-10-02（北京时间）。对应最后运行代码：`21633039abf6ac25e1f35e73498fd82ecf119dde`。此后冻结提交仅更新文档。项目状态和操作边界以[冻结决策](project-freeze-2026-10-02.md)为准。

## 1. 运行架构

浏览器使用原生JavaScript界面，与Python FastAPI后端同源。Caddy负责入口代理，应用容器只向内部网络暴露8000。一个Uvicorn进程内的后台调度器拥有任务；SQLite WAL保存状态和账单，服务器文件系统保存媒体，FFmpeg/ffprobe检查视频。

服务器不运行图像/视频生成模型，不需要GPU。所有实际生成由外部API执行。界面中的Skills是固定校验、提示词编译和执行模块，不是每步再调用一个规划Agent，也不是已经发布到百炼的托管Skill。

**部署工作流与生成工作流不同**：GitHub Actions检查和部署代码；用户生成图片/视频时，由现有应用提交供应商任务，不启动GitHub Actions。

## 2. 代码导航

|文件|实际职责|
|---|---|
|`web/index.html`、`web/style.css`|页面入口、暖橙白底布局、响应式样式|
|`web/app.js`|八页面、素材预览选择、个人形象、技能卡片、任务/费用/评价、结果对比、放大和循环|
|`web/input-rules.js`|前端共用模式/类型/数量/组合限制、参数联动、兼容任务编号|
|`app/main.py`|FastAPI路由、登录、上传、任务、请求预览、评价、账单、模板、个人形象、导出|
|`app/config.py`|环境配置、凭据、服务开关、供应商端点及允许范围|
|`app/security.py`|密码/会话签名、CSRF、同源、私人下载、临时签名媒体、外部地址安全检查|
|`app/catalog.py`、`config/models.json`|六渠道79档案、能力、模式、限制、价格来源和验证状态|
|`app/capabilities.py`|后端权威校验：素材角色、媒体实参、模式组合、授权、确认和模型能力|
|`app/contracts.py`|逐供应商请求/查询结构与响应归一化|
|`app/providers.py`|实际HTTP调用、异步查询；不自动重复不确定生成POST|
|`app/engine.py`|任务快照、幂等、调度、状态恢复、输出保存、估价和用量处理|
|`app/db.py`|SQLite表、素材/任务/事件/模板/形象/登录记录读写|
|`app/assets.py`|图片解码、去元数据、媒体探测、文件校验、参考板、模拟输出、结果下载|
|`app/personal.py`|个人形象参数、发型与姿势词库、引用素材、全身提示词、创作技能编译|
|`app/pricing.py`|按渠道、模式、时长、清晰度、声音和输入规格估价|
|`app/billing.py`|价格快照、金额/Token/积分核对、供应商用量自动成本|
|`config/templates.json`|初始模板、版本、技能、提示词、避免项与验收要求|
|`Dockerfile`、`compose.yaml`、`deploy/Caddyfile`|Python/FFmpeg运行环境、持久化挂载、代理和健康检查|
|`scripts/deploy.sh`|服务器构建、部署锁、配置检查、健康验证、当前版本链接和回退|
|`.github/workflows/ci.yml`|平台自动测试及Docker构建验证|
|`.github/workflows/deploy.yml`|main代码变更或手动触发，验证后SSH上传源码并部署|

测试目录保存后端、供应商契约、浏览器和部署相关自动验证；不使用真实Key、真人测试照片或付费API作为自动测试依赖。

## 3. 页面与接口

页面：个人形象、创作台、素材库、模板与提示词、技能与工作流、测试记录、结果对比、平台连接。

|接口组|用途|
|---|---|
|`GET /healthz`|健康检查|
|`POST /api/login`、`POST /api/logout`|私人访问会话|
|`GET /api/bootstrap`|界面启动数据及配置状态|
|`GET/POST /api/assets`|素材查询和上传|
|`GET /api/assets/{aid}/file`、`/download`|登录后的预览与下载|
|`GET /api/assets/{aid}/bindings`|删除/归档前查看绑定|
|`DELETE /api/assets/{aid}`|删除规则或归档隐藏|
|`GET /media/{aid}`|供应商取材的限时签名入口|
|`POST /api/preview`|构造并展示本次最终请求/提示词；不执行生成|
|`POST /api/jobs`、`GET /api/jobs`、`GET /api/jobs/{jid}`|创建及查看任务|
|`POST /api/jobs/{jid}/review`|人工质量与账单核对|
|`POST /api/jobs/{jid}/billing-preview`|核对金额与用量换算|
|`POST /api/jobs/{jid}/resume`|已有任务编号查询或保存续接|
|`DELETE /api/jobs/{jid}`|按模拟/真实记录保留规则处理|
|`POST /api/templates`|保存新模板版本|
|`GET/POST /api/personal-profiles`、`DELETE /api/personal-profiles/{pid}`|个人形象保存、列表和删除|
|`GET /api/export`|CSV/JSON实验导出|
|`POST /api/demo`|普通演示素材，不是付费模型生成|

这些是测试台接口，不是完整衣柜App的Garment、Outfit、WearRecord或支付API。

## 4. 任务状态与费用安全

正常状态：`queued → submitting → polling → saving → succeeded`。

- 创建时冻结模型、价格、模板/提示词版本、参数、素材角色、ID和SHA256。修改模板或文件不追溯改变旧实验。
- 使用Idempotency-Key及请求哈希。同一编号与相同参数返回同一任务；用同一编号提交不同参数拒绝。
- `submitting`先落盘再提交；网络中断、部分服务端错误或提交期间重启可能进入`uncertain`。不能确定是否已经扣费时，不自动再次POST。需先核对上游，填写已有任务编号后恢复查询。
- 已有供应商任务ID的查询异常延迟续查；长时间等待可进入`paused`，恢复查询不是新生成。
- 输出地址先保存于私人数据库再下载。下载失败进入`save_failed`，只续保存；已经保存的部分结果不重新生成。
- `failed`记录供应商失败；调整输入重新生成属于新任务，不假定失败免费。
- 自动测试使用模拟结果：图像是参考卡，视频是静态帧。模拟结果不能拿来证明质量，也不能作为真实生成输入。

仍只能部署一个Uvicorn worker。分布式租约/队列未实现，多进程直接扩容会破坏调度拥有权。

## 5. 素材、角色和能力校验

图片接受JPEG/PNG/WebP，解码检查后去元数据并保存PNG，不是原始字节归档；HEIC未支持。视频/音频实际探测编码、时长、尺寸等。文档类型另做格式检查。外部媒体引用由具体模式开放，不能只填假扩展名绕过限制。

前端上传与素材库引用共用限制；后端再次校验实际文件。库可存多文件，一次请求仍受当前型号/模式的名额、单类数量、总数、总时长、分辨率和大小限制。切换模式不能静默丢弃输入，应提示不兼容。

普通角色如`identity/upper/lower/shoes/accessory/pose/look`用于本站语义及提示词编号；`first_frame/last_frame`、主体分组和厂商ID只在对应契约使用。厂商未提供衣物角色字段时靠文字说明，不伪造它的API能力。

参考板用Pillow等普通处理拼接，无额外AI调用。仅适用于图像对照，不直接当普通视频首帧。拼图不等于AI抠图、换装或自动补全。

方舟可信真人Asset ID、MiniMax已有文件ID、百炼资产、可灵/腾讯元素及音色标识是不同协议；已提供的录入入口不等于本站实现创建/扫码授权。授权仍须在对应官方流程完成。

## 6. 当前仍存在的视频人工门槛

`app/capabilities.py`对关联AI生成`look`检查父任务`review.verdict == 'pass'`，否则返回“生成图需评为合格后才能做视频”。前端也使用合格状态提供相应入口；另有图片检查确认选项。

这是本站实验流程，不是厂商要求。最后一次用户提问后讨论了降低该门槛、保留明确确认；截至冻结代码没有修改，不能写成已移除。手工上传Look和AI关联Look走不同校验，模拟Look不进入真实视频任务。

## 7. 费用记录与自动填入

价格和计费规则来自任务创建时快照，不随配置更新覆盖旧结果。

|数值|意义|
|---|---|
|估价/参考金额|按档案规格计算的预计值，可能不含全部实际输入用量；不是上游扣费上限|
|供应商用量|响应返回的计费Token/积分，不能把所有usage字段都算人民币|
|用量计算金额|实际计费量乘明确单价得到，未必包含账号折扣/免费额度|
|金额反推用量|从金额按该单价折算，必须标为推算，不是实测Token|
|人工账单金额|用户核对的实际金额；与估价、自动计算及差额分别保存|

`app/billing.py.automatic`当前只对真实TokenHub任务、`official`计价快照、有效`total_tokens`或`credits`自动计算。没有适配其它渠道用量自动算价的通用承诺；缺少明确计费单位/单价时留待核对。

`reconcile`支持按金额、按实际用量或同时填写核对；自定义折扣单价须注明依据。换算：`费用 = 用量 × 单价 / 单价基数`，Token常用每百万，积分每单位。混合单价、赠送或折扣不能机械反推成实际用量。人工记录、供应商用量和估价分别显示，避免重复加总。

用户要求的每日次数/预算阻断已经取消。遗留`LAB_DAILY_*`配置可能仍被读取，但不能据此声称当前有每日阻断。真实总开关、Key、素材校验、授权与逐次付费确认仍存在。最终产品订阅额度与付费账本没有实现。

## 8. 持久化和删除

SQLite实际表包括`assets`、`templates`、`jobs`、`events`、`personal_profiles`、`login_attempts`。

- 素材记录文件、来源、尺寸、时长、大小、哈希及`details`元数据；`library_hidden`表示归档隐藏。
- 任务`body`保存请求、模型/价格/模板/输入快照；`result`保存归一化结果、私人上游地址和用量；`review`保存人工质量和账单。
- 形象资料保存参数及引用资产；保存形象是复用自己的图片，不创建通用厂商元素库。
- 真实任务费用历史保留；删除/归档前展示关联记录。隐藏素材不物理释放磁盘，也不应使历史费用丢失。
- 用户上传/AI来源是单个私人空间的来源标记，不是已经实现多用户身份系统。

服务器持久化目录为`/opt/wardrobe-lab/shared/data`，配置为`/opt/wardrobe-lab/shared/.env`，当前代码链接`/opt/wardrobe-lab/current`，历史版本位于`/opt/wardrobe-lab/releases`。本次不操作这些文件，没有额外制作离线备份。

## 9. 凭据与访问边界

凭据仅放服务器环境，不放GitHub源码、浏览器存储或本文。变量名称：`TOKENHUB_API_KEY`、`DASHSCOPE_API_KEY`、`ARK_API_KEY`、`MINIMAX_API_KEY`；可灵/Vidu原厂变量保留，但按用户决定不启用该两原厂渠道。

生产启动检查`LAB_PASSWORD`至少12位、`LAB_SESSION_SECRET`至少32位，公网关闭`LAB_DEV_MODE`；真实调用还受`LAB_LIVE_ENABLED`控制。显示“Key已配置”仅说明读到值，不证明账户权限、余额或接口成功。曾出现配置变为3位导致应用重启和502，属于配置错误，不是重新装机的理由。

会话HMAC、CSRF/同源、登录限流、登录后文件下载、供应商限时签名链接及SSRF检查已实现。导出不带Key、私有供应商结果URL或签名URL。当前访问记录是公网IP HTTP，未在此冻结操作中新增域名/HTTPS；正式多用户产品安全体系尚未完成。

## 10. 部署事实与证据

当前是腾讯轻量云Ubuntu/Docker Compose/Caddy，自GitHub Actions通过已验证主机密钥SSH部署。凭据在GitHub Secrets，服务器模型Key与部署私钥不是一回事。

早期尝试传完整镜像包出现极低上传速度，随后采用小源码归档上传、服务器构建并使用腾讯软件源。TAT/MCP/Cloudflare探索没有成为当前部署主路；细节留在[网络诊断](network-diagnosis.md)和[部署说明](deployment.md)，不作为产品冻结原因。

部署脚本使用`flock`避免并行争抢，构建新release，验证容器和健康后更新当前链接，失败可回退。最后工作流避免Runner已有FFmpeg时重复apt刷新，缺依赖安装设定有界等待。

最后运行版本及验证：

- 代码SHA：`21633039abf6ac25e1f35e73498fd82ecf119dde`。
- [部署run 36910724564](https://github.com/wenjinliuu/ai-wardrobe-lab/actions/runs/36910724564)，job `110532787907`成功。
- 日志：`311 passed, 1 warning in 66.78s`；`Deployment healthy: 21633039abf6ac25e1f35e73498fd82ecf119dde`；`{"status":"ok","version":"0.1.0"}`。
- 健康时间：2026-10-01 19:01 UTC / 2026-10-02 03:01北京时间。
- [独立CI run 36910724473](https://github.com/wenjinliuu/ai-wardrobe-lab/actions/runs/36910724473)测试与Docker成功。

这些证明该版本部署并通过自动测试，不能当作311次真实生成或冻结时持续在线监测。真实效果依据用户已反馈的腾讯调用，尚无全渠道完整验收报告。

部署push只监听应用、前端、配置、测试、依赖、Docker/Compose和部署脚本/工作流等路径。此次README、AGENTS、docs变更不触发部署；平台CI仍可因main推送运行。冻结不改变现有触发器，恢复后不能以旧工作流存在为继续开发授权。

## 11. 仍未实现与待复核

- 白底、84%人物占比、服装和身份保真依赖生成提示词与人工检查，无自动视觉质量保证。
- 个人形象小头像问题加强了提示词与可见编译内容，后续真实效果未确认。
- 多张结果支持不完整：部分供应商可返回多图，归一化/下载可处理结果列表，但目前主要请求`n=1`，批次生成、费用、逐图确认未完成。
- 未实现衣物自动识别/推荐业务闭环、专用虚拟试穿、自拍拆衣、自动视觉评分、可信真人资产创建、真正3D或打印。
- 未实现多用户隔离、账号支付、订阅、IAP及长期数据生命周期管理。
- 未实测所有档案；旧价格、接口、账户地域和认证要求须恢复前重新核验。
- 不确定提交要人工核对，不能为了消除失败提示而开启无条件POST重试。

## 12. 如何恢复阅读

先读[冻结决定](project-freeze-2026-10-02.md)，再读[产品设计](product-design-snapshot.md)、模型配置、模板与本文件。历史实现按[交接日志](handoff.md)核对，不把早期“37项通过”“每日限额”“无真实调用”等描述当当前状态。恢复开发需要项目发起者明确重新启动，并先重新验证成本与核心使用场景。
