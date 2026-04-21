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
    crawl.add_argument("--domain", dest="allowed_domains", action="append", default=[])

    subparsers.add_parser("serve")

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
        )
        asyncio.run(Crawler(config).run())

    elif args.command == "serve":
        from weave.mcp_server import serve

        asyncio.run(serve())


if __name__ == "__main__":
    main()
