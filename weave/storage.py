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


class Store:
    def __init__(self, db_path: str = "weave.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

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

    def save(self, page: Page):
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO pages (url, title, text, status, depth) VALUES (?, ?, ?, ?, ?)",
                    (page.url, page.title, page.text, page.status, page.depth),
                )

    def search(self, query: str, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT url, title, text FROM pages WHERE text LIKE ? OR title LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        return [{"url": r[0], "title": r[1], "snippet": r[2][:400]} for r in rows]

    def get_page(self, url: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT url, title, text, status, depth, crawled_at FROM pages WHERE url = ?",
                (url,),
            ).fetchone()
        if not row:
            return None
        return {"url": row[0], "title": row[1], "text": row[2], "status": row[3], "depth": row[4], "crawled_at": row[5]}

    def get_links(self, url: str) -> list[str]:
        """Return all pages that were found at the same depth-1 as this URL (rough outbound graph)."""
        with self._connect() as conn:
            row = conn.execute("SELECT depth FROM pages WHERE url = ?", (url,)).fetchone()
            if not row:
                return []
            rows = conn.execute(
                "SELECT url FROM pages WHERE depth = ? LIMIT 50",
                (row[0] + 1,),
            ).fetchall()
        return [r[0] for r in rows]

    def stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        return {"total_pages": total}
