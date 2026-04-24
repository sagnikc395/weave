import sqlite3
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass
class Page:
    url: str
    title: str
    text: str
    status: int
    depth: int


@dataclass
class LinkEdge:
    source_url: str
    target_url: str


class Store:
    def __init__(self, db_path: str = "weave.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pages (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    text TEXT,
                    status INTEGER,
                    depth INTEGER,
                    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    source_url TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    UNIQUE(source_url, target_url)
                )
            """)

    def save(self, page: Page):
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO pages (url, title, text, status, depth) VALUES (?, ?, ?, ?, ?)",
                    (page.url, page.title, page.text, page.status, page.depth),
                )

    def save_links(self, source_url: str, links: list[str]):
        if not links:
            return
        rows = [(source_url, link) for link in dict.fromkeys(links)]
        with self._lock:
            with self._connect() as conn:
                conn.executemany(
                    "INSERT OR IGNORE INTO links (source_url, target_url) VALUES (?, ?)",
                    rows,
                )

    def search(self, query: str, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT url, title, text, status, depth, crawled_at
                FROM pages
                WHERE text LIKE ? OR title LIKE ?
                ORDER BY crawled_at DESC
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        return [
            {
                "url": r[0],
                "title": r[1],
                "snippet": r[2][:400],
                "status": r[3],
                "depth": r[4],
                "crawled_at": r[5],
            }
            for r in rows
        ]

    def get_page(self, url: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT url, title, text, status, depth, crawled_at FROM pages WHERE url = ?",
                (url,),
            ).fetchone()
        if not row:
            return None
        return {"url": row[0], "title": row[1], "text": row[2], "status": row[3], "depth": row[4], "crawled_at": row[5]}

    def list_pages(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT url, title, status, depth, crawled_at
                FROM pages
                ORDER BY crawled_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "url": row[0],
                "title": row[1],
                "status": row[2],
                "depth": row[3],
                "crawled_at": row[4],
            }
            for row in rows
        ]

    def get_links(self, url: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT target_url
                FROM links
                WHERE source_url = ?
                ORDER BY target_url
                LIMIT 200
                """,
                (url,),
            ).fetchall()
        return [r[0] for r in rows]

    def stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            statuses = conn.execute(
                """
                SELECT status, COUNT(*)
                FROM pages
                GROUP BY status
                ORDER BY status
                """
            ).fetchall()
            max_depth = conn.execute("SELECT COALESCE(MAX(depth), 0) FROM pages").fetchone()[0]
            total_links = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        return {
            "total_pages": total,
            "total_links": total_links,
            "max_depth": max_depth,
            "statuses": {str(status): count for status, count in statuses},
        }
