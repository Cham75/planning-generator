from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .models import AgentProfile
from .utils import app_resource_path, normalize_name, token_name_key


class AgentStore:
    def __init__(self) -> None:
        appdata = os.environ.get("APPDATA") or str(Path.home() / ".planning_assistance")
        self.directory = Path(appdata) / "PlanningAssistance"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "agents.json"
        self._profiles: dict[str, AgentProfile] = {}
        self.load()

    @staticmethod
    def _key(agent_id: str, name: str) -> str:
        return str(agent_id).strip() or f"name:{token_name_key(name)}"

    def load(self) -> None:
        if self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            seed = app_resource_path("data/agents_seed.json")
            payload = json.loads(seed.read_text(encoding="utf-8")) if seed.exists() else []
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._profiles = {}
        for item in payload:
            profile = AgentProfile(
                agent_id=str(item.get("agent_id", "")).strip(),
                name=str(item.get("name", "")).strip(),
                role=str(item.get("role", "À définir")).strip() or "À définir",
                excluded=bool(item.get("excluded", False)),
                notes=str(item.get("notes", "")),
            )
            self._profiles[self._key(profile.agent_id, profile.name)] = profile

    def save(self) -> None:
        payload = [asdict(item) for item in sorted(self._profiles.values(), key=lambda p: normalize_name(p.name))]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_profiles(self) -> list[AgentProfile]:
        return sorted(self._profiles.values(), key=lambda p: normalize_name(p.name))

    def find(self, agent_id: str, name: str) -> AgentProfile | None:
        direct = self._profiles.get(self._key(agent_id, name))
        if direct:
            return direct
        wanted = token_name_key(name)
        for profile in self._profiles.values():
            if token_name_key(profile.name) == wanted:
                return profile
        return None

    def get_or_create(self, agent_id: str, name: str) -> tuple[AgentProfile, bool]:
        existing = self.find(agent_id, name)
        if existing:
            if not existing.agent_id and agent_id:
                existing.agent_id = agent_id
            if name and existing.name != name:
                existing.name = name
            return existing, False
        profile = AgentProfile(agent_id=str(agent_id), name=name)
        self._profiles[self._key(profile.agent_id, profile.name)] = profile
        return profile, True

    def upsert(self, profile: AgentProfile) -> None:
        stale_keys = [key for key, value in self._profiles.items() if value is profile]
        for key in stale_keys:
            self._profiles.pop(key, None)
        self._profiles[self._key(profile.agent_id, profile.name)] = profile
        self.save()
