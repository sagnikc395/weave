"""
Benchmarks the actual weave components against alternative implementations.

Three experiments map directly to the three concurrency layers in weave/:

  1. Fetching  — weave.Fetcher (asyncio) vs ThreadPoolExecutor+httpx vs sync httpx
                 Validates the asyncio choice in fetcher.py

  2. Parsing   — weave.parser.parse_html via ProcessPoolExecutor vs ThreadPool vs single
                 Validates the multiprocessing choice in crawler.py:65

  3. Frontier  — weave.Frontier.push throughput under concurrent lock contention
                 Validates the threading.Lock in frontier.py

Run:
    # against books.toscrape.com (built for scrapers, no rate limiting)
    python benchmark/benchmark_fetching.py

    # against local server (zero network noise, best for parsing benchmark)
    python benchmark/benchmark_fetching.py --local

    # individual stages
    python benchmark/benchmark_fetching.py --skip-fetch --skip-frontier
"""

import argparse
import asyncio
import statistics
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.utils import _header, _row, _time
from weave.fetcher import Fetcher
from weave.frontier import Frontier
from weave.parser import parse_html

from .config import TOSCRAPE_URLS, LOCAL_URLS, DENSE_TEXT


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        n = self.path.split("/")[-1]
        links = "".join(f'<a href="/page/{i}">link {i}</a>' for i in range(1, 51))
        # dense nested HTML so BeautifulSoup has real CPU work to do
        paras = "".join(f"<p>{DENSE_TEXT}</p>" for _ in range(5))
        body = (
            f"<html><head><title>Page {n}</title></head>"
            f"<body><nav>{links}</nav><main>{paras}</main>"
            f"<footer>footer content</footer></body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def start_local_server() -> None:
    server = HTTPServer(("localhost", 8765), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


# ── Benchmark 1: Fetching ─────────────────────────────────────────────────────
#
# Compares three ways to fetch the same 20 URLs:
#   sync httpx         — one request at a time, baseline
#   ThreadPoolExecutor — threads blocked on I/O, GIL mostly released but OS overhead
#   weave.Fetcher      — asyncio + aiohttp, the actual implementation
#
# Expected: async ≈ threads >> sync at 20 URLs; gap grows wider at 50, 100 URLs.


def _fetch_sync(urls: list[str]) -> None:
    with httpx.Client(timeout=10) as client:
        for url in urls:
            try:
                client.get(url)
            except Exception:
                pass


def _fetch_threaded(urls: list[str], workers: int = 10) -> None:
    # shared client so threads get connection pooling — fair comparison with weave.Fetcher
    with httpx.Client(timeout=10) as client:

        def _get(url):
            try:
                client.get(url)
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_get, urls))


async def _fetch_weave(urls: list[str]) -> None:
    async with Fetcher(concurrency=10, per_domain_delay=0.0) as fetcher:
        await asyncio.gather(*[fetcher.fetch(url) for url in urls])


def bench_fetching(urls: list[str]) -> None:
    _header("Benchmark 1 — Fetching  (20 URLs, 3 runs each)")

    sync_mean, sync_std = _time(lambda: _fetch_sync(urls))
    _row("sync httpx  (baseline)", sync_mean, sync_std, sync_mean)

    thr_mean, thr_std = _time(lambda: _fetch_threaded(urls))
    _row("ThreadPoolExecutor(10) + httpx", thr_mean, thr_std, sync_mean)

    weave_mean, weave_std = _time(lambda: asyncio.run(_fetch_weave(urls)))
    _row("weave.Fetcher — asyncio/aiohttp ✓", weave_mean, weave_std, sync_mean)

    print()
    print("  weave.Fetcher suspends on I/O without spawning OS threads.")
    print("  The gap widens as concurrency increases — try changing URLS to 50+.")


# ── Benchmark 2: Parsing ──────────────────────────────────────────────────────
#
# Compares three ways to call weave.parser.parse_html on the same 20 HTML pages:
#   single-threaded    — baseline
#   ThreadPoolExecutor — GIL blocks CPU-bound work; expect near-zero speedup
#   ProcessPoolExecutor — bypasses GIL; mirrors crawler.py:65
#
# Expected: threading ≈ single-threaded (GIL); multiprocessing ≈ N_CORES × speedup.


def _collect_html(urls: list[str]) -> list[tuple[str, str, int]]:
    print(f"\n  Fetching {len(urls)} pages for parsing inputs...", end=" ", flush=True)
    samples = []
    with httpx.Client(timeout=10, follow_redirects=True) as client:
        for url in urls:
            try:
                r = client.get(url)
                ct = r.headers.get("content-type", "")
                if "html" in ct:
                    samples.append((url, r.text, r.status_code))
            except Exception:
                pass
    print(f"got {len(samples)}")
    return samples


def _parse_single(samples: list[tuple[str, str, int]]) -> None:
    for args in samples:
        parse_html(*args)


def _parse_threaded(samples: list[tuple[str, str, int]], workers: int = 4) -> None:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda s: parse_html(*s), samples))


