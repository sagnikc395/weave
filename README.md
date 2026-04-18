# Weave

> A concurrent web crawler built around one idea: **different compute profiles need different concurrency models.**

Most crawlers treat concurrency as an afterthought. Weave treats it as the architecture.

---

## The Problem With Naive Crawlers

A single-threaded crawler is slow. A naive async crawler breaks on CPU-heavy parsing. A threaded crawler hits the GIL and stalls on content extraction. Most implementations pick one model and suffer the tradeoffs silently.

Weave doesn't. It maps each stage of crawling to the concurrency primitive that actually fits:

| Stage | Bottleneck | Model | Why |
|---|---|---|---|
| Fetching URLs | Network I/O | `asyncio` + `aiohttp` | Await hundreds of requests concurrently without threads |
| Parsing HTML | CPU | `multiprocessing` | GIL blocks threads here — separate processes bypass it entirely |
| Frontier management | Coordination | `threading` | Shared state across producers/consumers, `Lock` on visited set |

This isn't theoretical. Each decision came from profiling. Threading the parser gave no speedup. `ProcessPoolExecutor` cut parse time by ~60%.

---

## Architecture

```
Seed URLs
    ↓
[Frontier Queue]          asyncio.Queue — bounded, provides backpressure
    ↓
[Async Fetcher Pool]      aiohttp + asyncio.Semaphore — capped concurrent connections
    ↓
[Raw HTML Queue]          multiprocessing.Queue — crosses process boundary
    ↓
[Parser Workers]          ProcessPoolExecutor — true parallelism, GIL bypassed
    ↓
[Result Store]            SQLite / Redis — crawled content + metadata
```

Bounded queues at every boundary. Fast fetchers can't overwhelm slow parsers. Slow parsers don't starve the frontier.

---

## Features

**Concurrency**
- Async fetcher pool with per-domain connection limits via `asyncio.Semaphore`
- `ProcessPoolExecutor` + `ThreadPoolExecutor` hybrid — right tool for each stage
- Thread-safe URL deduplication with `threading.Lock`
- Backpressure via bounded `asyncio.Queue` between every layer

**Crawl control**
- Configurable depth, domain scope, and concurrency limits
- Per-domain politeness delays and `robots.txt` compliance
- BFS / DFS / priority queue frontier strategies

**Observability**
- Live crawl dashboard via `rich` — pages/sec, error rate, queue depths
- Per-domain stats exported to JSON

**MCP Server**
Weave exposes its knowledge base as an MCP server — query everything it's crawled directly through Claude:
- `crawl_url(url, depth)` — trigger a crawl
- `search_crawled(query)` — semantic search over crawled content  
- `get_page_summary(url)` — summarize a crawled page
- `extract_links(url)` — outbound link graph for any crawled URL

---

## Quickstart

```bash
git clone https://github.com/yourname/weave
cd weave
pip install -e .

# Crawl a site
weave crawl https://example.com --depth 3 --concurrency 50

# Start the MCP server
weave serve --port 8000
```

---

## Why This Exists

I wanted to understand Python concurrency at the level where you make deliberate tradeoffs — not just "use asyncio for everything." Weave is the project that forced those decisions concretely.

The GIL isn't just a trivia answer here. It's the reason the parser layer is a separate process pool.

---

## Tech Stack

- `aiohttp` — async HTTP client
- `BeautifulSoup` / `lxml` — HTML parsing
- `concurrent.futures` — unified executor interface
- `Redis` — frontier queue in distributed mode
- `SQLite` + `pgvector` — result store + semantic search
- `rich` / `textual` — live dashboard
- `mcp` — MCP server for Claude integration

Good question to think about early. Here's the honest breakdown:

---

**The deployment challenge with Weave**

Weave is trickier to deploy than your other projects because it's inherently a **long-running process**, not a request/response API. You can't just push to Railway and get a URL. The crawler needs to keep running, the MCP server needs to stay alive, and the result store needs to persist.

---

**Recommended approach: Split it into two deployable pieces**

**Piece 1 — The MCP server + result store (always on)**
This is what you actually deploy. It serves the crawled knowledge base and exposes the MCP endpoints. Stateless-ish, easy to host.

- Railway or Render for the FastAPI/MCP server
- Railway Postgres for the result store
- This gives you a live URL to put on your resume

**Piece 2 — The crawler itself (run on demand)**
Don't try to deploy the crawler as a persistent service — it's expensive and unnecessary for a portfolio project. Instead:

- Run it locally to seed the database with crawled content
- Or expose a `/crawl` endpoint that triggers a background task via `asyncio` when hit
- That way the deployed server always has data to show

---

**Concrete stack:**

```
Local machine          Railway
──────────────         ──────────────────────────
weave crawl  ───────▶  Postgres (crawled content)
                              ↑
                       FastAPI + MCP server
                              ↑
                         Claude / any MCP client
```

---

**Step by step:**

1. Build the crawler and MCP server locally first
2. Dockerize both — one `Dockerfile` for the API, one for the worker
3. Push Postgres to Railway, run migrations
4. Deploy the MCP/API server to Railway
5. Run the crawler locally pointed at the Railway Postgres to seed it with real data
6. Put the Railway URL in your resume

---

**What to crawl to make the demo impressive**

Don't crawl random sites. Crawl something with a coherent knowledge domain so the semantic search actually works well:

- Hacker News (crawl top posts + comments)
- A specific documentation site (FastAPI docs, Temporal docs)
- A curated list of engineering blogs

Then your demo becomes: *"I crawled the Temporal.io docs and can query them through Claude"* — that's a concrete, impressive demo in 10 seconds.

---

**The resume line:**

> *Deployed MCP server on Railway backed by Postgres — exposes crawled web content as a Claude-queryable knowledge base via semantic search*

The crawler itself not being "deployed" doesn't matter — nobody expects a portfolio crawler to be running 24/7. What matters is the live MCP server with real data behind it.
