@echo off
chcp 65001 >nul
title 雨课堂助手 - 构建 GitHub Release
cd /d "%~dp0"

echo ====================================================
echo      📦 雨课堂随堂助手 - 一键构建发布包
echo ====================================================
echo.

python build_release.py
pause
