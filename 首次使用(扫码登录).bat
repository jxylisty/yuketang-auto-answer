@echo off
chcp 65001 >nul
title 雨课堂助手 - 首次扫码登录
cd /d "%~dp0"

echo ====================================================
echo      🎓 雨课堂全自动随堂答题助手 - 首次登录引导
echo ====================================================
echo.
echo 正在启动专用登录浏览器，请稍候...
python login_helper.py

if errorlevel 1 (
    echo.
    echo ❌ 运行出错，请确保已安装 Python 并执行过:
    echo    pip install -r requirements.txt
    echo.
)
pause
