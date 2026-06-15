"""Cross-cutting instrumentation: HTTP, gRPC, DB, cache, EventBus, Celery.

Each module owns its standard metric instruments and exposes recorder helpers /
middleware that the platform wires in via ``init_telemetry``. Per-service
identity is the Prometheus ``job`` label (set by scrape config) plus OTel
``target_info`` — so these metrics deliberately carry no ``service`` label.
"""

from __future__ import annotations
