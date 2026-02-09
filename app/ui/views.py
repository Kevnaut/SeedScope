from __future__ import annotations

import time
from typing import Any, Dict, List

from pathlib import Path

from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from app.services.qbit_client import QbitClient
from app.services.transfer import TransferWorker, check_disk_space, total_size
from app.ui.components import EmptyState, SectionHeader, StatCard
from app.utils.formatting import (
    format_bytes,
    format_duration,
    format_percent,
    format_ratio,
    format_speed,
)
from app.theme import theme


def _map_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "world-map.svg"


class PeerMapWidget(QtWidgets.QWidget):
    def __init__(self, svg_text: str) -> None:
        super().__init__()
        self._base_svg = svg_text
        self._peer_data: Dict[str, Dict[str, Any]] = {}
        self._hover_bounds: Dict[str, QtCore.QRectF] = {}
        self._centers: Dict[str, QtCore.QPointF] = {}
        self._renderer = QtSvg.QSvgRenderer()
        self._scale = 1.0
        self._offset = QtCore.QPointF(0.0, 0.0)
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._load_svg(self._base_svg)

    def update_peers(self, peer_data: Dict[str, Dict[str, Any]]) -> None:
        self._peer_data = peer_data
        css = self._build_css(peer_data)
        svg = self._inject_style(self._base_svg, css)
        self._load_svg(svg)
        self._rebuild_bounds()
        self.update()

    def _build_css(self, peer_data: Dict[str, Dict[str, Any]]) -> str:
        theme_map = theme()
        base_fill = theme_map["panel"]
        border = theme_map["border"]
        accent = QtGui.QColor(theme_map["accent"])
        download_color = QtGui.QColor("#ff8a1f")
        max_download = max((data.get("downloading", 0) for data in peer_data.values()), default=0)
        max_upload = max((data.get("uploading", 0) for data in peer_data.values()), default=0)
        max_idle = max(
            (
                data.get("count", 0)
                for data in peer_data.values()
                if data.get("downloading", 0) <= 0 and data.get("uploading", 0) <= 0
            ),
            default=0,
        )
        lines = [
            f"path, polygon, g {{ fill: {base_fill}; stroke: {border}; stroke-width: 0.6; }}",
        ]
        for code, data in peer_data.items():
            downloading = int(data.get("downloading", 0))
            uploading = int(data.get("uploading", 0))
            if downloading <= 0 and uploading <= 0:
                continue
            if downloading > 0:
                intensity = 0.45 if max_download == 0 else min(1.0, 0.45 + 0.55 * (downloading / max_download))
                color = QtGui.QColor(download_color)
                color.setAlpha(int(255 * intensity))
                stroke = color.name()
            elif uploading > 0:
                intensity = 0.45 if max_upload == 0 else min(1.0, 0.45 + 0.55 * (uploading / max_upload))
                color = QtGui.QColor(accent)
                color.setAlpha(int(255 * intensity))
                stroke = color.name()
            else:
                intensity = 0.25 if max_idle == 0 else min(0.65, 0.25 + 0.4 * (data.get("count", 0) / max_idle))
                color = QtGui.QColor(theme_map["accent_soft"])
                color.setAlpha(int(255 * intensity))
                stroke = theme_map["accent_soft"]
            lines.append(
                f"#{code} {{ fill: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha() / 255:.2f}); "
                f"stroke: {stroke}; stroke-width: 1.3; }}"
            )
        return "\n".join(lines)

    @staticmethod
    def _inject_style(svg_text: str, css: str) -> str:
        import re

        svg_text = re.sub(r"<style id=\"peermap-style\">.*?</style>", "", svg_text, flags=re.S)
        style_block = f"<style id=\"peermap-style\"><![CDATA[{css}]]></style>"
        svg_start = svg_text.find("<svg")
        if svg_start == -1:
            return svg_text
        insert_at = svg_text.find(">", svg_start)
        if insert_at == -1:
            return svg_text
        return f"{svg_text[:insert_at + 1]}{style_block}{svg_text[insert_at + 1:]}"

    def _load_svg(self, svg_text: str) -> None:
        self._renderer.load(QtCore.QByteArray(svg_text.encode("utf-8")))

    def _rebuild_bounds(self) -> None:
        self._hover_bounds.clear()
        self._centers.clear()
        renderer = self._renderer
        for code in self._peer_data.keys():
            if renderer.elementExists(code):
                rect = renderer.boundsOnElement(code)
                self._hover_bounds[code] = rect
                self._centers[code] = rect.center()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        view_box, scale, offset = self._calc_transform()
        self._scale = scale
        self._offset = offset
        painter.translate(offset)
        painter.scale(scale, scale)
        self._renderer.render(painter)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        point = self._map_to_svg(event.position())
        if point is None:
            QtWidgets.QToolTip.hideText()
            return
        for code, rect in self._hover_bounds.items():
            if rect.contains(point):
                data = self._peer_data.get(code, {})
                name = data.get("name", code.upper())
                count = data.get("count", 0)
                downloading = data.get("downloading", 0)
                uploading = data.get("uploading", 0)
                tip = f"{name} • {count} peers\\nDL: {downloading}  UL: {uploading}"
                QtWidgets.QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        QtWidgets.QToolTip.hideText()

    def leaveEvent(self, event) -> None:  # noqa: N802
        QtWidgets.QToolTip.hideText()
        super().leaveEvent(event)

    def _map_to_svg(self, pos: QtCore.QPointF) -> QtCore.QPointF | None:
        view_box, scale, offset = self._calc_transform()
        if view_box.isNull():
            return None
        x = (pos.x() - offset.x()) / scale + view_box.x()
        y = (pos.y() - offset.y()) / scale + view_box.y()
        return QtCore.QPointF(x, y)

    def _calc_transform(self) -> tuple[QtCore.QRectF, float, QtCore.QPointF]:
        view_box = self._renderer.viewBoxF()
        if view_box.isNull():
            return QtCore.QRectF(0, 0, 1, 1), 1.0, QtCore.QPointF(0.0, 0.0)
        widget_w = max(1.0, float(self.width()))
        widget_h = max(1.0, float(self.height()))
        scale = min(widget_w / view_box.width(), widget_h / view_box.height())
        render_w = view_box.width() * scale
        render_h = view_box.height() * scale
        offset_x = (widget_w - render_w) / 2.0
        offset_y = (widget_h - render_h) / 2.0
        return view_box, scale, QtCore.QPointF(offset_x, offset_y)


