<div align="center">

# FileCraft 文档转换

**把 Word / PPT / Excel / PDF 转成 Markdown，再交给大模型总结、问答、导出 PDF**

桌面版 · 网页版 · 微信小程序 · Android — 四端共享同一套核心引擎

</div>

---

## 这是什么

FileCraft 是一个文档处理工具集，核心能力就两件事：

1. **转 Markdown** — 导入 `.docx` / `.pptx` / `.xlsx` / `.pdf`，纯本地解析，保留标题层级、表格、分页等结构
2. **AI 总结与问答** — 勾选任意几份文档，生成结构化中文总结（总体概述 / 各文档要点 / 关键数据 / 风险提示），或像聊天一样多轮提问，回答只依据文档内容并注明出处

总结结果可编辑后导出为 **PDF**（中文字体、页码、页眉）或 **Markdown**，也能一键生成**思维导图**（离线渲染，浏览器直接打开）。长文本超限时自动分段总结再合并（map-reduce）。

## 四个端

| 子项目 | 端 | 技术栈 | 说明 |
|---|---|---|---|
| [`filecraft/`](filecraft) | 桌面 (Windows) | Python + PyQt6 | 原始版本，纯本地运行，文件解析全部在本地完成，只有 AI 调用需联网 |
| [`filecraft-web/`](filecraft-web) | 网页 | FastAPI + 原生 HTML/JS | 带账号系统与历史记录，后端直接复用桌面版 `core/` 模块 |
| [`filecraft-mp/`](filecraft-mp) | 微信小程序 | WXML/WXSS/JS（无框架） | 原生小程序客户端，后端复用 filecraft-web 的 FastAPI 服务 |
| [`filecraft-android/`](filecraft-android) | Android | WebView 壳（原生 Java） | 把网页版包成 APK 的全屏 WebView 壳，处理文件上传与 blob 下载 |

四端共享的 `core/` 模块包含：格式转换器（docx/pptx/xlsx/pdf → Markdown）、OpenAI 兼容的大模型调用、长文本 map-reduce 总结、文档问答引擎、Markdown → PDF 导出、思维导图生成。

## 快速开始

### 桌面版

```bash
cd filecraft
pip install -r requirements.txt
python main.py
```

首次使用前，在「工具 → 设置」中填入你自己的大模型 API Key（支持任意 OpenAI 兼容接口）。预设了 ModelScope、OpenAI、智谱 GLM、DeepSeek、Kimi、通义千问、本地 Ollama 等配置，选一个填 key 即可。

### 网页版

```bash
cd filecraft-web
python sync_core.py          # 从桌面版同步 core/ 模块
pip install -r requirements.txt
python server.py             # http://127.0.0.1:3100
```

配置走环境变量，参考 `.env.example`。测试账号 `demo` / `demo123`（首次启动自动创建并预置样例文档）。

### 微信小程序

1. 微信开发者工具 → 导入项目 → 目录选 `filecraft-mp` → 填入你的 AppID
2. 本地设置 → 勾选「不校验合法域名」
3. 编译，用 `demo` / `demo123` 登录

### Android

```bash
cd filecraft-android
bash build_apk.sh
# 产物：FileCraft-v1.0.0.apk
```

> Android 壳应用加载的是网页版，需先部署好 filecraft-web 服务。

## 功能一览

| 功能 | 说明 |
|---|---|
| 转 Markdown | 批量导入 docx/pptx/xlsx/pdf，保留标题层级、表格、分页、备注，输出同名 .md |
| AI 总结 | 多文件合并总结，支持额外要求（如"重点关注财务数据""800 字以内"），可编辑后导出 PDF / .md / 思维导图 |
| 文档问答 | 多轮提问，回答只依据文档内容，没有依据会明确说"文档中未提及"，可选注明出处 |
| 文件库 | 可视化文件夹树（多级嵌套），自动归档、文件移动、全文搜索（按文件名或内容） |
| 历史记录 | 总结与问答的全部调用自动存档，退出重开仍在；总结可还原到编辑器，问答可载入对话继续追问 |

## 支持的模型

任何 OpenAI 兼容接口均可使用：

| 服务商 | Base URL |
|---|---|
| ModelScope 魔搭 | `https://api-inference.modelscope.cn/v1` |
| OpenAI | `https://api.openai.com/v1` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
| DeepSeek | `https://api.deepseek.com/v1` |
| 月之暗面 Kimi | `https://api.moonshot.cn/v1` |
| 阿里通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 本地 Ollama | `http://localhost:11434/v1` |

也可以选「自定义」填任意兼容接口。

## 已知限制

- **不支持旧版 `.doc` / `.ppt` / `.xls`**，请先另存为 `.docx` / `.pptx` / `.xlsx`
- **不支持扫描件 PDF**，没有集成 OCR
- **Excel 公式**读取的是缓存计算结果而非公式本身
- **PDF 排版**提取纯文本流，多栏和图文混排可能丢失原始阅读顺序
- 总结质量取决于所配置的模型能力

## 项目结构

```
app/
├── filecraft/              # 桌面版（Python + PyQt6）
│   ├── core/               # 共享核心：转换器、总结、问答、PDF、思维导图
│   ├── ui/                 # PyQt6 界面
│   ├── main.py             # 入口
│   ├── selftest.py         # 冻结包自检（13 项）
│   ├── FileCraft.spec      # PyInstaller 打包配置
│   └── testdata/           # 4 种格式的样例文件
├── filecraft-web/          # 网页版（FastAPI）
│   ├── server.py           # API 路由 + 静态页入口
│   ├── store.py             # 工作区/文件存储
│   ├── auth.py              # 账号系统
│   ├── core/                # 从桌面版同步的核心模块
│   ├── static/              # 前端（无构建步骤）
│   ├── seed/                # 预置样例文档
│   └── deploy/              # Nginx 配置
├── filecraft-mp/           # 微信小程序
│   ├── pages/               # 登录/文件/总结/问答/我的/历史
│   ├── utils/               # API 请求、SSE、UTF-8 解码、富文本
│   └── components/          # 文档多选弹层
├── filecraft-android/      # Android WebView 壳
│   ├── src/                 # Java 源码
│   ├── res/                 # 资源与图标
│   └── build_apk.sh         # 免 Gradle 构建脚本
├── .gitignore
└── README.md
```

各子项目有独立的 README，包含详细的安装、配置、打包、部署说明。

## 技术选型

- **文件解析全部本地完成**：`python-docx`（Word）、`python-pptx`（PPT）、`openpyxl`（Excel）、`pdfplumber`（PDF），不依赖任何外部服务
- **PDF 导出用 reportlab**：通过 `pdfmetrics` 注册系统 TTF 字体，中文渲染最稳定，零外部运行库依赖。WeasyPrint 需要 GTK，xhtml2pdf 无法读取系统字体目录——reportlab 是 Windows 上最省心的方案
- **长文本 map-reduce**：按 `max_chars_per_chunk`（默认 10 万字符）切块，单块一次出结果，多块先逐块提取要点再合并
- **思维导图离线渲染**：markmap 内嵌，浏览器直接打开，滚轮缩放/点击折叠，不联网
- **网页安全**：HTML 经 nh3 白名单消毒防 XSS，单文件 40MB 上限，AI 调用按 IP 限流，监听 127.0.0.1 由 Nginx 反代

## License

MIT
