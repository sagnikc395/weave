# weave

> A concurrent web crawler that uses different concurrency models for different stages of the pipeline.

Weave is built around one practical idea: network fetching, HTML parsing, frontier coordination, and query serving do not have the same bottlenecks, so they should not use the same execution model.

## Architecture

| Stage | Bottleneck | Model | Implementation |
|---|---|---|---|
| Fetching URLs | Network I/O | `asyncio` + `aiohttp` | `weave/fetcher.py` |
| Parsing HTML | CPU | `ProcessPoolExecutor` | `weave/parser.py` + `weave/crawler.py` |
| Frontier dedup | Shared state | `threading.Lock` | `weave/frontier.py` |
| Storage/query | Concurrent reads/writes | SQLite WAL | `weave/storage.py` |
| HTTP API | Request/response + background jobs | FastAPI | `weave/api.py` |
| MCP integration | stdio tools | `mcp` server | `weave/mcp_server.py` |

When multiprocessing is unavailable in the runtime environment, the crawler falls back to `ThreadPoolExecutor` so it still runs correctly, with reduced CPU parallelism.

## Implemented Features

- Async fetcher with global concurrency control and per-domain politeness delay
- CPU-bound HTML parsing offloaded through an executor
- Thread-safe URL deduplication in the frontier
- SQLite-backed page store with WAL mode enabled
- Stored outbound link graph for crawled pages
- Search over crawled content using SQLite `LIKE`
- FastAPI service for crawl jobs, page listing, stats, search, and link inspection
- MCP stdio server exposing crawl/search/page/link tools
- CLI for crawling, serving the HTTP API, and starting the MCP server
- Benchmarks for fetching, parsing, and frontier contention

## Project Layout

```text
main.py
weave/
  api.py
  config.py
  crawler.py
  fetcher.py
  frontier.py
  mcp_server.py
  parser.py
  storage.py
benchmark/
  benchmark.py
```

## Quickstart

### Install

```bash
git clone https://github.com/sagnikc395/weave
cd weave
uv sync
```

If you are not using `uv`, install from `pyproject.toml` into a virtualenv with your preferred tool.

### Crawl a Site

```bash
./.venv/bin/python -m weave crawl https://example.com \
  --depth 2 \
  --concurrency 10 \
  --max-pages 100 \
  --db-path weave.db
```

### Start the HTTP API

```bash
./.venv/bin/python -m weave serve \
  --host 127.0.0.1 \
  --port 8000 \
  --db-path weave.db
```

Available endpoints:

- `GET /health`
- `GET /stats`
- `GET /pages?limit=50&offset=0`
- `GET /pages/by-url?url=...`
- `GET /search?query=...`
- `GET /links?url=...`
- `POST /crawl`
- `GET /crawl/jobs`
- `GET /crawl/jobs/{job_id}`

Example crawl request:

```bash
curl -X POST http://127.0.0.1:8000/crawl \
  -H 'content-type: application/json' \
  -d '{
    "url": "https://example.com",
    "depth": 2,
    "concurrency": 10,
    "max_pages": 50,
    "allowed_domains": [],
    "per_domain_delay": 0.5
  }'
```

### Start the MCP Server

```bash
./.venv/bin/python -m weave mcp
```

Available MCP tools:

- `crawl_url`
- `search_crawled`
- `get_page_summary`
- `extract_links`

## CLI

```bash
./.venv/bin/python -m weave --help
./.venv/bin/python -m weave crawl --help
./.venv/bin/python -m weave serve --help
./.venv/bin/python -m weave mcp --help
```

The main commands are:

- `crawl`: runs the crawler directly
- `serve`: starts the FastAPI HTTP API
- `mcp`: starts the MCP stdio server

## Storage Model

Weave currently uses SQLite.

`pages` stores:
- URL
- title
- extracted text
- HTTP status
- crawl depth
- crawl timestamp

`links` stores:
- source URL
- target URL

This lets the project support:

- page retrieval by URL
- keyword search
- aggregate crawl stats
- outbound link inspection

## Verified End-to-End Flow

The current implementation has been exercised locally with:

- a real crawl against a temporary local HTTP site
- persisted results in SQLite
- API verification for `/health`, `/stats`, `/pages`, `/search`, and `/links`

Verified result from that run:

- `3` pages crawled
- `0` errors
- `4` links stored
- `/search?query=architecture` returned the expected crawled page

## Benchmarks

The benchmark suite is in `benchmark/benchmark.py` and covers:

- async fetching vs threaded vs sync fetching
- single-threaded vs threaded vs multiprocess parsing
- frontier dedup throughput under contention

Run it with:

```bash
./.venv/bin/python benchmark/benchmark.py
```

## Current Limitations

- `robots.txt` is not implemented yet
- frontier strategy is FIFO only
- search is keyword-based, not semantic
- storage is SQLite only
- Redis is installed as a future dependency but not used
- there is no Docker or deployment setup in the repo yet

## Why This Project Exists

This codebase exists to make Python concurrency tradeoffs concrete:

- `asyncio` is used where the bottleneck is waiting on the network
- processes are preferred for CPU-heavy parsing when available
- a lock protects exact URL deduplication in shared in-memory state

The point is not "use asyncio everywhere." The point is to use the concurrency primitive that matches the bottleneck.
