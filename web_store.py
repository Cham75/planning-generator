from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, MutableMapping, Protocol

from planning_tool.models import AgentProfile
from planning_tool.utils import normalize_name, token_name_key


BROWSER_STORAGE_KEY = "planning_assistance_agents_v1"
SESSION_CACHE_KEY = "_planning_assistance_agents_json"
SESSION_REVISION_KEY = "_planning_assistance_storage_revision"


def profile_key(agent_id: str, name: str) -> str:
    clean_id = str(agent_id).strip()
    return clean_id or f"name:{token_name_key(name)}"


def _profiles_from_payload(payload: object) -> list[AgentProfile]:
    if not isinstance(payload, list):
        raise ValueError("La configuration des agents doit contenir une liste JSON.")
    profiles: list[AgentProfile] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        agent_id = str(item.get("agent_id", "")).strip()
        if not name and not agent_id:
            continue
        profiles.append(
            AgentProfile(
                agent_id=agent_id,
                name=name,
                role=str(item.get("role", "À définir")).strip() or "À définir",
                excluded=bool(item.get("excluded", False)),
                notes=str(item.get("notes", "")).strip(),
            )
        )
    return profiles


def profiles_from_json_bytes(content: bytes) -> list[AgentProfile]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Le fichier de sauvegarde JSON est invalide.") from exc
    return _profiles_from_payload(payload)


def load_seed_profiles(seed_path: Path) -> list[AgentProfile]:
    return _profiles_from_payload(json.loads(seed_path.read_text(encoding="utf-8")))


def profiles_to_json(profiles: Iterable[AgentProfile]) -> bytes:
    payload = [asdict(item) for item in sorted(profiles, key=lambda item: normalize_name(item.name))]
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _copy_profile(profile: AgentProfile) -> AgentProfile:
    return AgentProfile(
        agent_id=str(profile.agent_id).strip(),
        name=str(profile.name).strip(),
        role=str(profile.role).strip() or "À définir",
        excluded=bool(profile.excluded),
        notes=str(profile.notes).strip(),
    )


class MemoryAgentStore:
    """In-memory adapter used by the scheduling engine."""

    def __init__(self, profiles: Iterable[AgentProfile] = ()) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        for profile in profiles:
            self.upsert(profile)

    @staticmethod
    def _key(agent_id: str, name: str) -> str:
        return profile_key(agent_id, name)

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


class BrowserStorageAdapter(Protocol):
    def getItem(self, itemKey: str): ...

    def setItem(self, itemKey: str, itemValue: Any, key: str = "set"): ...

    def eraseItem(self, itemKey: str, key: str = "eraseItem", default=None): ...


class AgentRepository(Protocol):
    mode: str
    persistent: bool

    def list_profiles(self) -> list[AgentProfile]: ...

    def upsert_many(self, profiles: Iterable[AgentProfile]) -> None: ...

    def replace_all(self, profiles: Iterable[AgentProfile]) -> None: ...

    def ensure_seed(self, profiles: Iterable[AgentProfile]) -> None: ...


class BrowserLocalStorageAgentRepository:
    """Stores the directory in the browser's localStorage.

    No database or server-side file is used. The data follows the browser profile
    and the Streamlit app origin, so it survives Streamlit reruns, app restarts,
    and code redeployments as long as the same app URL and browser profile are used.
    """

    mode = "Navigateur local"
    persistent = True

    def __init__(
        self,
        storage: BrowserStorageAdapter,
        session_cache: MutableMapping[str, Any],
        storage_key: str = BROWSER_STORAGE_KEY,
    ) -> None:
        self.storage = storage
        self.session_cache = session_cache
        self.storage_key = storage_key

    def _next_component_key(self, action: str) -> str:
        revision = int(self.session_cache.get(SESSION_REVISION_KEY, 0)) + 1
        self.session_cache[SESSION_REVISION_KEY] = revision
        return f"planning_agents_{action}_{revision}"

    def _read_raw(self) -> str | None:
        cached = self.session_cache.get(SESSION_CACHE_KEY)
        if isinstance(cached, str):
            return cached

        value = self.storage.getItem(self.storage_key)
        if value is None:
            return None
        if isinstance(value, str):
            raw = value
        else:
            raw = json.dumps(value, ensure_ascii=False)
        self.session_cache[SESSION_CACHE_KEY] = raw
        return raw

    def list_profiles(self) -> list[AgentProfile]:
        raw = self._read_raw()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
            return _profiles_from_payload(payload)
        except (json.JSONDecodeError, ValueError, TypeError):
            return []

    def _write_profiles(self, profiles: Iterable[AgentProfile]) -> None:
        raw = profiles_to_json(profiles).decode("utf-8")
        self.session_cache[SESSION_CACHE_KEY] = raw
        self.storage.setItem(
            self.storage_key,
            raw,
            key=self._next_component_key("save"),
        )

    def upsert_many(self, profiles: Iterable[AgentProfile]) -> None:
        merged = {profile_key(item.agent_id, item.name): item for item in self.list_profiles()}
        for profile in profiles:
            clean = _copy_profile(profile)
            merged[profile_key(clean.agent_id, clean.name)] = clean
        self._write_profiles(merged.values())

    def replace_all(self, profiles: Iterable[AgentProfile]) -> None:
        unique: dict[str, AgentProfile] = {}
        for profile in profiles:
            clean = _copy_profile(profile)
            unique[profile_key(clean.agent_id, clean.name)] = clean
        self._write_profiles(unique.values())

    def ensure_seed(self, profiles: Iterable[AgentProfile]) -> None:
        existing = {profile_key(item.agent_id, item.name) for item in self.list_profiles()}
        missing = [item for item in profiles if profile_key(item.agent_id, item.name) not in existing]
        if missing:
            self.upsert_many(missing)

    def reset_to_seed(self, profiles: Iterable[AgentProfile]) -> None:
        self.replace_all(profiles)


class SessionAgentRepository:
    """Safe fallback when the browser blocks the local-storage component."""

    mode = "Session temporaire"
    persistent = False

    def __init__(self, session_cache: MutableMapping[str, Any]) -> None:
        self.session_cache = session_cache
        self.cache_key = "_planning_assistance_fallback_agents_json"

    def list_profiles(self) -> list[AgentProfile]:
        raw = self.session_cache.get(self.cache_key)
        if not isinstance(raw, str) or not raw:
            return []
        try:
            return _profiles_from_payload(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            return []

    def _write(self, profiles: Iterable[AgentProfile]) -> None:
        self.session_cache[self.cache_key] = profiles_to_json(profiles).decode("utf-8")

    def upsert_many(self, profiles: Iterable[AgentProfile]) -> None:
        merged = {profile_key(item.agent_id, item.name): item for item in self.list_profiles()}
        for profile in profiles:
            clean = _copy_profile(profile)
            merged[profile_key(clean.agent_id, clean.name)] = clean
        self._write(merged.values())

    def replace_all(self, profiles: Iterable[AgentProfile]) -> None:
        self._write(_copy_profile(item) for item in profiles)

    def ensure_seed(self, profiles: Iterable[AgentProfile]) -> None:
        existing = {profile_key(item.agent_id, item.name) for item in self.list_profiles()}
        missing = [item for item in profiles if profile_key(item.agent_id, item.name) not in existing]
        if missing:
            self.upsert_many(missing)

    def reset_to_seed(self, profiles: Iterable[AgentProfile]) -> None:
        self.replace_all(profiles)
