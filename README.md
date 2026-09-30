# AI Wardrobe Lab · 衣橱实验室

数字衣橱的私人 API 测试平台。白底、暖橙色、手机适配界面；用相同素材验证多图穿搭、商品图整理和动态展示，并记录提示词版本、实际费用与人工质量评分。

[桌面界面](docs/screenshots/desktop-studio.png) · [手机界面](docs/screenshots/mobile-studio.png)（截图为模拟工作流，非真实AI效果）

## 当前已实现

- 创作台、素材库、模板与提示词、技能工作流、测试记录、结果对比、平台连接七个页面。
- 按角色上传人物、姿势、上衣、下装、鞋子、配饰、背景、完整穿搭图和动作视频。
- 固定后端工作流：校验 → 生成 → 保存 → 人工确认；图片确认合格后另建视频任务，复用图片。
- SQLite 持久化、幂等创建、模型/模板/素材快照、重启恢复、提交不确定保护、仅重试文件保存。
- 可版本化模板，原生多图与确定性参考板对照；生成前预览真实供应商请求结构。
- 九个模型档案、八类请求适配器，覆盖火山方舟、阿里百炼、腾讯 TokenHub 和 Vidu 国内。
- 私人访问密码、后端凭证、短期签名素材链接、输出转存和下载、CSV/JSON 实验导出。
- 默认零费用模拟。模拟图片是素材参考卡，模拟视频是静态帧，均不是实际 AI 效果。
- GitHub CI 与手动触发 SSH 部署、健康检查及上一版本回退脚本。

## 接入状态

|平台|模型/接口|当前状态|
|---|---|---|
|火山方舟|Seedream 多图、Seedance 首帧|请求适配与模拟契约测试；账号权限和结果待实测|
|阿里百炼|Qwen Image Edit Plus、万相2.6 Flash、万相Animate|请求适配与模拟契约测试；账号权限和结果待实测|
|腾讯 TokenHub|可灵V3首帧/动作控制、MiniMax H3首帧/多模态参考|请求适配与模拟契约测试；账号权限和结果待实测|
|Vidu 国内|Vidu2.0参考生视频保守档案|请求适配与模拟契约测试；新型号需新增能力档案|

**代码接入不等于已通过真实 API 验收。当前未执行任何付费模型调用。** 模型价格、账号可用型号、审核条件、结果保真与成功率须使用自己的授权素材逐个验证。供应商文档和接入清单见 [docs/providers.md](docs/providers.md)。

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
python -m pytest tests/test_backend.py -q
playwright install chromium
python -m pytest tests/test_ui.py -q
```

## 部署到腾讯轻量云

使用 Ubuntu Server 24.04 LTS、Docker Compose 和 Caddy。完整步骤、GitHub Secrets、域名/HTTPS、首次启动和回退说明见 [docs/deployment.md](docs/deployment.md)。已完成轻量云实际构建和启动，本机网页HTTP 200；外部80端口连接超时，需检查腾讯防火墙访问规则。部署采用源码上传、服务器本地构建和腾讯软件源，常规部署手动触发。

## 设计与边界

- [docs/architecture.md](docs/architecture.md)：任务状态、技能、模型适配、隐私及成本口径。
- [docs/test-plan.md](docs/test-plan.md)：阶段0～4、故障测试、质量验收与实测记录。
- [docs/handoff.md](docs/handoff.md)：实施结果、验证结果与待完成事项。
- 产品依据：2026-09-30《AI数字衣橱 产品技术与商业设计文档 v0.4》。本仓库实现测试台，不实现完整衣柜 App、账号支付或订阅系统。

模型凭证仅通过服务器 `.env` 提供，网页不存 Key。工作流由本服务器执行；百炼/腾讯的托管工作流可在后续作为适配节点加入。自拍拆衣、专用 Aidge 试穿、视觉AI评分、真实3D与Seedance真人资产授权录入均标为后续能力，不以空按钮假装已经实现。
