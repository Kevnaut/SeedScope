from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6 import QtCore, QtWidgets

from app.services.qbit_client import QbitClient


class ConnectionTester(QtCore.QThread):
    finished_test = QtCore.Signal(bool, str)

    def __init__(self, payload: Dict[str, Any]) -> None:
        super().__init__()
        self.payload = payload

    def run(self) -> None:
        try:
            client = QbitClient(self.payload, timeout=4.0)
            client.test_connection()
            self.finished_test.emit(True, "Connected")
        except Exception as exc:
            self.finished_test.emit(False, str(exc))


class ClientDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, data: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("qBittorrent Client")
        self.setModal(True)
        self._validated = False
        self._tester: Optional[ConnectionTester] = None

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFormAlignment(QtCore.Qt.AlignLeft)

        self.name_input = QtWidgets.QLineEdit()
        self.host_input = QtWidgets.QLineEdit()
        self.port_input = QtWidgets.QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(8080)
        self.user_input = QtWidgets.QLineEdit()
        self.pass_input = QtWidgets.QLineEdit()
        self.pass_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.https_toggle = QtWidgets.QCheckBox("Use HTTPS")
        self.completed_input = QtWidgets.QLineEdit()
        self.completed_button = QtWidgets.QPushButton("Browse")
        self.transfer_input = QtWidgets.QLineEdit()
        self.transfer_button = QtWidgets.QPushButton("Browse")
        self.webui_input = QtWidgets.QLineEdit()
        self.completed_input.setPlaceholderText("/downloads/completed")
        self.transfer_input.setPlaceholderText(r"\\server\share\downloads\completed")
        self.webui_input.setPlaceholderText("/qbt (optional)")

        form.addRow("Client Name", self.name_input)
        form.addRow("Host / IP", self.host_input)
        form.addRow("Port", self.port_input)
        form.addRow("Username", self.user_input)
        form.addRow("Password", self.pass_input)
        form.addRow("Web UI Path", self.webui_input)
        completed_row = QtWidgets.QHBoxLayout()
        completed_row.addWidget(self.completed_input, 1)
        completed_row.addWidget(self.completed_button)
        form.addRow("Completed Folder (Local)", completed_row)
        transfer_row = QtWidgets.QHBoxLayout()
        transfer_row.addWidget(self.transfer_input, 1)
        transfer_row.addWidget(self.transfer_button)
        form.addRow("Transfer Path (UNC)", transfer_row)
        form.addRow("", self.https_toggle)

        self.hint_label = QtWidgets.QLabel(
            "Examples: Local Completed Folder = /downloads/completed (container path). "
            "Transfer Path (UNC) = \\\\server\\share\\downloads\\completed. "
            "Find the local path in qBittorrent Settings \u2192 Downloads."
        )
        self.hint_label.setObjectName("Muted")

        self.status_label = QtWidgets.QLabel("Test connection before saving")
        self.status_label.setObjectName("Muted")

        self.test_button = QtWidgets.QPushButton("Test Connection")
        self.save_button = QtWidgets.QPushButton("Save")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.save_button.setEnabled(False)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.test_button)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addLayout(buttons)

        self.test_button.clicked.connect(self._on_test)
        self.save_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.completed_button.clicked.connect(self._browse_completed)
        self.transfer_button.clicked.connect(self._browse_transfer)

        for widget in [
            self.name_input,
            self.host_input,
            self.user_input,
            self.pass_input,
            self.completed_input,
            self.transfer_input,
            self.webui_input,
        ]:
            widget.textChanged.connect(self._mark_dirty)
        self.port_input.valueChanged.connect(self._mark_dirty)
        self.https_toggle.toggled.connect(self._mark_dirty)

        if data:
            self.name_input.setText(str(data.get("name", "")))
            self.host_input.setText(str(data.get("host", "")))
            self.port_input.setValue(int(data.get("port", 8080)))
            self.user_input.setText(str(data.get("username", "")))
            self.pass_input.setText(str(data.get("password", "")))
            self.https_toggle.setChecked(bool(data.get("use_https")))
            self.completed_input.setText(str(data.get("completed_path", "")))
            self.webui_input.setText(str(data.get("webui_path", "")))
            self.transfer_input.setText(str(data.get("transfer_path", "")))

    def _mark_dirty(self) -> None:
        self._validated = False
        self.status_label.setText("Test connection before saving")
        self.status_label.setStyleSheet("")
        self.save_button.setEnabled(False)

    def _on_test(self) -> None:
        payload = self.get_payload()
        if not payload["host"] or not payload["name"]:
            self.status_label.setText("Name and host are required")
            return
        self.test_button.setEnabled(False)
        self.status_label.setText("Testing connection...")
        self._tester = ConnectionTester(payload)
        self._tester.finished_test.connect(self._on_test_done)
        self._tester.start()

    def _on_test_done(self, ok: bool, message: str) -> None:
        self.test_button.setEnabled(True)
        if ok:
            self._validated = True
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: #23e0d0;")
            self.save_button.setEnabled(True)
        else:
            self._validated = False
            self.status_label.setText(f"Failed: {message}")
            self.status_label.setStyleSheet("color: #ff5d73;")
            self.save_button.setEnabled(False)

    def _browse_completed(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Completed Folder")
        if folder:
            self.completed_input.setText(folder)

    def _browse_transfer(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Transfer Folder")
        if folder:
            self.transfer_input.setText(folder)

    def get_payload(self) -> Dict[str, Any]:
        host_text = self.host_input.text().strip()
        port = int(self.port_input.value())
        webui_path = self.webui_input.text().strip() or None
        completed_path = self.completed_input.text().strip() or None
        transfer_path = self.transfer_input.text().strip() or None
        if host_text.startswith("http://") or host_text.startswith("https://"):
            try:
                from urllib.parse import urlparse

                parsed = urlparse(host_text)
                host_text = parsed.hostname or host_text
                if parsed.port:
                    port = parsed.port
                if parsed.path not in ("", "/") and not webui_path:
                    webui_path = parsed.path
            except Exception:
                pass
        if "/" in host_text:
            host_text = host_text.split("/", 1)[0]
        if completed_path:
            if completed_path.startswith("//"):
                completed_path = "\\\\" + completed_path[2:]
            if completed_path.startswith("\\\\") or (len(completed_path) >= 2 and completed_path[1] == ":"):
                completed_path = completed_path.replace("/", "\\")
        if transfer_path:
            if transfer_path.startswith("//"):
                transfer_path = "\\\\" + transfer_path[2:]
            if transfer_path.startswith("\\\\") or (len(transfer_path) >= 2 and transfer_path[1] == ":"):
                transfer_path = transfer_path.replace("/", "\\")
        return {
            "name": self.name_input.text().strip(),
            "host": host_text,
            "port": port,
            "username": self.user_input.text().strip(),
            "password": self.pass_input.text(),
            "use_https": self.https_toggle.isChecked(),
            "completed_path": completed_path,
            "webui_path": webui_path,
            "transfer_path": transfer_path,
        }
