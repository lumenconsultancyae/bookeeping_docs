"""Centralized E2E configuration module for Lumen Accounting Suite BDD tests."""

import os
from pathlib import Path
import socket

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE_DIR = Path(
    os.environ.get(
        "BOOKKEEPING_APP_DIR",
        str(REPO_ROOT.parent / "bookkeeping-tool"),
    )
)


from urllib.parse import urlparse


def _resolve_default_base_url() -> tuple[str, int, str, bool]:
    """Use explicit `BOOKKEEPING_BASE_URL`/`APP_BASE_URL` or reachable `bookkeeping-web`; fallback to local server."""
    explicit_url = os.environ.get("BOOKKEEPING_BASE_URL") or os.environ.get("APP_BASE_URL")
    host = os.environ.get("BOOKKEEPING_HOST", "localhost")
    port = int(os.environ.get("BOOKKEEPING_PORT", "9091"))
    if explicit_url:
        parsed = urlparse(explicit_url)
        target_host = parsed.hostname or host
        target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return target_host, target_port, explicit_url, True

    try:
        with socket.create_connection(("bookkeeping-web", 80), timeout=1.0):
            return "bookkeeping-web", 80, "http://bookkeeping-web:80", True
    except OSError:
        return host, port, f"http://{host}:{port}", False


HOST, PORT, BASE_URL, USING_DOCKER_COMPOSE = _resolve_default_base_url()

DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("E2E_TIMEOUT_SECONDS", "10.0"))
POLL_FREQUENCY_SECONDS = 0.1

HEADLESS = os.environ.get("E2E_HEADLESS", "true").lower() not in ("0", "false", "no")
CHROMIUM_BINARY = os.environ.get("CHROMIUM_BINARY", "/usr/bin/chromium")

ARTIFACTS_DIR = REPO_ROOT / "artifacts"
SCREENSHOTS_DIR = Path(
    os.environ.get(
        "E2E_SCREENSHOTS_DIR",
        str(ARTIFACTS_DIR / "screenshots"),
    )
)
