"""Telegram notification helper.

Uses `requests`, not `curl` -- found 2026-09-04 that curl isn't installed
in any agent's image (only git is), so the shell version of this had been
silently no-op-ing since it was written. `requests` is already a
hermes-agent dependency in every agent's image, so this needs nothing
extra installed.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def send_telegram(bot_token: str, chat_id: str, text: str, timeout: int = 10) -> bool:
    """Best-effort send. Never raises -- a failed notification should not
    take down whatever background loop called this. Returns whether it
    succeeded, for callers/tests that want to know.
    """
    try:
        import requests

        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=timeout,
        )
        return response.ok
    except Exception:
        logger.warning("Telegram notification failed", exc_info=True)
        return False
