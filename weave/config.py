from dataclasses import dataclass, field


@dataclass
class CrawlConfig:
    seed_urls: list[str]
    max_depth: int = 2
    max_pages: int = 100
    concurrency: int = 10
    per_domain_delay: float = 0.5
    db_path: str = "weave.db"
    allowed_domains: list[str] = field(default_factory=list)
