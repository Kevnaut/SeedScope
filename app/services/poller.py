from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

from PySide6 import QtCore

from app.services.qbit_client import QbitClient


class Poller(QtCore.QThread):
    data_ready = QtCore.Signal(object)
    status_ready = QtCore.Signal(object)

    def __init__(self, clients: List[Dict[str, Any]], interval: float) -> None:
        super().__init__()
        self._clients = clients
        self._interval = interval
        self._running = threading.Event()
        self._lock = threading.Lock()
        self._client_sessions: Dict[int, QbitClient] = {}

    def update_clients(self, clients: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._clients = list(clients)
            client_ids = {int(c["id"]) for c in clients}
            for cid in list(self._client_sessions.keys()):
                if cid not in client_ids:
                    self._client_sessions.pop(cid, None)
            lookup = {int(c["id"]): c for c in clients}
            for cid, session in list(self._client_sessions.items()):
                config = lookup.get(cid)
                if config is None:
                    continue
                if not self._config_equal(session.config, config):
                    self._client_sessions.pop(cid, None)

    @staticmethod
    def _config_equal(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
        keys = ["host", "port", "username", "password", "use_https", "webui_path"]
        return all(left.get(k) == right.get(k) for k in keys)

    def update_interval(self, interval: float) -> None:
        with self._lock:
            self._interval = interval

    def stop(self) -> None:
        self._running.clear()

    def _get_interval(self) -> float:
        with self._lock:
            return float(self._interval)

    def _get_clients(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._clients)

    def run(self) -> None:
        self._running.set()
        while self._running.is_set():
            clients = self._get_clients()
            snapshots: Dict[int, Dict[str, Any]] = {}
            statuses: Dict[int, str] = {}
            for client in clients:
                client_id = int(client["id"])
                qbit = self._client_sessions.get(client_id)
                if qbit is None:
                    qbit = QbitClient(client)
                    self._client_sessions[client_id] = qbit
                try:
                    snapshot = qbit.fetch_snapshot()
                    snapshot["client_id"] = client_id
                    snapshots[client_id] = snapshot
                    statuses[client_id] = "connected"
                except Exception:
                    statuses[client_id] = "offline"
            if snapshots:
                self.data_ready.emit(snapshots)
            if statuses:
                self.status_ready.emit(statuses)
            interval = max(1.0, self._get_interval())
            time.sleep(interval)
