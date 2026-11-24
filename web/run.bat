@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set CALVAL_WEB_PORT=8088
echo 启动 Cal/Val Agent Web: http://127.0.0.1:%CALVAL_WEB_PORT%
"D:\Software\anaconda3\envs\llm\python.exe" web\server.py
pause