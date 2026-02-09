from __future__ import annotations

from typing import Any, Dict, List

from PySide6 import QtCore, QtWidgets

from app.data import db
from app.ui.client_dialog import ClientDialog


class ClientManagerDialog(QtWidgets.QDialog):
    clients_updated = QtCore.Signal()

    def __init__(self, parent=None, statuses: Dict[int, str] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Clients")
        self.setModal(True)
        self.resize(600, 360)
        self._statuses = statuses or {}

        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Name",
                "Host",
                "Port",
                "HTTPS",
                "Web UI Path",
                "Completed Folder",
                "Transfer Path",
                "Status",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.add_button = QtWidgets.QPushButton("Add")
        self.edit_button = QtWidgets.QPushButton("Edit")
        self.remove_button = QtWidgets.QPushButton("Remove")
        self.close_button = QtWidgets.QPushButton("Close")

        button_row = QtWidgets.QHBoxLayout()
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.edit_button)
        button_row.addWidget(self.remove_button)
        button_row.addStretch(1)
        button_row.addWidget(self.close_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(button_row)

        self.add_button.clicked.connect(self._add_client)
        self.edit_button.clicked.connect(self._edit_client)
        self.remove_button.clicked.connect(self._remove_client)
        self.close_button.clicked.connect(self.accept)

        self.load_clients()

    def set_statuses(self, statuses: Dict[int, str]) -> None:
        self._statuses = statuses
        self.load_clients()

    def load_clients(self) -> None:
        clients = db.get_clients()
        self.table.setRowCount(len(clients))
        for row, client in enumerate(clients):
            name_item = QtWidgets.QTableWidgetItem(client["name"])
            name_item.setData(QtCore.Qt.UserRole, int(client["id"]))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(client["host"]))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(client["port"])))
            https_item = QtWidgets.QTableWidgetItem("Yes" if client["use_https"] else "No")
            self.table.setItem(row, 3, https_item)
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(client.get("webui_path") or ""))
            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(client.get("completed_path") or ""))
            self.table.setItem(row, 6, QtWidgets.QTableWidgetItem(client.get("transfer_path") or ""))
            status = self._statuses.get(int(client["id"]), "unknown")
            status_item = QtWidgets.QTableWidgetItem(status.capitalize())
            self.table.setItem(row, 7, status_item)
            self.table.setRowHeight(row, 36)
        self.table.resizeColumnsToContents()

    def _get_selected(self) -> Dict[str, Any] | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        name_item = self.table.item(row, 0)
        if name_item is None:
            return None
        client_id = name_item.data(QtCore.Qt.UserRole)
        clients = db.get_clients()
        for client in clients:
            if int(client["id"]) == int(client_id):
                return client
        return None

    def _add_client(self) -> None:
        dialog = ClientDialog(self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            db.add_client(dialog.get_payload())
            self.load_clients()
            self.clients_updated.emit()

    def _edit_client(self) -> None:
        client = self._get_selected()
        if not client:
            return
        dialog = ClientDialog(self, data=client)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            db.update_client(client["id"], dialog.get_payload())
            self.load_clients()
            self.clients_updated.emit()

    def _remove_client(self) -> None:
        client = self._get_selected()
        if not client:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Remove Client",
            f"Remove {client['name']}?",
        )
        if confirm == QtWidgets.QMessageBox.Yes:
            db.delete_client(client["id"])
            self.load_clients()
            self.clients_updated.emit()
