"""Metric facade: OTel instruments exposed through a Prometheus-style API.

Instruments are created via the OpenTelemetry Metrics API and exported in
Prometheus exposition format by a ``PrometheusMetricReader`` (see
``.docs/telemetry.md`` §5.1). The public handles (`Counter`, `Histogram`,
`Gauge`, `UpDownCounter`) keep the familiar ``.labels(...).inc()`` shape so the
back-compat shims in ``llamatrade_common`` and every call site read naturally.

Design notes:

* **Lazy creation.** The underlying OTel instrument is created on first use, so
  ``init_telemetry`` can set the resource + histogram Views before anything is
  recorded — even for module-level instruments imported before init.
* **Settable gauges** are backed by an ObservableGauge over a value holder
  (OTel's synchronous ``Gauge`` is not a public export), which also samples at
  scrape time — the model the existing DB pool observer already relies on.
* **Validation at the boundary.** Names and label keys are checked against
  ``conventions`` when the handle is built and when ``.labels(...)`` is called.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from time import perf_counter
from typing import cast

from opentelemetry import metrics as _metrics_api
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.metrics import (
    CallbackOptions,
    Meter,
    Observation,
)
from opentelemetry.metrics import (
    Counter as _OTelCounter,
)
from opentelemetry.metrics import (
    Histogram as _OTelHistogram,
)
from opentelemetry.metrics import (
    UpDownCounter as _OTelUpDown,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from prometheus_client import REGISTRY, generate_latest
from prometheus_client.registry import Collector

from llamatrade_telemetry import conventions

# A callback for observable gauges: CallbackOptions -> iterable of Observation.
ObservableCallback = Callable[[CallbackOptions], Iterable[Observation]]

_provider: MeterProvider | None = None
_meter: Meter | None = None
_reader: PrometheusMetricReader | None = None
_configured = False
_global_meter_set = False
_enabled = True

# name -> handle wrapper, so repeated factory calls return the same singleton
# (avoids OTel "duplicate instrument" warnings and keeps module-level shims stable).
_handles: dict[str, object] = {}


def _build_views() -> list[View]:
    return [
        View(
            instrument_name=name,
            aggregation=ExplicitBucketHistogramAggregation(list(buckets)),
        )
        for name, buckets in conventions.HISTOGRAM_BUCKETS.items()
    ]


def configure_metrics(resource: Resource, *, enabled: bool = True) -> None:
    """Build the MeterProvider (with histogram Views) and Prometheus reader.

    Idempotent: the first call wins. Call ``reset_for_testing`` to rebuild.
    """
    global _provider, _meter, _reader, _configured, _enabled, _global_meter_set
    _enabled = enabled
    if _configured:
        return
    _reader = PrometheusMetricReader()
    _provider = MeterProvider(
        metric_readers=[_reader],
        resource=resource,
        views=_build_views(),
    )
    # The global MeterProvider may be set only once per process; our facade uses
    # our own provider ref, so a stale global after a test reset is harmless.
    if not _global_meter_set:
        _metrics_api.set_meter_provider(_provider)
        _global_meter_set = True
    _meter = _provider.get_meter("llamatrade")
    _configured = True


def _meter_or_default() -> Meter:
    if _meter is None:
        configure_metrics(Resource.create({"service.name": "llamatrade"}))
    assert _meter is not None
    return _meter


def get_metrics() -> bytes:
    """Render all metrics in Prometheus exposition format (for ``/metrics``)."""
    return generate_latest(REGISTRY)


def reset_for_testing() -> None:
    """Tear down the provider + handle cache so a test starts clean."""
    global _provider, _meter, _reader, _configured
    if _reader is not None:
        try:
            REGISTRY.unregister(cast(Collector, _reader))
        except KeyError:
            pass
    if _provider is not None:
        _provider.shutdown()
    _provider = None
    _meter = None
    _reader = None
    _configured = False
    _handles.clear()


def _check_labels(declared: tuple[str, ...], provided: Mapping[str, str]) -> None:
    if set(declared) != set(provided):
        raise conventions.LabelError(
            f"labels {sorted(provided)} do not match declared {sorted(declared)}"
        )


# ---------------------------------------------------------------------------
# Handles
# ---------------------------------------------------------------------------
class _CounterChild:
    __slots__ = ("_instr", "_attrs")

    def __init__(self, instr: _OTelCounter, attrs: dict[str, str]) -> None:
        self._instr = instr
        self._attrs = attrs

    def inc(self, amount: float = 1.0) -> None:
        if _enabled:
            self._instr.add(amount, self._attrs)


class Counter:
    """Monotonic counter → Prometheus ``<name>_total``."""

    def __init__(self, name: str, labelnames: tuple[str, ...], description: str) -> None:
        self._name = name
        self._labelnames = labelnames
        self._description = description
        self._instr: _OTelCounter | None = None

    def _instrument(self) -> _OTelCounter:
        if self._instr is None:
            self._instr = _meter_or_default().create_counter(
                self._name, unit="1", description=self._description
            )
        return self._instr

    def labels(self, **labels: str) -> _CounterChild:
        _check_labels(self._labelnames, labels)
        return _CounterChild(self._instrument(), labels)

    def inc(self, amount: float = 1.0) -> None:
        if self._labelnames:
            raise conventions.LabelError(f"{self._name} requires labels {self._labelnames}")
        if _enabled:
            self._instrument().add(amount, {})


class _HistogramChild:
    __slots__ = ("_instr", "_attrs")

    def __init__(self, instr: _OTelHistogram, attrs: dict[str, str]) -> None:
        self._instr = instr
        self._attrs = attrs

    def observe(self, value: float) -> None:
        if _enabled:
            self._instr.record(value, self._attrs)


class Histogram:
    """Distribution with buckets declared in ``conventions.HISTOGRAM_BUCKETS``."""

    def __init__(self, name: str, labelnames: tuple[str, ...], description: str) -> None:
        self._name = name
        self._labelnames = labelnames
        self._description = description
        self._instr: _OTelHistogram | None = None

    def _instrument(self) -> _OTelHistogram:
        if self._instr is None:
            unit = "s" if self._name.endswith("_seconds") else "1"
            self._instr = _meter_or_default().create_histogram(
                self._name, unit=unit, description=self._description
            )
        return self._instr

    def labels(self, **labels: str) -> _HistogramChild:
        _check_labels(self._labelnames, labels)
        return _HistogramChild(self._instrument(), labels)

    def observe(self, value: float) -> None:
        if self._labelnames:
            raise conventions.LabelError(f"{self._name} requires labels {self._labelnames}")
        if _enabled:
            self._instrument().record(value, {})

    @contextmanager
    def time(self, **labels: str) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            value = perf_counter() - start
            if labels:
                self.labels(**labels).observe(value)
            else:
                self.observe(value)


class _UpDownChild:
    __slots__ = ("_instr", "_attrs")

    def __init__(self, instr: _OTelUpDown, attrs: dict[str, str]) -> None:
        self._instr = instr
        self._attrs = attrs

    def inc(self, amount: float = 1.0) -> None:
        if _enabled:
            self._instr.add(amount, self._attrs)

    def dec(self, amount: float = 1.0) -> None:
        if _enabled:
            self._instr.add(-amount, self._attrs)


class UpDownCounter:
    """Non-monotonic count (inc/dec) → Prometheus gauge. For in-flight counts."""

    def __init__(self, name: str, labelnames: tuple[str, ...], description: str) -> None:
        self._name = name
        self._labelnames = labelnames
        self._description = description
        self._instr: _OTelUpDown | None = None

    def _instrument(self) -> _OTelUpDown:
        if self._instr is None:
            self._instr = _meter_or_default().create_up_down_counter(
                self._name, unit="1", description=self._description
            )
        return self._instr

    def labels(self, **labels: str) -> _UpDownChild:
        _check_labels(self._labelnames, labels)
        return _UpDownChild(self._instrument(), labels)

    def inc(self, amount: float = 1.0) -> None:
        if not self._labelnames and _enabled:
            self._instrument().add(amount, {})

    def dec(self, amount: float = 1.0) -> None:
        if not self._labelnames and _enabled:
            self._instrument().add(-amount, {})


class _GaugeChild:
    __slots__ = ("_values", "_key")

    def __init__(
        self,
        values: dict[tuple[tuple[str, str], ...], float],
        key: tuple[tuple[str, str], ...],
    ) -> None:
        self._values = values
        self._key = key

    def set(self, value: float) -> None:
        self._values[self._key] = value


class Gauge:
    """Settable level → Prometheus gauge, backed by an ObservableGauge.

    ``.set(...)`` stores into a value holder; the callback yields the current
    values at scrape time (same model as the legacy DB pool observer).
    """

    def __init__(self, name: str, labelnames: tuple[str, ...], description: str) -> None:
        self._name = name
        self._labelnames = labelnames
        self._description = description
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        self._registered = False

    def _ensure(self) -> None:
        if not self._registered:
            _meter_or_default().create_observable_gauge(
                self._name, callbacks=[self._observe], unit="1", description=self._description
            )
            self._registered = True

    def _observe(self, options: CallbackOptions) -> Iterable[Observation]:
        return [Observation(value, dict(key)) for key, value in self._values.items()]

    def labels(self, **labels: str) -> _GaugeChild:
        _check_labels(self._labelnames, labels)
        self._ensure()
        key = tuple(sorted(labels.items()))
        return _GaugeChild(self._values, key)

    def set(self, value: float) -> None:
        if self._labelnames:
            raise conventions.LabelError(f"{self._name} requires labels {self._labelnames}")
        self._ensure()
        self._values[()] = value


# ---------------------------------------------------------------------------
# Factories (validated + cached singletons)
# ---------------------------------------------------------------------------
def _labelnames(
    labelnames: Sequence[str],
    *,
    allow_high_cardinality: bool = False,
) -> tuple[str, ...]:
    conventions.validate_label_keys(labelnames, allow_high_cardinality=allow_high_cardinality)
    return tuple(labelnames)


def counter(name: str, labelnames: Sequence[str] = (), description: str = "") -> Counter:
    conventions.validate_metric_name(name)
    if name in _handles:
        return cast(Counter, _handles[name])
    handle = Counter(name, _labelnames(labelnames), description)
    _handles[name] = handle
    return handle


def histogram(name: str, labelnames: Sequence[str] = (), description: str = "") -> Histogram:
    conventions.validate_metric_name(name)
    conventions.buckets_for(name)  # fail fast if buckets undeclared
    if name in _handles:
        return cast(Histogram, _handles[name])
    handle = Histogram(name, _labelnames(labelnames), description)
    _handles[name] = handle
    return handle


def gauge(
    name: str,
    labelnames: Sequence[str] = (),
    description: str = "",
    *,
    allow_high_cardinality: bool = False,
) -> Gauge:
    conventions.validate_metric_name(name)
    if name in _handles:
        return cast(Gauge, _handles[name])
    handle = Gauge(
        name,
        _labelnames(labelnames, allow_high_cardinality=allow_high_cardinality),
        description,
    )
    _handles[name] = handle
    return handle


def up_down_counter(
    name: str,
    labelnames: Sequence[str] = (),
    description: str = "",
) -> UpDownCounter:
    conventions.validate_metric_name(name)
    if name in _handles:
        return cast(UpDownCounter, _handles[name])
    handle = UpDownCounter(name, _labelnames(labelnames), description)
    _handles[name] = handle
    return handle


def observable_gauge(
    name: str,
    callback: ObservableCallback,
    labelnames: Sequence[str] = (),
    description: str = "",
    *,
    allow_high_cardinality: bool = False,
) -> None:
    """Register a sampled-at-scrape gauge driven by ``callback``.

    ``callback`` takes ``CallbackOptions`` and returns an iterable of
    ``Observation``. Used by the DB pool observer and EventBus lag gauges.
    """
    conventions.validate_metric_name(name)
    _labelnames(labelnames, allow_high_cardinality=allow_high_cardinality)
    if name in _handles:
        return
    _meter_or_default().create_observable_gauge(
        name, callbacks=[callback], unit="1", description=description
    )
    _handles[name] = callback