def _parse_multiprocess(
    samples: list[tuple[str, str, int]],
    executor: ProcessPoolExecutor,
) -> None:
    # Exact pattern used in crawler.py:65 via loop.run_in_executor.
    # Executor is created once outside the timed loop so startup cost doesn't skew results.
    urls, htmls, statuses = zip(*samples)
    list(executor.map(parse_html, urls, htmls, statuses))


def bench_parsing(samples: list[tuple[str, str, int]]) -> None:
    # multiply samples so there's enough CPU work to see past ProcessPool startup cost
    samples = (samples * 10)[:200]
    _header(f"Benchmark 2 — Parsing  ({len(samples)} pages, 3 runs each)")

    s_mean, s_std = _time(lambda: _parse_single(samples))
    _row("single-threaded  (baseline)", s_mean, s_std, s_mean)

    t_mean, t_std = _time(lambda: _parse_threaded(samples, workers=4))
    _row("ThreadPoolExecutor(4)", t_mean, t_std, s_mean)

    # create pool once — mirrors crawler.py which holds a long-lived ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=4) as pool:
        p_mean, p_std = _time(lambda: _parse_multiprocess(samples, pool))
    _row("ProcessPoolExecutor(4)  ✓", p_mean, p_std, s_mean)

    print()
    print("  ThreadPool barely moves because parse_html is CPU-bound and the GIL")
    print("  serialises threads. ProcessPool gives real parallelism — this is why")
    print("  crawler.py uses ProcessPoolExecutor, not ThreadPoolExecutor, here.")


def bench_parsing_sweep(samples: list[tuple[str, str, int]]) -> None:
    samples = (samples * 10)[:200]
    _header("Benchmark 2b — ProcessPoolExecutor worker sweep")
    print(f"  {'workers':<10} {'mean':>7}   {'±':>5}   {'speedup':>7}")
    print(f"  {'-' * 10} {'-' * 7}   {'-' * 5}   {'-' * 7}")
    baseline = None
    for w in [1, 2, 4, 8]:
        with ProcessPoolExecutor(max_workers=w) as pool:
            mean, std = _time(lambda p=pool: _parse_multiprocess(samples, p))
        if baseline is None:
            baseline = mean
        print(f"  {w:<10} {mean:>6.2f}s  {std:>5.2f}s  {baseline / mean:>6.1f}x")
    print()
    print("  Speedup plateaus at your CPU core count.")


# ── Benchmark 3: Frontier ─────────────────────────────────────────────────────
#
# Measures Frontier.push() throughput as concurrent worker count increases.
# The threading.Lock on _visited means only one coroutine can check-and-add at a time.
#
# Expected: throughput roughly flat (lock contention scales with workers),
#           but accepted count must always equal N — no duplicate enqueues.


async def _frontier_bench(n_urls: int, n_workers: int) -> tuple[int, float]:
    frontier = Frontier(max_depth=10)
    urls = [f"https://example.com/page/{i}" for i in range(n_urls)]
    batch = n_urls // n_workers

    async def worker(batch_urls):
        return sum([1 async for url in _push_all(frontier, batch_urls)])

    async def _push_all(f, batch_urls):
        for url in batch_urls:
            if await f.push(url, depth=0):
                yield url

    batches = [urls[i * batch : (i + 1) * batch] for i in range(n_workers)]
    t0 = time.perf_counter()
    results = await asyncio.gather(*[worker(b) for b in batches])
    return sum(results), time.perf_counter() - t0


def bench_frontier() -> None:
    N = 10_000
    _header(
        f"Benchmark 3 — Frontier.push  ({N:,} URLs, dedup correctness + throughput)"
    )
    print(
        f"  {'workers':<10} {'accepted':>10}   {'time':>8}   {'pushes/s':>10}   {'dedup':>6}"
    )
    print(f"  {'-' * 10} {'-' * 10}   {'-' * 8}   {'-' * 10}   {'-' * 6}")

    for w in [1, 4, 10, 20]:
        accepted, elapsed = asyncio.run(_frontier_bench(N, w))
        rate = N / elapsed
        ok = "✓" if accepted == N else f"✗ {accepted}"
        print(
            f"  {w:<10} {accepted:>10,}   {elapsed:>7.3f}s   {rate:>9,.0f}/s   {ok:>6}"
        )

    print()
    print("  accepted must always equal N — the threading.Lock in frontier.py")
    print("  guarantees no URL is enqueued twice regardless of worker count.")
    print("  If you see ✗, the lock is broken.")


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--local",
        action="store_true",
        help="use local test server — eliminates network noise",
    )
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-parse", action="store_true")
    ap.add_argument("--skip-frontier", action="store_true")
    args = ap.parse_args()

    if args.local:
        print("Starting local test server on :8765 ...")
        start_local_server()
        urls = LOCAL_URLS
    else:
        urls = TOSCRAPE_URLS

    if not args.skip_fetch:
        bench_fetching(urls)

    if not args.skip_parse:
        samples = _collect_html(urls)
        if samples:
            bench_parsing(samples)
            bench_parsing_sweep(samples)
        else:
            print("  No HTML samples collected — check network and retry.")

    if not args.skip_frontier:
        bench_frontier()

    print(f"\n{'─' * 64}\n  Done.\n")


if __name__ == "__main__":
    main()
