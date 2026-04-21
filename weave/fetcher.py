import asyncio
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import aiohttp


@dataclass
class FetchResult:
    url: str
    html: Optional[str]
    status: int
    error: Optional[str] = None


class Fetcher:
    """Async HTTP fetcher.
    - asyncio.Semaphore caps total concurrent connections
    - per-domain asyncio.Lock + sleep enforces politeness delay
    """

    def __init__(self, concurrency: int = 10, per_domain_delay: float = 0.5):
        self._semaphore = asyncio.Semaphore(concurrency)
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._per_domain_delay = per_domain_delay
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "Fetcher":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "weave/0.1 (concurrent web crawler; POC)"},
        )
        return self

    async def __aexit__(self, *_):
        if self._session:
            await self._session.close()

    def _domain_lock(self, domain: str) -> asyncio.Lock:
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Lock()
        return self._domain_locks[domain]

    async def fetch(self, url: str) -> FetchResult:
        domain = urlparse(url).netloc
        async with self._semaphore:
            lock = self._domain_lock(domain)
            async with lock:
                await asyncio.sleep(self._per_domain_delay)
                try:
                    assert self._session is not None
                    async with self._session.get(url, allow_redirects=True) as resp:
                        ct = resp.content_type or ""
                        if "html" not in ct and ct != "":
                            return FetchResult(url=url, html=None, status=resp.status, error=f"non-html: {ct}")
                        html = await resp.text(errors="replace")
                        return FetchResult(url=url, html=html, status=resp.status)
                except Exception as exc:
                    return FetchResult(url=url, html=None, status=0, error=str(exc))
