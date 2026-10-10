@echo off
rem ============================================================
rem  FileCraft 打包脚本
rem  产物：dist\FileCraft.exe（单文件，双击即可运行，可独立分发）
rem
rem  使用 FileCraft.spec 而不是纯命令行参数，因为 spec 里显式指定了
rem  Qt6 核心 DLL、平台插件、MSVC 运行库——PyInstaller 的默认 PyQt6
rem  钩子会漏掉这些（详见 spec 顶部的注释）。
rem ============================================================
setlocal
cd /d "%~dp0"

echo [1/5] 检查 PyInstaller...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo     未安装，正在安装...
    python -m pip install pyinstaller
    if errorlevel 1 goto :fail
)

echo [2/5] 清理旧产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/5] 打包中（约需 2-4 分钟）...
python -m PyInstaller --noconfirm --clean FileCraft.spec
if errorlevel 1 goto :fail

echo [4/5] 自动更新使用文档（版本戳 + 更新日志 + 重新生成 PDF）...
python update_docs.py
if errorlevel 1 goto :fail

echo [5/5] 运行冻结包自检（转换 + PDF 导出）...
if exist frozen_report.txt del frozen_report.txt
dist\FileCraft.exe --selftest frozen_report.txt
echo.
echo ============================================================
echo  打包完成： dist\FileCraft.exe
echo  使用文档： docs\FileCraft 使用文档.pdf（版本已自动同步）
echo  自检报告： frozen_report.txt（应显示 通过 13，失败 0）
echo ============================================================
goto :eof

:fail
echo.
echo *** 打包失败，请查看上方错误信息 ***
exit /b 1