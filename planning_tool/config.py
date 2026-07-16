from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import Category, Slot
from .utils import app_resource_path, normalize_text


@dataclass
class AppConfig:
    slots: list[Slot]
    activity_map: dict[str, Category]
    blocked_categories_after_18: set[Category]
    role_options: list[str]
    excluded_agent_ids: set[str]
    excluded_name_keys: set[str]

    @classmethod
    def load_default(cls) -> "AppConfig":
        path = app_resource_path("data/default_config.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        slots = [Slot(int(item["start"]), int(item["end"]), int(item["need"])) for item in payload["slots"]]
        activity_map = {
            normalize_text(label): Category(category)
            for label, category in payload["activity_map"].items()
        }
        return cls(
            slots=slots,
            activity_map=activity_map,
            blocked_categories_after_18={Category(value) for value in payload["blocked_categories_after_18"]},
            role_options=list(payload["role_options"]),
            excluded_agent_ids=set(payload.get("excluded_agent_ids", [])),
            excluded_name_keys=set(payload.get("excluded_name_keys", [])),
        )

    def classify_activity(self, activity: str) -> Category:
        normalized = normalize_text(activity)
        if normalized in self.activity_map:
            return self.activity_map[normalized]
        # Conservative fuzzy handling for harmless punctuation/casing variations.
        for key, category in self.activity_map.items():
            if key and (normalized == key or normalized.startswith(key + " ")):
                return category
        return Category.NON_ELIGIBLE
