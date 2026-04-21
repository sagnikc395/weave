import asyncio
import threading


class Frontier:
    """Thread-safe URL frontier. asyncio.Queue for async producers/consumers,
    threading.Lock on the visited set since multiple coroutines push concurrently."""

    def __init__(self, max_depth: int):
        self._queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self._visited: set[str] = set()
        self._lock = threading.Lock()
        self.max_depth = max_depth

    async def push(self, url: str, depth: int) -> bool:
        if depth > self.max_depth:
            return False
        with self._lock:
            if url in self._visited:
                return False
            self._visited.add(url)
        await self._queue.put((url, depth))
        return True

    async def pop(self) -> tuple[str, int]:
        return await self._queue.get()

    def task_done(self):
        self._queue.task_done()

    def empty(self) -> bool:
        return self._queue.empty()

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def visited_count(self) -> int:
        with self._lock:
            return len(self._visited)
