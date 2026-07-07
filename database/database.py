from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional


class AyraDatabase:
    """SQLite-backed database manager for Ayra AI."""

    def __init__(self, db_path: Optional[str] = None, logger: Optional[logging.Logger] = None) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent
        self.db_path = Path(db_path or self.base_dir / "database" / "memory.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logger or self._create_logger()
        self._initialize_database()

    def _create_logger(self) -> logging.Logger:
        log_path = self.base_dir / "logs" / "database.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("ayra.database")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        return logger

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    nickname TEXT,
                    preferred_language TEXT,
                    theme TEXT,
                    voice_settings TEXT,
                    city TEXT,
                    country TEXT,
                    time_zone TEXT,
                    birthday TEXT,
                    profession TEXT,
                    skills TEXT,
                    interests TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_archived INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_done INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.commit()
        self.logger.info("Database created")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def close(self) -> None:
        pass
