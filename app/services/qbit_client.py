from __future__ import annotations

import time
from typing import Any, Dict, List

import requests

from app.utils.logging import get_logger

try:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


class QbitClient:
    def __init__(self, config: Dict[str, Any], timeout: float = 4.0) -> None:
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()
        self._logged_in = False
        self._base_checked = False
        self._logger = get_logger("qbit")
        self._logger.info("QbitClient source: %s", __file__)
        auto_paths = {"qbit", "/qbit", "qbt", "/qbt", "qbittorrent", "/qbittorrent"}
        current_path = str(self.config.get("webui_path") or "").strip()
        if current_path in auto_paths:
            self.config["webui_path"] = ""

    @property
    def base_url(self) -> str:
        return self._build_base_url(self.config.get("webui_path"))

    def _parse_host(self) -> tuple[str, str, int, str]:
        scheme = "https" if self.config.get("use_https") else "http"
        host = str(self.config.get("host", "")).strip()
        port = int(self.config.get("port", 0))
        host_path = ""
        if host.startswith("http://") or host.startswith("https://"):
            try:
                from urllib.parse import urlparse

                parsed = urlparse(host)
                host = parsed.hostname or host
                if parsed.port:
                    port = parsed.port
                if parsed.path not in ("", "/"):
                    host_path = parsed.path
            except Exception:
                pass
        if "/" in host:
            host = host.split("/", 1)[0]
        return scheme, host, port, host_path

    def _build_base_url(self, webui_path: Any) -> str:
        scheme, host, port, host_path = self._parse_host()
        base_path = str(webui_path or "").strip()
        if base_path.startswith("http://") or base_path.startswith("https://"):
            # If a full URL is pasted into the Web UI Path, keep only the path segment.
            try:
                from urllib.parse import urlparse

                base_path = urlparse(base_path).path
            except Exception:
                base_path = ""
        if not base_path and host_path:
            base_path = host_path
        if base_path and not base_path.startswith("/"):
            base_path = f"/{base_path}"
        base_path = base_path.rstrip("/")
        return f"{scheme}://{host}:{port}{base_path}"

    def _build_root_url(self) -> str:
        scheme, host, port, _host_path = self._parse_host()
        return f"{scheme}://{host}:{port}"

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        suppress_http_error_log = bool(kwargs.pop("suppress_http_error_log", False))
        kwargs.setdefault("timeout", self.timeout)
        if self.config.get("use_https"):
            kwargs.setdefault("verify", False)
        if path.startswith("/api/v2/") and not self._base_checked:
            self._ensure_base_path(kwargs)
        base = self._build_base_url(self.config.get("webui_path")) if path.startswith("/api/v2/") else self.base_url
        url = f"{base}{path}"
        if "/qbit/" in url or "/qbt/" in url or "/qbittorrent/" in url:
            self._logger.debug("Using webui_path=%s url=%s", self.config.get("webui_path"), url)
        resp = self.session.request(method, url, **kwargs)
        if resp.status_code == 404:
            # Force-try root and known prefixes on 404 to avoid stale webui_path.
            for candidate in [""] + self._fallback_paths():
                url = f"{self._build_base_url(candidate)}{path}"
                resp = self.session.request(method, url, **kwargs)
                if resp.status_code != 404:
                    self.config["webui_path"] = candidate
                    break
        if resp.status_code == 403:
            self._logged_in = False
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            if not suppress_http_error_log:
                self._logger.error("HTTP %s %s -> %s", method, url, resp.status_code)
            raise
        return resp

    def _ensure_base_path(self, kwargs: Dict[str, Any]) -> None:
        # Probe API version to validate the base path.
        if self._base_checked:
            return
        candidates = ["", self.config.get("webui_path")] + self._fallback_paths()
        probe_kwargs = {"timeout": kwargs.get("timeout", self.timeout)}
        if self.config.get("use_https"):
            probe_kwargs["verify"] = False
        tried = set()
        for candidate in candidates:
            candidate = "" if candidate is None else candidate
            if candidate in tried:
                continue
            tried.add(candidate)
            base = self._build_base_url(candidate)
            url = f"{base}/api/v2/app/version"
            resp = self.session.request("GET", url, **probe_kwargs)
            if resp.status_code in (200, 403):
                self.config["webui_path"] = candidate
                break
        self._base_checked = True

    def _fallback_paths(self) -> List[str]:
        paths = []
        current = str(self.config.get("webui_path") or "").strip()
        if current:
            paths.append("")
        for candidate in ["qbittorrent", "qbt", "qbit"]:
            if current.strip("/") != candidate:
                paths.append(candidate)
        return paths

    def login(self) -> bool:
        data = {
            "username": self.config.get("username", ""),
            "password": self.config.get("password", ""),
        }
        try:
            resp = self._request("POST", "/api/v2/auth/login", data=data)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 400:
                headers = {
                    "Referer": self.base_url,
                    "Origin": self.base_url,
                    "User-Agent": "SeedScope/1.0",
                }
                url = f"{self.base_url}/api/v2/auth/login"
                resp = self.session.post(url, data=data, headers=headers, timeout=self.timeout)
            else:
                raise
        if resp.text.strip() == "Ok.":
            self._logged_in = True
            return True
        self._logged_in = False
        return False

    def ensure_login(self) -> None:
        if not self._logged_in:
            if not self.login():
                raise RuntimeError("Authentication failed")

    def fetch_sync(self) -> Dict[str, Any]:
        self.ensure_login()
        resp = self._request("GET", "/api/v2/sync/maindata")
        return resp.json()

    def fetch_torrents(self) -> List[Dict[str, Any]]:
        self.ensure_login()
        resp = self._request("GET", "/api/v2/torrents/info", params={"filter": "all"})
        return list(resp.json())

    def get_torrent_info(self, torrent_hash: str) -> Dict[str, Any] | None:
        self.ensure_login()
        resp = self._request("GET", "/api/v2/torrents/info", params={"hashes": torrent_hash})
        data = list(resp.json())
        return data[0] if data else None

    def has_torrent(self, torrent_hash: str) -> bool:
        return self.get_torrent_info(torrent_hash) is not None

    def pause_torrent(self, torrent_hash: str) -> None:
        self.ensure_login()
        try:
            self._request(
                "POST",
                "/api/v2/torrents/pause",
                data={"hashes": torrent_hash},
                suppress_http_error_log=True,
            )
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 404:
                self._request("POST", "/api/v2/torrents/stop", data={"hashes": torrent_hash})
            else:
                raise

    def resume_torrent(self, torrent_hash: str) -> None:
        self.ensure_login()
        try:
            self._request(
                "POST",
                "/api/v2/torrents/resume",
                data={"hashes": torrent_hash},
                suppress_http_error_log=True,
            )
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 404:
                self._request("POST", "/api/v2/torrents/start", data={"hashes": torrent_hash})
            else:
                raise

    def recheck_torrent(self, torrent_hash: str) -> None:
        self.ensure_login()
        self._request("POST", "/api/v2/torrents/recheck", data={"hashes": torrent_hash})

    def delete_torrent(self, torrent_hash: str, delete_files: bool = False) -> None:
        self.ensure_login()
        data = {"hashes": torrent_hash, "deleteFiles": "true" if delete_files else "false"}
        try:
            self._request("POST", "/api/v2/torrents/delete", data=data)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in {400, 404}:
                # Try alternate param name and query string format.
                alt_data = {"hashes": torrent_hash, "deletefiles": "true" if delete_files else "false"}
                try:
                    self._request("POST", "/api/v2/torrents/delete", data=alt_data)
                    return
                except Exception:
                    self._request(
                        "GET",
                        "/api/v2/torrents/delete",
                        params=alt_data,
                    )
            else:
                raise

    def export_torrent(self, torrent_hash: str) -> bytes | None:
        self.ensure_login()
        try:
            resp = self._request("GET", "/api/v2/torrents/export", params={"hash": torrent_hash})
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 400:
                resp = self._request("GET", "/api/v2/torrents/export", params={"hashes": torrent_hash})
            else:
                raise
        return resp.content if resp.content else None

    def add_torrent(self, torrent_data: bytes, save_path: str, torrent_hash: str | None = None) -> None:
        self.ensure_login()
        files = {"torrents": ("transfer.torrent", torrent_data)}
        data = {"savepath": save_path, "paused": "true", "autoTMM": "false"}
        self._request("POST", "/api/v2/torrents/add", files=files, data=data)
        if torrent_hash:
            try:
                self._request(
                    "POST",
                    "/api/v2/torrents/setLocation",
                    data={"hashes": torrent_hash, "location": save_path},
                )
            except Exception:
                pass

    def fetch_snapshot(self) -> Dict[str, Any]:
        sync = self.fetch_sync()
        torrents = self.fetch_torrents()
        server_state = sync.get("server_state", {})
        return {
            "server_state": server_state,
            "torrents": torrents,
            "sync_time": time.time(),
        }

    def test_connection(self) -> None:
        self.fetch_snapshot()
