from __future__ import annotations

import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_name(value: Any) -> str:
    return normalize_text(value)


def token_name_key(value: Any) -> str:
    return "|".join(sorted(normalize_name(value).split()))


def parse_excel_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    text = str(value).strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_time_minutes(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.hour * 60 + value.minute
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return int(value.hour) * 60 + int(value.minute)
    if isinstance(value, (int, float)):
        fraction = float(value) % 1
        return int(round(fraction * 24 * 60))
    text = str(value).strip().lower().replace("h", ":")
    if text in {"libre", "repos", "conge", "congé"}:
        return None
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def format_minutes(value: Optional[int]) -> str:
    if value is None:
        return "—"
    hour, minute = divmod(value, 60)
    return f"{hour:02d}h{minute:02d}"


def app_resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def safe_filename(value: str) -> str:
    value = re.sub(r"[<>:\"/\\|?*]+", "_", value).strip(" .")
    return value or "planning_assistance"