class PeerMapView(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        header = SectionHeader("Peer Map", "Country-level peer activity across selected clients")
        path = _map_path()

        self.empty_state = EmptyState(
            "Map asset missing",
            "Add world-map.svg to app/assets to render the peer map.",
        )

        self.map_widget: PeerMapWidget | None = None
        self.status_label = QtWidgets.QLabel("Waiting for peer data...")
        self.status_label.setObjectName("Muted")
        if path.exists():
            svg_text = path.read_text(encoding="utf-8")
            self.map_widget = PeerMapWidget(svg_text)
            self.map_widget.setMinimumHeight(420)

        legend_row = QtWidgets.QHBoxLayout()
        self.legend_upload = QtWidgets.QFrame()
        self.legend_upload.setFixedSize(12, 12)
        self.legend_download = QtWidgets.QFrame()
        self.legend_download.setFixedSize(12, 12)
        legend_row.addWidget(self._legend_item(self.legend_upload, "Upload"))
        legend_row.addSpacing(12)
        legend_row.addWidget(self._legend_item(self.legend_download, "Download"))
        legend_row.addStretch(1)
        legend_row.addWidget(self.status_label)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(header)
        if self.map_widget:
            layout.addWidget(self.map_widget, 1)
        else:
            layout.addWidget(self.empty_state)
        layout.addLayout(legend_row)

        self._update_legend_colors()

    def update_peers(self, peer_data: Dict[str, Dict[str, Any]]) -> None:
        if not self.map_widget:
            return
        self.map_widget.update_peers(peer_data)
        self._update_legend_colors()
        if peer_data:
            self.status_label.setText(f"{sum(d.get('count', 0) for d in peer_data.values())} peers mapped")
        else:
            self.status_label.setText(
                "No peer country data yet. Ensure qBittorrent is resolving peer countries."
            )

    def _legend_item(self, color_box: QtWidgets.QFrame, label: str) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(color_box)
        text = QtWidgets.QLabel(label)
        text.setObjectName("Muted")
        layout.addWidget(text)
        return container

    def _update_legend_colors(self) -> None:
        theme_map = theme()
        upload = theme_map["accent"]
        download = "#ff8a1f"
        self.legend_upload.setStyleSheet(
            f"background: {upload}; border-radius: 6px; border: 1px solid {theme_map['border']};"
        )
        self.legend_download.setStyleSheet(
            f"background: {download}; border-radius: 6px; border: 1px solid {theme_map['border']};"
        )


class TransferPreviewDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        source: Dict[str, Any],
        destinations: List[Dict[str, Any]],
        torrents: List[Dict[str, Any]],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Transfer Preview")
        self.setModal(True)
        self.resize(520, 320)

        self.source = source
        self.destinations = destinations
        self.torrents = torrents

        self.source_label = QtWidgets.QLabel(source.get("name", "Unknown"))
        self.dest_combo = QtWidgets.QComboBox()
        for dest in destinations:
            self.dest_combo.addItem(dest["name"], dest)

        self.dest_hint = QtWidgets.QLabel("")
        self.dest_hint.setObjectName("Muted")

        self.count_label = QtWidgets.QLabel(str(len(torrents)))
        self.size_label = QtWidgets.QLabel("0 B")
        self.space_label = QtWidgets.QLabel("Unknown")
        self.warning_label = QtWidgets.QLabel(
            "Seeding time and client-side statistics will reset on the destination host."
        )
        self.warning_label.setObjectName("Muted")
        self.clean_toggle = QtWidgets.QCheckBox("Delete destination data before copy (recommended)")
        self.clean_toggle.setChecked(True)

        form = QtWidgets.QFormLayout()
        form.addRow("Source Host", self.source_label)
        form.addRow("Destination Host", self.dest_combo)
        form.addRow("Torrents Selected", self.count_label)
        form.addRow("Total Size", self.size_label)
        form.addRow("Estimated Space Required", self.space_label)

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.preview_button = QtWidgets.QPushButton("Preview (dry run)")
        self.transfer_button = QtWidgets.QPushButton("Transfer")

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.preview_button)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.transfer_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.dest_hint)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.clean_toggle)
        layout.addStretch(1)
        layout.addLayout(buttons)

        self.dest_combo.currentIndexChanged.connect(self._populate_destination)
        self.cancel_button.clicked.connect(self.reject)
        self.preview_button.clicked.connect(self._dry_run)
        self.transfer_button.clicked.connect(self.accept)

        self._populate_destination()
        self._update_sizes()

    def _populate_destination(self) -> None:
        dest = self.dest_combo.currentData()
        source_copy = self._resolve_transfer_path(self.source)
        dest_copy = self._resolve_transfer_path(dest) if dest else None
        dest_save = dest.get("completed_path") if dest else None
        if source_copy and dest_copy and dest_save:
            self.dest_hint.setText("")
            self.transfer_button.setEnabled(True)
        else:
            missing = []
            if not (self.source.get("completed_path")):
                missing.append("source local path")
            if not source_copy:
                missing.append("source transfer path")
            if dest:
                if not dest.get("completed_path"):
                    missing.append("destination local path")
                if not dest_copy:
                    missing.append("destination transfer path")
            hint = "Set Local Completed Folder and Transfer Path (UNC) in Host Settings."
            if missing:
                hint = f"Missing: {', '.join(missing)}"
            self.dest_hint.setText(hint)
            self.transfer_button.setEnabled(False)

    def _update_sizes(self) -> None:
        total = total_size(self.torrents)
        self.size_label.setText(format_bytes(total))
        self.space_label.setText(format_bytes(total))

    def _dry_run(self) -> None:
        dest = self.dest_combo.currentData()
        if not dest:
            QtWidgets.QMessageBox.warning(self, "Missing Destination", "Select a destination host.")
            return
        source_copy = self._resolve_transfer_path(self.source)
        dest_copy = self._resolve_transfer_path(dest)
        dest_save = dest.get("completed_path")
        if not source_copy or not dest_copy or not dest_save:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing Path",
                "Local Completed Folder and Transfer Path must be set in Host Settings.",
            )
            return
        try:
            dest_client = QbitClient(dest)
            for torrent in self.torrents:
                if dest_client.has_torrent(torrent["hash"]):
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Duplicate Torrent",
                        f"{torrent['name']} already exists on the destination host.",
                    )
                    return
            total = total_size(self.torrents)
            if not check_disk_space(dest_copy, total):
                QtWidgets.QMessageBox.warning(
                    self, "Disk Space", "Destination disk does not have enough free space."
                )
                return
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Validation Error", str(exc))
            return
        QtWidgets.QMessageBox.information(self, "Dry Run", "All checks passed.")

    def get_transfer_config(self) -> Dict[str, Any]:
        source_copy = self._resolve_transfer_path(self.source)
        dest = self.dest_combo.currentData()
        dest_copy = self._resolve_transfer_path(dest) if dest else None
        dest_save = dest.get("completed_path") if dest else None
        return {
            "destination": self.dest_combo.currentData(),
            "source_path": source_copy,
            "dest_path": dest_copy,
            "dest_save_path": dest_save,
            "clean_destination": self.clean_toggle.isChecked(),
        }

    @staticmethod
    def _resolve_transfer_path(client: Dict[str, Any] | None) -> str | None:
        if not client:
            return None
        transfer_path = client.get("transfer_path")
        if transfer_path and str(transfer_path).strip().lower() != "none":
            return transfer_path
        completed = client.get("completed_path")
        if completed and str(completed).startswith("\\\\"):
            return completed
        return None


class TransferProgressDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget, total: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Transfer Progress")
        self.setModal(True)
        self.resize(520, 205)
        self.total = max(1, total)

        self.title = QtWidgets.QLabel("Preparing transfer...")
        self.title.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.step_label = QtWidgets.QLabel("")
        self.step_label.setObjectName("Muted")
        self.eta_label = QtWidgets.QLabel("ETA: calculating...")
        self.eta_label.setObjectName("Muted")
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.step_label)
        layout.addWidget(self.eta_label)
        layout.addWidget(self.progress)

    def update_status(self, torrent_name: str, state: str, percent: int, eta_text: str = "") -> None:
        self.title.setText(f"{torrent_name}")
        self.step_label.setText(state)
        self.eta_label.setText(eta_text or "ETA: calculating...")
        self.progress.setValue(max(0, min(100, percent)))


class TransferTable(QtWidgets.QTableWidget):
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() != QtCore.Qt.LeftButton:
            return super().mousePressEvent(event)
        index = self.indexAt(event.position().toPoint())
        if not index.isValid():
            return super().mousePressEvent(event)
        row = index.row()
        item = self.item(row, 0)
        if not item or not bool(item.data(QtCore.Qt.UserRole + 1)):
            return
        selection = self.selectionModel()
        model_index = self.model().index(row, 0)
        selection.select(
            model_index, QtCore.QItemSelectionModel.Toggle | QtCore.QItemSelectionModel.Rows
        )
        self.setCurrentCell(row, 0)


