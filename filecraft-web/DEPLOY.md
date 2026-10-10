# filecraft-web 服务器部署手册（vibenav.xyz 服务器 · 方式 A：子域名 + 独立端口）

> 遵循 `D:\dev\DEPLOY-NEW-PROJECT.md` 的三条铁律：
> 不动 vibenav 的 Nginx 配置；监听 127.0.0.1:3100（不用 3000）；代码放 /var/www/filecraft。
> 出问题时删除新增文件即可回滚，主站毫发无损。

## 站点信息（2026-09-19 实际部署）

| 事项 | 值 |
|---|---|
| 地址 | `https://filecraft.vibenav.xyz` |
| 进程名 | `filecraft-web`（PM2，独立于 `vibenav`） |
| 端口 | `127.0.0.1:3100` |
| 代码目录 | `/var/www/filecraft` |
| 数据目录 | `/var/www/filecraft/data`（上传/转换结果/总结，7 天自动清理） |
| 日志 | `/var/log/filecraft-web/` |
| 服务器 | 112.124.36.195，Alibaba Cloud Linux 3（dnf 系） |
| 证书 | Let's Encrypt，2026-12-18 到期，certbot 定时续期 |

## ⚠ 重要现状（与原手册假设不同）

1. **vibenav.xyz 未备案**。阿里云边缘拦截外部 80 端口流量（Beaver 403 拦截页），
   主站因此一直跑在 8080。本站 https 正常，但 `http://` 入口和证书的 HTTP-01 续期受影响（见下）。
2. **vibenav.xyz 主域在权威 DNS（hichina）上原本没有任何 A 记录**——主站此前只能通过 `IP:8080` 访问。
   已添加 `filecraft` 子域 A 记录；建议再补 `@` → 112.124.36.195 让主域名可用。
3. **证书续期**：HTTP-01 验证走 80 端口，会被备案拦截，约 2026-11-18 起自动续期会失败。
   到期前二选一：① 完成备案；② 改用 DNS-01（需要阿里云 AccessKey，`certbot certonly --dns-... ` 或手动 `certbot renew --manual` 换 DNS TXT）。

## 部署步骤（已执行记录）

### 0. 前置（控制台操作，已完成）

- 阿里云 DNS A 记录：`filecraft` → 112.124.36.195
- 安全组放行 TCP 80 / 443 / 22（80 现在仅用于证书签发尝试与跳转，实际被备案拦截）

### 1. 本地打包（Windows，Git Bash）

```bash
cd /d/app/filecraft-web
tar -czf /tmp/filecraft-web.tar.gz \
    --exclude=data --exclude=.env --exclude=__pycache__ \
    --exclude=venv --exclude=.git \
    .
scp /tmp/filecraft-web.tar.gz root@112.124.36.195:/var/www/
```

### 2. 服务器安装（Alibaba Cloud Linux 3 · dnf 系）

```bash
# 2.1 Python 3.11 + TrueType 中文字体
#     注意：google-noto-sans-cjk 是 CFF 轮廓，reportlab 不支持，必须装文泉驿！
dnf install -y python3.11 python3.11-pip wqy-microhei-fonts

# 2.2 解压代码
cd /var/www && mkdir -p filecraft
tar -xzf filecraft-web.tar.gz -C filecraft && rm filecraft-web.tar.gz
cd filecraft

# 2.3 虚拟环境 + 依赖
python3.11 -m venv venv
venv/bin/pip install -r requirements.txt

# 2.4 环境配置（密钥只在服务器上，不进代码包）
cp .env.example .env && chmod 600 .env && vi .env

# 2.5 手动试跑
set -a; source .env; set +a
venv/bin/python server.py
curl -s http://127.0.0.1:3100/api/health   # {"ok":true,...} 即成功，Ctrl+C 停掉
```

### 3. 交给 PM2

```bash
mkdir -p /var/log/filecraft-web
cd /var/www/filecraft && pm2 start ecosystem.config.js
pm2 save
pm2 status        # vibenav 与 filecraft-web 都应 online
```

### 4. Nginx（新文件，不动旧的）

```bash
cp /var/www/filecraft/deploy/filecraft.conf /etc/nginx/conf.d/filecraft.conf
nginx -t && systemctl reload nginx
```

### 5. 签发 HTTPS 证书（服务器此前无任何证书，全新签发而非扩签）

```bash
dnf install -y certbot python3-certbot-nginx
certbot certonly --nginx -d filecraft.vibenav.xyz --non-interactive \
    --agree-tos --register-unsafely-without-email
# 证书落在 /etc/letsencrypt/live/filecraft.vibenav.xyz/
```

### 6. 验收清单（2026-09-19 全部通过）

| # | 检查项 | 结果 |
|---|---|---|
| 1 | `https://filecraft.vibenav.xyz` 证书链校验 | ✓ 无告警 |
| 2 | 上传 docx/pptx/xlsx/pdf → 批量转换 | ✓ 4/4 |
| 3 | AI 总结（真实模型，SSE 进度） | ✓ |
| 4 | 导出 PDF（服务器中文字体 wqy-microhei） | ✓ |
| 5 | 文档问答（真实模型） | ✓ |
| 6 | zip 打包下载 | ✓ |
| 7 | 主站回归 `IP:8080` | ✓ 302 正常 |
| 8 | `pm2 restart filecraft-web` 只影响新站 | ✓ |

## 7. 回滚 / 下线（不影响主站）

```bash
pm2 delete filecraft-web && pm2 save
rm /etc/nginx/conf.d/filecraft.conf
nginx -t && systemctl reload nginx
rm -rf /var/www/filecraft /var/log/filecraft-web
certbot delete --cert-name filecraft.vibenav.xyz   # 可选：删除证书
# （可选）删除 DNS 的 filecraft A 记录
```

## 8. 日常运维

```bash
pm2 logs filecraft-web --lines 50   # 看日志
pm2 restart filecraft-web           # 更新代码后重启
ls /var/www/filecraft/data/workspaces | wc -l   # 当前工作区数（7 天自动清理）
certbot certificates                # 查看证书状态（注意 11 月中旬续期问题）
```

更新版本：本地改完 → 重新打包上传解压（先 `pm2 stop filecraft-web`）→
依赖有变时 `venv/bin/pip install -r requirements.txt` → `pm2 start filecraft-web`。
桌面版 `core/` 有改动时，先在本地 `python sync_core.py` 再打包。
