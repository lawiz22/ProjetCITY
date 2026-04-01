"""Mammouth AI API integration service."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from flask import current_app, has_app_context, session as flask_session

from .app_state import load_json_setting, save_json_setting

MAMMOUTH_API_BASE = "https://api.mammouth.ai/v1"
MAMMOUTH_MODELS_URL = "https://api.mammouth.ai/public/models"
SETTINGS_FILE = Path(__file__).resolve().parents[2] / "data" / "mammouth_settings.json"
SETTINGS_KEY = "mammouth_settings"

DEFAULT_SETTINGS: dict[str, Any] = {
    "api_key": "",
    "model": "gpt-4.1-mini",
    "tokens_used": 0,
}


def _require_user_key() -> bool:
    """Return True when each user must supply their own API key (prod mode)."""
    return has_app_context() and current_app.config.get("REQUIRE_USER_API_KEY", False)


def load_settings() -> dict[str, Any]:
    settings = load_json_setting(SETTINGS_KEY, DEFAULT_SETTINGS, fallback_path=SETTINGS_FILE)
    if _require_user_key():
        # In prod mode, the API key lives in the browser session, not in the DB.
        settings["api_key"] = flask_session.get("mammouth_api_key", "")
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    normalized = {**DEFAULT_SETTINGS, **settings}
    if _require_user_key():
        # Store the key in the user's browser session; save everything else to DB.
        flask_session["mammouth_api_key"] = normalized.pop("api_key", "")
        flask_session.permanent = True
    save_json_setting(SETTINGS_KEY, normalized, fallback_path=SETTINGS_FILE)


def add_tokens(count: int) -> int:
    """Add tokens to the cumulative counter and return new total."""
    settings = load_settings()
    settings["tokens_used"] = settings.get("tokens_used", 0) + count
    save_settings(settings)
    return settings["tokens_used"]


def reset_tokens() -> None:
    """Reset the token counter to zero."""
    settings = load_settings()
    settings["tokens_used"] = 0
    save_settings(settings)


def fetch_models() -> list[dict[str, Any]]:
    """Fetch available models from Mammouth AI public endpoint."""
    try:
        resp = requests.get(MAMMOUTH_MODELS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return []
    except Exception:
        return []


def test_connection(api_key: str, model: str) -> dict[str, Any]:
    """Send a minimal chat completion to verify the API key works."""
    try:
        resp = requests.post(
            f"{MAMMOUTH_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Réponds uniquement: OK"}],
                "max_tokens": 10,
            },
            timeout=15,
        )
        if resp.status_code == 401:
            return {"success": False, "error": "Clé API invalide (401)."}
        if resp.status_code == 429:
            return {"success": False, "error": "Limite de requêtes dépassée (429)."}
        resp.raise_for_status()
        data = resp.json()
        reply = ""
        if data.get("choices"):
            reply = data["choices"][0].get("message", {}).get("content", "")
        tokens = data.get("usage", {}).get("total_tokens", 0)
        if isinstance(tokens, int) and tokens > 0:
            add_tokens(tokens)
        return {
            "success": True,
            "model": data.get("model", model),
            "reply": reply.strip(),
            "tokens": tokens,
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Délai d'attente dépassé (timeout 15s)."}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Impossible de se connecter à api.mammouth.ai."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "data" / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt template from data/prompts/."""
    path = PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def generate_city(api_key: str, model: str, city_input: str, prompt_text: str, *, max_tokens: int = 2000, temperature: float = 0.3) -> dict[str, Any]:
    """Send a city generation prompt and return the AI response."""
    try:
        final_prompt = prompt_text.replace("{CITY_INPUT}", city_input)
        resp = requests.post(
            f"{MAMMOUTH_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": final_prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=300,
        )
        if resp.status_code == 401:
            return {"success": False, "error": "Clé API invalide (401)."}
        if resp.status_code == 429:
            return {"success": False, "error": "Limite de requêtes dépassée (429)."}
        resp.raise_for_status()
        data = resp.json()
        reply = ""
        if data.get("choices"):
            reply = data["choices"][0].get("message", {}).get("content", "")
        tokens = data.get("usage", {}).get("total_tokens", 0)
        if isinstance(tokens, int) and tokens > 0:
            add_tokens(tokens)
        return {
            "success": True,
            "model": data.get("model", model),
            "reply": reply.strip(),
            "tokens": tokens,
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Délai d'attente dépassé (timeout 120s)."}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Impossible de se connecter à api.mammouth.ai."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
