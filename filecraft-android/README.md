# FileCraft Android（网页版壳）

把 [filecraft-web](../filecraft-web)（已部署于 https://filecraft.vibenav.xyz ）包成 Android APK 的原生 WebView 壳。
纯壳应用，无任何业务代码：所有解析、AI、存储都在服务器端，App 只负责在手机上把网页用好。

## 产物

`FileCraft-v1.0.0.apk`（约 49KB），最低 Android 7.0（API 24），竖屏，自签名，直接安装。

## 功能（原生层做了什么）

| 功能 | 实现 |
|---|---|
| 网页加载 | 全屏 WebView，默认加载线上站点；顶部 3px 蓝色加载进度条 |
| 文件上传 | `onShowFileChooser` 接管 `<input type=file accept=".docx,.pptx,.xlsx,.pdf">`，扩展名映射为 MIME 后调系统文件选择器，支持多选 |
| 导出下载 | 网页导出（PDF/MD/zip/思维导图 HTML）全走 `blob:` URL，WebView 原生下载不支持，故注入 `res/raw/inject.js` 拦截 `a.click()`，blob 分块（1.5MB）经 `AndroidSaver` JS 桥传给 `SaverBridge`，写入系统「下载」目录（API 29+ 走 MediaStore 无需权限；24-28 请求存储权限，拒绝则存应用私有目录并提示路径） |
| 直链兜底 | `setDownloadListener` 处理万一出现的 http(s) 直链下载（DownloadManager） |
| 断网处理 | 主框架加载失败显示错误页，可重试或更换服务器地址 |
| 切换服务器 | 右下角半透明 ⋮ 按钮 → 切换服务器地址（如局域网 `http://192.168.x.x:3100`），存 SharedPreferences；另有刷新/回首页/清除登录状态 |
| 返回键 | WebView 可后退则后退，否则退出 |

## 构建

免 Gradle：直接用本机 Android SDK 工具链（aapt2 → javac → d8 → zipalign → apksigner），
JDK 用 Android Studio 自带的 JBR 21，无需另装任何东西。

```bash
# Git Bash
cd /d/app/filecraft-android
python make_icons.py   # 仅图标改动时
bash build_apk.sh
```

产物：`FileCraft-v1.0.0.apk`。改版本号：同步改 `AndroidManifest.xml`、`build_apk.sh` 里的 `VERSION_*`。

工具链版本要求：build-tools 35.0.0、platform android-34（均可换，脚本里两个变量）。
2026-09-20 曾把 SDK 里的 emulator 升级到 37.2.10（旧版 35.6.11 带不动 API 36 镜像）；
本机嵌套虚拟化仍无法完成该镜像启动，故未做模拟器实测，真机验证通过前建议先装一台试。

## 签名

`debug.keystore`（密码 `filecraft123`，别名 `filecraft`，自签名 10000 天）。
**以后升级版本必须用同一个 keystore 签名**，否则用户手机上会提示签名不一致、需卸载重装。

## 已知限制

- 依赖线上服务器：无网 / 服务器宕机时 App 只能显示错误页（可切局域网地址自救）。
- 超大导出（>40MB）经 base64 桥传输较慢；正常 MD/PDF/zip 在几 MB 量级，无感。
- 未做深色模式、桌面小组件、推送等原生增强；网页是竖屏适配过的基础布局，横屏体验一般。
