from __future__ import annotations

import os
import shutil
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PySide6 import QtCore

from app.services.qbit_client import QbitClient
from app.utils.logging import get_logger


class TransferWorker(QtCore.QThread):
    state_changed = QtCore.Signal(str, str)
    progress_changed = QtCore.Signal(str, str, float)
    error = QtCore.Signal(str, str)
    finished_all = QtCore.Signal()

    def __init__(
        self,
        source: Dict[str, Any],
        destination: Dict[str, Any],
        torrents: List[Dict[str, Any]],
        source_base: str,
        dest_base: str,
        dest_save_path: str,
        clean_destination: bool = True,
    ) -> None:
        super().__init__()
        self.source = source
        self.destination = destination
        self.torrents = torrents
        self.source_base = _normalize_share_path(source_base)
        self.dest_base = _normalize_share_path(dest_base)
        self.dest_save_path = str(dest_save_path or "").strip() or self.dest_base
        self.clean_destination = bool(clean_destination)
        self._abort = False
        self._logger = get_logger("transfer")

    def stop(self) -> None:
        self._abort = True

    def run(self) -> None:
        src_client = QbitClient(self.source)
        dst_client = QbitClient(self.destination)
        for torrent in self.torrents:
            if self._abort:
                break
            torrent_hash = torrent.get("hash")
            if not torrent_hash:
                continue
            try:
                self._logger.info("Transfer start: %s", torrent.get("name", torrent_hash))
                self._transfer_one(src_client, dst_client, torrent)
                self._logger.info("Transfer complete: %s", torrent.get("name", torrent_hash))
            except Exception as exc:
                self._logger.exception("Transfer failed: %s", torrent.get("name", torrent_hash))
                self.error.emit(torrent_hash, str(exc))
                break
        self.finished_all.emit()

    def _transfer_one(self, src_client: QbitClient, dst_client: QbitClient, torrent: Dict[str, Any]) -> None:
        torrent_hash = torrent["hash"]
        if torrent.get("progress", 0) < 1:
            raise RuntimeError("Torrent is not 100% complete")
        if dst_client.has_torrent(torrent_hash):
            raise RuntimeError("Destination already has this torrent hash")
        if self.source_base and not Path(self.source_base).exists():
            raise RuntimeError(f"Source completed folder not accessible: {self.source_base}")
        if self.dest_base and not Path(self.dest_base).exists():
            raise RuntimeError(f"Destination completed folder not accessible: {self.dest_base}")
        total = int(torrent.get("size", 0) or 0)
        if not check_disk_space(self.dest_base, total):
            raise RuntimeError("Destination disk space is insufficient")
        self.state_changed.emit(torrent_hash, "Paused on source")
        self._logger.info("Pause source: %s", torrent_hash)
        src_client.pause_torrent(torrent_hash)

        self.state_changed.emit(torrent_hash, "Copying")
        self._logger.info("Copying data: %s", torrent_hash)
        source_path, dest_rel = _resolve_transfer_paths(torrent, self.source_base)
        if source_path is None:
            raise RuntimeError("Unable to resolve source content path")
        dest_path = Path(self.dest_base) / dest_rel if dest_rel else Path(self.dest_base)
        self._logger.info("Resolved paths: source=%s dest=%s", source_path, dest_path)
        if self.clean_destination:
            _clean_destination_path(dest_path)
        self.progress_changed.emit(torrent_hash, "Copying", 0.0)
        last_progress = -1.0
        last_emit = 0.0

        def copy_progress(done: int, total: int) -> None:
            nonlocal last_progress, last_emit
            progress = 1.0 if total <= 0 else max(0.0, min(1.0, float(done) / float(total)))
            now = time.monotonic()
            if progress >= 1.0 or progress - last_progress >= 0.01 or (now - last_emit) >= 0.5:
                last_progress = progress
                last_emit = now
                self.progress_changed.emit(torrent_hash, "Copying", progress)

        _copy_with_resume(Path(source_path), dest_path, progress_cb=copy_progress)

        self.state_changed.emit(torrent_hash, "Adding to destination")
        self._logger.info("Add to destination after copy: %s", torrent_hash)
        torrent_file = src_client.export_torrent(torrent_hash)
        if torrent_file is None:
            raise RuntimeError("Failed to export torrent file from source")
        self._logger.info("Destination save path: %s", self.dest_save_path)
        dst_client.add_torrent(torrent_file, str(self.dest_save_path), torrent_hash)
        time.sleep(2)
        info = dst_client.get_torrent_info(torrent_hash)
        if info:
            self._logger.info(
                "Destination info: save_path=%s content_path=%s state=%s progress=%s",
                info.get("save_path"),
                info.get("content_path"),
                info.get("state"),
                info.get("progress"),
            )
        _enforce_destination_location(dst_client, torrent_hash, self.dest_save_path, self._logger)
        dst_client.pause_torrent(torrent_hash)

        self.state_changed.emit(torrent_hash, "Rechecking")
        self._logger.info("Recheck destination: %s", torrent_hash)
        _enforce_destination_location(dst_client, torrent_hash, self.dest_save_path, self._logger)
        dst_client.recheck_torrent(torrent_hash)
        dst_client.resume_torrent(torrent_hash)
        if not _wait_for_recheck(
            dst_client,
            torrent_hash,
            progress_cb=lambda p: self.progress_changed.emit(torrent_hash, "Rechecking", p),
        ):
            raise RuntimeError("Destination recheck did not complete")

        self.state_changed.emit(torrent_hash, "Seeding on destination")
        self._logger.info("Resume destination: %s", torrent_hash)
        dst_client.resume_torrent(torrent_hash)

        self.state_changed.emit(torrent_hash, "Cleaning up source")
        self._logger.info("Delete source data: %s", torrent_hash)
        try:
            src_client.delete_torrent(torrent_hash, delete_files=True)
        except Exception as exc:
            self._logger.info("API delete failed, will try filesystem cleanup: %s", exc)
        if source_path:
            _cleanup_source_path(Path(source_path))

        self.state_changed.emit(torrent_hash, "Complete")


