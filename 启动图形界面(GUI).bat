@echo off
chcp 65001 >nul
title 雨课堂助手 - 桌面图形客户端
cd /d "%~dp0"

echo ====================================================
echo      🎓 雨课堂随堂助手 - 桌面可视化客户端 (GUI)
echo ====================================================
echo.
echo 正在启动图形界面，请稍候...

start "" pythonw ykt_gui.py
if errorlevel 1 (
    python ykt_gui.py
)
