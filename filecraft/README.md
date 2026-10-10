# FileCraft

本地文档处理工具：把 Word / PPT / Excel / PDF 转成 Markdown，并把选中的若干文件交给大模型总结、导出 PDF。

纯 Python + PyQt6 桌面程序，文件解析全部在本地完成，只有「AI 总结」需要联网调用你配置的大模型接口。

## 功能

**① AI 总结并导出 PDF**
- 勾选任意几个已导入的文件，生成一份结构化中文总结
- 总结按「总体概述 / 各文档要点 / 关键数据 / 风险提示」组织，可在界面上直接编辑
- 支持填写额外要求（如"重点关注财务数据""800 字以内"）
- 内容超出单次输入上限时自动分段总结再合并（map-reduce）
- 可导出为 PDF（含中文字体、页码、页眉），也可存成 `.md` 或一键生成思维导图

**② 转 Markdown**
- 导入 `.docx` / `.pptx` / `.xlsx` / `.pdf`，可多选，也可直接把文件或文件夹拖进窗口
- 勾选任意文件批量转换，输出同名 `.md`
- 输出目录可自选，留空则与源文件同目录
- Word 的标题层级与表格、PPT 的每页文本与备注、Excel 的每个工作表、PDF 的分页文本与表格都会被保留

**④ 文档问答**
- 勾选任意几个文件，像聊天一样多轮提问（"第三季度毛利率是多少？"）
- 回答只依据文件内容，没有依据会明确说"文档中未提及"，可选注明出处
- 上下文超长时自动按比例截断并提示

**③ 文件库**
- 可视化文件夹树，支持**多级嵌套**：在任意选中的文件夹下还能继续新建子文件夹
- 导入页有「归档到」下拉框（列出全部层级的文件夹），也可在文件库里选中文件夹作为默认位置
- 文件可以在文件夹之间**移动**（「移动到…」），同名同大小自动跳过、同名不同大小自动改名
- 由某文件夹内文件生成的总结，自动存到该文件夹的「总结」子夹——总结与来源文件始终对应
- 自动归档是复制副本、不动原文件；两个开关均可关闭后手动归档
- **全文搜索**：按文件名或文件内容搜整个文件库（docx/pptx/xlsx/pdf 现场解析文本）；超大文件（>30MB）跳过、PDF 只解析前 50 页
- 选中 .md 文件可一键生成**思维导图**（离线渲染，浏览器直接打开，滚轮缩放/点击折叠）
- 文件夹须清空后才能删除；文件库位置可整体更换；所有配置与本机文件随重启保留

## 安装

需要 Python 3.10+。

```bash
cd D:\app\filecraft
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

**首次使用前需在「工具 → 设置」中填入自己的 API Key**（Base URL 已预设好，只需填 Key）。接口为 OpenAI 兼容格式，内置以下预设：

| 服务商 | Base URL | 示例模型 |
|---|---|---|
| ModelScope 魔搭（默认） | `https://api-inference.modelscope.cn/v1` | `deepseek-ai/DeepSeek-V4.1-Flash` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-plus` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 月之暗面 Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 阿里通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 本地 Ollama | `http://localhost:11434/v1` | `llama3` |

也可以选「自定义」，填任意 OpenAI 兼容接口。密钥保存在 `%USERPROFILE%\.filecraft\config.json`，只存在本机。

## 打包为 exe

双击 `build.bat` 即可。它调用的是 `FileCraft.spec`（不是纯命令行参数），因为 spec 里显式指定了 Qt6 核心 DLL、平台插件和 MSVC 运行库——PyInstaller 默认的 PyQt6 钩子会漏掉这些，漏掉的 exe 在开发机上能跑（偷偷借用本机 Python 的 Qt），换台电脑就启动失败。

产物 `dist\FileCraft.exe` 约 88 MB，单文件自包含。

**验证打包结果**

GUI 程序没有控制台，打包后如果缺模块只会静默崩溃。所以内置了自检模式：

```bash
dist\FileCraft.exe --selftest report.txt
```

它会在冻结环境里真实走一遍四种格式转换和 Markdown 导出 PDF（含中文字体反解校验），把结果写进 `report.txt`。**文档自动更新**：`build.bat` 在打包后会自动执行 `update_docs.py`——把 `version.py` 的版本号刷进 `docs/FileCraft 使用文档.md`，同步 `docs/CHANGELOG.md` 为文档末尾的「更新日志」章节，并重新生成 PDF。所以只要用 build.bat 打包，使用文档永远和软件版本一致。发新版本时的规矩：升 version.py 的版本号 + 在 CHANGELOG.md 顶部加一条 + 需要时更新文档正文。

`build.bat` 已自动带上这一步。源码模式下同样可用：

```bash
python main.py --selftest report.txt
```

**打包是否自包含，可以用这两个小工具确认**（都在项目根目录）：

```bash
python win_probe.py FileCraft.exe    # 确认主窗口真的显示了（而不是 Qt 错误弹窗）
python module_probe.py FileCraft.exe # 确认 Qt6Core.dll 是从 exe 解包目录加载的
```