def _resolve_transfer_paths(
    torrent: Dict[str, Any], base_path: str | None
) -> tuple[Optional[str], Optional[Path]]:
    content = torrent.get("content_path")
    save_path = torrent.get("save_path")
    name = torrent.get("name")
    rel = None
    if content and save_path:
        try:
            rel = PurePosixPath(str(content)).relative_to(PurePosixPath(str(save_path)))
        except Exception:
            rel = None
    if rel is None and name:
        rel = PurePosixPath(str(name))

    def rel_path(value: PurePosixPath | None) -> Path | None:
        if value is None:
            return None
        if str(value) in ("", "."):
            return Path()
        return Path(str(value))

    rel_clean = rel_path(rel)

    if base_path:
        base = Path(base_path)
        if rel_clean is not None:
            candidate = base if rel_clean == Path() else base / rel_clean
            if candidate.exists():
                return str(candidate), rel_clean
        if content:
            candidate = base / PurePosixPath(str(content)).name
            if candidate.exists():
                return str(candidate), Path(candidate.name)
        if name:
            candidate = base / str(name)
            if candidate.exists():
                return str(candidate), Path(str(name))

    if content:
        return str(content), rel_clean or Path(PurePosixPath(str(content)).name)
    if save_path and name:
        return str(Path(save_path) / name), Path(str(name))
    return None, None


def _copy_with_resume(source: Path, dest: Path, progress_cb=None) -> None:
    if source.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        source_size = source.stat().st_size
        existing = min(dest.stat().st_size, source_size) if dest.exists() else 0
        if progress_cb:
            progress_cb(existing, source_size)
        if existing == source_size:
            return
        _copy_file_with_progress(
            source,
            dest,
            start_offset=existing if 0 < existing < source_size else 0,
            progress_cb=progress_cb,
            progress_base=0,
            progress_total=max(1, source_size),
        )
        return

    if source.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        files: list[tuple[Path, Path, int, int]] = []
        total_size = 0
        completed = 0
        for root, _dirs, file_names in os.walk(source):
            rel = Path(root).relative_to(source)
            target_dir = dest / rel
            target_dir.mkdir(parents=True, exist_ok=True)
            for file_name in file_names:
                src_file = Path(root) / file_name
                dst_file = target_dir / file_name
                size = src_file.stat().st_size
                existing = min(dst_file.stat().st_size, size) if dst_file.exists() else 0
                files.append((src_file, dst_file, size, existing))
                total_size += size
                completed += existing
        if progress_cb:
            progress_cb(completed, max(1, total_size))
        for src_file, dst_file, size, existing in files:
            if existing == size:
                continue
            _copy_file_with_progress(
                src_file,
                dst_file,
                start_offset=existing if 0 < existing < size else 0,
                progress_cb=progress_cb,
                progress_base=completed - existing,
                progress_total=max(1, total_size),
            )
            completed += size - existing
            if progress_cb:
                progress_cb(completed, max(1, total_size))
        return
    raise RuntimeError(f"Source path does not exist: {source}")


