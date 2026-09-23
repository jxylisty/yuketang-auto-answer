# -*- coding: utf-8 -*-
"""
雨课堂随堂助手 - GitHub Release 一键自动化独立虚拟环境打包发布工具
特点：
1. 自动创建纯净独立的 .venv_build 虚拟环境，彻底隔离 Anaconda 庞杂依赖与多重 Qt 冲突
2. 仅安装打包所必须的最小运行时 (PyQt5, Selenium, Requests, PyInstaller)
3. 产物体积极小 (约 50MB)，启动极速，开箱即用，免去用户安装任何 Python 环境
"""

import os
import sys

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import shutil
import zipfile
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, ".venv_build")
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")
APP_NAME = "雨课堂随堂助手"
ZIP_NAME = "yuketang-auto-answer-v2.0-windows-x64.zip"

def get_venv_executables():
    if sys.platform.startswith("win"):
        py_exe = os.path.join(VENV_DIR, "Scripts", "python.exe")
        pip_exe = os.path.join(VENV_DIR, "Scripts", "pip.exe")
        pyinstaller_exe = os.path.join(VENV_DIR, "Scripts", "pyinstaller.exe")
    else:
        py_exe = os.path.join(VENV_DIR, "bin", "python")
        pip_exe = os.path.join(VENV_DIR, "bin", "pip")
        pyinstaller_exe = os.path.join(VENV_DIR, "bin", "pyinstaller")
    return py_exe, pip_exe, pyinstaller_exe

def setup_clean_venv():
    py_exe, pip_exe, pyinstaller_exe = get_venv_executables()
    if not os.path.exists(py_exe):
        print(f"🌱 正在创建纯净独立的打包虚拟环境: {VENV_DIR} ...")
        cmd = [sys.executable, "-m", "venv", VENV_DIR]
        subprocess.check_call(cmd, cwd=BASE_DIR)
        print("✅ 虚拟环境创建成功！")

    print("📦 正在检查并安装独立打包环境最小必要依赖 (清华镜像源加速)...")
    reqs = ["pyinstaller", "pyqt5", "selenium", "requests"]
    pip_cmd = [
        pip_exe, "install",
        *reqs,
        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
        "--trusted-host", "pypi.tuna.tsinghua.edu.cn"
    ]
    subprocess.check_call(pip_cmd)
    print("✅ 打包环境纯净依赖准备完毕！\n")
    return pyinstaller_exe

def build():
    print("=" * 65)
    print("🚀 开始构建【雨课堂随堂助手】GitHub Release 便携分发包...")
    print("=" * 65)

    # 1. 准备纯净 venv 与 pyinstaller
    pyinstaller_exe = setup_clean_venv()

    # 2. 清理旧构建缓存
    for p in [BUILD_DIR]:
        if os.path.exists(p):
            try:
                shutil.rmtree(p)
            except Exception:
                pass

    # 3. 构建 PyInstaller 参数
    cmd = [
        pyinstaller_exe,
        "--noconfirm",
        "--clean",
        "--windowed", # 隐藏黑框控制台，纯原生 GUI
        "--name", APP_NAME,
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        "--add-data", f"config.example.json;.",
        "--add-data", f"login_helper.py;.",
        "--add-data", f"ykt_standalone_agent.py;.",
        # 严格排除多余 Qt 绑定及无关大库，避免环境冲突
        "--exclude-module", "PySide6",
        "--exclude-module", "shiboken6",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "torch",
        "--exclude-module", "paddle",
        os.path.join(BASE_DIR, "ykt_gui.py")
    ]

    print(f"🔨 正在编译 Windows 原生可执行程序...")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        print("❌ PyInstaller 编译失败！")
        return False

    app_folder = os.path.join(DIST_DIR, APP_NAME)
    if not os.path.exists(app_folder):
        print(f"❌ 未找到生成的目标文件夹: {app_folder}")
        return False

    # 4. 复制发布附加说明文件与配置模板
    print("📋 正在填充发布附加文件 (README, 配置文件模板)...")
    for f in ["config.example.json", "README.md", "LICENSE"]:
        src = os.path.join(BASE_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, app_folder)

    # 创建一个方便小白直接编辑的默认 config.json
    cfg_dst = os.path.join(app_folder, "config.json")
    cfg_src = os.path.join(BASE_DIR, "config.example.json")
    if not os.path.exists(cfg_dst) and os.path.exists(cfg_src):
        shutil.copy2(cfg_src, cfg_dst)

    # 5. 打包为 Release ZIP
    zip_path = os.path.join(DIST_DIR, ZIP_NAME)
    print(f"🗜️ 正在压缩打包为绿色免安装包: {zip_path} ...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(app_folder):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, DIST_DIR)
                zipf.write(full_path, rel_path)

    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print("\n" + "=" * 65)
    print(f"🎉 全部构建成功！GitHub Release 便携分发包已生成！")
    print(f"📁 发布文件夹: {app_folder}")
    print(f"📦 Release ZIP 压缩包: {zip_path} ({round(zip_size_mb, 2)} MB)")
    print(f"👉 您只需将此 ZIP 上传到 GitHub 仓库 Releases 附件即可！")
    print(f"👉 同学下载后解压，直接双击【雨课堂随堂助手.exe】即可使用！")
    print("=" * 65 + "\n")
    return True

if __name__ == "__main__":
    build()
