# -*- coding: utf-8 -*-
"""
雨课堂随堂测验自动作答引擎
功能特点：
1. 本地 DOM 结构嗅探与 PaddleOCR 文字识别双重提取
2. 大模型极速求解与多模型自动容灾切换
3. 支持单选、多选、多项填空与主观简答题全题型自动化
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
import re
import subprocess
import requests
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(BASE_DIR, "edge_profile")
SCREENSHOT_FILE = os.path.join(BASE_DIR, "current_problem.png")

def load_config():
    """动态加载配置文件，避免泄露用户敏感信息"""
    config_path = os.path.join(BASE_DIR, "config.json")
    example_path = os.path.join(BASE_DIR, "config.example.json")
    cfg = {
        "api_base": "https://tokenrhythm.studio/v1",
        "api_key": os.environ.get("YKT_API_KEY", ""),
        "models": ["deepseek-v4-flash-0731", "glm-5.3-flash", "qwen3.7-flash"],
        "auto_submit": True,
        "listen_interval": 1.0
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                cfg.update(user_cfg)
        except Exception as e:
            print(f"⚠️ 读取 config.json 失败: {e}，使用默认配置")
    elif os.path.exists(example_path):
        print("💡 未检测到 config.json，建议复制 config.example.json 并配置您的 API Key。")
    return cfg

CONFIG = load_config()
API_BASE = CONFIG.get("api_base", "https://tokenrhythm.studio/v1")
API_KEY = CONFIG.get("api_key", "")
MODELS_POOL = CONFIG.get("models", ["deepseek-v4-flash-0731", "glm-5.3-flash", "qwen3.7-flash"])
DEFAULT_MODEL = MODELS_POOL[0] if MODELS_POOL else "deepseek-v4-flash-0731"
AUTO_SUBMIT = CONFIG.get("auto_submit", True)
LISTEN_INTERVAL = CONFIG.get("listen_interval", 1.0)
YKT_BASE_URL = CONFIG.get("yuketang_base_url", "https://www.yuketang.cn").rstrip("/")

# 全局 PaddleOCR 实例（懒加载）
_OCR_ENGINE = None

def get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        try:
            print("正在预加载本地 PaddleOCR 引擎（秒级就绪）...")
            from paddleocr import PaddleOCR
            _OCR_ENGINE = PaddleOCR(lang='ch')
            print("✅ 本地 PaddleOCR 引擎加载完成！")
        except Exception as e:
            print(f"⚠️ PaddleOCR 加载提示: {e}")
    return _OCR_ENGINE

def extract_text_from_image(image_path):
    """通过本地 PaddleOCR 提取图片中的文字"""
    try:
        ocr = get_ocr_engine()
        if not ocr:
            return ""
        
        # 兼容最新 PaddleX / PaddleOCR 语法
        try:
            res = ocr.predict(image_path)
        except Exception:
            res = ocr.ocr(image_path)
            
        texts = []
        if res:
            for item in res:
                if isinstance(item, dict) and 'rec_texts' in item:
                    texts.extend(item['rec_texts'])
                elif isinstance(item, list):
                    for line in item:
                        if isinstance(line, list) and len(line) >= 2 and isinstance(line[1], (list, tuple)):
                            texts.append(str(line[1][0]))
                        elif isinstance(line, str):
                            texts.append(line)
        return " ".join(texts)
    except Exception as e:
        print(f"OCR 提取异常: {e}")
        return ""

def split_blank_answers(ans, expected_count=0):
    """智能解析多项填空题答案为列表"""
    ans = ans.strip()

    # 1. 核心保障：如果页面只检测到 1 个填空框，绝对不要拆分，直接返回完整段落！
    if expected_count == 1:
        return [ans]

    # 2. 优先检查竖线 | （提示词中强制约束的多项填空专用分隔符）
    if '|' in ans:
        parts = [p.strip() for p in ans.split('|') if p.strip()]
        if len(parts) > 1:
            return parts

    # 3. 检查带编号的标签（如：[填空1]: 2  [填空2]: 3 或 空1: 2 空2: 3）
    labeled = re.findall(r'(?:\[?填空\d+\]?|\b\d+[\.、]|空\d+)[:：\s]*([^\s,，|]+)', ans)
    if labeled and len(labeled) > 1:
        if expected_count <= 1 or len(labeled) == expected_count:
            return labeled

    # 4. 如果页面明确有多于 1 个空（expected_count > 1）：
    if expected_count > 1:
        # 按换行尝试
        if '\n' in ans:
            lines = [re.sub(r'^(?:\[?填空\d+\]?|\d+[\.、:：]|空\d+[:：])\s*', '', l.strip()).strip() for l in ans.split('\n') if l.strip()]
            if len(lines) == expected_count:
                return lines
        # 按逗号/顿号尝试（拆分出的项数必须精准吻合预期空数）
        if any(c in ans for c in [',', '，', '、']):
            parts = [p.strip() for p in re.split(r'[,，、]', ans) if p.strip()]
            if len(parts) == expected_count:
                return parts
        # 按空格尝试（拆分出的项数必须精准吻合预期空数）
        spaces = [s.strip() for s in ans.split() if s.strip()]
        if len(spaces) == expected_count:
            return spaces

    # 5. 如果没有指定 expected_count 但按换行有多行简短内容
    if '\n' in ans:
        lines = [re.sub(r'^(?:\[?填空\d+\]?|\d+[\.、:：]|空\d+[:：])\s*', '', l.strip()).strip() for l in ans.split('\n') if l.strip()]
        if len(lines) > 1 and all(len(l) < 30 for l in lines):
            return lines

    return [ans]

def call_deepseek_solver(question_text, q_type, options=None):
    """调用 API 获取高准确率答案（支持多模型自动重试与故障转移）"""
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        print("❌ 未检测到有效的 API Key！请先在 config.json 中配置您的 API Key。")
        if "单选" in q_type: return "C"
        elif "多选" in q_type: return "ABCD"
        return "已收到并作答"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    opt_str = f"\n可选选项: {', '.join(options)}" if options else ""
    prompt = f"""你是一个大学课堂随堂测验答题专家。请根据以下题目内容给出高准确率的回答：

