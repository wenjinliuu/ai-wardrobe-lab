# 腾讯轻量云部署

已连接实例并完成网络对照诊断；采用源码上传、服务器构建。建议 Ubuntu Server 24.04 LTS 64位；已有数据的实例不要直接重装。公网建议使用有条件部署的域名和HTTPS，国内实例使用域名时先确认备案和腾讯接入条件。

## 1. 服务器准备

安装 Docker Engine 与 Compose 插件，参考 [Docker 官方 Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/)。GitHub只上传源码；轻量云Docker构建内使用腾讯Debian及PyPI软件源，保留TLS和包签名校验。基础Python镜像和Caddy继续使用服务器现有Docker镜像配置。CI构建默认使用官方源，腾讯源由服务器部署脚本显式开启。

创建部署用户、项目目录与单独的数据目录：

```bash
sudo adduser --disabled-password --gecos '' deploy
sudo usermod -aG docker deploy
sudo install -d -o deploy -g deploy /opt/wardrobe-lab
sudo install -d -o deploy -g deploy /opt/wardrobe-lab/releases /opt/wardrobe-lab/shared
sudo install -d -o 10001 -g 10001 /opt/wardrobe-lab/shared/data
```

Docker组具备较高系统权限，只供部署使用。部署账号需要SSH公钥登录；配置完成后重新登录使Docker组生效。现有80/443端口如已被其他服务占用，先整合反向代理，不能盲目停止现有服务。

将仓库 `.env.example` 复制为 `/opt/wardrobe-lab/shared/.env`，权限600，owner为deploy。设置：

- `LAB_PASSWORD`：至少12位的私人访问密码。
- `LAB_SESSION_SECRET`：至少32位随机字符串，可通过 `openssl rand -hex 32` 生成。
- `LAB_DEV_MODE=false`：公网必须保持关闭。
- `LAB_LIVE_ENABLED=false`：先跑模拟验收，之后再主动开启。
- `CADDY_SITE`：指向该实例的域名，例如 `lab.your-domain.cn`。
- `LAB_PUBLIC_BASE_URL`：对应完整HTTPS地址，例如 `https://lab.your-domain.cn`。
- `LAB_DATA_PATH=/opt/wardrobe-lab/shared/data`。
- `LAB_ENV_FILE=/opt/wardrobe-lab/shared/.env`。
- `ARK_API_KEY`、`DASHSCOPE_API_KEY`、`TOKENHUB_API_KEY`、`VIDU_API_KEY`：按需填写，未配置的平台仍可跑模拟。

不要把示例占位密码直接用于公网。不要将真实 `.env` 放进GitHub，也不要让访问日志记录签名素材链接。

只有IP时，临时可将 `CADDY_SITE=:80` 和 `LAB_PUBLIC_BASE_URL=http://服务器IP` 用于模拟验证。涉及自拍、密码传输和动作视频取材前，应配置HTTPS；当前动作接口在真实模式要求HTTPS公网素材地址。Caddy会对正确指向服务器的域名自动申请证书，需要80/443可达。

## 2. GitHub Secrets

在仓库 **Settings → Secrets and variables → Actions → Repository secrets** 添加：

|Secret|填写内容|
|---|---|
|LIGHTHOUSE_HOST|服务器公网IP或部署域名|
|LIGHTHOUSE_USER|`deploy`|
|LIGHTHOUSE_PORT|SSH端口，一般22|
|LIGHTHOUSE_SSH_KEY|专用部署私钥，含完整BEGIN/END行|
|LIGHTHOUSE_KNOWN_HOSTS|经过核对的服务器SSH主机公钥记录|

SSH公钥放进部署用户的 `~/.ssh/authorized_keys`，私钥只放GitHub Secret。主机公钥记录应从腾讯控制台终端读取该实例的主机公钥并核对指纹，再形成known_hosts内容；默认22端口格式为 `IP ssh-ed25519 公钥`，非默认端口使用 `[IP]:端口`。不要把运行时未验证的ssh-keyscan结果直接当作可信身份。

## 3. 执行部署

仓库 Actions → **Deploy to Tencent Lighthouse** → Run workflow → main。

常规部署手动触发。此次修复暂时允许部署工作流文件的main提交自动触发，以完成已授权的首次验证；验证后移除此触发。流程先执行测试，核对SSH及部署锁，仅传源码包，清理三个已知失败上传目录，再在服务器构建并启动服务。SSH每15秒保活，服务器构建与部署限时15分钟。日志保存在release的deploy.log；工作流最后从公网检查/healthz。

`cleanup-old-uploads.py`仅检查c8121eff、905f2bf、571d6575三个已知失败版本，保护current链接及现有Compose容器关联的版本；部署锁被占用时中止清理。shared/.env、数据、SSH授权、其他版本和Docker缓存不清理。未新增镜像仓库或凭证。

镜像使用提交SHA命名，环境与数据存放在shared目录。Docker构建成功后更新服务，健康检查通过才更新current链接；失败时恢复上一release和对应镜像。第一版没有上一版本时需根据日志修复后重部署。当前数据库结构仅使用CREATE IF NOT EXISTS；未来涉及不可逆数据库迁移时，需要另加备份与兼容迁移方案，不能依赖代码回退恢复数据库。

## 4. 验收与运维

1. 打开网页，私人密码登录。
2. 载入示例素材，运行模拟图片，人工评为合格。
3. 点击生成动态展示，测试播放、拖动与下载。
4. 在测试记录检查任务ID、素材哈希、模板版本和零模型费用。
5. 使用模拟故障选项，检查生成失败、提交不确定、保存失败仅重试保存。
6. 配置某一家Key，核对模型权限和参数后，开启LIVE并只进行少量真实测试。

查看服务状态：

```bash
cd /opt/wardrobe-lab/current
export LAB_APP_IMAGE="wardrobe-lab:$(basename "$(readlink -f /opt/wardrobe-lab/current)")"
docker compose --env-file /opt/wardrobe-lab/shared/.env -p wardrobe-lab ps
docker compose --env-file /opt/wardrobe-lab/shared/.env -p wardrobe-lab logs --tail=100 app
```

备份shared数据目录和.env；SQLite在线备份使用SQLite backup API，不能在写入时只复制单个数据库文件而忽略WAL。版本回退优先使用已保留release运行部署脚本。不要删除仍用于回退的镜像。

## 5. TAT替代路线

当前实现并验证的是SSH部署脚本结构，实际服务器部署待配置。TAT是后续替换部署传输的候选：Actions发布安装包到受控存储，腾讯TAT下发固定下载/部署命令，再查询执行状态。需要配置TAT客户端、最小权限CAM凭证及安装包下载渠道。不要把未实现的TAT或MCP接入描述为已完成；它们不影响本项目AI生成工作流。

## 历史故障与排查

见[network-diagnosis.md](network-diagnosis.md)。最初在服务器下载Debian官方源很慢，等待期间SSH Broken pipe/255；后来整包上传也只有约24KiB/s。三种SSH传输对照都慢，而腾讯软件源约4.3MiB/s。因此移除整包上传和预加载镜像包流程，回到只传代码并使用腾讯软件源，保留SSH保活。诊断工具仍可手动运行，不会部署应用或安装依赖。
