"""
Performance Benchmarking for Screening Pipeline

Tracks timing of each pipeline stage to identify bottlenecks.
"""

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkStage:
    """Single benchmark measurement."""

    name: str
    duration_ms: float
    items_processed: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ms_per_item(self) -> float:
        """Average milliseconds per item processed."""
        return self.duration_ms / self.items_processed if self.items_processed else 0

    @property
    def items_per_second(self) -> float:
        """Throughput in items per second."""
        if self.duration_ms == 0:
            return 0
        return (self.items_processed / self.duration_ms) * 1000


@dataclass
class PipelineBenchmark:
    """Tracks performance of entire screening pipeline."""

    stages: list[BenchmarkStage] = field(default_factory=list)
    total_duration_ms: float = 0
    start_time: Optional[float] = None

    def start(self) -> None:
        """Start overall timer."""
        self.start_time = time.time()

    def finish(self) -> None:
        """Finish overall timer."""
        if self.start_time:
            self.total_duration_ms = (time.time() - self.start_time) * 1000

    def add_stage(
        self,
        name: str,
        duration_ms: float,
        items_processed: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Add a completed stage measurement."""
        stage = BenchmarkStage(
            name=name,
            duration_ms=duration_ms,
            items_processed=items_processed,
            metadata=metadata or {},
        )
        self.stages.append(stage)
        logger.debug(
            "Benchmark | %s: %.0fms (%d items, %.1fms/item)",
            name,
            duration_ms,
            items_processed,
            stage.ms_per_item,
        )

    @contextmanager
    def measure(
        self, name: str, items: int = 0, metadata: Optional[dict[str, Any]] = None
    ) -> Generator[None, None, None]:
        """Context manager for timing a stage."""
        stage_start = time.time()
        try:
            yield
        finally:
            duration_ms = (time.time() - stage_start) * 1000
            self.add_stage(name, duration_ms, items, metadata)

    def get_report(self) -> dict[str, Any]:
        """Generate performance report."""
        if not self.stages:
            return {"error": "No stages recorded"}

        # Calculate percentage of total time for each stage
        stage_reports = []
        for stage in self.stages:
            pct = (
                (stage.duration_ms / self.total_duration_ms * 100) if self.total_duration_ms else 0
            )
            stage_reports.append(
                {
                    "stage": stage.name,
                    "duration_ms": round(stage.duration_ms, 1),
                    "pct_total": round(pct, 1),
                    "items": stage.items_processed,
                    "ms_per_item": round(stage.ms_per_item, 2),
                    "items_per_sec": round(stage.items_per_second, 1),
                    "metadata": stage.metadata,
                }
            )

        # Find top 3 bottlenecks
        sorted_stages = sorted(self.stages, key=lambda s: s.duration_ms, reverse=True)
        bottlenecks = [
            {
                "stage": s.name,
                "duration_ms": round(s.duration_ms, 1),
                "pct_total": round((s.duration_ms / self.total_duration_ms * 100), 1),
            }
            for s in sorted_stages[:3]
        ]

        return {
            "total_duration_ms": round(self.total_duration_ms, 1),
            "total_duration_sec": round(self.total_duration_ms / 1000, 2),
            "stages": stage_reports,
            "bottlenecks": bottlenecks,
        }

    def print_report(self) -> None:
        """Print formatted performance report to console."""
        report = self.get_report()

        print("\n" + "=" * 80)
        print("PERFORMANCE BENCHMARK")
        print("=" * 80)
        print(
            f"Total Time: {report['total_duration_ms']:.0f}ms ({report['total_duration_sec']:.2f}s)"
        )
        print()

        print("STAGE BREAKDOWN")
        print("-" * 80)
        print(f"{'Stage':<30} {'Time (ms)':<12} {'% Total':<10} {'Items':<8} {'ms/item':<10}")
        print("-" * 80)

        for stage in report["stages"]:
            print(
                f"{stage['stage']:<30} "
                f"{stage['duration_ms']:<12.0f} "
                f"{stage['pct_total']:<10.1f} "
                f"{stage['items']:<8} "
                f"{stage['ms_per_item']:<10.2f}"
            )

        print()
        print("TOP BOTTLENECKS")
        print("-" * 80)
        for i, bottleneck in enumerate(report["bottlenecks"], 1):
            print(
                f"{i}. {bottleneck['stage']}: {bottleneck['duration_ms']:.0f}ms "
                f"({bottleneck['pct_total']:.1f}% of total)"
            )

        print("=" * 80)
