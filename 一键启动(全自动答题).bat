@echo off
chcp 65001 >nul
title 雨课堂助手 - 正在后台全自动值守
cd /d "%~dp0"

echo ====================================================
echo      🎓 雨课堂独立全自动作答引擎 (PaddleOCR + DeepSeek)
echo ====================================================
echo.
echo 正在检查配置文件...
if not exist "config.json" (
    if exist "config.example.json" (
        echo ⚠️ 未检测到 config.json，正在自动从 config.example.json 创建模板...
        copy config.example.json config.json >nul
        echo 👉 请使用记事本打开 config.json 并填写你的 API Key 后重新启动！
        notepad config.json
        pause
        exit /b
    )
)

echo 正在启动后台全自动答题引擎，请保持本窗口开启...
echo.
python ykt_standalone_agent.py

if errorlevel 1 (
    echo.
    echo ❌ 进程异常退出，请检查网络连接或依赖环境。
    echo.
    pause
)
