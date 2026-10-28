"""NetPilot main window (PySide6). The GUI itself needs no admin rights:
privileged work goes through the local agent HTTP API."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QSystemTrayIcon,
)

from . import paths, updater, vpn
from .agent_client import AgentClient, AgentOffline, ClashClient
from .config_builder import generate, load_settings, save_settings
from .netinfo import list_adapters, list_processes

def make_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#2563eb"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(4, 4, 56, 56)
    painter.setPen(QColor("white"))
    painter.drawLine(20, 24, 44, 24)
    painter.drawLine(20, 40, 44, 40)
    painter.drawLine(44, 24, 38, 18)
    painter.drawLine(44, 24, 38, 30)
    painter.drawLine(20, 40, 26, 34)
    painter.drawLine(20, 40, 26, 46)
    painter.end()
    return QIcon(pix)


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = Signals()

    def run(self):
        try:
            self.signals.done.emit(self.fn())
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class ProcessPicker(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择正在运行的进程")
        self.resize(640, 480)
        layout = QVBoxLayout(self)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("输入进程名过滤，如 chrome")
        layout.addWidget(self.filter)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["进程名", "路径", "实例数"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.table.doubleClicked.connect(self.accept)
        self.filter.textChanged.connect(self.apply_filter)
        self.processes: list[dict] = []
        self.reload()

    def reload(self):
        self._task = Task(list_processes)
        self._task.signals.done.connect(self._processes_loaded)
        QThreadPool.globalInstance().start(self._task)

    def _processes_loaded(self, procs):
        self.processes = procs
        self.apply_filter()

    def apply_filter(self):
        text = self.filter.text().lower()
        rows = [p for p in self.processes if text in p["name"].lower() or text in (p["exe"] or "").lower()]
        self.table.setRowCount(len(rows))
        for i, proc in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(proc["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(proc["exe"] or ""))
            self.table.setItem(i, 2, QTableWidgetItem(str(len(proc["pids"]))))

    def selected_name(self) -> str:
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return item.text() if item else ""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"NetPilot · 应用分流管家 v{updater.APP_VERSION}")
        self.resize(980, 700)
        self.setWindowIcon(make_icon())
        self.agent = AgentClient()
        self.clash = ClashClient()
        self.settings = load_settings()
        self._channel_rows = []
        self.core_running = False
        self.agent_online = False
        self._tasks = set()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(8)
        self._prev_conns: dict[str, tuple[int, int, float]] = {}
        self._first_tray_message = True

        central = QWidget()
        root = QVBoxLayout(central)
        root.addLayout(self._build_header())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_rules_tab(), "分流规则")
        self.tabs.addTab(self._build_connections_tab(), "实时连接")
        self.tabs.addTab(self._build_vpn_tab(), "VPN 与网卡")
        self.tabs.addTab(self._build_logs_tab(), "日志与诊断")
        root.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.statusBar().showMessage("就绪")
        self._build_tray()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start(5000)
        self.conn_timer = QTimer(self)
        self.conn_timer.timeout.connect(self.refresh_connections)
        self.conn_timer.start(2000)
        self.vpn_timer = QTimer(self)
        self.vpn_timer.timeout.connect(self.refresh_vpn_states)
        self.vpn_timer.start(8000)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.refresh_status()
        self.refresh_adapters()
        self.refresh_vpn_states()

    # ---------- infrastructure ----------
    def name_map(self) -> dict:
        """Channel id -> display name, preferring the live channel table so
        renames in progress are reflected everywhere immediately."""
        if getattr(self, "_channel_rows", None):
            return {row["id"]: row["name_item"].text() for row in self._channel_rows}
        return {ch["id"]: ch["name"] for ch in self.settings["channels"]}

    def channel_label(self, tag: str) -> str:
        return self.name_map().get(tag, tag)

    def run_task(self, fn, on_done=None, on_error=None):
        task = Task(fn)
        self._tasks.add(task)

        def _done(value):
            self._tasks.discard(task)
            if on_done:
                on_done(value)

        def _failed(msg):
            self._tasks.discard(task)
            if on_error:
                on_error(msg)
            else:
                self.statusBar().showMessage("操作失败: " + msg, 10000)

        task.signals.done.connect(_done)
        task.signals.failed.connect(_failed)
        self._pool.start(task)

    def _build_header(self):
        layout = QHBoxLayout()
        self.status_label = QLabel("正在检查核心状态…")
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.version_label = QLabel(f"v{updater.APP_VERSION}")
        layout.addWidget(self.version_label)
        self.update_button = QPushButton("检查更新")
        self.update_button.clicked.connect(self.check_update)
        layout.addWidget(self.update_button)
        self.agent_button = QPushButton("启动核心服务（管理员）")
        self.agent_button.clicked.connect(self.start_agent)
        self.agent_button.setVisible(False)
        layout.addWidget(self.agent_button)
        self.toggle_button = QPushButton("启动分流")
        self.toggle_button.clicked.connect(self.toggle_core)
        layout.addWidget(self.toggle_button)
        return layout

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.showNormal)
        menu.addAction(show_action)
        toggle_action = QAction("启动/停止分流", self)
        toggle_action.triggered.connect(self.toggle_core)
        menu.addAction(toggle_action)
        quit_action = QAction("退出界面（核心保持运行）", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def closeEvent(self, event):
        if self._first_tray_message:
            self.tray.showMessage("NetPilot", "界面已最小化到托盘，分流核心保持运行。", QSystemTrayIcon.Information, 4000)
            self._first_tray_message = False
        event.ignore()
        self.hide()

    def showEvent(self, event):
        # The settings file may have changed while we were hidden (e.g. edited
        # externally); resync the rules tables when the window is shown again.
        super().showEvent(event)
        if hasattr(self, "process_table"):
            self.settings = load_settings()
            self._rebuild_channel_table()
            self._fill_rule_table(self.process_table, self.settings.get("process_rules", []), "process")
            self._fill_rule_table(self.domain_table, self.settings.get("domain_rules", []), "suffix")
            self._fill_channel_combo(self.default_combo, self.settings.get("default_channel", "direct"))

    def _tab_changed(self, index):
        if index == 1:
            self.refresh_connections()
        elif index == 2:
            self.refresh_adapters()
            self.refresh_vpn_states()
        elif index == 3:
            self.refresh_logs()

    # ---------- status / core control ----------
    def refresh_status(self):
        def work():
            try:
                return self.agent.status()
            except AgentOffline:
                return None

        self.run_task(work, self._update_status)

    def _update_status(self, status):
        self.agent_online = status is not None
        self.agent_button.setVisible(not self.agent_online)
        if not self.agent_online:
            self.core_running = False
            self.status_label.setText("🔴 核心服务离线（分流未生效）")
            self.toggle_button.setText("启动分流")
            self.toggle_button.setEnabled(False)
            return
        self.toggle_button.setEnabled(True)
        self.core_running = bool(status.get("singbox_running"))
        if self.core_running:
            self.status_label.setText(f"🟢 分流运行中  (sing-box pid {status.get('singbox_pid')})")
            self.toggle_button.setText("停止分流")
        else:
            self.status_label.setText("⚪ 核心服务在线，分流已停止")
            self.toggle_button.setText("启动分流")

    def start_agent(self):
        script = paths.ROOT / "scripts" / "start_agent.ps1"
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-File", str(script)], creationflags=subprocess.CREATE_NO_WINDOW)
        self.statusBar().showMessage("已请求管理员授权，请在 UAC 弹窗中点“是”…", 10000)
        QTimer.singleShot(6000, self.refresh_status)

    def toggle_core(self):
        if not self.agent_online:
            self.start_agent()
            return
        self.toggle_button.setEnabled(False)
        if self.core_running:
            self.run_task(self.agent.stop,
                          lambda r: (self.statusBar().showMessage(r.get("message", ""), 8000), self.refresh_status()))
        else:
            self.apply_settings(start_only=True)
        QTimer.singleShot(2500, lambda: self.toggle_button.setEnabled(True))

    # ---------- auto update ----------
    def check_update(self):
        self.update_button.setEnabled(False)
        self.statusBar().showMessage("正在检查 GitHub 最新版本…", 8000)

        def done(info):
            self.update_button.setEnabled(True)
            if not updater.is_newer(info["tag"]):
                self.statusBar().showMessage(f"当前已是最新版本（{info['tag']}）", 10000)
                return
            notes = info["notes"].splitlines()[0] if info["notes"] else ""
            answer = QMessageBox.question(
                self, "发现新版本",
                f"当前版本 v{updater.APP_VERSION}，最新版本 {info['tag']}。\n{notes}\n\n"
                "是否下载并自动更新？更新会重启 NetPilot，规则和配置保留。")
            if answer == QMessageBox.Yes:
                self._download_update(info)

        def failed(msg):
            self.update_button.setEnabled(True)
            self.statusBar().showMessage("检查更新失败：" + msg, 12000)

        self.run_task(updater.check_latest, done, failed)

    def _download_update(self, info):
        self.update_button.setEnabled(False)
        dest = paths.ROOT / "build" / "update" / info["zip_name"]
        progress = {"pct": -1, "done": 0, "total": 0}

        def cb(done, total):
            progress["done"], progress["total"] = done, total
            if total:
                progress["pct"] = int(done * 100 / total)

        def work():
            updater.download_zip(info["zip_url"], dest, cb)
            return dest

        def done(path):
            self._progress_timer.stop()
            self.statusBar().showMessage("下载完成，正在应用更新，程序将自动重启…", 20000)
            self._launch_updater(path)

        def failed(msg):
            self._progress_timer.stop()
            self.update_button.setEnabled(True)
            self.statusBar().showMessage("下载失败：" + msg, 12000)

        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(
            lambda: self.statusBar().showMessage(
                f"正在下载 {info['tag']}：{progress['pct']}%"
                f"（{progress['done'] // 1048576}MB / {progress['total'] // 1048576}MB）", 30000)
            if progress["pct"] >= 0 else None)
        self._progress_timer.start(500)
        self.run_task(work, done, failed)

    def _launch_updater(self, zip_path):
        script = paths.ROOT / "scripts" / "apply_update.ps1"
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
             "Start-Process powershell -Verb RunAs -ArgumentList "
             f"'-NoProfile -ExecutionPolicy Bypass -File \"{script}\" -ZipPath \"{zip_path}\"'"],
            creationflags=subprocess.CREATE_NO_WINDOW)
        QApplication.quit()

    # ---------- rules tab ----------
    def _build_rules_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        default_row = QHBoxLayout()
        default_row.addWidget(QLabel("未匹配规则的流量走默认通道："))
        self.default_combo = QComboBox()
        default_row.addWidget(self.default_combo)
        default_row.addStretch()
        layout.addLayout(default_row)

        channel_group = QGroupBox("通道 → 网卡绑定（名称可双击重命名，规则与默认通道同步更新）")
        channel_layout = QVBoxLayout(channel_group)
        self.channel_table = QTableWidget(0, 4)
        self.channel_table.setHorizontalHeaderLabels(["通道名称", "绑定网卡（可下拉或手动输入）", "网卡状态", ""])
        self.channel_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.channel_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.channel_table.setColumnWidth(0, 150)
        self.channel_table.setColumnWidth(3, 46)
        self.channel_table.verticalHeader().setVisible(False)
        self.channel_table.setMaximumHeight(200)
        self.channel_table.itemChanged.connect(lambda _item: self._sync_channel_names())
        channel_layout.addWidget(self.channel_table)
        new_channel_btn = QPushButton("＋ 新建通道")
        new_channel_btn.clicked.connect(self.add_channel)
        channel_layout.addWidget(new_channel_btn, alignment=Qt.AlignLeft)
        layout.addWidget(channel_group)
        self._rebuild_channel_table()
        self._fill_channel_combo(self.default_combo, self.settings.get("default_channel", "direct"))

        self.process_group, self.process_table = self._make_rule_group(
            "进程规则（按 exe 名称匹配，自上而下生效）", ["启用", "进程名", "通道"])
        layout.addWidget(self.process_group)
        self.domain_group, self.domain_table = self._make_rule_group(
            "域名/IP 规则（后缀匹配，如 google.com；进程规则优先）", ["启用", "域名后缀", "通道"])
        layout.addWidget(self.domain_group)

        button_row = QHBoxLayout()
        add_process = QPushButton("＋ 添加运行进程")
        add_process.clicked.connect(self.add_process_rule)
        add_manual = QPushButton("＋ 手动输入进程名")
        add_manual.clicked.connect(self.add_process_manual)
        add_domain = QPushButton("＋ 添加域名规则")
        add_domain.clicked.connect(self.add_domain_rule)
        remove = QPushButton("－ 删除选中规则")
        remove.clicked.connect(self.remove_selected_rules)
        up = QPushButton("上移")
        up.clicked.connect(lambda: self.move_rule(-1))
        down = QPushButton("下移")
        down.clicked.connect(lambda: self.move_rule(1))
        for btn in (add_process, add_manual, add_domain, remove, up, down):
            button_row.addWidget(btn)
        button_row.addStretch()
        apply_btn = QPushButton("💾 保存并应用")
        apply_btn.setStyleSheet("font-weight:bold;padding:6px 18px;")
        apply_btn.clicked.connect(lambda: self.apply_settings())
        button_row.addWidget(apply_btn)
        layout.addLayout(button_row)

        self._fill_rule_table(self.process_table, self.settings.get("process_rules", []), "process")
        self._fill_rule_table(self.domain_table, self.settings.get("domain_rules", []), "suffix")
        return tab

    def _make_rule_group(self, title, headers):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(table)
        return group, table

    def _fill_rule_table(self, table, rules, key):
        table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            enabled = QCheckBox()
            enabled.setChecked(rule.get("enabled", True))
            table.setCellWidget(row, 0, enabled)
            table.setItem(row, 1, QTableWidgetItem(rule[key]))
            combo = QComboBox()
            table.setCellWidget(row, 2, combo)
            self._fill_channel_combo(combo, rule["channel"])

    def add_process_rule(self):
        picker = ProcessPicker(self)
        if picker.exec() and picker.selected_name():
            self._append_rule(self.process_table, "process", picker.selected_name())

    def add_process_manual(self):
        name, ok = QInputDialog.getText(self, "添加进程规则", "进程 exe 名称（如 chrome.exe）：")
        if ok and name.strip():
            self._append_rule(self.process_table, "process", name.strip())

    def add_domain_rule(self):
        suffix, ok = QInputDialog.getText(self, "添加域名规则", "域名后缀（如 google.com 或 .company.local）：")
        if ok and suffix.strip():
            self._append_rule(self.domain_table, "suffix", suffix.strip().lstrip("*."))

    def _append_rule(self, table, key, value):
        self._fill_rule_table(table, self._read_rule_table(table, key) + [
            {"enabled": True, key: value, "channel": self.settings.get("default_channel", "direct")}
        ], key)

    def _read_rule_table(self, table, key):
        rules = []
        for row in range(table.rowCount()):
            enabled = table.cellWidget(row, 0)
            combo = table.cellWidget(row, 2)
            item = table.item(row, 1)
            if not item or not combo:
                continue
            rules.append({
                "enabled": enabled.isChecked() if enabled else True,
                key: item.text().strip(),
                "channel": combo.currentData(),
            })
        return rules

    def remove_selected_rules(self):
        for table, key in ((self.process_table, "process"), (self.domain_table, "suffix")):
            rows = sorted({i.row() for i in table.selectedIndexes()}, reverse=True)
            if rows:
                rules = self._read_rule_table(table, key)
                for row in rows:
                    if 0 <= row < len(rules):
                        rules.pop(row)
                self._fill_rule_table(table, rules, key)

    def move_rule(self, delta):
        for table, key in ((self.process_table, "process"), (self.domain_table, "suffix")):
            rows = sorted({i.row() for i in table.selectedIndexes()})
            if len(rows) != 1:
                continue
            row = rows[0]
            rules = self._read_rule_table(table, key)
            target = row + delta
            if 0 <= target < len(rules):
                rules[row], rules[target] = rules[target], rules[row]
                self._fill_rule_table(table, rules, key)
                table.selectRow(target)

    def _append_channel_row(self, channel: dict) -> None:
        row = len(self._channel_rows)
        self.channel_table.insertRow(row)
        name_item = QTableWidgetItem(channel["name"])
        name_item.setData(Qt.UserRole, channel["id"])
        self.channel_table.setItem(row, 0, name_item)
        iface_combo = QComboBox()
        iface_combo.setEditable(True)
        iface_combo.setCurrentText(channel.get("interface", ""))
        self.channel_table.setCellWidget(row, 1, iface_combo)
        self.channel_table.setItem(row, 2, QTableWidgetItem("检测中…"))
        delete_btn = QPushButton("✕")
        delete_btn.setToolTip("删除此通道（被规则使用或为默认通道时不可删）")
        delete_btn.setMaximumWidth(46)
        delete_btn.clicked.connect(lambda _=False, cid=channel["id"]: self.delete_channel(cid))
        self.channel_table.setCellWidget(row, 3, delete_btn)
        self._channel_rows.append({"id": channel["id"], "name_item": name_item, "iface_combo": iface_combo})
        self.refresh_adapters()

    def _rebuild_channel_table(self) -> None:
        self.channel_table.blockSignals(True)
        self.channel_table.setRowCount(0)
        self._channel_rows = []
        for channel in self.settings["channels"]:
            self._append_channel_row(channel)
        self.channel_table.blockSignals(False)

    def _fill_channel_combo(self, combo: QComboBox, selected_id) -> None:
        combo.blockSignals(True)
        combo.clear()
        for row in self._channel_rows:
            combo.addItem(row["name_item"].text(), row["id"])
        index = combo.findData(selected_id)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _refresh_all_combos(self) -> None:
        self._fill_channel_combo(self.default_combo, self.default_combo.currentData())
        for table in (self.process_table, self.domain_table):
            for row in range(table.rowCount()):
                combo = table.cellWidget(row, 2)
                if combo:
                    self._fill_channel_combo(combo, combo.currentData())

    def _sync_channel_names(self) -> None:
        """After a rename, update every dropdown's display text in place."""
        names = self.name_map()

        def relabel(combo):
            for i in range(combo.count()):
                cid = combo.itemData(i)
                combo.setItemText(i, names.get(cid, cid))

        relabel(self.default_combo)
        for table in (self.process_table, self.domain_table):
            for row in range(table.rowCount()):
                combo = table.cellWidget(row, 2)
                if combo:
                    relabel(combo)

    def add_channel(self) -> None:
        existing = {row["id"] for row in self._channel_rows}
        n = 1
        while f"ch{n}" in existing:
            n += 1
        self._append_channel_row({"id": f"ch{n}", "name": f"新通道{n}", "interface": ""})
        self._refresh_all_combos()
        self.statusBar().showMessage("已添加新通道：请重命名、选择绑定网卡，然后点“保存并应用”。", 10000)

    def delete_channel(self, channel_id: str) -> None:
        if len(self._channel_rows) <= 1:
            QMessageBox.warning(self, "无法删除", "至少需要保留一个通道。")
            return
        if self.default_combo.currentData() == channel_id:
            QMessageBox.warning(self, "无法删除", "该通道正在作为默认通道使用，请先更换默认通道。")
            return
        used_by = []
        for table in (self.process_table, self.domain_table):
            for row in range(table.rowCount()):
                combo = table.cellWidget(row, 2)
                if combo and combo.currentData() == channel_id:
                    used_by.append(table.item(row, 1).text())
        if used_by:
            QMessageBox.warning(self, "无法删除",
                                "以下规则正在使用该通道，请先修改或删除这些规则：\n" + "\n".join(used_by))
            return
        index = next(i for i, row in enumerate(self._channel_rows) if row["id"] == channel_id)
        self.channel_table.blockSignals(True)
        self.channel_table.removeRow(index)
        self._channel_rows.pop(index)
        self.channel_table.blockSignals(False)
        self._refresh_all_combos()
        self.statusBar().showMessage("通道已删除，点“保存并应用”生效。", 8000)

    def apply_settings(self, start_only=False):
        channels = []
        for row in self._channel_rows:
            name = row["name_item"].text().strip() or row["id"]
            channels.append({
                "id": row["id"],
                "name": name,
                "interface": row["iface_combo"].currentText().strip(),
            })
        missing = [c["name"] for c in channels if not c["interface"]]
        if missing:
            QMessageBox.warning(self, "无法应用", "以下通道还没有绑定网卡：\n" + "\n".join(missing))
            return
        self.settings["channels"] = channels
        self.settings["default_channel"] = self.default_combo.currentData()
        self.settings["process_rules"] = self._read_rule_table(self.process_table, "process")
        self.settings["domain_rules"] = self._read_rule_table(self.domain_table, "suffix")
        save_settings(self.settings)
        generate()
        self._refresh_all_combos()

        def work():
            if self.core_running and not start_only:
                return self.agent.restart()
            return self.agent.start()

        def done(result):
            message = result.get("message", "")
            self.statusBar().showMessage(("已应用: " if not start_only else "") + message.splitlines()[0], 10000)
            self.refresh_status()

        self.run_task(work, done)

    # ---------- connections tab ----------
    def _build_connections_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        hint = QLabel("每 2 秒自动刷新，按下载速率排序。通道列显示该连接实际使用的出口。")
        layout.addWidget(hint)
        self.conn_table = QTableWidget(0, 7)
        self.conn_table.setHorizontalHeaderLabels(["进程", "目标", "通道", "匹配规则", "↓速率", "↑速率", "累计 ↓/↑"])
        self.conn_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.conn_table.verticalHeader().setVisible(False)
        self.conn_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.conn_table)
        return tab

    @staticmethod
    def _fmt_rate(value: float) -> str:
        if value > 1024 * 1024:
            return f"{value / 1024 / 1024:.1f} MB/s"
        if value > 1024:
            return f"{value / 1024:.1f} KB/s"
        return f"{value:.0f} B/s"

    @staticmethod
    def _fmt_bytes(value: float) -> str:
        if value > 1024 ** 3:
            return f"{value / 1024 ** 3:.2f} GB"
        if value > 1024 ** 2:
            return f"{value / 1024 ** 2:.1f} MB"
        return f"{value / 1024:.1f} KB"

    def refresh_connections(self):
        if not self.core_running or self.tabs.currentIndex() != 1:
            return

        def work():
            try:
                return self.clash.connections()
            except Exception:
                return None

        self.run_task(work, self._update_connections)

    def _update_connections(self, connections):
        if connections is None:
            return
        now = time.time()
        ids = set(self.name_map())
        rows = []
        current_ids = set()
        for conn in connections:
            cid = conn.get("id")
            meta = conn.get("metadata", {})
            up, down = conn.get("upload", 0), conn.get("download", 0)
            current_ids.add(cid)
            prev = self._prev_conns.get(cid)
            down_rate = max(0, down - prev[1]) / max(0.1, now - prev[2]) if prev else 0.0
            up_rate = max(0, up - prev[0]) / max(0.1, now - prev[2]) if prev else 0.0
            self._prev_conns[cid] = (up, down, now)
            process = Path(meta.get("process") or meta.get("processPath") or "?").name
            host = meta.get("host") or meta.get("destinationIP") or ""
            target = f"{host}:{meta.get('destinationPort', '')}"
            chains = conn.get("chains") or []
            channel = next((c for c in chains if c in ids), chains[0] if chains else "?")
            rows.append({
                "process": process, "target": target, "channel": channel,
                "rule": f"{conn.get('rule', '')} {conn.get('rulePayload', '')}".strip(),
                "down_rate": down_rate, "up_rate": up_rate, "down": down, "up": up,
            })
        for cid in list(self._prev_conns):
            if cid not in current_ids:
                del self._prev_conns[cid]
        rows.sort(key=lambda r: r["down_rate"] + r["up_rate"], reverse=True)
        rows = rows[:200]
        self.conn_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = [
                row["process"], row["target"], self.channel_label(row["channel"]), row["rule"],
                self._fmt_rate(row["down_rate"]), self._fmt_rate(row["up_rate"]),
                f"{self._fmt_bytes(row['down'])} / {self._fmt_bytes(row['up'])}",
            ]
            for col, value in enumerate(values):
                self.conn_table.setItem(i, col, QTableWidgetItem(value))

    # ---------- VPN tab ----------
    def _build_vpn_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        fo_group = QGroupBox("快橙 FastOrange（国际外网）")
        fo = QFormLayout(fo_group)
        self.fo_state = QLabel("检测中…")
        fo.addRow("状态：", self.fo_state)
        self.fo_node = QLabel("-")
        fo.addRow("当前节点：", self.fo_node)
        fo_buttons = QHBoxLayout()
        for text, handler in (("连接", self.fo_connect), ("断开", self.fo_disconnect), ("刷新", self.refresh_vpn_states)):
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            fo_buttons.addWidget(btn)
        self.fo_server_input = QLineEdit()
        self.fo_server_input.setPlaceholderText("节点匹配，如 *gc x13（留空列出节点）")
        fo_buttons.addWidget(self.fo_server_input)
        switch_btn = QPushButton("切换节点")
        switch_btn.clicked.connect(self.fo_switch)
        fo_buttons.addWidget(switch_btn)
        fo.addRow(fo_buttons)
        layout.addWidget(fo_group)

        seco_group = QGroupBox("SecoClient（公司内网）")
        seco = QFormLayout(seco_group)
        self.seco_state = QLabel("检测中…")
        seco.addRow("状态：", self.seco_state)
        seco_buttons = QHBoxLayout()
        for text, handler in (("连接", self.seco_connect), ("断开", self.seco_disconnect), ("刷新", self.refresh_vpn_states)):
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            seco_buttons.addWidget(btn)
        seco.addRow(seco_buttons)
        seco.addRow(QLabel("首次使用需在 SecoClient 窗口手动登录；连接异常时关闭程序重试几次。"))
        layout.addWidget(seco_group)

        adapter_group = QGroupBox("网卡状态")
        adapter_layout = QVBoxLayout(adapter_group)
        self.adapter_table = QTableWidget(0, 3)
        self.adapter_table.setHorizontalHeaderLabels(["网卡", "状态", "IPv4 地址"])
        self.adapter_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.adapter_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.adapter_table.verticalHeader().setVisible(False)
        self.adapter_table.setEditTriggers(QTableWidget.NoEditTriggers)
        adapter_layout.addWidget(self.adapter_table)
        layout.addWidget(adapter_group)
        return tab

    def refresh_vpn_states(self):
        if self.tabs.currentIndex() != 2:
            return
        self.run_task(vpn.fastorange_state, self._update_fo_state)
        self.run_task(vpn.seco_state, self._update_seco_state)

    def _update_fo_state(self, result):
        state_map = {"connected": "🟢 已连接", "disconnected": "⚪ 已断开",
                     "connecting": "🟡 连接中", "not_running": "⚪ 未运行"}
        self.fo_state.setText(state_map.get(result.get("state"), result.get("state", "未知")))
        self.fo_node.setText(result.get("node") or "-")

    def _update_seco_state(self, result):
        state_map = {
            "connected": "🟢 已连接", "disconnected": "⚪ 已断开",
            "login_required": "🟡 等待手动登录", "not_running": "⚪ 未运行",
        }
        self.seco_state.setText(state_map.get(result.get("state"), result.get("state", "未知")))

    def fo_connect(self):
        self._vpn_action(vpn.fastorange_connect)

    def fo_disconnect(self):
        self._vpn_action(vpn.fastorange_disconnect)

    def fo_switch(self):
        name = self.fo_server_input.text().strip()
        self._vpn_action(lambda: vpn.fastorange_select_server(name))

    def seco_connect(self):
        self._vpn_action(vpn.seco_connect)

    def seco_disconnect(self):
        self._vpn_action(vpn.seco_disconnect)

    def _vpn_action(self, fn):
        self.statusBar().showMessage("正在执行 VPN 操作，请稍候（约 5–30 秒）…", 15000)

        def done(result):
            text = result if isinstance(result, str) else str(result)
            self.statusBar().showMessage(text.strip().splitlines()[-1][:150] if text.strip() else "完成", 10000)
            self.refresh_vpn_states()
            if self.core_running:
                self.run_task(self.agent.fixroutes)

        self.run_task(fn, done)

    def refresh_adapters(self):
        def work():
            return list_adapters()

        def done(adapters):
            self._adapters = adapters
            names = [a["name"] for a in adapters]
            for row in self._channel_rows:
                combo = row["iface_combo"]
                current = combo.currentText()
                combo.clear()
                combo.addItems(names)
                combo.setCurrentText(current)
            self.adapter_table.setRowCount(len(adapters))
            for i, adapter in enumerate(adapters):
                self.adapter_table.setItem(i, 0, QTableWidgetItem(adapter["name"]))
                self.adapter_table.setItem(i, 1, QTableWidgetItem("🟢 在线" if adapter["is_up"] else "⚪ 离线"))
                self.adapter_table.setItem(i, 2, QTableWidgetItem(", ".join(adapter["ipv4"])))
            for i, row in enumerate(self._channel_rows):
                bound = row["iface_combo"].currentText()
                match = next((a for a in adapters if a["name"] == bound), None)
                if match and match["is_up"]:
                    text = "🟢 " + (", ".join(match["ipv4"]) or "在线")
                elif bound:
                    text = "⚪ 离线/未找到"
                else:
                    text = "未绑定"
                self.channel_table.setItem(i, 2, QTableWidgetItem(text))

        self.run_task(work, done)

    # ---------- logs tab ----------
    def _build_logs_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        buttons = QHBoxLayout()
        for text, handler in (
            ("刷新日志", self.refresh_logs),
            ("修复路由", self.fix_routes),
            ("网络诊断", self.run_diagnostics),
            ("打开安装目录", self.open_root),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            buttons.addWidget(btn)
        self.log_auto = QCheckBox("自动刷新")
        buttons.addWidget(self.log_auto)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(5000)
        layout.addWidget(self.log_text)
        note = QLabel("DNS 说明：本机的安全驱动会过滤 53 端口，NetPilot 不改变系统 DNS 的现有路径，"
                      "只负责连接分流。域名解析仍按系统原方式进行（目前已验证正常）。")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.refresh_logs)
        self.log_timer.start(4000)
        return tab

    def refresh_logs(self):
        if self.tabs.currentIndex() != 3:
            return
        if not self.log_auto.isChecked() and self.log_text.toPlainText():
            return
        log_path = paths.LOG_DIR / "singbox.log"
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
            import re
            text = "\n".join(re.sub(r"\x1b\[[0-9;]*m", "", line) for line in lines)
            self.log_text.setPlainText(text)
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        except OSError:
            self.log_text.setPlainText("(暂无日志)")

    def fix_routes(self):
        self.run_task(self.agent.fixroutes,
                      lambda r: self.statusBar().showMessage(r.get("message", "完成"), 10000))

    def run_diagnostics(self):
        def done(result):
            text = "\n\n".join(f"=== {k} ===\n{v}" for k, v in result.items())
            self.log_text.setPlainText(text)

        self.run_task(self.agent.diagnostics, done)

    def open_root(self):
        subprocess.Popen(["explorer", str(paths.ROOT)])


def main():
    if sys.platform == "win32":
        # Give the taskbar its own app identity (icon + grouping) instead of
        # lumping the window under the generic Python launcher.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NetPilot.App")
    app = QApplication(sys.argv)
    app.setApplicationName("NetPilot")
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
