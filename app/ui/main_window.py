from __future__ import annotations

import time
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional

from PySide6 import QtCore, QtWidgets

from app.data import db
from app.services.poller import Poller
from app.ui.client_manager import ClientManagerDialog
from app.ui.components import StatusDot
from app.theme import apply_theme
from app.ui.views import ActivityView, DashboardView, FunStatsView, SettingsView, TransferView
from app.utils.formatting import format_bytes, format_duration, truncate_text

DOWNLOAD_STATES = {
    "downloading",
    "stalledDL",
    "checkingDL",
    "forcedDL",
    "metaDL",
    "allocating",
    "checkingResumeData",
}

SEEDING_STATES = {
    "uploading",
    "stalledUP",
    "forcedUP",
    "queuedUP",
}

ACTIVE_STATES = DOWNLOAD_STATES | SEEDING_STATES


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SeedScope")
        self.resize(1200, 760)

        self.snapshots: Dict[int, Dict[str, Any]] = {}
        self.statuses: Dict[int, str] = {}
        self.clients: List[Dict[str, Any]] = []
        self._latest_transfer_torrents: List[Dict[str, Any]] = []
        self._transfer_hosts_key: tuple[int, ...] = ()

        self._build_ui()
        self._load_settings()
        self._load_clients()
        if not self.clients:
            self._open_client_manager()
            self._load_clients()
        self._start_poller()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        self.sidebar = QtWidgets.QFrame()
        self.sidebar.setObjectName("Panel")
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(14, 14, 14, 14)
        sidebar_layout.setSpacing(10)

        title = QtWidgets.QLabel("SeedScope")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        subtitle = QtWidgets.QLabel("qBittorrent Monitor")
        subtitle.setObjectName("Muted")
        sidebar_layout.addWidget(title)
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addSpacing(8)

        self.nav_buttons: Dict[str, QtWidgets.QPushButton] = {}
        for label in ["Dashboard", "Activity", "Insights", "Torrent Transfer", "Settings"]:
            btn = QtWidgets.QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.nav_buttons[label] = btn
            sidebar_layout.addWidget(btn)
        sidebar_layout.addStretch(1)

        self.stack = QtWidgets.QStackedWidget()
        self.dashboard_view = DashboardView()
        self.activity_view = ActivityView()
        self.fun_view = FunStatsView()
        self.transfer_view = TransferView()
        self.settings_view = SettingsView(interval=5, theme_mode="dark")
        self.stack.addWidget(self.dashboard_view)
        self.stack.addWidget(self.activity_view)
        self.stack.addWidget(self.fun_view)
        self.stack.addWidget(self.transfer_view)
        self.stack.addWidget(self.settings_view)

        self.nav_buttons["Dashboard"].clicked.connect(lambda: self._select_view(0))
        self.nav_buttons["Activity"].clicked.connect(lambda: self._select_view(1))
        self.nav_buttons["Insights"].clicked.connect(lambda: self._select_view(2))
        self.nav_buttons["Torrent Transfer"].clicked.connect(lambda: self._select_view(3))
        self.nav_buttons["Settings"].clicked.connect(lambda: self._select_view(4))

        self.nav_buttons["Dashboard"].setChecked(True)

        content = QtWidgets.QVBoxLayout()
        content.setSpacing(16)

        top_bar = QtWidgets.QFrame()
        top_bar.setObjectName("Panel")
        top_layout = QtWidgets.QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 12, 16, 12)
        top_layout.setSpacing(12)

        self.client_selector = QtWidgets.QComboBox()
        self.client_selector.setMinimumWidth(260)
        self.client_selector.currentIndexChanged.connect(self._on_client_changed)

        self.status_dot = StatusDot(10)
        self.status_label = QtWidgets.QLabel("Offline")
        self.status_label.setObjectName("Muted")

        top_layout.addWidget(QtWidgets.QLabel("Client Scope"))
        top_layout.addWidget(self.client_selector)
        top_layout.addStretch(1)
        top_layout.addWidget(self.status_dot)
        top_layout.addWidget(self.status_label)

        content.addWidget(top_bar)
        content.addWidget(self.stack)

        root.addWidget(self.sidebar)
        root.addLayout(content, 1)

        self.setCentralWidget(central)

        self.settings_view.interval_changed.connect(self._on_interval_changed)
        self.settings_view.theme_changed.connect(self._on_theme_changed)
        self.settings_view.manage_clients.connect(self._open_client_manager)
        self.transfer_view.manage_button.clicked.connect(self._open_client_manager)
        self.transfer_view.set_refresh_callback(self._refresh_transfer_view)

    def _select_view(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for idx, btn in enumerate(self.nav_buttons.values()):
            btn.setChecked(idx == index)

    def _load_settings(self) -> None:
        db.init_db()
        interval_value = db.get_setting("refresh_interval", "5")
        theme_mode = db.get_setting("theme_mode", "dark")
        try:
            interval = int(interval_value)
        except ValueError:
            interval = 5
        db.set_setting("refresh_interval", str(interval))
        self.settings_view.interval_spin.setValue(interval)
        self.settings_view.set_theme_mode(theme_mode)
        apply_theme(QtWidgets.QApplication.instance(), theme_mode)

    def _load_clients(self) -> None:
        self.clients = db.get_clients()
        self.client_selector.blockSignals(True)
        self.client_selector.clear()
        self.client_selector.addItem("All Clients (Combined)", None)
        for client in self.clients:
            self.client_selector.addItem(client["name"], client["id"])
        self.client_selector.blockSignals(False)
        self._on_client_changed()

    def _start_poller(self) -> None:
        interval = self.settings_view.interval_spin.value()
        self.poller = Poller(self.clients, interval)
        self.poller.data_ready.connect(self._on_data_ready)
        self.poller.status_ready.connect(self._on_status_ready)
        self.poller.start()

    def _on_data_ready(self, snapshots: Dict[int, Dict[str, Any]]) -> None:
        self.snapshots.update(snapshots)
        self._refresh_views()

    def _on_status_ready(self, statuses: Dict[int, str]) -> None:
        self.statuses.update(statuses)
        self._refresh_status()
        self._refresh_views()

    def _on_interval_changed(self, value: int) -> None:
        db.set_setting("refresh_interval", str(value))
        if hasattr(self, "poller"):
            self.poller.update_interval(value)

    def _on_theme_changed(self, mode: str) -> None:
        db.set_setting("theme_mode", mode)
        apply_theme(QtWidgets.QApplication.instance(), mode)
        self._refresh_status()

    def _open_client_manager(self) -> None:
        dialog = ClientManagerDialog(self, statuses=self.statuses)
        dialog.clients_updated.connect(self._reload_clients)
        dialog.exec()

    def _reload_clients(self) -> None:
        self._load_clients()
        if hasattr(self, "poller"):
            self.poller.update_clients(self.clients)

    def _selected_client_id(self) -> Optional[int]:
        return self.client_selector.currentData()

    def _on_client_changed(self) -> None:
        self._refresh_views()
        self._refresh_status()

    def _refresh_status(self) -> None:
        client_id = self._selected_client_id()
        if client_id is None:
            total = len(self.clients)
            connected = sum(1 for status in self.statuses.values() if status == "connected")
            offline = total - connected
            if total == 0:
                self.status_label.setText("No clients")
                self.status_dot.set_status("unknown")
            else:
                self.status_label.setText(f"{connected} connected, {offline} offline")
                self.status_dot.set_status("connected" if connected else "offline")
            return
        status = self.statuses.get(int(client_id), "offline")
        self.status_label.setText(status.capitalize())
        self.status_dot.set_status(status)

    def _refresh_views(self) -> None:
        if not self.clients:
            self.dashboard_view.set_empty(True)
        else:
            self.dashboard_view.set_empty(False)

        selected_id = self._selected_client_id()
        snapshots = self._get_snapshots_for_selection(selected_id)
        stats = self._aggregate_stats(snapshots)
        self.dashboard_view.update_stats(stats)

        torrents = self._aggregate_torrents(snapshots)
        downloading = [t for t in torrents if t.get("state") in DOWNLOAD_STATES]
        seeding = [t for t in torrents if t.get("state") in SEEDING_STATES]
        self.activity_view.update_tables(downloading, seeding)

        fun_stats = self._compute_fun_stats(torrents)
        self.fun_view.update_stats(fun_stats)

        self._latest_transfer_torrents = torrents
        if self.stack.currentWidget() is not self.transfer_view:
            self._sync_transfer_hosts()
            self.transfer_view.update_torrents(torrents)

    def _get_snapshots_for_selection(self, client_id: Optional[int]) -> List[Dict[str, Any]]:
        if client_id is None:
            return [
                snapshot
                for cid, snapshot in self.snapshots.items()
                if self.statuses.get(int(cid)) == "connected"
            ]
        if self.statuses.get(int(client_id)) != "connected":
            return []
        snapshot = self.snapshots.get(int(client_id))
        return [snapshot] if snapshot else []

    def _aggregate_stats(self, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_upload = 0
        total_download = 0
        dl_speed = 0
        up_speed = 0
        torrents_total = 0
        downloading = 0
        seeding = 0

        def first_value(source: Dict[str, Any], keys: List[str]) -> int:
            for key in keys:
                if key in source and source[key] is not None:
                    return int(source[key])
            return 0

        for snapshot in snapshots:
            server_state = snapshot.get("server_state", {})
            torrents = snapshot.get("torrents", [])
            total_upload += first_value(
                server_state, ["alltime_ul", "total_uploaded", "total_upload", "up_info_data"]
            )
            total_download += first_value(
                server_state, ["alltime_dl", "total_downloaded", "total_download", "dl_info_data"]
            )
            dl_speed += int(server_state.get("dl_info_speed", 0))
            up_speed += int(server_state.get("up_info_speed", 0))
            torrents_total += len(torrents)
            downloading += sum(1 for t in torrents if t.get("state") in DOWNLOAD_STATES)
            seeding += sum(1 for t in torrents if t.get("state") in SEEDING_STATES)

        ratio = (total_upload / total_download) if total_download > 0 else 0
        return {
            "total_upload": total_upload,
            "total_download": total_download,
            "ratio": ratio,
            "torrents_total": torrents_total,
            "downloading": downloading,
            "seeding": seeding,
            "dl_speed": dl_speed,
            "up_speed": up_speed,
        }

    def _aggregate_torrents(self, snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        torrents: List[Dict[str, Any]] = []
        client_map = {int(c["id"]): c for c in self.clients}
        for snapshot in snapshots:
            client_id = snapshot.get("client_id")
            client = client_map.get(int(client_id)) if client_id is not None else None
            torrents.extend(self._normalize_torrents(snapshot.get("torrents", []), client))
        return torrents

    def _normalize_torrents(
        self, torrents: List[Dict[str, Any]], client: Dict[str, Any] | None
    ) -> List[Dict[str, Any]]:
        normalized = []
        for torrent in torrents:
            uploaded = torrent.get("uploaded")
            if uploaded is None:
                uploaded = torrent.get("total_uploaded", torrent.get("uploaded_session", 0))
            tracker_raw = torrent.get("tracker") or ""
            tracker = tracker_raw
            if tracker_raw:
                parsed = urlparse(tracker_raw)
                if parsed.hostname:
                    tracker = parsed.hostname
            normalized.append(
                {
                    "client_id": client.get("id") if client else None,
                    "client_name": client.get("name") if client else "",
                    "hash": torrent.get("hash"),
                    "name": torrent.get("name", ""),
                    "size": torrent.get("size", torrent.get("total_size", 0)),
                    "progress": torrent.get("progress", 0),
                    "ratio": torrent.get("ratio", 0),
                    "upspeed": torrent.get("upspeed", 0),
                    "dlspeed": torrent.get("dlspeed", 0),
                    "uploaded": uploaded or 0,
                    "seeding_time": torrent.get("seeding_time", 0),
                    "completion_on": torrent.get("completion_on", 0),
                    "added_on": torrent.get("added_on", 0),
                    "last_activity": torrent.get("last_activity", 0),
                    "state": torrent.get("state", ""),
                    "save_path": torrent.get("save_path"),
                    "content_path": torrent.get("content_path"),
                    "tracker": tracker,
                }
            )
        return normalized

    def _sync_transfer_hosts(self) -> None:
        host_ids = tuple(sorted(int(c["id"]) for c in self.clients))
        if host_ids != self._transfer_hosts_key:
            self._transfer_hosts_key = host_ids
            self.transfer_view.set_hosts(self.clients)

    def _refresh_transfer_view(self) -> None:
        self._sync_transfer_hosts()
        self.transfer_view.update_torrents(self._latest_transfer_torrents)

    def _compute_fun_stats(self, torrents: List[Dict[str, Any]]) -> Dict[str, Any]:
        stats = {
            "highest_upload": "--",
            "longest_seeded": "--",
            "completed": 0,
            "avg_ratio": 0,
            "longest_active": "--",
        }
        if not torrents:
            return stats

        highest = max(torrents, key=lambda t: t.get("uploaded", 0))
        highest_name = truncate_text(highest.get("name", "Unknown"), 20)
        stats["highest_upload"] = f"{highest_name} ({format_bytes(highest.get('uploaded', 0))})"

        longest_seed = max(torrents, key=lambda t: t.get("seeding_time", 0))
        seed_name = truncate_text(longest_seed.get("name", "Unknown"), 20)
        stats["longest_seeded"] = f"{seed_name} ({format_duration(longest_seed.get('seeding_time', 0))})"

        completed = [t for t in torrents if t.get("completion_on", 0) > 0]
        stats["completed"] = len(completed)

        ratios = [t.get("ratio", 0) for t in torrents if t.get("ratio", 0) is not None]
        if ratios:
            stats["avg_ratio"] = sum(ratios) / len(ratios)

        active = [t for t in torrents if t.get("state") in ACTIVE_STATES and t.get("added_on", 0) > 0]
        if active:
            longest = min(active, key=lambda t: t.get("added_on", time.time()))
            age = time.time() - longest.get("added_on", time.time())
            active_name = truncate_text(longest.get("name", "Unknown"), 20)
            stats["longest_active"] = f"{active_name} ({format_duration(age)})"
        return stats

    def closeEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "poller"):
            self.poller.stop()
            self.poller.wait(1000)
        super().closeEvent(event)
