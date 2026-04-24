import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .config import CrawlConfig
from .crawler import Crawler
from .storage import Store

_store = Store()
server = Server("weave")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="crawl_url",
            description="Trigger a crawl starting from a URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Seed URL to crawl"},
                    "depth": {
                        "type": "integer",
                        "default": 2,
                        "description": "Max crawl depth",
                    },
                    "max_pages": {"type": "integer", "default": 50},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="search_crawled",
            description="Keyword search over all crawled pages",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="get_page_summary",
            description="Return the stored title + text for a crawled URL",
            inputSchema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        ),
        Tool(
            name="extract_links",
            description="Return pages found at the depth immediately below a given URL",
            inputSchema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "crawl_url":
        config = CrawlConfig(
            seed_urls=[arguments["url"]],
            max_depth=arguments.get("depth", 2),
            max_pages=arguments.get("max_pages", 50),
        )
        crawler = Crawler(config)
        asyncio.create_task(crawler.run())
        return [TextContent(type="text", text=f"Crawl started for {arguments['url']}")]

    if name == "search_crawled":
        results = _store.search(arguments["query"])
        return [TextContent(type="text", text=json.dumps(results, indent=2))]

    if name == "get_page_summary":
        page = _store.get_page(arguments["url"])
        if not page:
            return [TextContent(type="text", text="Not found in store.")]
        body = f"**{page['title']}**\n\n{page['text'][:600]}"
        return [TextContent(type="text", text=body)]

    if name == "extract_links":
        links = _store.get_links(arguments["url"])
        return [TextContent(type="text", text=json.dumps(links, indent=2))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def serve_stdio():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())
