# FileCraft 微信小程序

[FileCraft](../filecraft)（桌面版）/[filecraft-web](../filecraft-web)（网页版）的微信小程序版：
上传 Word / PPT / Excel / PDF → 转 Markdown → AI 总结（实时进度、可编辑、导出 PDF）→
基于文档的多轮问答，含总结历史与问答会话历史。

**原生小程序客户端**（WXML/WXSS/JS，无框架、无构建步骤），后端直接复用
[filecraft-web](../filecraft-web) 的 FastAPI 服务（默认
`https://filecraft.vibenav.xyz`），文件解析与大模型调用全部在服务器完成。

## 功能对照

| Tab | 功能 |
|---|---|
| 文件 | 上传（从微信聊天记录选文件）、按名搜索、勾选批量转换 / 删除、预览 Markdown（渲染/原文）、系统预览原文件（pdf/docx/xlsx/pptx） |
| AI 总结 | 多选文档 → 额外要求 → 开始总结（分段 SSE 实时进度，可取消）→ 结果可编辑 → 渲染预览 → 导出 PDF / 存入历史 / 复制 |
| 问答 | 多选文档 → 多轮提问（回答只依据文档并注明出处）→ 会话历史载入 / 长按删除 |
| 我的 | 账号信息、总结历史、问答历史、关于、退出登录 |

## 使用前提

1. **微信开发者工具**（最新稳定版）：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html
2. **一个小程序 AppID**：个人主体免费注册即可（mp.weixin.qq.com）。没有也可以先用
   「测试号」体验，本项目 `project.config.json` 里的 `appid` 已填 `touristappid`
   占位，导入时换成你自己的即可。

## 导入运行（3 步）

```
1. 微信开发者工具 → 导入项目 → 目录选择 D:\app\filecraft-mp → 填入你的 AppID
2. 右上角「详情 → 本地设置」→ 勾选「不校验合法域名、web-view（业务域名）、
   TLS 版本以及 HTTPS 证书」（开发期临时绕过域名校验）
3. 编译 → 用 demo / demo123 登录（服务器预置了 4 份样例文档，可直接体验）
```

## 上线前：配置服务器合法域名

登录 [mp.weixin.qq.com](https://mp.weixin.qq.com) → 开发管理 → 开发设置 →
服务器域名，把 `https://filecraft.vibenav.xyz` 同时加进这三类（都要）：

- **request 合法域名**（列表/转换/总结/问答/导出 PDF）
- **uploadFile 合法域名**（上传文件）
- **downloadFile 合法域名**（下载原文件预览）

要求：HTTPS、已备案（个人主体也可用自己的已备案域名；`vibenav.xyz` 已满足）。
配置好后即可真机预览 / 提交审核发布。

## 本地后端联调

```
1. 启动本地 filecraft-web：cd D:\app\filecraft-web && python server.py
2. 把 config.js 的 BASE_URL 改为 http://127.0.0.1:3100
3. 开发者工具保持「不校验合法域名」勾选
```

## 测试账号（服务器预置）

| 账号 | 密码 | 说明 |
|---|---|---|
| `demo` | `demo123` | 预置 4 份样例文档（已转换） |
| `test1` / `test2` | `test123456` | 空白账号 |

## 实现说明

- **会话鉴权**：后端用 `fc_auth` Cookie；小程序不会自动管理 Cookie，
  登录后把 sid 存 Storage，之后每次请求手动带 `Cookie: fc_auth=<sid>` 头
  （见 `utils/api.js`）。401 全局拦截 → 自动跳登录页。
- **上传**：`wx.chooseMessageFile` 从微信聊天记录选文件（这是小程序获取
  任意文件的唯一途径；`extension` 过滤**不带点**且安卓端大小写敏感，两种
  写法都传了）。选中后先 `copyFile` 到用户目录、以原始文件名命名再
  `wx.uploadFile`，保证服务端收到的 multipart filename 是真实文件名。
- **AI 总结进度**：`wx.request({enableChunked: true})` 分段接收 SSE，
  `onChunkReceived` + 自实现流式 UTF-8 解码（`utils/utf8.js`，处理跨块
  多字节截断）；分段不可用的环境自动退化为按完整 body 解析（`utils/sse.js`）。
- **Markdown 渲染**：服务端返回 nh3 消毒后的 HTML，`utils/rich.js` 给常见
  标签注入内联样式（rich-text 不认 class），交给 `<rich-text>` 展示。
- **导出 PDF**：`/api/export/pdf` 以 `responseType: 'arraybuffer'` 接收
  二进制 → 写入用户目录 → `wx.openDocument` 预览/分享。
- **超时**：`app.json` 的 `networkTimeout` 放大到 300s（长文档分段总结较慢）。
- **限流**：沿用服务端限制——AI 调用每账号 30 次/小时，登录 10 次/小时/IP。

## 目录结构

```
filecraft-mp/
├── project.config.json        # appid 占位 touristappid，导入时替换
├── app.json                   # 页面/tabBar/网络超时
├── app.js                     # 401 全局拦截、服务健康探测
├── config.js                  # BASE_URL（唯一需要改的配置）
├── make_icons.py              # tabBar 图标生成脚本（PIL）
├── assets/tab/                # 8 张 tabBar 图标
├── utils/
│   ├── api.js                 # 请求/上传/下载 + Cookie 鉴权
│   ├── sse.js                 # 总结 SSE（分段优先、全量兜底）
│   ├── utf8.js                # 流式 UTF-8 解码（跨块安全）
│   ├── rich.js                # HTML → rich-text 内联样式
│   └── fmt.js                 # 大小/时间/扩展名展示
├── components/file-picker/    # 文档多选弹层（总结/问答共用）
└── pages/
    ├── login/                 # 登录
    ├── files/                 # 文件：上传/转换/删除/预览
    ├── summary/               # AI 总结：进度/编辑/导出
    ├── qa/                    # 文档问答：聊天 + 会话历史
    ├── me/                    # 我的：入口 + 退出
    ├── history/               # 总结历史 / 问答历史
    └── doc-view/              # Markdown 详情（渲染/原文/导出 PDF）
```

## 已知限制

- **选文件依赖聊天记录**：小程序沙盒里没有系统文件管理器，`docx` 等文件
  需先通过任意聊天（如「文件传输助手」）发送到手机再选取——微信平台规则，
  所有同类小程序均如此。
- **不支持思维导图导出**：小程序无法直接打开服务器生成的 HTML，如需思维
  导图请用网页版。
- **总结进度**：极少数旧基础库不支持分段接收时，进度退化为「等待模型响应…」
  一次提示，结果不受影响。
- **扫描件 PDF / 老格式**：与桌面版一致，不支持 OCR 与 `.doc/.ppt/.xls`。
- **服务器保留 7 天**：文件与历史按账号隔离，超期自动清理（服务端策略）。
