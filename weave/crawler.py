import asyncio
import time
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from rich.console import Console
from rich.live import Live
from rich.table import Table

from .config import CrawlConfig
from .fetcher import Fetcher
from .frontier import Frontier
from .parser import ParseResult, parse_html
from .storage import Page, Store

console = Console()


@dataclass
class CrawlSummary:
    pages_crawled: int
    errors: int
    elapsed_seconds: float
    frontier_visited: int
    store_stats: dict


class Crawler:
    def __init__(self, config: CrawlConfig):
        self.config = config
        self.frontier = Frontier(config.max_depth)
        self.store = Store(config.db_path)
        self._pages_crawled = 0
        self._errors = 0
        self._start_time = time.time()

    def _allowed(self, url: str) -> bool:
        if not self.config.allowed_domains:
            return True
        domain = urlparse(url).netloc
        return any(domain == d or domain.endswith("." + d) for d in self.config.allowed_domains)

    def _status_table(self) -> Table:
        elapsed = time.time() - self._start_time
        rate = self._pages_crawled / elapsed if elapsed > 0 else 0.0
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_row("[bold]Pages crawled[/]", str(self._pages_crawled))
        t.add_row("[bold]Errors[/]", str(self._errors))
        t.add_row("[bold]Queue depth[/]", str(self.frontier.size))
        t.add_row("[bold]Visited[/]", str(self.frontier.visited_count))
        t.add_row("[bold]Rate[/]", f"{rate:.1f} pages/s")
        return t

    def _build_parser_executor(self) -> Executor:
        try:
            return ProcessPoolExecutor(max_workers=4)
        except (OSError, PermissionError):
            console.print(
                "[yellow]ProcessPoolExecutor unavailable in this environment; falling back to threads.[/]"
            )
            return ThreadPoolExecutor(max_workers=4)

    async def _worker(self, fetcher: Fetcher, executor: ProcessPoolExecutor):
        loop = asyncio.get_running_loop()
        while self._pages_crawled < self.config.max_pages:
            try:
                url, depth = await asyncio.wait_for(self.frontier.pop(), timeout=3.0)
            except asyncio.TimeoutError:
                break

            if not self._allowed(url):
                self.frontier.task_done()
                continue

            result = await fetcher.fetch(url)

            if result.error or result.html is None:
                self._errors += 1
                self.frontier.task_done()
                continue

            try:
                parsed: ParseResult = await loop.run_in_executor(
                    executor, parse_html, url, result.html, result.status
                )
            except Exception:
                self._errors += 1
                self.frontier.task_done()
                continue

            self.store.save(Page(
                url=parsed.url,
                title=parsed.title,
                text=parsed.text,
                status=parsed.status,
                depth=depth,
            ))
            self.store.save_links(parsed.url, parsed.links)
            self._pages_crawled += 1

            if depth < self.config.max_depth:
                for link in parsed.links:
                    if self._allowed(link) and self._pages_crawled < self.config.max_pages:
                        await self.frontier.push(link, depth + 1)

            self.frontier.task_done()

    async def run(self) -> CrawlSummary:
        for url in self.config.seed_urls:
            await self.frontier.push(url, 0)

        async with Fetcher(
            concurrency=self.config.concurrency,
            per_domain_delay=self.config.per_domain_delay,
        ) as fetcher:
            with self._build_parser_executor() as executor:
                with Live(self._status_table(), refresh_per_second=2, console=console):
                    workers = [
                        asyncio.create_task(self._worker(fetcher, executor))
                        for _ in range(self.config.concurrency)
                    ]
                    await asyncio.gather(*workers)

        elapsed = time.time() - self._start_time
        stats = self.store.stats()
        console.print(f"\n[bold green]Done.[/] {self._pages_crawled} pages crawled, {self._errors} errors.")
        console.print(stats)
        return CrawlSummary(
            pages_crawled=self._pages_crawled,
            errors=self._errors,
            elapsed_seconds=elapsed,
            frontier_visited=self.frontier.visited_count,
            store_stats=stats,
        )

    def run_sync(self) -> dict:
        return asdict(asyncio.run(self.run()))
