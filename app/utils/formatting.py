from __future__ import annotations


def format_bytes(num: float) -> str:
    if num is None:
        return "0 B"
    step = 1024.0
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num)
    for unit in units:
        if size < step:
            return f"{size:.2f} {unit}"
        size /= step
    return f"{size:.2f} EB"


def format_speed(num: float) -> str:
    return f"{format_bytes(num)}/s"


def format_ratio(ratio: float) -> str:
    if ratio is None:
        return "0.00"
    return f"{ratio:.2f}"


def format_percent(value: float) -> str:
    if value is None:
        return "0%"
    return f"{value * 100:.1f}%"


def format_duration(seconds: float) -> str:
    if seconds is None:
        return "0s"
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def truncate_text(text: str, max_len: int = 20) -> str:
    if text is None:
        return ""
    value = str(text)
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return value[:max_len]
    return f"{value[: max_len - 3]}..."