class TransferView(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        header = SectionHeader("Management Mode — Torrent Transfer", "Guided migration between hosts")

        self.notice = QtWidgets.QLabel(
            "Transfers modify data on both hosts. Use with caution and confirm before proceeding."
        )
        self.notice.setObjectName("Muted")

        self.completed_only = QtWidgets.QCheckBox("Completed only")
        self.completed_only.setChecked(True)
        self.host_filter = QtWidgets.QComboBox()
        self.seed_time_spin = QtWidgets.QSpinBox()
        self.seed_time_spin.setRange(0, 9999)
        self.seed_time_spin.setSuffix(" h")
        self.refresh_button = QtWidgets.QPushButton("Refresh List")

        filters = QtWidgets.QHBoxLayout()
        filters.addWidget(self.completed_only)
        filters.addSpacing(12)
        filters.addWidget(QtWidgets.QLabel("Host"))
        filters.addWidget(self.host_filter)
        filters.addSpacing(12)
        filters.addWidget(QtWidgets.QLabel("Seed time >"))
        filters.addWidget(self.seed_time_spin)
        filters.addStretch(1)
        filters.addWidget(self.refresh_button)

        self.table = TransferTable(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Torrent Name",
                "Size",
                "Seed Time",
                "Tracker",
                "Host",
                "Status",
                "Completion %",
                "Transfer State",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.itemSelectionChanged.connect(self._update_transfer_button)

        self.transfer_button = QtWidgets.QPushButton("Transfer Selected")
        self.transfer_button.setEnabled(False)
        self.transfer_hint = QtWidgets.QLabel("Select completed torrents from a single host.")
        self.transfer_hint.setObjectName("Muted")

        footer = QtWidgets.QHBoxLayout()
        footer.addWidget(self.transfer_hint)
        footer.addStretch(1)
        footer.addWidget(self.transfer_button)

        self.empty_state = EmptyState(
            "Add another host to enable transfers",
            "You need at least two configured qBittorrent hosts to use Management Mode.",
        )
        self.empty_state.hide()
        self.manage_button = QtWidgets.QPushButton("Open Host Settings")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(header)
        layout.addWidget(self.notice)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addLayout(footer)
        layout.addWidget(self.empty_state)
        layout.addWidget(self.manage_button)

        self._all_torrents: List[Dict[str, Any]] = []
        self._clients: Dict[int, Dict[str, Any]] = {}
        self._transfer_state: Dict[str, str] = {}
        self._hash_row: Dict[str, int] = {}
        self._eta_tracker: Dict[str, Dict[str, Any]] = {}
        self._refresh_callback = None

        self.completed_only.toggled.connect(self._apply_filters)
        self.host_filter.currentIndexChanged.connect(self._apply_filters)
        self.seed_time_spin.valueChanged.connect(self._apply_filters)
        self.transfer_button.clicked.connect(self._open_transfer_dialog)
        self.refresh_button.clicked.connect(self._manual_refresh)

    def set_hosts(self, clients: List[Dict[str, Any]]) -> None:
        self._clients = {int(c["id"]): c for c in clients}
        self.host_filter.blockSignals(True)
        self.host_filter.clear()
        self.host_filter.addItem("All Hosts", None)
        for client in clients:
            self.host_filter.addItem(client["name"], client["id"])
        self.host_filter.blockSignals(False)
        self.empty_state.setVisible(len(clients) < 2)
        self.manage_button.setVisible(len(clients) < 2)
        self.table.setEnabled(len(clients) >= 2)
        self.transfer_button.setEnabled(False)

    def set_refresh_callback(self, callback) -> None:
        self._refresh_callback = callback

    def _manual_refresh(self) -> None:
        if self._refresh_callback:
            self._refresh_callback()

    def update_torrents(self, torrents: List[Dict[str, Any]]) -> None:
        self._all_torrents = torrents
        self._apply_filters()

    def _apply_filters(self) -> None:
        host_id = self.host_filter.currentData()
        seed_hours = self.seed_time_spin.value()
        completed_only = self.completed_only.isChecked()

        filtered = []
        for torrent in self._all_torrents:
            if host_id is not None and torrent.get("client_id") != host_id:
                continue
            if completed_only and torrent.get("progress", 0) < 1:
                continue
            if seed_hours > 0:
                if (torrent.get("seeding_time", 0) or 0) < seed_hours * 3600:
                    continue
            filtered.append(torrent)
        self._fill_table(filtered)

    def _fill_table(self, torrents: List[Dict[str, Any]]) -> None:
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(torrents))
        self._hash_row.clear()
        for row, torrent in enumerate(torrents):
            torrent_hash = torrent.get("hash")
            self._hash_row[torrent_hash] = row
            eligible = torrent.get("progress", 0) >= 1

            name_item = QtWidgets.QTableWidgetItem(torrent.get("name", ""))
            name_item.setData(QtCore.Qt.UserRole, torrent_hash)
            name_item.setData(QtCore.Qt.UserRole + 1, eligible)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, SortItem(format_bytes(torrent.get("size", 0)), torrent.get("size", 0)))
            self.table.setItem(
                row,
                2,
                SortItem(format_duration(torrent.get("seeding_time", 0)), torrent.get("seeding_time", 0)),
            )
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(torrent.get("tracker", "")))
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(torrent.get("client_name", "")))
            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(torrent.get("state", "")))
            self.table.setItem(
                row,
                6,
                SortItem(format_percent(torrent.get("progress", 0)), torrent.get("progress", 0)),
            )
            state = self._transfer_state.get(torrent_hash, "Idle")
            self.table.setItem(row, 7, QtWidgets.QTableWidgetItem(state))
            self.table.setRowHeight(row, 32)
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if not item:
                    continue
                if not eligible:
                    item.setFlags(QtCore.Qt.NoItemFlags)
                else:
                    item.setFlags(
                        QtCore.Qt.ItemIsEnabled
                        | QtCore.Qt.ItemIsSelectable
                        | QtCore.Qt.ItemNeverHasChildren
                    )
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        self._update_transfer_button()

    def _selected_torrents(self) -> List[Dict[str, Any]]:
        selected = []
        for index in self.table.selectionModel().selectedRows():
            row = index.row()
            item = self.table.item(row, 0)
            if not item:
                continue
            torrent_hash = item.data(QtCore.Qt.UserRole)
            if not torrent_hash:
                continue
            for torrent in self._all_torrents:
                if torrent.get("hash") == torrent_hash:
                    selected.append(torrent)
                    break
        return selected

    def _update_transfer_button(self) -> None:
        selected = self._selected_torrents()
        if not selected:
            self.transfer_button.setEnabled(False)
            self.transfer_hint.setText("Select completed torrents from a single host.")
            return
        hosts = {t.get("client_id") for t in selected}
        if len(hosts) != 1:
            self.transfer_button.setEnabled(False)
            self.transfer_hint.setText("Select torrents from only one source host.")
            return
        self.transfer_button.setEnabled(True)
        self.transfer_hint.setText(f"{len(selected)} torrents selected")

    def _open_transfer_dialog(self) -> None:
        selected = self._selected_torrents()
        if not selected:
            return
        host_ids = {t.get("client_id") for t in selected}
        if len(host_ids) != 1:
            return
        source_id = next(iter(host_ids))
        source = self._clients.get(int(source_id))
        if not source:
            return
        destinations = [c for cid, c in self._clients.items() if cid != source_id]
        if not destinations:
            return
        dialog = TransferPreviewDialog(self, source, destinations, selected)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        config = dialog.get_transfer_config()
        destination = config.get("destination")
        if not destination:
            return
        if not config.get("dest_path") or not config.get("dest_save_path"):
            QtWidgets.QMessageBox.warning(self, "Missing Path", "Destination path is required.")
            return
        self._progress_hashes = [t.get("hash") for t in selected]
        self._hash_to_name = {t.get("hash"): t.get("name", "") for t in selected}
        self._eta_tracker.clear()
        self._progress_dialog = TransferProgressDialog(self, len(selected))
        self._progress_dialog.show()
        worker = TransferWorker(
            source,
            destination,
            selected,
            config.get("source_path", ""),
            config["dest_path"],
            config["dest_save_path"],
            config.get("clean_destination", True),
        )
        worker.state_changed.connect(self._on_transfer_state)
        worker.progress_changed.connect(self._on_transfer_progress)
        worker.error.connect(self._on_transfer_error)
        worker.finished_all.connect(lambda: self._on_transfer_finished(worker))
        self._active_worker = worker
        worker.start()

    def _on_transfer_state(self, torrent_hash: str, state: str) -> None:
        if state.split(" (", 1)[0] not in {"Copying", "Rechecking"}:
            self._eta_tracker.pop(torrent_hash, None)
        self._transfer_state[torrent_hash] = state
        row = self._find_row_by_hash(torrent_hash)
        if row is not None:
            item = self.table.item(row, 7)
            if item:
                item.setText(state)
        self._update_progress_dialog(torrent_hash, state)

    def _on_transfer_progress(self, torrent_hash: str, stage: str, progress: float) -> None:
        self._update_progress_dialog(torrent_hash, stage, progress)

    def _on_transfer_error(self, torrent_hash: str, message: str) -> None:
        self._transfer_state[torrent_hash] = "Failed"
        row = self._find_row_by_hash(torrent_hash)
        if row is not None:
            item = self.table.item(row, 7)
            if item:
                item.setText("Failed")
        self._update_progress_dialog(torrent_hash, "Failed")
        QtWidgets.QMessageBox.warning(self, "Transfer Failed", message)

    def _on_transfer_finished(self, worker: TransferWorker) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None
        worker.deleteLater()

    def _find_row_by_hash(self, torrent_hash: str) -> int | None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(QtCore.Qt.UserRole) == torrent_hash:
                return row
        return None

    def _row_is_eligible(self, row: int) -> bool:
        item = self.table.item(row, 0)
        if not item:
            return False
        return bool(item.data(QtCore.Qt.UserRole + 1))

    def _update_progress_dialog(
        self, torrent_hash: str, state: str, progress_override: float | None = None
    ) -> None:
        if not self._progress_dialog:
            return
        clean_state = state.split(" (", 1)[0]
        step_fraction = {
            "Paused on source": 0.05,
            "Copying": 0.05,
            "Adding to destination": 0.78,
            "Rechecking": 0.78,
            "Seeding on destination": 0.97,
            "Cleaning up source": 0.99,
            "Complete": 1.0,
            "Failed": 1.0,
        }
        total = len(getattr(self, "_progress_hashes", [])) or 1
        current = 0
        if hasattr(self, "_progress_hashes"):
            try:
                current = self._progress_hashes.index(torrent_hash)
            except ValueError:
                current = 0
        if progress_override is not None:
            progress_val = max(0.0, min(1.0, float(progress_override)))
            if clean_state == "Copying":
                torrent_progress = 0.05 + (0.73 * progress_val)
            elif clean_state == "Rechecking":
                torrent_progress = 0.78 + (0.17 * progress_val)
            else:
                torrent_progress = step_fraction.get(clean_state, 0.0)
            percent = int(((current + torrent_progress) / max(1, total)) * 100)
            state = f"{clean_state} ({int(progress_val * 100)}%)"
        else:
            torrent_progress = step_fraction.get(clean_state, 0.0)
            percent = int(((current + torrent_progress) / max(1, total)) * 100)
        eta_text = self._estimate_eta_text(torrent_hash, clean_state, progress_override)
        name = self._hash_to_name.get(torrent_hash, torrent_hash) if hasattr(self, "_hash_to_name") else torrent_hash
        self._progress_dialog.update_status(name, state, percent, eta_text)

    def _estimate_eta_text(
        self, torrent_hash: str, stage: str, progress_override: float | None
    ) -> str:
        if stage in {"Complete", "Failed"}:
            return "ETA: --"
        if progress_override is None or stage not in {"Copying", "Rechecking"}:
            return "ETA: calculating..."

        now = time.monotonic()
        progress = max(0.0, min(1.0, float(progress_override)))
        tracker = self._eta_tracker.get(torrent_hash)
        if (
            tracker is None
            or tracker.get("stage") != stage
            or progress < float(tracker.get("progress", 0.0)) - 0.02
        ):
            self._eta_tracker[torrent_hash] = {
                "stage": stage,
                "start": now,
                "last_ts": now,
                "progress": progress,
                "rate": None,
            }
            return "ETA: calculating..."

        last_ts = float(tracker.get("last_ts", now))
        last_progress = float(tracker.get("progress", progress))
        dt = now - last_ts
        dp = progress - last_progress
        rate = tracker.get("rate")
        if dt > 0 and dp > 0:
            inst_rate = dp / dt
            rate = inst_rate if rate is None else (0.75 * float(rate) + 0.25 * inst_rate)
            tracker["rate"] = rate
        tracker["last_ts"] = now
        tracker["progress"] = progress

        if progress >= 0.999:
            return "ETA: <1s"

        eta_seconds = None
        if rate and float(rate) > 0:
            eta_seconds = (1.0 - progress) / float(rate)
        elif progress > 0.02:
            elapsed = now - float(tracker.get("start", now))
            if elapsed > 0:
                eta_seconds = elapsed * ((1.0 / progress) - 1.0)
        if eta_seconds is None:
            return "ETA: calculating..."
        eta_seconds = max(0.0, eta_seconds)
        return f"ETA: {format_duration(eta_seconds)}"


