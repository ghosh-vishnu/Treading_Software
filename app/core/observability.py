from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Mapping


def _label_key(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in (labels or {}).items()))


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    serialized = ",".join(f'{key}="{value}"' for key, value in labels)
    return "{" + serialized + "}"


@dataclass
class _TimerSample:
    total_seconds: float = 0
    count: int = 0


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
        self._timers: dict[str, dict[tuple[tuple[str, str], ...], _TimerSample]] = defaultdict(dict)

    def increment(self, name: str, labels: Mapping[str, str] | None = None, value: float = 1) -> None:
        key = _label_key(labels)
        with self._lock:
            self._counters[name][key] = self._counters[name].get(key, 0) + value

    def observe(self, name: str, seconds: float, labels: Mapping[str, str] | None = None) -> None:
        key = _label_key(labels)
        with self._lock:
            sample = self._timers[name].setdefault(key, _TimerSample())
            sample.total_seconds += seconds
            sample.count += 1

    @contextmanager
    def timer(self, name: str, labels: Mapping[str, str] | None = None) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter() - started, labels)

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, series in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                for labels, value in sorted(series.items()):
                    lines.append(f"{name}{_format_labels(labels)} {value:g}")
            for name, series in sorted(self._timers.items()):
                lines.append(f"# TYPE {name} summary")
                for labels, sample in sorted(series.items()):
                    suffix = _format_labels(labels)
                    lines.append(f"{name}_count{suffix} {sample.count}")
                    lines.append(f"{name}_sum{suffix} {sample.total_seconds:.6f}")
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()
