"""Is there an internet connection? A quick check, so Rinne can say it's showing saved data."""

from __future__ import annotations

import socket

HOSTS = (("graphql.anilist.co", 443), ("api.github.com", 443))


def online(timeout: float = 3.0) -> bool:
    """True if any of the services Rinne uses can be reached."""
    for host in HOSTS:
        try:
            with socket.create_connection(host, timeout=timeout):
                return True
        except OSError:
            continue
    return False
