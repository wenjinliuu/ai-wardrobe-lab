# AI 数字衣橱 · 设计文稿阶段附录
## TAT 接入研究与测试记录

记录日期：2026-10-01（北京时间）；覆盖 2026-09-30 至 10-01 凌晨的讨论与测试。
配套主文稿：《AI数字衣橱_产品技术与商业设计文档_v0.4》。本附录只记录 TAT 接入研究；不改动衣柜业务、收费或生成模型设计。按用户最新确认，TAT 部分作为独立阶段附录保存。目前暂停进一步接入。

### 1. 目的与当前状态

测试网站已经部署并能进入。希望研究 TAT 作为服务器运维和部署通道，减少 GitHub 执行节点通过 SSH 连接服务器产生的海外登录告警与跨境传输问题。这是运维能力，不是衣柜图片、视频或 3D 生成工作流的一环。

当前没有完成 TAT 接入验收，不能写为“已通过 TAT 部署”或“ChatGPT 已能通过 TAT 管理服务器”。现有网站和既有部署方式未迁移到 TAT。

### 2. TAT、MCP 与两种接法

TAT 是腾讯云自动化助手，提供在实例上运行命令并查询结果的 API。MCP 是供 AI 客户端使用这些工具的接口层。

官方详情页链接源码项目：https://github.com/jubaoliang/mcp-server-tat 。已读取 server.py：使用 Python 与 stdio transport；提供 SyncRunCommand、RunCommand、QueryTask 三个工具。工具列表为静态定义，真正执行工具时才创建腾讯 SDK 客户端并调用 TAT API。公开源码不包含腾讯 MCP 广场的专属 SSE 托管层。不能据此确认托管平台内部日志或实际部署版本。

详情页存在两种接法：
- 本地接法：把含 command、args、env 的配置放入 Claude Desktop 配置文件，客户端在本地启动 MCP 进程。
- 云托管接法：在“连接服务”填写参数，点击“连接 Server”，获得含 type=sse 与 url 的远程连接配置。

所谓“集成代码”在这里是客户端连接配置，不是需要贴到 GitHub 或轻量云终端执行的业务代码。当前尝试的是云托管接法。

### 3. 已完成的准备

已创建用于本次测试的 CAM 子用户 wardrobe-tat，选择编程访问，关联 QcloudTATFullAccess，并在腾讯官方页面填写凭据与地域。凭据值不进入文稿、仓库或截图记录。

配置字段：TENCENTCLOUD_SECRET_ID、TENCENTCLOUD_SECRET_KEY、TENCENTCLOUD_REGION。前两项为同一对 CAM API 凭据；第三项必须依据实例实际地域填写。上海代码为 ap-shanghai，但实例地域仍应以控制台或 API 查询确认，不把此前推测当作已验收结论。

腾讯页面返回了专属 SSE 配置。ChatGPT 创建 MCP 应用时显示通用的“无法创建 MCP 应用。请重试。”，没有给出更具体的协议或鉴权错误。该错误不能单独证明密钥错误、网络封锁或某种协议必定不支持。

### 4. 实际连接诊断

已通过 Cloudflare 插件部署独立的临时诊断 Worker，验证 Worker 可以访问，并尝试连接专属 SSE 地址。探针只允许连接、初始化和加载工具定义，不执行 tools/call。

早期两轮在 20 秒等待上限内均超时。随后增加同源控制请求，并延长专属连接的等待上限：

| 请求 | 默认请求头对照轮 | 增加明确 User-Agent 的对照轮 |
| --- | --- | --- |
| 腾讯 MCP 域名首页 | HTTP 404，760 ms | HTTP 404，1177 ms |
| 一个无效 SSE 地址 | HTTP 404，743 ms | HTTP 404，1203 ms |
| 用户专属 SSE 地址 | 45000 ms 超时，没有响应头 | 20001 ms 超时，没有响应头 |

两个 404 属于控制请求的预期结果，说明该测试路径能从腾讯 MCP 域名获得 HTTP 响应。测试 Worker 自身返回 HTTP 200。专属连接没有得到响应头或 SSE endpoint 事件，因而未进入 initialize、tools/list，更没有执行轻量云命令。

### 5. 可确认的结论与未确认项

可确认：Cloudflare 到该域名的普通 HTTPS 访问可用；故障集中在专属 SSE 路由及其后续处理。延长到 45 秒及增加 User-Agent 都未使此连接成功。

尚未确认：托管会话是否失效、服务是否启动失败、专属路由是否存在访问策略或其他后台问题。现有结果不能证明轻量云防火墙、CAM 密钥或实例 TAT Agent 有故障，也不能证明这些配置已经通过验收。

腾讯“大模型＋MCP”体验馆可以打开、选择 TAT 并显示示例问题，但截图没有实际握手、工具加载或调用成功证据，不能作为专属地址的连通性验收。

临时 Worker 已删除。现有两个 CloudBase Worker 没有改动；未执行服务器命令，也未调用付费图片、视频或 3D 模型。

### 6. 保留的候选方案

方案 A：继续核查腾讯云托管 MCP，取得最新连接结果后重复有限的对照测试；若仍失败，需要腾讯托管平台的后台诊断。当前未完成。

方案 B：GitHub Actions 直接调用官方 TAT API 完成服务器部署，不依赖 ChatGPT 的 MCP 连接。需要另外验证地域、权限、Agent 在线状态、命令任务查询、超时与回滚。当前仅为候选，未替换现有部署。

方案 C：利用源码自管 MCP，或实现直接调用官方 TAT API 的 MCP HTTP 服务。需要补充远程 HTTP 通信、鉴权与部署管理。原始 stdio Python 程序不能当作现成的 HTTP Worker 上传。当前仅为候选，未实现或部署。

两类目标分别验收：AI 客户端能够管理服务器，不等于 GitHub 自动部署已完成；GitHub 能使用 TAT 部署，也不要求先连接 MCP。

### 7. 暂停与恢复条件

当前暂停 TAT、SSE 转接和新连接器工作。不会因本附录更新而重跑部署、重建密钥或继续修改服务器。

恢复时先确认目标是自动部署还是 AI 运维；再使用已确认地域与受控凭据做最小验证。连接测试成功后才进行实例状态检查和经授权的最小命令测试。正式部署通道需要通过完整的发布、健康检查和失败恢复验收，不能以页面显示“连接成功”替代。

### 8. 参考与证据

- 官方 TAT MCP 详情：https://cloud.tencent.com/developer/mcp/server/11729
- MCP 广场使用说明：https://cloud.tencent.com/document/product/1212/123193
- 源码：https://github.com/jubaoliang/mcp-server-tat
- 已保存的连接对照记录：https://github.com/wenjinliuu/cloudbase-mcp-worker/blob/tat-connectivity-probe/diagnostics/tat-probe/diagnosis-2026-10-01.md

本附录不包含 SecretKey、完整专属 SSE 地址、网页密码或 SSH 私钥。
