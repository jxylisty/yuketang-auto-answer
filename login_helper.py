# -*- coding: utf-8 -*-
"""
雨课堂首次扫码登录助手
使用方法：直接运行或双击【首次使用(扫码登录).bat】
运行后会自动弹出 Edge 浏览器，请使用微信扫码登录雨课堂。
登录成功后关闭浏览器即可，登录凭证会自动保存在本地，之后上课免扫码自动登录。
"""

import sys
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import os
import time
import json
import subprocess
from selenium import webdriver
from selenium.webdriver.edge.options import Options

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(BASE_DIR, "edge_profile")

def get_base_url():
    cfg_file = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f).get("yuketang_base_url", "https://www.yuketang.cn").rstrip("/")
        except Exception:
            pass
    return "https://www.yuketang.cn"

def ensure_edge_clean():
    """清理可能冲突的残留 Edge 进程"""
    try:
        cmd = 'Get-CimInstance Win32_Process -Filter "name = \'msedge.exe\'" | Where-Object { $_.CommandLine -like "*edge_profile*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }'
        subprocess.run(['powershell', '-Command', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def main():
    base_url = get_base_url()
    print("=" * 60)
    print(f"🔑 雨课堂【首次扫码登录助手】(目标平台: {base_url})")
    print("=" * 60)
    print("1. 正在唤起 Edge 专属配置窗口...")
    ensure_edge_clean()
    os.makedirs(PROFILE_DIR, exist_ok=True)

    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--log-level=3")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Edge(options=opts)
    try:
        login_url = f"{base_url}/v2/web/index"
        print(f"2. 正在打开雨课堂登录页: {login_url}")
        driver.get(login_url)
        print("\n👉 请在弹出的浏览器中，使用【微信】扫码完成雨课堂登录！")
        print("💡 提示：扫码成功并进入主页后，系统会自动检测并完成保存。")
        print("   (若已扫码完毕，亦可直接在控制台按回车继续)")

        # 循环检测是否已登录成功
        logged_in = False
        for _ in range(120): # 最长等待 2 分钟
            time.sleep(1.5)
            try:
                # 检查页面是否包含已登录的特征元素或跳转到了大屏/个人中心
                is_logged = driver.execute_script("""
                    const text = document.body ? document.body.innerText : '';
                    const hasAvatar = !!document.querySelector('.avatar, .user-name, [class*="userInfo"], [class*="avatar"]');
                    const hasMyCourse = text.includes('我听的课') || text.includes('我的课程') || text.includes('课堂动态');
                    return hasAvatar || hasMyCourse;
                """)
                if is_logged:
                    logged_in = True
                    break
            except Exception:
                pass

        if logged_in:
            print("\n🎉 恭喜！检测到登录成功！")
        else:
            print("\n⏰ 超时或已手动确认。")

        print("💾 登录会话与 Cookie 已妥善保存在本地 edge_profile 目录。")
        print("✅ 后续上课运行【一键启动(全自动答题).bat】即可全自动作答，无需重复扫码！")
        print("=" * 60)
    finally:
        time.sleep(1)
        driver.quit()

if __name__ == "__main__":
    main()
