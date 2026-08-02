"""Client-IP derivation from ``X-Forwarded-For`` for the auth rate limiters.

Behind the GCP L7 load balancer the client controls every hop it writes into
``X-Forwarded-For``; only the rightmost entries appended by our own
infrastructure are trustworthy. The LB appends the real client IP followed by
its own forwarding IP, so the trusted client IP is the entry immediately left of
the ``TRUSTED_PROXY_HOPS`` trailing infrastructure entries. Reading the leftmost
hop instead lets an attacker rotate the rate-limit key per request.
"""

from __future__ import annotations

import os

# Trailing X-Forwarded-For entries appended by trusted infrastructure. The GCP L7
# LB appends its own IP as the last entry after the real client IP, so the
# default of 1 selects the second-to-last entry.
TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))


def trusted_client_ip(forwarded_for: str, *, trusted_hops: int = TRUSTED_PROXY_HOPS) -> str | None:
    """Client IP from a trusted position in ``X-Forwarded-For``, or None.

    The rightmost ``trusted_hops`` entries are appended by infrastructure we
    control and cannot be spoofed; the real client IP is the entry immediately to
    their left. Returns None when the header is absent or carries fewer entries
    than ``trusted_hops`` implies, so there is nothing trustworthy to read.
    """
    parts = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    index = len(parts) - trusted_hops - 1
    if index < 0:
        return None
    return parts[index]
