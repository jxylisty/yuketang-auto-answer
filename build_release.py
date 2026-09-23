# -*- coding: utf-8 -*-
"""
雨课堂随堂助手 - GitHub Release 一键自动化打包发布工具
使用 PyInstaller 将项目打包为免安装可执行程序，并压缩为 release.zip 供分发给他人使用。
"""

import os
import sys
import shutil
import zipfile
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")
APP_NAME = "雨课堂随堂助手"
ZIP_NAME = "yuketang-auto-answer-v2.0-windows-x64.zip"

def build():
    print("=" * 65)
    print("📦 开始构建【雨课堂随堂助手】GitHub Release 便携分发包...")
    print("=" * 65)

    # 1. 检查 PyInstaller
    try:
        import PyInstaller
        print(f"✅ 检测到 PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        print("❌ 未检测到 PyInstaller，正在自动安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])

    # 2. 构建 PyInstaller 参数
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed", # 隐藏黑框，纯 GUI
        "--name", APP_NAME,
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        "--add-data", f"config.example.json;.",
        "--add-data", f"login_helper.py;.",
        "--add-data", f"ykt_standalone_agent.py;.",
        # 排除过大无用的测试库
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "notebook",
        "--exclude-module", "jupyter",
        os.path.join(BASE_DIR, "ykt_gui.py")
    ]

    print(f"🚀 正在执行 PyInstaller 编译命令...")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        print("❌ PyInstaller 编译失败！")
        return False

    app_folder = os.path.join(DIST_DIR, APP_NAME)
    if not os.path.exists(app_folder):
        print(f"❌ 未找到生成的目标文件夹: {app_folder}")
        return False

    # 3. 复制说明文档与示例配置
    print("📋 正在填充发布附加文件 (README, 配置文件模板)...")
    for f in ["config.example.json", "README.md", "LICENSE"]:
        src = os.path.join(BASE_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, app_folder)

    # 创建一个方便的默认 config.json
    cfg_dst = os.path.join(app_folder, "config.json")
    cfg_src = os.path.join(BASE_DIR, "config.example.json")
    if not os.path.exists(cfg_dst) and os.path.exists(cfg_src):
        shutil.copy2(cfg_src, cfg_dst)

    # 4. 打包为 Release ZIP
    zip_path = os.path.join(DIST_DIR, ZIP_NAME)
    print(f"🗜️ 正在压缩打包为: {zip_path} ...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(app_folder):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, DIST_DIR)
                zipf.write(full_path, rel_path)

    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print("\n" + "=" * 65)
    print(f"🎉 构建成功！发布包已就绪！")
    print(f"📁 发布文件夹: {app_folder}")
    print(f"📦 Release ZIP 压缩包: {zip_path} ({round(zip_size_mb, 2)} MB)")
    print(f"👉 您可以直接将此 ZIP 文件上传到 GitHub 仓库的 Releases 页面供大家下载使用！")
    print("=" * 65 + "\n")
    return True

if __name__ == "__main__":
    build()