def _copy_file_with_progress(
    source: Path,
    dest: Path,
    start_offset: int,
    progress_cb=None,
    progress_base: int = 0,
    progress_total: int = 1,
    chunk_size: int = 8 * 1024 * 1024,
) -> None:
    source_size = source.stat().st_size
    if start_offset >= source_size:
        if progress_cb:
            progress_cb(progress_base + source_size, progress_total)
        return
    if start_offset > 0 and dest.exists():
        dst_mode = "ab"
    else:
        dst_mode = "wb"
        start_offset = 0
    with source.open("rb") as src_stream, dest.open(dst_mode) as dst_stream:
        if start_offset:
            src_stream.seek(start_offset)
        copied = start_offset
        if progress_cb:
            progress_cb(progress_base + copied, progress_total)
        while True:
            chunk = src_stream.read(chunk_size)
            if not chunk:
                break
            dst_stream.write(chunk)
            copied += len(chunk)
            if progress_cb:
                progress_cb(progress_base + copied, progress_total)
    shutil.copystat(source, dest)


def _clean_destination_path(dest_path: Path) -> None:
    if not dest_path.exists():
        return
    # Safety: never delete the root destination folder itself.
    if dest_path.parent == dest_path or dest_path.name in ("", ".", ".."):
        raise RuntimeError("Refusing to delete destination root")
    if dest_path.is_file():
        dest_path.unlink()
        return
    shutil.rmtree(dest_path)


def _cleanup_source_path(source_path: Path) -> None:
    if not source_path.exists():
        return
    # Safety: never delete a root path.
    if source_path.parent == source_path or source_path.name in ("", ".", ".."):
        raise RuntimeError("Refusing to delete source root")
    if source_path.is_file():
        try:
            source_path.unlink()
        except FileNotFoundError:
            return
        return
    try:
        shutil.rmtree(source_path)
    except FileNotFoundError:
        return


def _normalize_share_path(path: str | None) -> str:
    if not path:
        return ""
    value = str(path).strip()
    if value.lower() == "none":
        return ""
    if value.startswith("//"):
        value = "\\\\" + value[2:]
    if value.startswith("\\\\") or (len(value) >= 2 and value[1] == ":"):
        value = value.replace("/", "\\")
    return value


def _enforce_destination_location(
    client: QbitClient, torrent_hash: str, dest_save_path: str, logger
) -> None:
    if not dest_save_path:
        return
    desired = str(dest_save_path).rstrip("/\\")
    for _ in range(4):
        info = client.get_torrent_info(torrent_hash)
        if not info:
            time.sleep(1)
            continue
        current = str(info.get("content_path") or "").rstrip("/\\")
        if current.startswith(desired):
            return
        try:
            client._request(
                "POST",
                "/api/v2/torrents/setLocation",
                data={"hashes": torrent_hash, "location": dest_save_path},
            )
            time.sleep(1)
        except Exception as exc:
            logger.info("SetLocation retry: %s", exc)
            time.sleep(1)
    info = client.get_torrent_info(torrent_hash)
    current = str(info.get("content_path") or "").rstrip("/\\") if info else ""
    if current and not current.startswith(desired):
        raise RuntimeError(
            f"Destination content path mismatch. content_path={current} expected={desired}"
        )


def _wait_for_recheck(
    client: QbitClient,
    torrent_hash: str,
    timeout: int = 900,
    progress_cb=None,
) -> bool:
    start = time.time()
    last_progress = None
    while time.time() - start < timeout:
        info = client.get_torrent_info(torrent_hash)
        if not info:
            time.sleep(2)
            continue
        state = info.get("state")
        progress = info.get("progress", 0)
        if state not in {"checkingUP", "checkingDL", "checkingResumeData", "allocating", "pausedDL"}:
            if progress >= 1.0:
                return True
        else:
            try:
                progress_val = max(0.0, min(1.0, float(progress)))
            except Exception:
                progress_val = 0.0
            if progress_cb and progress_val != last_progress:
                last_progress = progress_val
                progress_cb(progress_val)
        time.sleep(3)
    return False


def check_disk_space(path: str, required_bytes: int) -> bool:
    usage = shutil.disk_usage(path)
    return usage.free >= required_bytes


def total_size(torrents: Iterable[Dict[str, Any]]) -> int:
    return sum(int(t.get("size", 0) or 0) for t in torrents)
