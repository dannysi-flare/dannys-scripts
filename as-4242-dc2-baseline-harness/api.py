#!/usr/bin/env python3
"""Shared HTTP access for the DC v2 harness scripts.

The API key comes from the environment (`X_API_KEY`, or a `.env` at the repo root) and is only
ever sent to a Flare host — never hardcoded, never sent to an arbitrary `--base-url`.
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.artemis.flaretechnologies.com"
ALLOWED_HOST_SUFFIXES = (".flaretechnologies.com", ".helloflare.com")


def _load_key() -> str:
    key = os.environ.get("X_API_KEY")
    if not key:
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                name, _, value = line.partition("=")
                if name.strip() == "X_API_KEY":
                    key = value.strip().strip("\"'")
                    break
    if not key:
        sys.exit("X_API_KEY is not set — export it or put it in the repo's .env (see env.example)")
    return key


def get(base: str, path: str) -> dict:
    """GET a Flare endpoint and return the parsed JSON body."""
    host = urlparse(base).hostname or ""
    if not host.endswith(ALLOWED_HOST_SUFFIXES):
        sys.exit(f"refusing to send the API key to {host!r} — expected a Flare host")
    request = Request(f"{base}{path}", headers={"x-api-key": _load_key()})
    with urlopen(request, timeout=300) as response:
        return json.load(response)
