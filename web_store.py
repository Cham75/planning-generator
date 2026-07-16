from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from planning_tool.models import AgentProfile
from planning_tool.utils import normalize_name, token_name_key


class MemoryAgentStore:
    """Small in-memory replacement for the desktop AgentStore.

    Streamlit Community Cloud can restart at any time, so the web version does
    not write application data to the server. Roles can instead be downloaded
    as a JSON configuration and uploaded again on the next use.
    """

    def __init__(self, profiles: Iterable[AgentProfile] = ()) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        for profile in profiles:
            self.upsert(profile)

    @staticmethod
    def _key(agent_id: str, name: str) -> str:
        return str(agent_id).strip() or f"name:{token_name_key(name)}"

    def load(self) -> None:
        return None

    def save(self) -> None:
        return None

    def list_profiles(self) -> list[AgentProfile]:
        return sorted(self._profiles.values(), key=lambda item: normalize_name(item.name))

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
                existing.agent_id = str(agent_id)
            if name:
                existing.name = name
            return existing, False
        profile = AgentProfile(agent_id=str(agent_id), name=name)
        self._profiles[self._key(profile.agent_id, profile.name)] = profile
        return profile, True

    def upsert(self, profile: AgentProfile) -> None:
        stale = [key for key, value in self._profiles.items() if value is profile]
        for key in stale:
            self._profiles.pop(key, None)
        self._profiles[self._key(profile.agent_id, profile.name)] = profile


def load_profiles(seed_path: Path, uploaded_json: bytes | None = None) -> list[AgentProfile]:
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    if uploaded_json:
        custom = json.loads(uploaded_json.decode("utf-8-sig"))
        if not isinstance(custom, list):
            raise ValueError("La configuration agents doit contenir une liste JSON.")
        by_key = {
            MemoryAgentStore._key(str(item.get("agent_id", "")), str(item.get("name", ""))): item
            for item in payload
        }
        for item in custom:
            key = MemoryAgentStore._key(str(item.get("agent_id", "")), str(item.get("name", "")))
            by_key[key] = item
        payload = list(by_key.values())

    profiles: list[AgentProfile] = []
    for item in payload:
        profiles.append(
            AgentProfile(
                agent_id=str(item.get("agent_id", "")).strip(),
                name=str(item.get("name", "")).strip(),
                role=str(item.get("role", "À définir")).strip() or "À définir",
                excluded=bool(item.get("excluded", False)),
                notes=str(item.get("notes", "")),
            )
        )
    return profiles


def profiles_to_json(profiles: Iterable[AgentProfile]) -> bytes:
    payload = [asdict(item) for item in sorted(profiles, key=lambda item: normalize_name(item.name))]
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
