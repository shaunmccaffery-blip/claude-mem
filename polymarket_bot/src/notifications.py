from __future__ import annotations

import json

import httpx


def notify_console(message: str) -> None:
    print(message)


def notify_discord(webhook_url: str, message: str) -> None:
    if not webhook_url:
        return
    httpx.post(webhook_url, json={"content": message}, timeout=10)


def log_json(message: str, **kwargs: object) -> None:
    print(json.dumps({"message": message, **kwargs}))
