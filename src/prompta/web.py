"""Read-only web UI for Prompta's local conversation cache."""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

from .cache import DEFAULT_CACHE_PATH

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")


class ReadOnlyChatStore:
    """Open a fresh read-only SQLite connection for each web request."""

    def __init__(self, path: Path = DEFAULT_CACHE_PATH) -> None:
        self.path = path.expanduser()

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        connection = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=2000")
        return connection

    def conversations(self, *, limit: int = 200, query: str = "") -> list[dict[str, Any]]:
        search = query.strip()
        where = ""
        parameters: list[Any] = []
        if search:
            where = """
                WHERE c.title LIKE ? COLLATE NOCASE
                   OR c.job_name LIKE ? COLLATE NOCASE
                   OR c.prompt LIKE ? COLLATE NOCASE
                   OR EXISTS (
                       SELECT 1 FROM messages sm
                       WHERE sm.conversation_id = c.id
                         AND sm.content LIKE ? COLLATE NOCASE
                   )
            """
            needle = f"%{search}%"
            parameters.extend([needle, needle, needle, needle])
        parameters.append(max(1, min(limit, 500)))
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        c.id,
                        c.job_name,
                        c.url,
                        c.title,
                        c.status,
                        c.created_at,
                        c.updated_at,
                        c.completed_at,
                        (
                            SELECT m.content FROM messages m
                            WHERE m.conversation_id = c.id
                            ORDER BY m.ordinal DESC LIMIT 1
                        ) AS preview,
                        (
                            SELECT COUNT(*) FROM messages m
                            WHERE m.conversation_id = c.id
                        ) AS message_count
                    FROM conversations c
                    {where}
                    ORDER BY
                        CASE c.status WHEN 'active' THEN 0 ELSE 1 END,
                        c.updated_at DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
        except FileNotFoundError:
            return []
        return [dict(row) for row in rows]

    def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                conversation = connection.execute(
                    """
                    SELECT id, job_name, prompt, url, title, status,
                           created_at, updated_at, completed_at
                    FROM conversations
                    WHERE id = ?
                    """,
                    (conversation_id,),
                ).fetchone()
                if conversation is None:
                    return None
                messages = connection.execute(
                    """
                    SELECT message_key, ordinal, role, content, status,
                           created_at, updated_at
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY ordinal
                    """,
                    (conversation_id,),
                ).fetchall()
        except FileNotFoundError:
            return None
        payload = dict(conversation)
        payload["messages"] = [dict(message) for message in messages]
        return payload

    def stats(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"exists": False, "total": 0, "active": 0}
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active
                    FROM conversations
                    """
                ).fetchone()
        except (FileNotFoundError, sqlite3.Error):
            return {"exists": False, "total": 0, "active": 0}
        return {
            "exists": True,
            "total": int(row["total"] or 0),
            "active": int(row["active"] or 0),
        }


class PromptaUIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: ReadOnlyChatStore) -> None:
        super().__init__(address, PromptaUIHandler)
        self.store = store


class PromptaUIHandler(BaseHTTPRequestHandler):
    server_version = "PromptaUI/1"

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("%s - %s", self.address_string(), format % args)

    @property
    def store(self) -> ReadOnlyChatStore:
        return cast(PromptaUIServer, self.server).store

    def _headers(self, status: HTTPStatus, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'; "
            "font-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self._headers(status, "application/json; charset=utf-8")
        self.wfile.write(body)

    def _static(self, relative_path: str, content_type: str | None = None) -> None:
        target = (_STATIC_ROOT / relative_path).resolve()
        try:
            target.relative_to(_STATIC_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = target.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = content_type or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._headers(HTTPStatus.OK, f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._static("index.html", "text/html")
            return
        if path == "/app.css":
            self._static("app.css", "text/css")
            return
        if path == "/app.js":
            self._static("app.js", "text/javascript")
            return
        if path == "/api/health":
            self._json(self.store.stats())
            return
        if path == "/api/chats":
            query = parse_qs(parsed.query)
            search = query.get("q", [""])[0]
            try:
                limit = int(query.get("limit", ["200"])[0])
            except ValueError:
                limit = 200
            self._json({"chats": self.store.conversations(limit=limit, query=search)})
            return
        prefix = "/api/chats/"
        if path.startswith(prefix):
            conversation_id = unquote(path[len(prefix) :])
            chat = self.store.conversation(conversation_id)
            if chat is None:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(chat)
            return
        self.send_error(HTTPStatus.NOT_FOUND)


def serve(cache_path: Path, host: str, port: int) -> None:
    store = ReadOnlyChatStore(cache_path)
    server = PromptaUIServer((host, port), store)
    logger.info("Prompta UI listening on http://%s:%d", host, port)
    logger.info("Reading cache %s in SQLite query-only mode", cache_path.expanduser())
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Prompta's read-only conversation UI")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(args.cache, args.host, max(1, min(args.port, 65535)))


if __name__ == "__main__":
    main()
