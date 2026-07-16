from __future__ import annotations

import uuid
from typing import Any

import streamlit as st


PENDING_WRITE_KEY = "_planning_assistance_pending_browser_write"

_STORAGE_JS = r"""
export default function(component) {
    const { data, setStateValue } = component;
    const storageKey = data.storage_key;

    const publishValue = () => {
        try {
            const value = window.localStorage.getItem(storageKey);
            setStateValue("value", value);
            setStateValue("available", true);
            setStateValue("error", "");
            setStateValue("loaded", true);
        } catch (error) {
            setStateValue("available", false);
            setStateValue("error", String(error?.message || error || "Stockage indisponible"));
            setStateValue("loaded", true);
        }
    };

    try {
        if (data.write_token && data.write_value !== null && data.write_value !== undefined) {
            window.localStorage.setItem(storageKey, data.write_value);
            setStateValue("ack_token", data.write_token);
        }
        publishValue();
    } catch (error) {
        setStateValue("available", false);
        setStateValue("error", String(error?.message || error || "Stockage indisponible"));
        setStateValue("loaded", true);
    }

    const onStorage = (event) => {
        if (event.key === storageKey) {
            publishValue();
        }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
}
"""

_storage_component = st.components.v2.component(
    "planning_assistance_browser_storage",
    js=_STORAGE_JS,
)


def _read_state(result: Any, name: str, default=None):
    try:
        value = getattr(result, name)
    except (AttributeError, KeyError, TypeError):
        return default
    return default if value is None else value


class StreamlitBrowserStorage:
    """Small localStorage bridge built with Streamlit's native v2 component."""

    def __init__(self, storage_key: str) -> None:
        self.storage_key = storage_key
        pending = st.session_state.get(PENDING_WRITE_KEY)
        if not isinstance(pending, dict) or pending.get("storage_key") != storage_key:
            pending = None

        result = _storage_component(
            data={
                "storage_key": storage_key,
                "write_token": pending.get("token") if pending else None,
                "write_value": pending.get("value") if pending else None,
            },
            key="planning_assistance_browser_storage_mount",
            on_loaded_change=lambda: None,
            on_value_change=lambda: None,
            on_available_change=lambda: None,
            on_error_change=lambda: None,
            on_ack_token_change=lambda: None,
        )

        self.loaded = bool(_read_state(result, "loaded", False))
        self.available = bool(_read_state(result, "available", False))
        self.error = str(_read_state(result, "error", "") or "")
        browser_value = _read_state(result, "value", None)
        ack_token = _read_state(result, "ack_token", None)

        if pending:
            # Use the newest server-side value immediately so edits are never
            # lost while the browser component is acknowledging the write.
            self.current_value = pending.get("value")
            if ack_token == pending.get("token"):
                st.session_state.pop(PENDING_WRITE_KEY, None)
                self.current_value = browser_value
        else:
            self.current_value = browser_value

    def getItem(self, itemKey: str):
        if itemKey != self.storage_key:
            return None
        return self.current_value

    def setItem(self, itemKey: str, itemValue: Any, key: str = "set") -> None:
        if itemKey != self.storage_key:
            raise ValueError("Clé de stockage inattendue.")
        value = str(itemValue)
        st.session_state[PENDING_WRITE_KEY] = {
            "storage_key": self.storage_key,
            "value": value,
            "token": uuid.uuid4().hex,
        }
        self.current_value = value

    def eraseItem(self, itemKey: str, key: str = "eraseItem", default=None) -> None:
        # The application always keeps at least its seed directory, so clearing
        # is represented by writing an empty JSON list.
        self.setItem(itemKey, "[]", key=key)
