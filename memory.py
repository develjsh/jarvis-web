import sqlite3
from pathlib import Path


class Memory:
    def __init__(self, db_path: str = "data/jarvis.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts
                    USING fts5(content, content=conversations, content_rowid=id);

                CREATE TRIGGER IF NOT EXISTS conversations_fts_insert
                    AFTER INSERT ON conversations BEGIN
                        INSERT INTO conversations_fts(rowid, content)
                        VALUES (new.id, new.content);
                    END;

                CREATE TRIGGER IF NOT EXISTS conversations_fts_delete
                    AFTER DELETE ON conversations BEGIN
                        INSERT INTO conversations_fts(conversations_fts, rowid, content)
                        VALUES ('delete', old.id, old.content);
                    END;

                CREATE TABLE IF NOT EXISTS facts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    key         TEXT NOT NULL UNIQUE,
                    value       TEXT NOT NULL,
                    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status      TEXT DEFAULT 'pending',
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    # ── Conversations ──────────────────────────────────────────────────────────

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )

    def get_context(self, session_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT role, content FROM conversations
                   WHERE session_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def search(self, query: str, limit: int = 5) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT c.role, c.content, c.created_at
                   FROM conversations c
                   JOIN conversations_fts f ON c.id = f.rowid
                   WHERE conversations_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))

    def prune_old_messages(self, session_id: str, keep: int = 50) -> None:
        with self._connect() as conn:
            conn.execute(
                """DELETE FROM conversations
                   WHERE session_id = ? AND id NOT IN (
                       SELECT id FROM conversations
                       WHERE session_id = ?
                       ORDER BY id DESC LIMIT ?
                   )""",
                (session_id, session_id, keep),
            )

    # ── Facts ──────────────────────────────────────────────────────────────────

    def add_fact(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO facts (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE
                   SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
                (key, value),
            )

    def get_facts(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM facts").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def delete_fact(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM facts WHERE key = ?", (key,))

    # ── Tasks ──────────────────────────────────────────────────────────────────

    def add_task(self, title: str, description: str = "") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (title, description) VALUES (?, ?)",
                (title, description),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_tasks(self, status: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY id", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def update_task(self, task_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ?", (status, task_id)
            )
