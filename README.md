# AI Wardrobe Lab · 衣橱实验室

> **项目已冻结（2026-10-02，北京时间）。** 保留代码、设计和测试成果，暂停开发与付费评测。高频换搭配的核心需求，与当前图像/视频生成的成本及一致性约束仍冲突。详见[冻结决策与阶段结论](docs/project-freeze-2026-10-02.md)。本次仅归档文档，没有停服、删除运行数据或将GitHub仓库设为只读。

## 冻结交接入口

- [产品设计快照](docs/product-design-snapshot.md)：总体用户流程、个人形象、素材角色、模板、评测和商业边界。
- [完整v0.5设计存档](docs/product-design-v0.5-archive.md)：原27页设计正文，含数据模型、Skills、订阅假设与3D规划；价格和旧状态是历史记录。
- [技术架构与代码交接](docs/architecture.md)：模块、接口、任务状态、费用、持久化、部署和未完成问题。
- 最后成功部署代码：`21633039abf6ac25e1f35e73498fd82ecf119dde`；[部署与311项自动验证证据](https://github.com/wenjinliuu/ai-wardrobe-lab/actions/runs/36910724564)。自动测试不代表真实模型质量验收。

数字衣橱的私人 API 测试平台。白底、暖橙色、手机适配界面；用相同素材验证多图穿搭、商品图整理和动态展示，并记录提示词版本、实际费用与人工质量评分。

[桌面界面](docs/screenshots/desktop-studio.png) · [手机界面](docs/screenshots/mobile-studio.png)（截图为模拟工作流，非真实AI效果）

## 当前已实现

- 个人形象、创作台、素材库、模板与提示词、技能工作流、测试记录、结果对比、平台连接八个页面。
- 按角色上传人物、姿势、上衣、下装、鞋子、配饰、背景、完整穿搭图和动作视频。
- 固定后端工作流：校验 → 生成 → 保存 → 人工确认；图片确认合格后另建视频任务，复用图片。
- SQLite 持久化、幂等创建、模型/模板/素材快照、重启恢复、提交不确定保护、仅重试文件保存。
- 可版本化模板，原生多图与确定性参考板对照；生成前预览真实供应商请求结构。
- 79个模型档案、6个渠道，包含火山方舟、阿里百炼、腾讯TokenHub、MiniMax原厂、可灵原厂和Vidu；按输入模式提供图片、视频、音频、文档、授权资产ID入口。
- 私人访问密码、后端凭证、短期签名素材链接、输出转存和下载、CSV/JSON 实验导出。
- 默认零费用模拟。模拟图片是素材参考卡，模拟视频是静态帧，均不是实际 AI 效果。
- GitHub CI 与main相关代码更新自动/手动 SSH 部署、健康检查及上一版本回退脚本。

## 接入状态

完整的逐渠道/逐模型能力、价格、真人授权流程与尚未开放入口见[接入核对文档](docs/provider-integration-2026-09-30.md)。页面的平台连接也展示每个模型的能力与官方来源。

**代码接入不等于全部真实 API 验收。用户已反馈腾讯TokenHub真实调用成功；自动测试不运行付费调用，其它渠道与全部型号并未完成统一效果/账单验收。** 模型价格、账号可用型号、审核条件、结果保真与成功率须使用自己的授权素材逐个验证。供应商文档和接入清单见 [docs/providers.md](docs/providers.md)。

## 本地运行

需要 Python 3.12、FFmpeg（含 ffprobe）。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
LAB_DEV_MODE=true uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

打开 `http://127.0.0.1:8000`。本地开发模式仅允许回环地址免登录，不可在公网开启。Windows PowerShell 可用 `$env:LAB_DEV_MODE='true'`，启动命令相同。

```bash
python -m pytest tests/test_backend.py tests/test_contracts.py -q
playwright install chromium
python -m pytest tests/test_ui.py -q
```

## 部署到腾讯轻量云

使用 Ubuntu Server 24.04 LTS、Docker Compose 和 Caddy。完整步骤、GitHub Secrets、域名/HTTPS、首次启动和回退说明见 [docs/deployment.md](docs/deployment.md)。扩展版已在轻量云实际构建和启动，公网HTTP健康检查通过。部署采用源码上传、服务器本地构建和腾讯软件源，模型扩展后对main相关代码更新自动部署，也可手动启动。

## 设计与边界

- [docs/architecture.md](docs/architecture.md)：任务状态、技能、模型适配、隐私及成本口径。
- [docs/test-plan.md](docs/test-plan.md)：阶段0～4、故障测试、质量验收与实测记录。
- [docs/handoff.md](docs/handoff.md)：实施结果、验证结果与待完成事项。
- 产品依据：《AI数字衣橱 产品技术与商业设计文档 v0.5》及后续讨论，见仓库历史存档与冻结快照。本仓库实现测试台，不实现完整衣柜 App、账号支付或订阅系统。

模型凭证仅通过服务器 `.env` 提供，网页不存 Key。工作流由本服务器执行；百炼/腾讯的托管工作流可在后续作为适配节点加入。自拍拆衣、专用 Aidge 试穿、视觉AI评分、真实3D均为后续能力；Seedance授权Asset ID录入已提供，但创建/扫码授权须在方舟官方完成，不以空按钮假装已经实现。
