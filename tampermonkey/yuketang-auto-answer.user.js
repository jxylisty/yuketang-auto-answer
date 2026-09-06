// ==UserScript==
// @name         雨课堂随堂习题全自动值守助手 (自动进课堂+AI秒答+微信通知)
// @namespace    https://github.com/jxylisty/yuketang-auto-answer
// @version      1.1.0
// @description  雨课堂/长江雨课堂 宿舍电脑后台全自动挂机：自动检测开课并进入、WebSocket毫秒捕获题目、AI秒解秒交、手机微信推送答题通知。
// @author       jxylisty
// @match        https://*.yuketang.cn/*
// @match        https://*.ykt.io/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @grant        GM_xmlhttpRequest
// @run-at       document-start
// ==/UserScript==

(function () {
    'use strict';

    // 默认配置
    const DEFAULT_CONFIG = {
        apiBase: 'https://api.siliconflow.cn/v1', // 默认硅基流动，支持 OpenAI 兼容 API
        apiKey: '',
        model: 'deepseek-ai/DeepSeek-V3',
        autoEnterLesson: true, // 核心功能：检测到开课自动进入课堂！
        autoSubmit: true,      // 自动提交（签到互动无需等待，立即提交）
        submitDelaySec: 1,     // 延迟 1 秒提交，确保输入事件触发完成
        enableAudio: true,     // 蜂鸣提示音
        pushToken: '',         // 可选：PushPlus (pushplus.plus) 微信推送 Token
    };

    function getConfig() {
        const cfg = {};
        for (const k of Object.keys(DEFAULT_CONFIG)) {
            cfg[k] = GM_getValue(k, DEFAULT_CONFIG[k]);
        }
        return cfg;
    }

    function saveConfig(cfg) {
        for (const [k, v] of Object.entries(cfg)) {
            GM_setValue(k, v);
        }
    }

    // 播放蜂鸣提示音
    function playBeep() {
        const cfg = getConfig();
        if (!cfg.enableAudio) return;
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            gain.gain.setValueAtTime(0.15, ctx.currentTime);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.35);
        } catch (e) {}
    }

    // 推送微信通知到手机（利用 PushPlus 免费微信推送服务）
    function pushToMobile(title, content) {
        const cfg = getConfig();
        if (!cfg.pushToken) return;

        GM_xmlhttpRequest({
            method: 'POST',
            url: 'https://www.pushplus.plus/send',
            headers: { 'Content-Type': 'application/json' },
            data: JSON.stringify({
                token: cfg.pushToken,
                title: title,
                content: content,
                template: 'html'
            }),
            onload: () => console.log('[雨课堂助手] 微信通知推送成功'),
            onerror: (e) => console.warn('[雨课堂助手] 微信推送失败:', e)
        });
    }

    // UI 悬浮面板
    let hudElement = null;
    function createHUD() {
        if (hudElement || !document.body) return;
        hudElement = document.createElement('div');
        hudElement.id = 'ykt-hud-container';
        hudElement.innerHTML = `
            <style>
                #ykt-hud-container {
                    position: fixed;
                    top: 15px;
                    right: 20px;
                    z-index: 999999;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }
                .ykt-card {
                    background: rgba(255, 255, 255, 0.96);
                    backdrop-filter: blur(8px);
                    border: 1px solid #e2e8f0;
                    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
                    border-radius: 12px;
                    padding: 14px 18px;
                    min-width: 280px;
                    max-width: 360px;
                    transition: all 0.3s ease;
                }
                .ykt-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    font-weight: 600;
                    color: #1e293b;
                    font-size: 14px;
                    margin-bottom: 8px;
                }
                .ykt-status {
                    display: inline-block;
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    background: #10b981;
                    margin-right: 6px;
                }
                .ykt-status.busy { background: #f59e0b; animation: pulse 1s infinite; }
                .ykt-status.error { background: #ef4444; }
                @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
                .ykt-body {
                    font-size: 13px;
                    color: #475569;
                    line-height: 1.5;
                }
                .ykt-answer-box {
                    margin-top: 8px;
                    padding: 8px 12px;
                    background: #f1f5f9;
                    border-radius: 8px;
                    border-left: 3px solid #3b82f6;
                    font-weight: bold;
                    color: #1e40af;
                    word-break: break-all;
                }
                .ykt-settings-btn {
                    background: none;
                    border: none;
                    cursor: pointer;
                    color: #64748b;
                    font-size: 14px;
                }
            </style>
            <div class="ykt-card">
                <div class="ykt-header">
                    <span><span class="ykt-status" id="ykt-status-dot"></span>雨课堂全自动值守助手</span>
                    <button class="ykt-settings-btn" id="ykt-open-settings" title="设置">⚙️</button>
                </div>
                <div class="ykt-body" id="ykt-status-text">初始化中...</div>
                <div id="ykt-answer-container" style="display:none;"></div>
            </div>
        `;
        document.body.appendChild(hudElement);
        document.getElementById('ykt-open-settings').addEventListener('click', showSettingsModal);
    }

    function updateHUD(text, status = 'normal', answerText = null) {
        if (!hudElement) createHUD();
        const dot = document.getElementById('ykt-status-dot');
        const statusText = document.getElementById('ykt-status-text');
        const ansContainer = document.getElementById('ykt-answer-container');

        if (dot) dot.className = 'ykt-status ' + (status === 'busy' ? 'busy' : status === 'error' ? 'error' : '');
        if (statusText) statusText.innerText = text;

        if (ansContainer) {
            if (answerText) {
                ansContainer.style.display = 'block';
                ansContainer.innerHTML = `<div class="ykt-answer-box">AI 答案：${answerText}</div>`;
            } else {
                ansContainer.style.display = 'none';
            }
        }
    }

    // 设置面板弹窗
    function showSettingsModal() {
        const cfg = getConfig();
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.5); z-index: 1000000;
            display: flex; align-items: center; justify-content: center;
        `;
        modal.innerHTML = `
            <div style="background: white; border-radius: 12px; padding: 24px; width: 440px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.2); font-family: sans-serif;">
                <h3 style="margin-top:0; color:#1e293b; font-size:18px;">雨课堂全自动值守配置</h3>
                <div style="margin-bottom: 12px;">
                    <label style="font-size:13px; color:#475569; display:block; margin-bottom:4px;">API Base URL (OpenAI 兼容接口)</label>
                    <input id="cfg-api-base" type="text" value="${cfg.apiBase}" style="width:100%; padding:8px; border:1px solid #cbd5e1; border-radius:6px; box-sizing:border-box;">
                    <span style="font-size:11px; color:#94a3b8;">默认硅基流动：https://api.siliconflow.cn/v1</span>
                </div>
                <div style="margin-bottom: 12px;">
                    <label style="font-size:13px; color:#475569; display:block; margin-bottom:4px;">API Key</label>
                    <input id="cfg-api-key" type="password" value="${cfg.apiKey}" placeholder="sk-..." style="width:100%; padding:8px; border:1px solid #cbd5e1; border-radius:6px; box-sizing:border-box;">
                </div>
                <div style="margin-bottom: 12px;">
                    <label style="font-size:13px; color:#475569; display:block; margin-bottom:4px;">Model 模型名称</label>
                    <input id="cfg-model" type="text" value="${cfg.model}" style="width:100%; padding:8px; border:1px solid #cbd5e1; border-radius:6px; box-sizing:border-box;">
                </div>
                <div style="margin-bottom: 12px;">
                    <label style="font-size:13px; color:#475569; display:block; margin-bottom:4px;">PushPlus 微信推送 Token (可选)</label>
                    <input id="cfg-push-token" type="text" value="${cfg.pushToken}" placeholder="从 pushplus.plus 获取，手机接收答题结果" style="width:100%; padding:8px; border:1px solid #cbd5e1; border-radius:6px; box-sizing:border-box;">
                </div>
                <div style="margin-bottom: 12px; display:flex; align-items:center; gap:8px;">
                    <input id="cfg-auto-enter" type="checkbox" ${cfg.autoEnterLesson ? 'checked' : ''}>
                    <label for="cfg-auto-enter" style="font-size:13px; color:#334155; font-weight:600;">开课自动进入课堂（宿舍挂机核心）</label>
                </div>
                <div style="margin-bottom: 12px; display:flex; align-items:center; gap:8px;">
                    <input id="cfg-auto-submit" type="checkbox" ${cfg.autoSubmit ? 'checked' : ''}>
                    <label for="cfg-auto-submit" style="font-size:13px; color:#334155;">做完立即自动提交（签到秒交）</label>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:16px;">
                    <button id="cfg-test-btn" style="padding:8px 12px; border:1px solid #2563eb; color:#2563eb; background:none; border-radius:6px; cursor:pointer;">测试 AI 连接</button>
                    <div>
                        <button id="cfg-cancel-btn" style="padding:8px 12px; border:none; background:#f1f5f9; color:#475569; border-radius:6px; cursor:pointer; margin-right:8px;">取消</button>
                        <button id="cfg-save-btn" style="padding:8px 16px; border:none; background:#2563eb; color:white; border-radius:6px; cursor:pointer;">保存</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        modal.querySelector('#cfg-cancel-btn').onclick = () => modal.remove();
        modal.querySelector('#cfg-save-btn').onclick = () => {
            saveConfig({
                apiBase: modal.querySelector('#cfg-api-base').value.trim(),
                apiKey: modal.querySelector('#cfg-api-key').value.trim(),
                model: modal.querySelector('#cfg-model').value.trim(),
                pushToken: modal.querySelector('#cfg-push-token').value.trim(),
                autoEnterLesson: modal.querySelector('#cfg-auto-enter').checked,
                autoSubmit: modal.querySelector('#cfg-auto-submit').checked,
            });
            modal.remove();
            updateHUD('配置已更新！');
        };

        modal.querySelector('#cfg-test-btn').onclick = () => {
            const base = modal.querySelector('#cfg-api-base').value.trim();
            const key = modal.querySelector('#cfg-api-key').value.trim();
            const model = modal.querySelector('#cfg-model').value.trim();
            const testBtn = modal.querySelector('#cfg-test-btn');
            testBtn.innerText = '测试中...';

            callLLM('请仅回答四个字：连接成功', { apiBase: base, apiKey: key, model: model })
                .then(ans => {
                    alert('✅ 接口连接测试成功！模型返回：' + ans);
                    testBtn.innerText = '测试 AI 连接';
                })
                .catch(err => {
                    alert('❌ 连接失败：' + err.message);
                    testBtn.innerText = '测试 AI 连接';
                });
        };
    }

    // 调用 LLM API
    function callLLM(prompt, overrideCfg = null) {
        const cfg = overrideCfg || getConfig();
        if (!cfg.apiKey) {
            return Promise.reject(new Error('未配置 API Key！请点击面板右上角 ⚙️ 图标配置。'));
        }

        const url = cfg.apiBase.replace(/\/+$/, '') + '/chat/completions';
        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method: 'POST',
                url: url,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${cfg.apiKey}`
                },
                data: JSON.stringify({
                    model: cfg.model,
                    messages: [
                        {
                            role: 'system',
                            content: '你是一个专业的随堂答题助手。用户将为你提供雨课堂的随堂题目。请精准给出答案：选择题直接输出选项字母（如 A 或 B 或 ABC），填空题直接输出最简洁准确的答案，绝对不要有任何多余废话。'
                        },
                        { role: 'user', content: prompt }
                    ],
                    temperature: 0.1,
                    max_tokens: 150
                }),
                timeout: 15000,
                onload: (res) => {
                    if (res.status >= 200 && res.status < 300) {
                        try {
                            const data = JSON.parse(res.responseText);
                            const answer = data.choices[0].message.content.trim();
                            resolve(answer);
                        } catch (e) {
                            reject(new Error('解析模型响应失败'));
                        }
                    } else {
                        reject(new Error(`API 报错 ${res.status}: ${res.responseText}`));
                    }
                },
                onerror: () => reject(new Error('网络连接异常')),
                ontimeout: () => reject(new Error('大模型请求超时（15s）'))
            });
        });
    }

    // ==========================================
    // 模块一：开课检测与自动进入课堂（Auto Join）
    // ==========================================
    function startAutoJoinMonitor() {
        const isLessonPage = window.location.href.includes('/lesson/');
        if (isLessonPage) {
            console.log('[雨课堂助手] 当前已在课堂页面内，启动答题监听模块。');
            updateHUD('已进入课堂，正在监听题目推送...');
            return;
        }

        console.log('[雨课堂助手] 当前在主页/课程列表，启动开课检测定时轮询...');
        updateHUD('宿舍挂机中：等待老师开课...');

        const candidateUrls = [
            '/api/v3/classroom/on-lesson',
            '/mooc-api/v1/lms/classroom/on-lesson',
            '/apiv3/classroom/on-lesson'
        ];

        async function checkOnLesson() {
            const cfg = getConfig();
            if (!cfg.autoEnterLesson) return;

            for (const path of candidateUrls) {
                try {
                    const res = await fetch(path, { credentials: 'include' });
                    if (!res.ok) continue;
                    const json = await res.json();
                    const lessonList = json.data?.on_lessons || json.data?.lessons || (json.data?.lesson_id ? [json.data] : []);

                    if (Array.isArray(lessonList) && lessonList.length > 0) {
                        const target = lessonList[0];
                        const lessonId = target.lesson_id || target.id;
                        const courseName = target.course_name || target.name || '课堂';

                        console.log(`[雨课堂助手] 🎯 发现正在上课！课程: ${courseName}, ID: ${lessonId}`);
                        updateHUD(`🚨 检测到【${courseName}】开课！正在自动进入...`, 'busy');
                        pushToMobile('雨课堂自动开课通知', `检测到课程【${courseName}】已开始，正在自动进入课堂！`);

                        // 自动跳转进入课堂大屏
                        window.location.href = `/lesson/fullscreen/v3/${lessonId}`;
                        return;
                    }
                } catch (e) {
                    // 忽略网络重试错误
                }
            }
        }

        // 每 15 秒轮询一次
        setInterval(checkOnLesson, 15000);
        checkOnLesson();
    }

    // ==========================================
    // 模块二：WebSocket 题目拦截与秒级作答
    // ==========================================
    function initWebSocketHook() {
        const originalWebSocket = window.WebSocket;
        window.WebSocket = function (...args) {
            const ws = new originalWebSocket(...args);
            console.log('[雨课堂助手] 成功拦截 WebSocket 连接:', args[0]);

            ws.addEventListener('message', function (event) {
                try {
                    const data = typeof event.data === 'string' ? JSON.parse(event.data) : null;
                    if (data) {
                        handleWebSocketMessage(data);
                    }
                } catch (e) {}
            });

            return ws;
        };
        window.WebSocket.prototype = originalWebSocket.prototype;
    }

    function handleWebSocketMessage(msg) {
        const op = msg.op || msg.type || (msg.msg && msg.msg.op);
        console.log('[雨课堂助手] 收到 WS 消息类型:', op);

        if (op === 'problem' || op === 'problem_unlock' || (msg.data && msg.data.problem)) {
            console.log('🚨 [雨课堂助手] 检测到随堂题目下发！', msg);
            playBeep();
            updateHUD('🚨 检测到新习题！AI 正在极速作答...', 'busy');

            setTimeout(() => {
                extractAndSolveQuestion(msg);
            }, 600);
        }
    }

    async function extractAndSolveQuestion(wsData) {
        let questionText = '';
        let options = [];

        // 1. 尝试 DOM 抓取
        const problemContainer = document.querySelector('.problem-wrap, .exam-problem, .question-container, .exercise-content, [class*="problem"]');
        if (problemContainer) {
            const titleEl = problemContainer.querySelector('.title, .subject, .question-title, [class*="title"]');
            if (titleEl) questionText = titleEl.innerText.trim();

            const optEls = problemContainer.querySelectorAll('.option-item, .choice-item, li[class*="option"], [class*="radio"], [class*="checkbox"]');
            optEls.forEach(el => options.push(el.innerText.trim()));
        }

        // 2. 备选 WebSocket 提取
        if (!questionText && wsData) {
            const p = wsData.data?.problem || wsData.problem || wsData;
            if (p.body || p.title) questionText = p.body || p.title;
            if (Array.isArray(p.options)) {
                options = p.options.map(o => (o.key || '') + '. ' + (o.value || o.text || ''));
            }
        }

        if (!questionText) {
            updateHUD('已检测到发题，但 DOM 未能解析，请稍候...', 'error');
            return;
        }

        const prompt = `【题目】\n${questionText}\n\n【选项】\n${options.length ? options.join('\n') : '（无选项，属于填空题）'}\n\n请直接输出最终答案：`;

        try {
            const answer = await callLLM(prompt);
            console.log('[雨课堂助手] AI 返回答案:', answer);
            updateHUD('已解出答案，正在自动勾选与提交！', 'normal', answer);

            autoFillAndSubmit(questionText, answer);
        } catch (err) {
            console.error('[雨课堂助手] AI 解答异常:', err);
            updateHUD('解答出错：' + err.message, 'error');
            pushToMobile('雨课堂答题异常', `题目：${questionText.substring(0, 30)}...，求解失败：${err.message}`);
        }
    }

    // 自动勾选并秒级提交
    function autoFillAndSubmit(questionText, answer) {
        const cleanAns = answer.toUpperCase().replace(/[^A-Z]/g, '');
        if (cleanAns) {
            console.log('[雨课堂助手] 勾选选择题选项:', cleanAns);
            const options = document.querySelectorAll('.option-item, .choice-item, [class*="choice"], li[class*="option"]');
            options.forEach(opt => {
                const text = opt.innerText.trim();
                for (const char of cleanAns) {
                    if (text.startsWith(char) || text.includes(char + '.') || text.includes(char + '、')) {
                        opt.click();
                    }
                }
            });
        } else {
            const inputs = document.querySelectorAll('input[type="text"], textarea, .blank-input, [class*="input"]');
            if (inputs.length > 0) {
                inputs[0].value = answer;
                inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
                inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
            }
        }

        const cfg = getConfig();
        if (cfg.autoSubmit) {
            const delay = Math.max(0, cfg.submitDelaySec) * 1000;
            setTimeout(() => {
                const submitBtn = document.querySelector('button.submit, button[class*="submit"], .btn-submit, [class*="btn"][class*="submit"]');
                if (submitBtn) {
                    submitBtn.click();
                    updateHUD('🎉 已秒级自动完成作答与提交！', 'normal', answer);
                    pushToMobile('雨课堂自动答题成功', `题目：${questionText.substring(0, 40)}...<br>AI 提交答案：<b>${answer}</b>`);
                } else {
                    updateHUD('已选中答案，未找到提交按钮！', 'normal', answer);
                }
            }, delay);
        }
    }

    // 初始化
    initWebSocketHook();

    window.addEventListener('DOMContentLoaded', () => {
        createHUD();
        startAutoJoinMonitor();
    });

    if (document.body) {
        createHUD();
        startAutoJoinMonitor();
    }
})();