`module_probe.py` 是关键：它列出运行中进程加载的 Qt 模块来源。凡是 `_MEI...\PyQt6\Qt6\` 开头的就是自带，凡是 `site-packages` 开头的就是借用本机环境，不能分发。

**关于体积和启动速度**

`--onefile` 每次启动都要把 88 MB 解压到临时目录，首次启动约 3-5 秒。如果更在意启动速度，把 spec 里的 `console=False` 和 onefile 结构换成 onedir 会快很多，但分发时要拷整个文件夹。

## 分发给别人

打包完成后，**只需要把 `dist\FileCraft.exe` 这一个文件发给对方**，对方不需要装 Python，双击即用。但有三件事要交代清楚：

1. **对方的电脑必须装了中文字体**：极少数精简版 Windows 可能没有微软雅黑，PDF 导出会退回到系统里找其它中文字体（黑体/宋体），全没有才会报错。正常 Windows 都有，可不管。
2. **对方需要自己填 API Key**：程序预设了 ModelScope 的 base_url 与模型名，对方拿到 exe 后需在「工具 → 设置」中填入自己的 API Key 才能使用「AI 总结」。每个机器上会生成一份 `%USERPROFILE%\.filecraft\config.json` 记录当前配置（含明文 Key，注意不要外传该文件）。
4. **杀毒软件可能误报**：PyInstaller 打包的单文件 exe 是未签名程序，Windows SmartScreen 首次可能提示"已保护你的电脑"，点击"更多信息 → 仍要运行"即可，不是真病毒。如果对方杀毒软件直接隔离，可以在项目目录里保留 `dist\FileCraft.exe` 之外的源码作为"这不是病毒"的佐证，但没有任何软件能保证 100% 不被误报。

**对方电脑的要求**：64 位 Windows 10/11，不需要管理员权限，不需要装 Python、Qt 或任何运行库。

## 已知限制

- **不支持旧版 `.doc` / `.ppt` / `.xls`**：Python 生态解析这些二进制老格式不可靠，导入时会被自动跳过。请先用 Office / WPS 另存为 `.docx` / `.pptx` / `.xlsx`。
- **不支持扫描件 PDF**：没有集成 OCR，只能提取文本型 PDF 的内容。扫描件请先用 OCR 工具转成文本。
- **Excel 的公式**：读取的是缓存的计算结果而非公式本身；合并单元格的从属格可能显示为空。
- **PDF 排版**：提取的是纯文本流，多栏排版和图文混排可能丢失原始阅读顺序。
- **总结质量**取决于你所配置的模型能力。

## 项目结构

```
filecraft/
├── main.py                     # 入口（--selftest 走自检）
├── selftest.py                 # 冻结包/源码自检脚本（13 项检查）
├── build.bat                   # 一键打包（调用 FileCraft.spec）
├── FileCraft.spec              # 打包配置（显式指定 Qt6 DLL/插件/MSVC 运行库）
├── win_probe.py                # 验证 exe 是否弹出主窗口而非错误框
├── module_probe.py             # 验证 exe 是否自包含 Qt（加载来源判定）
├── config.py                   # 配置读写（%USERPROFILE%\.filecraft\config.json）
├── requirements.txt
├── core/
│   ├── registry.py             # 按扩展名分发转换器
│   ├── converters/
│   │   ├── base.py             # Converter 抽象基类
│   │   ├── docx_converter.py   # Word -> Markdown
│   │   ├── pptx_converter.py   # PPT  -> Markdown
│   │   ├── xlsx_converter.py   # Excel -> Markdown
│   │   └── pdf_converter.py    # PDF  -> Markdown
│   ├── summarizer.py           # OpenAI 兼容调用 + 长文本 map-reduce
│   ├── archive.py              # 文件库归档（分类复制/去重/历史记录）
│   ├── qa.py                   # 基于文档的问答引擎
│   ├── mindmap.py              # 思维导图生成（markmap 离线渲染）
│   └── md_to_pdf.py            # Markdown -> PDF（reportlab）
├── ui/
│   ├── main_window.py          # 主窗口、菜单、拖拽导入
│   ├── summary_tab.py          # ① AI 总结并导出 PDF
│   ├── convert_tab.py          # ② 转 Markdown
│   ├── settings_dialog.py      # 接口设置
│   ├── archive_tab.py          # ③ 文件库（可视化文件夹树/新建/归档）
│   ├── qa_tab.py               # ④ 文档问答（多轮对话）
│   ├── file_store.py           # 各标签页共享的文件列表
│   ├── file_table.py           # 文件列表控件
│   └── worker.py               # 后台线程封装
└── testdata/                   # 4 种格式的样例文件，可直接用来试
```

## 实现说明

**PDF 生成为什么用 reportlab 而不是 HTML 转 PDF**
最初用 WeasyPrint，但它在 Windows 上需要 GTK 运行库；改用 xhtml2pdf 后又受其资源策略限制，无法读取项目目录外的系统中文字体，导致中文变成空白方块。最终改为 reportlab Platypus 直接把 Markdown 结构渲染成 PDF —— 它可以通过 `pdfmetrics` 注册任意路径的系统 TTF 字体，中文渲染最稳定，且零外部运行库依赖。

字体按 `msyh.ttc`（微软雅黑，正文）+ `msyhbd.ttc`（雅黑粗体，标题与加粗）优先，缺失时依次退化到黑体、楷体、宋体。注意不要用 `simsunb.ttf`，那是 SimSun-ExtB，只含扩展区生僻字，常规汉字会缺字。

**长文本总结**
`core/summarizer.py` 按 `max_chars_per_chunk`（默认 100000 字符，可在设置里改）切块。单块时一次调用出结果；多块时先逐块提取要点，再把各段要点合并成最终总结。