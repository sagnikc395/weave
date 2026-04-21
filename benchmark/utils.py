import statistics
import time

# ── timing helper ─────────────────────────────────────────────────────────────


def _time(fn, runs: int = 3) -> tuple[float, float]:
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.mean(times), (statistics.stdev(times) if runs > 1 else 0.0)


def _header(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print(f"{'─' * 64}")
    print(f"  {'Model':<32} {'Mean':>7}   {'±':>5}   {'Speedup':>7}")
    print(f"  {'-' * 32} {'-' * 7}   {'-' * 5}   {'-' * 7}")


def _row(label: str, mean: float, std: float, baseline: float) -> None:
    speedup = baseline / mean if mean > 0 else float("inf")
    print(f"  {label:<32} {mean:>6.2f}s  {std:>5.2f}s  {speedup:>6.1f}x")
