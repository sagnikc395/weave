import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .config import CrawlConfig
from .crawler import Crawler
from .storage import Store


class CrawlRequest(BaseModel):
    url: str
    depth: int = Field(default=2, ge=0)
    concurrency: int = Field(default=10, ge=1, le=200)
    max_pages: int = Field(default=100, ge=1)
    allowed_domains: list[str] = Field(default_factory=list)
    per_domain_delay: float = Field(default=0.5, ge=0.0)


class CrawlJobStatus(BaseModel):
    job_id: str
    status: str
    config: dict[str, Any]
    summary: dict[str, Any] | None = None
    error: str | None = None


class CrawlManager:
    def __init__(self, db_path: str = "weave.db"):
        self.db_path = db_path
        self._jobs: dict[str, dict[str, Any]] = {}
        self._counter = 0
        self._lock = asyncio.Lock()

    async def start(self, request: CrawlRequest) -> dict[str, Any]:
        async with self._lock:
            self._counter += 1
            job_id = f"crawl-{self._counter}"
            config = CrawlConfig(
                seed_urls=[request.url],
                max_depth=request.depth,
                concurrency=request.concurrency,
                max_pages=request.max_pages,
                allowed_domains=request.allowed_domains,
                per_domain_delay=request.per_domain_delay,
                db_path=self.db_path,
            )
            record = {
                "job_id": job_id,
                "status": "running",
                "config": asdict(config),
                "summary": None,
                "error": None,
            }
            self._jobs[job_id] = record
            asyncio.create_task(self._run(job_id, config))
            return record.copy()

    async def _run(self, job_id: str, config: CrawlConfig) -> None:
        try:
            summary = await Crawler(config).run()
            self._jobs[job_id]["status"] = "completed"
            self._jobs[job_id]["summary"] = asdict(summary)
        except Exception as exc:
            self._jobs[job_id]["status"] = "failed"
            self._jobs[job_id]["error"] = str(exc)

    def get(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        return job.copy()

    def list(self) -> list[dict[str, Any]]:
        return [job.copy() for job in self._jobs.values()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = getattr(app.state, "db_path", "weave.db")
    app.state.store = Store(db_path=db_path)
    app.state.crawl_manager = CrawlManager(db_path=db_path)
    yield


def create_app(db_path: str = "weave.db") -> FastAPI:
    app = FastAPI(title="weave", version="0.1.0", lifespan=lifespan)
    app.state.db_path = db_path

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/stats")
    async def stats() -> dict[str, Any]:
        return app.state.store.stats()

    @app.get("/pages")
    async def list_pages(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return {
            "items": app.state.store.list_pages(limit=limit, offset=offset),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/pages/by-url")
    async def get_page(url: str) -> dict[str, Any]:
        page = app.state.store.get_page(url)
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        return page

    @app.get("/search")
    async def search(query: str = Query(min_length=1), limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
        return {"items": app.state.store.search(query, limit=limit), "query": query}

    @app.get("/links")
    async def links(url: str) -> dict[str, Any]:
        return {"url": url, "links": app.state.store.get_links(url)}

    @app.post("/crawl", response_model=CrawlJobStatus, status_code=202)
    async def crawl(request: CrawlRequest) -> dict[str, Any]:
        return await app.state.crawl_manager.start(request)

    @app.get("/crawl/jobs", response_model=list[CrawlJobStatus])
    async def crawl_jobs() -> list[dict[str, Any]]:
        return app.state.crawl_manager.list()

    @app.get("/crawl/jobs/{job_id}", response_model=CrawlJobStatus)
    async def crawl_job(job_id: str) -> dict[str, Any]:
        job = app.state.crawl_manager.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    return app