class DashboardView(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.cards: Dict[str, StatCard] = {}

        header = SectionHeader("Global Overview", "Aggregated stats across selected clients")

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(14)

        for idx, label in enumerate(
            [
                "Total Upload",
                "Total Download",
                "Global Ratio",
                "Total Torrents",
                "Number Downloading",
                "Number Seeding",
            ]
        ):
            card = StatCard(label)
            self.cards[label] = card
            grid.addWidget(card, idx // 3, idx % 3)

        speed_header = SectionHeader("Live Transfer Rates", "Auto-refreshes per interval")
        speed_layout = QtWidgets.QHBoxLayout()
        self.cards["Total Download Speed"] = StatCard("Total Download Speed")
        self.cards["Total Upload Speed"] = StatCard("Total Upload Speed")
        speed_layout.addWidget(self.cards["Total Download Speed"])
        speed_layout.addWidget(self.cards["Total Upload Speed"])

        self.empty_state = EmptyState(
            "No clients configured",
            "Add a qBittorrent client in Settings to start monitoring transfer statistics.",
        )
        self.empty_state.hide()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.addWidget(header)
        layout.addLayout(grid)
        layout.addWidget(speed_header)
        layout.addLayout(speed_layout)
        layout.addStretch(1)
        layout.addWidget(self.empty_state)

    def set_empty(self, show: bool) -> None:
        self.empty_state.setVisible(show)

    def update_stats(self, stats: Dict[str, Any]) -> None:
        self.cards["Total Upload"].set_value(format_bytes(stats.get("total_upload", 0)))
        self.cards["Total Download"].set_value(format_bytes(stats.get("total_download", 0)))
        self.cards["Global Ratio"].set_value(format_ratio(stats.get("ratio", 0)))
        self.cards["Total Torrents"].set_value(str(stats.get("torrents_total", 0)))
        self.cards["Number Downloading"].set_value(str(stats.get("downloading", 0)))
        self.cards["Number Seeding"].set_value(str(stats.get("seeding", 0)))
        self.cards["Total Download Speed"].set_value(format_speed(stats.get("dl_speed", 0)))
        self.cards["Total Upload Speed"].set_value(format_speed(stats.get("up_speed", 0)))


class ActivityView(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        header = SectionHeader("Torrent Activity", "Read-only activity across selected clients")

        self.downloading_table = self._build_table()
        self.seeding_table = self._build_table()
        self.downloading_table.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.seeding_table.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(header)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._wrap_section("Currently Downloading", self.downloading_table))
        self.splitter.addWidget(self._wrap_section("Currently Seeding", self.seeding_table))
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([1, 1])

        layout.addWidget(self.splitter, 1)

    def _build_table(self) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(
            ["Name", "Size", "Progress", "Ratio", "Upload Speed", "Download Speed", "Host"]
        )
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSortIndicatorShown(True)
        return table

    def _wrap_section(self, title: str, table: QtWidgets.QTableWidget) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader(title))
        layout.addWidget(table, 1)
        return container

    def update_tables(self, downloading: List[Dict[str, Any]], seeding: List[Dict[str, Any]]) -> None:
        self._fill_table(self.downloading_table, downloading)
        self._fill_table(self.seeding_table, seeding)

    def _fill_table(self, table: QtWidgets.QTableWidget, data: List[Dict[str, Any]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(len(data))
        for row, torrent in enumerate(data):
            name_item = QtWidgets.QTableWidgetItem(torrent.get("name", ""))
            name_item.setData(QtCore.Qt.UserRole, torrent.get("hash"))
            table.setItem(row, 0, name_item)
            table.setItem(
                row,
                1,
                SortItem(format_bytes(torrent.get("size", 0)), torrent.get("size", 0)),
            )
            table.setItem(
                row,
                2,
                SortItem(format_percent(torrent.get("progress", 0)), torrent.get("progress", 0)),
            )
            table.setItem(
                row,
                3,
                SortItem(format_ratio(torrent.get("ratio", 0)), torrent.get("ratio", 0)),
            )
            table.setItem(
                row,
                4,
                SortItem(format_speed(torrent.get("upspeed", 0)), torrent.get("upspeed", 0)),
            )
            table.setItem(
                row,
                5,
                SortItem(format_speed(torrent.get("dlspeed", 0)), torrent.get("dlspeed", 0)),
            )
            table.setItem(row, 6, QtWidgets.QTableWidgetItem(torrent.get("client_name", "")))
            table.setRowHeight(row, 32)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)


class SortItem(QtWidgets.QTableWidgetItem):
    def __init__(self, text: str, sort_value: float) -> None:
        super().__init__(text)
        self._sort_value = sort_value if sort_value is not None else 0

    def __lt__(self, other: QtWidgets.QTableWidgetItem) -> bool:
        if isinstance(other, SortItem):
            return float(self._sort_value) < float(other._sort_value)
        return super().__lt__(other)


class FunStatsView(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        header = SectionHeader("Insight Layer", "Fun stats from active torrents")

        self.cards: Dict[str, StatCard] = {}
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(14)
        labels = [
            "Highest Total Upload",
            "Longest Seeded",
            "Total Torrents Completed",
            "Average Ratio",
            "Longest Running Active",
        ]
        for idx, label in enumerate(labels):
            card = StatCard(label)
            self.cards[label] = card
            grid.addWidget(card, idx // 2, idx % 2)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.addWidget(header)
        layout.addLayout(grid)
        layout.addStretch(1)

    def update_stats(self, stats: Dict[str, Any]) -> None:
        self.cards["Highest Total Upload"].set_value(stats.get("highest_upload", "--"))
        self.cards["Longest Seeded"].set_value(stats.get("longest_seeded", "--"))
        self.cards["Total Torrents Completed"].set_value(str(stats.get("completed", 0)))
        self.cards["Average Ratio"].set_value(format_ratio(stats.get("avg_ratio", 0)))
        self.cards["Longest Running Active"].set_value(stats.get("longest_active", "--"))


class SettingsView(QtWidgets.QWidget):
    interval_changed = QtCore.Signal(int)
    theme_changed = QtCore.Signal(str)
    manage_clients = QtCore.Signal()

    def __init__(self, interval: int, theme_mode: str = "dark") -> None:
        super().__init__()
        header = SectionHeader("Settings", "Tune refresh behavior and clients")

        self.interval_spin = QtWidgets.QSpinBox()
        self.interval_spin.setRange(1, 120)
        self.interval_spin.setValue(interval)
        self.interval_spin.setSuffix(" s")

        interval_row = QtWidgets.QHBoxLayout()
        interval_row.addWidget(QtWidgets.QLabel("Refresh interval"))
        interval_row.addStretch(1)
        interval_row.addWidget(self.interval_spin)

        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.set_theme_mode(theme_mode)

        theme_row = QtWidgets.QHBoxLayout()
        theme_row.addWidget(QtWidgets.QLabel("Appearance"))
        theme_row.addStretch(1)
        theme_row.addWidget(self.theme_combo)

        self.manage_button = QtWidgets.QPushButton("Manage qBittorrent Clients")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.addWidget(header)
        layout.addLayout(interval_row)
        layout.addLayout(theme_row)
        layout.addWidget(self.manage_button)
        layout.addStretch(1)

        self.interval_spin.valueChanged.connect(self.interval_changed.emit)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        self.manage_button.clicked.connect(self.manage_clients.emit)

    def _on_theme_changed(self, value: str) -> None:
        mode = "light" if value.lower().startswith("light") else "dark"
        self.theme_changed.emit(mode)

    def set_theme_mode(self, mode: str) -> None:
        target = "Light" if str(mode).lower() == "light" else "Dark"
        idx = self.theme_combo.findText(target)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
