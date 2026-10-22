@echo off
rem 启动课件批注工作台（本地服务 + 默认浏览器）
chcp 65001 >nul
cd /d "%~dp0"

rem 已在运行就直接开页面，避免重复启动撞端口
where curl >nul 2>nul
if not errorlevel 1 (
  curl -s --max-time 1 -o nul http://127.0.0.1:8765/api/health
  if not errorlevel 1 (
    start "" http://127.0.0.1:8765/
    exit /b 0
  )
)

where python >nul 2>nul
if errorlevel 1 (
  echo 没有找到 python，请安装 Python 3.10+ 后重试。
  pause
  exit /b 1
)
python scripts\serve_workbench.py --root . --open
if errorlevel 1 pause
