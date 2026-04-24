import argparse
import asyncio


def main():
    parser = argparse.ArgumentParser(prog="weave")
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl = subparsers.add_parser("crawl")
    crawl.add_argument("url")
    crawl.add_argument("--depth", type=int, default=2)
    crawl.add_argument("--concurrency", type=int, default=10)
    crawl.add_argument("--max-pages", type=int, default=100)
    crawl.add_argument("--db-path", default="weave.db")
    crawl.add_argument("--per-domain-delay", type=float, default=0.5)
    crawl.add_argument("--domain", dest="allowed_domains", action="append", default=[])

    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--db-path", default="weave.db")

    subparsers.add_parser("mcp")

    args = parser.parse_args()

    if args.command == "crawl":
        from weave.config import CrawlConfig
        from weave.crawler import Crawler

        config = CrawlConfig(
            seed_urls=[args.url],
            max_depth=args.depth,
            concurrency=args.concurrency,
            max_pages=args.max_pages,
            allowed_domains=args.allowed_domains,
            per_domain_delay=args.per_domain_delay,
            db_path=args.db_path,
        )
        asyncio.run(Crawler(config).run())

    elif args.command == "serve":
        import uvicorn
        from weave.api import create_app

        uvicorn.run(create_app(db_path=args.db_path), host=args.host, port=args.port)

    elif args.command == "mcp":
        from weave.mcp_server import serve_stdio

        asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