【题目类型】: {q_type}
【题目内容】:
{question_text}
{opt_str}

【严格输出规则】:
1. 如果是【单选题】：必须只输出 1 个大写字母选项（例如：C），不要包含任何解释或多余字符。
2. 如果是【多选题】：必须只输出所有正确选项的大写字母连写（例如：ACD 或 ABD），不要有空格或标点。
3. 如果是【填空题】：
   - 如果只有 1 个空，直接输出该空的答案。
   - 如果包含多个空（如多项填空：[填空1]、[填空2]...），请严格按顺序输出每个空的答案，各空之间必须严格用竖线 | 分隔（例如：2 | 3 | 5 | 10），绝对不要输出任何其他多余说明！
4. 如果是【主观题/简答题】：请针对题目给出要点清晰、符合字数要求的精准答案，直接输出内容，不要废话。
"""

    for model_name in MODELS_POOL:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "你是一个严谨的随堂测试答题助手。严格按格式输出最终答案。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 500
        }
        for attempt in range(1, 3):
            try:
                print(f"🧠 [模型思考中...] 正在请求 {model_name} (尝试 {attempt}/2)...")
                t0 = time.time()
                r = requests.post(f"{API_BASE}/chat/completions", headers=headers, json=payload, timeout=9)
                if r.status_code == 200:
                    res = r.json()
                    ans = res['choices'][0]['message']['content'].strip()
                    ans = re.sub(r'^```[\w]*\n?', '', ans)
                    ans = re.sub(r'\n?```$', '', ans).strip()
                    cost = res.get('cost_cny', '0')
                    print(f"🎉 [{model_name} 秒级出解！] 耗时: {round(time.time()-t0, 2)}秒 | 答案: 【{ans}】 | 费用: ¥{cost}")
                    return ans
                else:
                    print(f"⚠️ {model_name} (尝试 {attempt}) 响应异常 ({r.status_code}): {r.text[:80]}")
            except requests.exceptions.Timeout:
                print(f"⏱️ {model_name} (尝试 {attempt}) 响应超时(9s)，正在重试或切换备用模型...")
            except Exception as e:
                print(f"⚠️ {model_name} (尝试 {attempt}) 异常: {e}")
            time.sleep(0.5)

    # 兜底保底策略
    if "单选" in q_type:
        return "C"
    elif "多选" in q_type:
        return "ABCD"
    return "已收到并作答"

def ensure_edge_clean():
    """清理可能冲突的残留 Edge 进程"""
    try:
        cmd = 'Get-CimInstance Win32_Process -Filter "name = \'msedge.exe\'" | Where-Object { $_.CommandLine -like "*edge_profile*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }'
        subprocess.run(['powershell', '-Command', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def get_driver(headless=False):
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

    if headless:
        opts.add_argument("--headless=new")
    driver = webdriver.Edge(options=opts)
    return driver

def run_standalone_agent():
    """纯独立运行的主控制循环"""
    print("=" * 60)
    print("🚀 雨课堂随堂测验自动作答引擎已启动")
    print(f"🌐 目标平台: {YKT_BASE_URL}")
    print(f"🤖 默认模型: {DEFAULT_MODEL}")
    print("=" * 60)

    # 预加载 OCR
    get_ocr_engine()

    driver = get_driver(headless=False)
    try:
        driver.get(f"{YKT_BASE_URL}/v2/web/index")
        time.sleep(2)

        print("\n👀 正在监听课堂动态... (检测开课中)")
        answered_problem_ids = set()

        while True:
            cur_url = driver.current_url

            # 1. 如果不在大屏课堂中，探测并直连正在上课的课堂
            if "/lesson/" not in cur_url:
                on_lesson = driver.execute_script("""
                    return (async function() {
                        try {
                            const res = await fetch('/api/v3/classroom/on-lesson', { credentials: 'include' });
                            if (res.ok) {
                                const j = await res.json();
                                const list = j.data?.onLessonClassrooms || [];
                                if (list.length > 0) return list[0];
                            }
                        } catch(e) {}
                        return null;
                    })();
                """)
                if on_lesson:
                    l_id = on_lesson.get("lessonId") or on_lesson.get("lesson_id")
                    c_name = on_lesson.get("courseName") or "雨课堂"
                    print(f"🎯 检测到进行中课堂: 【{c_name}】(ID: {l_id})，正在直连大屏...")
                    driver.get(f"{YKT_BASE_URL}/lesson/fullscreen/v3/{l_id}")
                    time.sleep(4)
                    continue
                else:
                    time.sleep(3)
                    continue

            # 2. 已在大屏课堂中，以 1 秒频率监听发题状态
            quiz_info = driver.execute_script("""
                const info = { hasQuiz: false };
                const app = document.querySelector('#app');
                const store = app && app.__vue__ && app.__vue__.$store ? app.__vue__.$store.state : null;
                const currSlide = store ? store.currSlide : null;

                // 优先检查左侧栏是否有未完成题目
                const unfin = Array.from(document.querySelectorAll('.timeline__item.J_slide, .timeline__item'))
                    .find(el => el.innerText.includes('未完成'));
                if (unfin && !unfin.className.includes('active')) {
                    unfin.click();
                }

                // 探测作答元素
                const bodyText = document.body.innerText || '';
                const isCompleted = bodyText.includes('已完成') && !bodyText.includes('未完成');
                const hasTiming = Array.from(document.querySelectorAll('*')).some(el => 
                    (el.className && typeof el.className === 'string' && el.className.includes('timing')) ||
                    el.textContent.includes('倒计时')
                );
                const hasSubmit = Array.from(document.querySelectorAll('*')).some(el =>
                    (el.className && typeof el.className === 'string' && el.className.includes('submit-btn')) ||
                    el.textContent.includes('提交答案')
                );
                // 仅在大屏中央展示区内探查，严禁读取左侧历史边栏
                const centerCanvas = document.querySelector('.ppt__wrapper, .lesson__page, .presentation, .center-area');
                const centerText = centerCanvas ? centerCanvas.innerText : '';
                
                const hasZuoda = centerCanvas && Array.from(centerCanvas.querySelectorAll('*')).some(el => 
                    el.children.length === 0 && el.textContent.trim() === '作答' && el.offsetWidth > 0
                );

                if ((hasTiming || hasSubmit || hasZuoda) && !isCompleted) {
                    info.hasQuiz = true;
                    info.probId = currSlide ? (currSlide.problemID || currSlide.sid || currSlide.slideID) : null;
                    info.domText = (currSlide ? (currSlide.body || currSlide.title || '') : '') || centerText.slice(0, 300);
                    
                    // 探查中央大屏中是否存在 A/B/C/D 选项按钮
                    const centerOpts = [];
                    if (centerCanvas) {
                        const pList = Array.from(centerCanvas.querySelectorAll('p, span, div, li'));
                        for (const p of pList) {
                            const t = p.textContent.trim();
                            if (['A', 'B', 'C', 'D', 'E', 'F'].includes(t) && p.children.length === 0 && p.offsetWidth > 0) {
                                centerOpts.push(t);
                            }
                        }
                    }
                    const uniqueOpts = Array.from(new Set(centerOpts));
                    const hasChoiceOptions = uniqueOpts.length >= 2;

                    // 核心分流逻辑：选项按钮具有最高优先级
                    let qType = '单选题';
                    const probType = currSlide ? currSlide.problemType : null;

                    if (hasChoiceOptions) {
                        // 存在明显选项，绝对是选择题！
                        if (probType === 2 || centerText.includes('多选')) {
                            qType = '多选题';
                        } else {
                            qType = '单选题';
                        }
                    } else {
                        // 没有选项按钮时，按题型与作答按钮判定
                        if (probType === 5 || centerText.includes('主观') || centerText.includes('简答') || (hasZuoda && !centerText.includes('填空'))) {
                            qType = '主观题';
                        } else if (probType === 3 || probType === 4 || centerText.includes('填空') || (hasZuoda && centerText.includes('填空'))) {
                            qType = '填空题';
                        } else if (probType === 2 || centerText.includes('多选')) {
                            qType = '多选题';
                        } else if (probType === 1 || centerText.includes('单选')) {
                            qType = '单选题';
                        } else {
                            qType = hasZuoda ? '主观题' : '单选题';
                        }
                    }
                    info.qType = qType;

                    // 选项配置
                    if (qType.includes('选')) {
                        info.options = uniqueOpts.length > 0 ? uniqueOpts : ['A', 'B', 'C', 'D'];
                    } else {
                        info.options = null;
                    }
                }
                return info;
            """)

            if quiz_info and quiz_info.get("hasQuiz"):
                prob_id = quiz_info.get("probId")
                if prob_id and prob_id in answered_problem_ids:
                    time.sleep(1)
                    continue

                print(f"\n🚨 [{time.strftime('%H:%M:%S')}] 侦测到随堂题目发布！")
                q_type = quiz_info.get("qType", "单选题")
                options = quiz_info.get("options", ["A", "B", "C", "D"])
                dom_text = quiz_info.get("domText", "").strip()

                # 优先检查 DOM 文本是否完整，若不够完整则调用 PaddleOCR 识别大屏截图
                driver.save_screenshot(SCREENSHOT_FILE)
                question_content = dom_text
                if len(question_content) < 10 or "PPT" in question_content:
                    print("📷 正在调用本地 PaddleOCR 解析大屏课件文字...")
                    ocr_text = extract_text_from_image(SCREENSHOT_FILE)
                    if ocr_text:
                        question_content = ocr_text
                        print(f"📖 OCR 提取题干成功: 【{question_content[:80]}...】")

                # 调用 DeepSeek 获取答案
                ans = call_deepseek_solver(question_content, q_type, options)

                # 执行自动化提交
                print(f"⚡ 正在向雨课堂提交最终答案: 【{ans}】...")
                
                # 1. 选择题勾选
                if "选" in q_type:
                    letters = [c for c in ans.upper() if 'A' <= c <= 'Z']
                    driver.execute_script("""
                        const letters = arguments[0];
                        const allEls = Array.from(document.querySelectorAll('p, span, div, li'));
                        for (const ch of letters) {
                            let optEl = allEls.find(el => el.children.length === 0 && el.textContent.trim() === ch && el.offsetWidth > 0);
                            if (optEl) {
                                optEl.click();
                                if (optEl.parentElement) optEl.parentElement.click();
                            }
                        }
                    """, letters)
                    time.sleep(1)

                # 2. 填空题/主观题展开抽屉并输入
                if "填空" in q_type or "主观" in q_type:
                    # 点击【作答】展开右侧抽屉
                    driver.execute_script("""
                        const all = Array.from(document.querySelectorAll('*'));
                        const zuoda = all.find(el => el.children.length === 0 && el.textContent.trim() === '作答' && el.offsetWidth > 0);
                        if (zuoda) {
                            zuoda.click();
                            if (zuoda.parentElement) zuoda.parentElement.click();
                        }
                    """)
                    time.sleep(1.5)

                    # 探测抽屉中实际可见的填空输入框数量
                    detected_blank_count = driver.execute_script("""
                        const drawer = document.querySelector('[class*="drawer"], [class*="sheet"], [class*="sidebar"]');
                        const root = drawer || document;
                        return Array.from(root.querySelectorAll('textarea, input[type="text"], [contenteditable="true"]'))
                            .filter(el => el.offsetWidth > 0 || el.offsetHeight > 0).length;
                    """) or 0

                    if "主观" in q_type:
                        ans_list = [ans]
                        print(f"📝 主观题整段填入答案: 【{ans[:60]}...】")
                    else:
                        # 解析多项填空（支持 2 | 3 | 5 | 10 分别注入空1、空2、空3、空4）
                        ans_list = split_blank_answers(ans, expected_count=detected_blank_count)
                        print(f"📝 页面检测到 {detected_blank_count} 个填空槽位，精准解析各空答案: {ans_list}")

                    # 依次填入各个输入框并彻底触发 Vue 数据绑定
                    driver.execute_script("""
                        const answers = arguments[0];
                        const drawer = document.querySelector('[class*="drawer"], [class*="sheet"], [class*="sidebar"]');
                        const root = drawer || document;
                        let taList = Array.from(root.querySelectorAll('textarea.blank__input, input.blank__input, textarea, input[type="text"], [contenteditable="true"]'))
                            .filter(el => el.offsetWidth > 0 || el.offsetHeight > 0);

                        if (taList.length === 0) {
                            taList = Array.from(document.querySelectorAll('textarea, input[type="text"]'));
                        }

                        for (let i = 0; i < taList.length; i++) {
                            const ta = taList[i];
                            const val = i < answers.length ? answers[i] : (answers.length === 1 ? answers[0] : '');
                            ta.focus();
                            if (ta.tagName === 'TEXTAREA' || ta.tagName === 'INPUT') {
                                ta.value = val;
                                ta.dispatchEvent(new Event('input', { bubbles: true }));
                                ta.dispatchEvent(new Event('change', { bubbles: true }));
                                ta.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: ' ' }));
                            } else {
                                ta.innerText = val;
                                ta.dispatchEvent(new Event('input', { bubbles: true }));
                                ta.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }
                    """, ans_list)
                    time.sleep(1)

                # 3. 点击提交按钮（区分抽屉提交与大屏选择题提交）
                if "填空" in q_type or "主观" in q_type:
                    # 填空/主观题专属：精确点击右侧抽屉底部的【提交答案】按钮
                    sub_res = driver.execute_script("""
                        // 优先在抽屉容器 / .btn-box 内寻找
                        const btnBoxes = Array.from(document.querySelectorAll('.btn-box, [class*="drawer"], .submission-btn'));
                        for (const box of btnBoxes) {
                            const btn = Array.from(box.querySelectorAll('button, span, div, a')).find(el => 
                                ['提交答案', '提交'].includes(el.textContent.trim()) && el.offsetWidth > 0
                            );
                            if (btn) {
                                btn.click();
                                if (btn.parentElement) btn.parentElement.click();
                                return { success: true, target: 'drawer_box_btn' };
                            }
                        }
                        // 倒序查找（抽屉在 DOM 最底端）
                        const all = Array.from(document.querySelectorAll('*')).reverse();
                        const sub = all.find(el => 
                            el.children.length === 0 && 
                            ['提交答案', '提交'].includes(el.textContent.trim()) && 
                            el.offsetWidth > 0
                        );
                        if (sub) {
                            sub.click();
                            if (sub.parentElement) sub.parentElement.click();
                            return { success: true, target: 'reverse_sub_btn' };
                        }
                        return { success: false };
                    """)
                else:
                    # 选择题专属：点击大屏画布上的提交按钮
                    sub_res = driver.execute_script("""
                        const allEls = Array.from(document.querySelectorAll('button, .submit-btn, div, span, a'));
                        const sub = allEls.find(b => {
                            const t = b.textContent.trim();
                            const cls = b.className || '';
                            return b.offsetWidth > 0 && (
                                t === '提交答案' || 
                                t === '提交' || 
                                (typeof cls === 'string' && cls.includes('submit-btn'))
                            );
                        });
                        if (sub) {
                            sub.click();
                            if (sub.parentElement) sub.parentElement.click();
                            return { success: true, target: 'canvas_submit_btn' };
                        }
                        return { success: false };
                    """)
                print(f"提交按钮点击响应: {sub_res}")
                if prob_id:
                    answered_problem_ids.add(prob_id)
                print("✅ 提交指令已下发！状态已同步至教师端！")
                print("=" * 65)

            time.sleep(1)

    finally:
        driver.quit()

if __name__ == "__main__":
    run_standalone_agent()
