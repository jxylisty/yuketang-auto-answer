# -*- coding: utf-8 -*-
"""
雨课堂随堂助手 - 现代化桌面图形客户端 (GUI)
基于 PyQt5 构建，集全自动值守、实时日志、配置可视化、VIP课堂一键同步于一体。
"""

import sys
import os
import re
import json
import time
import queue
import threading
import subprocess

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QTextEdit,
    QGroupBox, QFormLayout, QFrame, QSplitter, QMessageBox, QInputDialog,
    QDoubleSpinBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QTextCursor, QIcon

# 确保本模块所在目录在 sys.path 中
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import ykt_standalone_agent

class LogRedirector(QObject):
    """线程安全的 stdout/stderr 重定向发射器"""
    text_written = pyqtSignal(str)

    def __init__(self, original_stream):
        super().__init__()
        self.original_stream = original_stream

    def write(self, text):
        if text:
            self.text_written.emit(text)
        if self.original_stream:
            try:
                self.original_stream.write(text)
                self.original_stream.flush()
            except Exception:
                pass

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass


class AgentWorker(QThread):
    """后台自动化值守工作线程"""
    status_changed = pyqtSignal(dict)
    finished_signal = pyqtSignal()

    def __init__(self, command_queue):
        super().__init__()
        self.command_queue = command_queue
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        def callback(status_dict):
            self.status_changed.emit(status_dict)

        try:
            ykt_standalone_agent.run_standalone_agent(
                stop_event=self.stop_event,
                command_queue=self.command_queue,
                status_callback=callback
            )
        except Exception as e:
            print(f"\n❌ [工作线程未捕获异常]: {e}")
        finally:
            self.finished_signal.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("雨课堂随堂助手 - 全自动值守引擎 v2.0 (VIP增强版)")
        self.resize(1020, 720)
        self.setMinimumSize(860, 580)

        self.worker = None
        self.command_queue = queue.Queue()
        self.is_running = False

        # 初始化日志重定向
        self.redirector = LogRedirector(sys.stdout)
        self.redirector.text_written.connect(self.append_log)
        sys.stdout = self.redirector
        sys.stderr = self.redirector

        self.init_ui()
        self.load_config_to_ui()

    def init_ui(self):
        # 整体暗黑科技风 QSS 样式表
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0F172A;
            }
            QWidget {
                color: #F8FAFC;
                font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
                margin-top: 12px;
                padding: 14px 10px 10px 10px;
                font-weight: bold;
                font-size: 13px;
                color: #38BDF8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background-color: #0F172A;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 6px 10px;
                color: #F8FAFC;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #38BDF8;
            }
            QCheckBox {
                spacing: 8px;
                color: #E2E8F0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #475569;
                background-color: #0F172A;
            }
            QCheckBox::indicator:checked {
                background-color: #10B981;
                border: 1px solid #10B981;
            }
            QPushButton {
                background-color: #334155;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 500;
                color: #F8FAFC;
            }
            QPushButton:hover {
                background-color: #475569;
                border: 1px solid #64748B;
            }
            QPushButton:pressed {
                background-color: #1E293B;
            }
            QTextEdit {
                background-color: #080D1A;
                border: 1px solid #1E293B;
                border-radius: 8px;
                padding: 8px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 12px;
                line-height: 1.4;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        # 1. 顶部 Header 导航卡片
        header_card = QFrame()
        header_card.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px 12px;
            }
        """)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(8, 6, 8, 6)

        title_vbox = QVBoxLayout()
        title_lbl = QLabel("🎓 雨课堂全自动值守引擎 (Yuketang Auto Answer)")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38BDF8;")
        sub_lbl = QLabel("纯本地运行 · 智能大屏课件同步 · 随堂测验秒级出解 · 自动自愈重启")
        sub_lbl.setStyleSheet("font-size: 11px; color: #94A3B8;")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(sub_lbl)
        header_layout.addLayout(title_vbox)

        header_layout.addStretch()

        # 状态指示胶囊
        self.status_pill = QLabel("● 系统已就绪 (待启动)")
        self.status_pill.setStyleSheet("""
            background-color: #334155;
            color: #94A3B8;
            font-size: 12px;
            font-weight: bold;
            border-radius: 12px;
            padding: 6px 14px;
        """)
        header_layout.addWidget(self.status_pill)

        main_layout.addWidget(header_card)

        # 2. 中部核心区域（左侧配置面板，右侧实时日志终端）
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        # 左侧控制与配置面板
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(10)

        # 核心启动大按钮
        self.btn_toggle_run = QPushButton("🚀 启动全自动值守")
        self.btn_toggle_run.setFixedHeight(46)
        self.btn_toggle_run.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                border: none;
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
                color: #FFFFFF;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.btn_toggle_run.clicked.connect(self.toggle_engine)
        left_layout.addWidget(self.btn_toggle_run)

        # 快捷工具栏
        tools_group = QGroupBox("🛠️ 快捷工具箱")
        tools_layout = QHBoxLayout(tools_group)
        tools_layout.setSpacing(8)

        self.btn_refresh_screen = QPushButton("🔄 刷新大屏")
        self.btn_refresh_screen.setToolTip("专为 VIP / 扫码进班设计，强制刷新课堂大屏同步课件与 WebSocket")
        self.btn_refresh_screen.clicked.connect(self.action_refresh_screen)
        tools_layout.addWidget(self.btn_refresh_screen)

        self.btn_login_helper = QPushButton("📱 扫码登录")
        self.btn_login_helper.setToolTip("首次使用唤起 Edge 进行雨课堂微信扫码并持久化凭据")
        self.btn_login_helper.clicked.connect(self.action_open_login_helper)
        tools_layout.addWidget(self.btn_login_helper)

        self.btn_direct_lesson = QPushButton("🎯 直连课堂")
        self.btn_direct_lesson.setToolTip("手动输入课堂链接或 Lesson ID 瞬间直达大屏")
        self.btn_direct_lesson.clicked.connect(self.action_direct_navigate)
        tools_layout.addWidget(self.btn_direct_lesson)

        left_layout.addWidget(tools_group)

        # 配置参数面板
        cfg_group = QGroupBox("⚙️ 参数配置")
        cfg_form = QFormLayout(cfg_group)
        cfg_form.setSpacing(10)
        cfg_form.setLabelAlignment(Qt.AlignRight)

        # API Key
        key_hbox = QHBoxLayout()
        self.edit_key = QLineEdit()
        self.edit_key.setEchoMode(QLineEdit.Password)
        self.edit_key.setPlaceholderText("填入 sk- 开头的 API Key")
        self.btn_toggle_key = QPushButton("👁️")
        self.btn_toggle_key.setFixedWidth(36)
        self.btn_toggle_key.clicked.connect(self.toggle_key_visibility)
        key_hbox.addWidget(self.edit_key)
        key_hbox.addWidget(self.btn_toggle_key)
        cfg_form.addRow("API Key:", key_hbox)

        # API Base
        self.edit_api_base = QLineEdit("https://tokenrhythm.studio/v1")
        cfg_form.addRow("API 节点:", self.edit_api_base)

        # 模型选择
        self.combo_model = QComboBox()
        self.combo_model.setEditable(True)
        self.combo_model.addItems([
            "deepseek-v4-flash-0731",
            "glm-5.3-flash",
            "qwen3.7-flash",
            "deepseek-chat",
            "gpt-4o-mini"
        ])
        cfg_form.addRow("主选模型:", self.combo_model)

        # 雨课堂主域名
        self.edit_base_url = QLineEdit("https://www.yuketang.cn")
        cfg_form.addRow("雨课堂域名:", self.edit_base_url)

        # 监听间隔
        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setRange(0.5, 10.0)
        self.spin_interval.setSingleStep(0.5)
        self.spin_interval.setValue(1.0)
        cfg_form.addRow("监听间隔 (秒):", self.spin_interval)

        # 开关项容器
        switches_vbox = QVBoxLayout()
        switches_vbox.setSpacing(8)

        self.chk_multimodal = QCheckBox("👁️ 开启多模态视觉看图解题 (支持电路/几何/图表)")
        self.chk_multimodal.setToolTip("遇到非文字图形题时，将屏幕截图送至视觉大模型高精度求解")
        switches_vbox.addWidget(self.chk_multimodal)

        self.chk_auto_submit = QCheckBox("⚡ 自动点击最终提交答案 (关闭后只填不交)")
        self.chk_auto_submit.setChecked(True)
        switches_vbox.addWidget(self.chk_auto_submit)

        self.chk_headless = QCheckBox("👻 无头静默模式 (不弹出 Edge 界面，纯后台运行)")
        switches_vbox.addWidget(self.chk_headless)

        cfg_form.addRow("功能特性:", switches_vbox)

        # 保存配置按钮
        self.btn_save_cfg = QPushButton("💾 保存配置")
        self.btn_save_cfg.clicked.connect(self.save_config_from_ui)
        cfg_form.addRow("", self.btn_save_cfg)

        left_layout.addWidget(cfg_group)
        left_layout.addStretch()

        splitter.addWidget(left_widget)

        # 右侧日志终端面板
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)

        log_top_hbox = QHBoxLayout()
        log_title = QLabel("🖥️ 实时运行监视控制台")
        log_title.setStyleSheet("font-weight: bold; color: #38BDF8; font-size: 13px;")
        log_top_hbox.addWidget(log_title)

        log_top_hbox.addStretch()

        self.chk_auto_scroll = QCheckBox("自动滚屏")
        self.chk_auto_scroll.setChecked(True)
        log_top_hbox.addWidget(self.chk_auto_scroll)

        self.btn_clear_log = QPushButton("🗑️ 清空日志")
        self.btn_clear_log.setFixedHeight(28)
        self.btn_clear_log.clicked.connect(self.clear_logs)
        log_top_hbox.addWidget(self.btn_clear_log)

        right_layout.addLayout(log_top_hbox)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        right_layout.addWidget(self.txt_log)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)

        main_layout.addWidget(splitter)

        # 底部状态栏小贴士
        footer_lbl = QLabel("💡 提示：进入课堂后系统将自动刷新页面同步课件；如遇课件显示延迟，可点击【🔄 刷新大屏】。上课期间电脑防休眠锁会自动激活。")
        footer_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        main_layout.addWidget(footer_lbl)

    def toggle_key_visibility(self):
        if self.edit_key.echoMode() == QLineEdit.Password:
            self.edit_key.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_key.setText("🙈")
        else:
            self.edit_key.setEchoMode(QLineEdit.Password)
            self.btn_toggle_key.setText("👁️")

    def load_config_to_ui(self):
        cfg_file = os.path.join(BASE_DIR, "config.json")
        if not os.path.exists(cfg_file):
            cfg_file = os.path.join(BASE_DIR, "config.example.json")

        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.edit_key.setText(data.get("api_key", ""))
                self.edit_api_base.setText(data.get("api_base", "https://tokenrhythm.studio/v1"))
                models = data.get("models", [])
                if models:
                    self.combo_model.setCurrentText(models[0])
                self.edit_base_url.setText(data.get("yuketang_base_url", "https://www.yuketang.cn"))
                self.chk_multimodal.setChecked(data.get("enable_multimodal", False))
                self.chk_auto_submit.setChecked(data.get("auto_submit", True))
                self.chk_headless.setChecked(data.get("headless", False))
                self.spin_interval.setValue(float(data.get("listen_interval", 1.0)))
            except Exception as e:
                self.append_log(f"⚠️ 读取配置文件提示: {e}\n")

    def save_config_from_ui(self, show_msg=True):
        cfg_file = os.path.join(BASE_DIR, "config.json")
        data = {}
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        data["api_key"] = self.edit_key.text().strip()
        data["api_base"] = self.edit_api_base.text().strip()
        cur_m = self.combo_model.currentText().strip()
        if cur_m:
            models = data.get("models", [])
            if cur_m in models:
                models.remove(cur_m)
            models.insert(0, cur_m)
            data["models"] = models

        data["yuketang_base_url"] = self.edit_base_url.text().strip()
        data["enable_multimodal"] = self.chk_multimodal.isChecked()
        data["auto_submit"] = self.chk_auto_submit.isChecked()
        data["headless"] = self.chk_headless.isChecked()
        data["listen_interval"] = self.spin_interval.value()

        try:
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if show_msg:
                QMessageBox.information(self, "成功", "✅ 配置已成功保存至 config.json！")
        except Exception as e:
            if show_msg:
                QMessageBox.critical(self, "错误", f"保存配置失败: {e}")

    def append_log(self, text):
        # 简单色彩增强
        color = "#E2E8F0"
        if "🚨" in text or "侦测到" in text:
            color = "#F59E0B"
        elif "🎉" in text or "秒级出解" in text or "已提交" in text:
            color = "#10B981"
        elif "🧠" in text or "思考中" in text:
            color = "#60A5FA"
        elif "⚠️" in text or "温馨提示" in text:
            color = "#FBBF24"
        elif "❌" in text or "错误" in text or "异常" in text:
            color = "#F87171"
        elif "🎯" in text:
            color = "#A78BFA"

        html_text = f"<span style='color: {color}; white-space: pre-wrap;'>{self.escape_html(text)}</span>"
        self.txt_log.insertHtml(html_text)
        if self.chk_auto_scroll.isChecked():
            self.txt_log.moveCursor(QTextCursor.End)

    def escape_html(self, s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def clear_logs(self):
        self.txt_log.clear()

    def update_status_badge(self, status_dict):
        state = status_dict.get("state", "")
        text = status_dict.get("text", "")
        if state == "waiting":
            self.status_pill.setText(f"● {text}")
            self.status_pill.setStyleSheet("background-color: #1E293B; color: #38BDF8; font-size: 12px; font-weight: bold; border-radius: 12px; padding: 6px 14px; border: 1px solid #38BDF8;")
        elif state == "connecting" or state == "syncing":
            self.status_pill.setText(f"● {text}")
            self.status_pill.setStyleSheet("background-color: #78350F; color: #FBBF24; font-size: 12px; font-weight: bold; border-radius: 12px; padding: 6px 14px;")
        elif state == "listening":
            self.status_pill.setText(f"● 🟢 正在值守: {text}")
            self.status_pill.setStyleSheet("background-color: #064E3B; color: #34D399; font-size: 12px; font-weight: bold; border-radius: 12px; padding: 6px 14px; border: 1px solid #059669;")
        elif state == "solving":
            self.status_pill.setText(f"● 🧠 正在解题: {text}")
            self.status_pill.setStyleSheet("background-color: #1E3A8A; color: #60A5FA; font-size: 12px; font-weight: bold; border-radius: 12px; padding: 6px 14px;")
        elif state == "submitted":
            self.status_pill.setText(f"● ✅ 答题提交成功")
            self.status_pill.setStyleSheet("background-color: #064E3B; color: #34D399; font-size: 12px; font-weight: bold; border-radius: 12px; padding: 6px 14px;")
        elif state == "stopped":
            self.status_pill.setText("● 系统已停止")
            self.status_pill.setStyleSheet("background-color: #334155; color: #94A3B8; font-size: 12px; font-weight: bold; border-radius: 12px; padding: 6px 14px;")

    def toggle_engine(self):
        if not self.is_running:
            # 启动
            self.save_config_from_ui(show_msg=False)
            if not self.edit_key.text().strip():
                QMessageBox.warning(self, "提示", "请先填入有效的 API Key！")
                return

            self.is_running = True
            self.btn_toggle_run.setText("⏹️ 停止全自动值守")
            self.btn_toggle_run.setStyleSheet("""
                QPushButton {
                    background-color: #EF4444;
                    border: none;
                    border-radius: 8px;
                    font-size: 15px;
                    font-weight: bold;
                    color: #FFFFFF;
                }
                QPushButton:hover {
                    background-color: #DC2626;
                }
                QPushButton:pressed {
                    background-color: #B91C1C;
                }
            """)
            self.status_pill.setText("● 正在唤起自动化引擎...")
            self.status_pill.setStyleSheet("background-color: #78350F; color: #FBBF24; font-size: 12px; font-weight: bold; border-radius: 12px; padding: 6px 14px;")

            self.worker = AgentWorker(self.command_queue)
            self.worker.status_changed.connect(self.update_status_badge)
            self.worker.finished_signal.connect(self.on_worker_finished)
            self.worker.start()
        else:
            # 停止
            self.append_log("\n🛑 正在请求停止全自动值守引擎...\n")
            if self.worker:
                self.worker.stop()
            self.btn_toggle_run.setEnabled(False)
            self.btn_toggle_run.setText("正在停止中...")

    def on_worker_finished(self):
        self.is_running = False
        self.btn_toggle_run.setEnabled(True)
        self.btn_toggle_run.setText("🚀 启动全自动值守")
        self.btn_toggle_run.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                border: none;
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
                color: #FFFFFF;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.status_pill.setText("● 系统已停止")
        self.status_pill.setStyleSheet("background-color: #334155; color: #94A3B8; font-size: 12px; font-weight: bold; border-radius: 12px; padding: 6px 14px;")
        self.append_log("⏹️ 引擎线程已完全终止。\n")

    def action_refresh_screen(self):
        if not self.is_running:
            QMessageBox.information(self, "提示", "请先启动全自动值守引擎，再执行大屏刷新。")
            return
        self.command_queue.put(("refresh", None))
        self.append_log("👉 [用户触发] 已发送强制刷新大屏指令...\n")

    def action_open_login_helper(self):
        login_script = os.path.join(BASE_DIR, "login_helper.py")
        if not os.path.exists(login_script):
            QMessageBox.warning(self, "错误", "未找到 login_helper.py 脚本！")
            return
        self.append_log("📱 正在启动微信扫码登录助手...\n")
        try:
            subprocess.Popen([sys.executable, login_script], cwd=BASE_DIR)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"唤起扫码助手失败: {e}")

    def action_direct_navigate(self):
        if not self.is_running:
            QMessageBox.information(self, "提示", "请先启动全自动值守引擎，再使用直连功能。")
            return
        text, ok = QInputDialog.getText(self, "直连课堂", "请输入课堂完整 URL 或数字 Lesson ID:")
        if ok and text.strip():
            self.command_queue.put(("navigate", text.strip()))
            self.append_log(f"👉 [用户触发] 已发送直连课堂指令: {text.strip()}\n")

    def closeEvent(self, event):
        if self.is_running and self.worker:
            reply = QMessageBox.question(
                self, '确认退出',
                '全自动值守引擎正在运行中，关闭窗口将停止答题监听，是否确认退出？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.worker.stop()
                ykt_standalone_agent.ensure_edge_clean()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("雨课堂随堂助手")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
