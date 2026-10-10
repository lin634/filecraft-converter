# FileCraft Web

桌面版 [FileCraft](../filecraft) 的网页版：登录后上传 Word / PPT / Excel / PDF，
转成 Markdown、AI 总结（可编辑后导出 PDF / 思维导图）、基于文档的多轮问答。
带账号系统与历史记录（总结历史 / 问答会话历史，每账号独立）。

后端 FastAPI 直接复用桌面版的 `core/` 模块（转换器、总结、问答、PDF、思维导图），
前端为无构建步骤的原生 HTML/JS。文件与历史按账号隔离，7 天自动清理。

## 测试账号（首次启动自动创建，存于 data/accounts.json）

| 账号 | 密码 | 说明 |
|---|---|---|
| `demo` | `demo123` | 演示账号，首次启动自动预置 4 份样例文档（已转换） |
| `test1` | `test123456` | 空白账号，可直接使用 |
| `test2` | `test123456` | 空白账号，可直接使用 |

账号定义在 `auth.py` 的 `TEST_ACCOUNTS`，改后删除服务器上的
`data/accounts.json` 重启即可重建。

## 本地开发

```bash
cd D:\app\filecraft-web
python sync_core.py        # 桌面版 core/ 有改动后，先同步过来
python -m pip install -r requirements.txt
python server.py           # http://127.0.0.1:3100
```

端到端自测（需先启动 server，会真实调用大模型接口）：

```bash
python selftest_web.py
```

配置全部走环境变量（见 `.env.example`）；不设则用与桌面版一致的内置默认值。

## 功能

| 页签 | 说明 |
|---|---|
| 转 Markdown | 批量转换 docx/pptx/xlsx/pdf，在线预览、单个下载、打包 zip |
| AI 总结 | 勾选多份已转换文档 → SSE 实时进度 → 结果可编辑 → 导出 PDF / .md / 思维导图 HTML |
| 文档问答 | 围绕勾选文档多轮提问，回答只依据文档内容并注明出处 |

安全措施：渲染 HTML 经 nh3 白名单消毒（防文档内嵌脚本 XSS）；单文件 40MB 上限；
每 IP 每小时 AI 调用限流（默认 30 次）；监听 127.0.0.1，由 Nginx 反代对外。

## 部署

见 [DEPLOY.md](DEPLOY.md)（vibenav.xyz 服务器，子域名 filecraft.vibenav.xyz，
PM2 进程 `filecraft-web`，端口 3100）。

## 目录结构

```
filecraft-web/
├── server.py              # FastAPI：API 路由 + 静态页（入口）
├── config.py              # 环境变量配置（提供 core 需要的 LLMConfig）
├── store.py               # 工作区/文件存储（会话隔离、TTL 清理）
├── core/                  # 桌面版核心（sync_core.py 同步，勿手改）
├── assets/markmap/        # 思维导图离线渲染脚本（同步）
├── static/                # 前端（index.html / app.js / style.css）
├── selftest_web.py        # 端到端自测（21 项）
├── ecosystem.config.js    # PM2 配置
├── deploy/filecraft.conf  # Nginx 配置
├── .env.example           # 生产环境配置模板
└── DEPLOY.md              # 部署手册
```
