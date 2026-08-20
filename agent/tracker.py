"""
agent/tracker.py
SQLite-based application tracker. Logs every application attempt
and prevents re-applying to the same job.
"""

import sqlite3
import csv
from datetime import datetime
from pathlib import Path


DB_PATH = "applications.db"


class ApplicationTracker:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT NOT NULL,
                    platform    TEXT NOT NULL,
                    company     TEXT,
                    job_title   TEXT NOT NULL,
                    role_name   TEXT,
                    resume_used TEXT,
                    status      TEXT NOT NULL,
                    job_url     TEXT,
                    notes       TEXT
                )
            """)

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def already_applied(self, platform: str, job_url: str) -> bool:
        """Returns True if we've already applied to this job URL on this platform."""
        if not job_url:
            return False
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM applications WHERE platform=? AND job_url=? AND status != 'DRY_RUN'",
                (platform, job_url),
            ).fetchone()
        return row is not None

    def log(
        self,
        platform: str,
        job_title: str,
        company: str = "",
        role_name: str = "",
        resume_used: str = "",
        status: str = "APPLIED",
        job_url: str = "",
        notes: str = "",
    ):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO applications
                    (date, platform, company, job_title, role_name, resume_used, status, job_url, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(timespec="seconds"),
                    platform,
                    company,
                    job_title,
                    role_name,
                    resume_used,
                    status,
                    job_url,
                    notes,
                ),
            )

    def count_today(self, platform: str) -> int:
        """How many successful applications today on a given platform."""
        today = datetime.now().date().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM applications WHERE platform=? AND date LIKE ? AND status='APPLIED'",
                (platform, f"{today}%"),
            ).fetchone()
        return row[0] if row else 0

    def export_csv(self, path: str = "applications.csv"):
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM applications ORDER BY id DESC").fetchall()
            headers = [d[0] for d in conn.execute("SELECT * FROM applications LIMIT 0").description or []]

        # Re-fetch headers properly
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM applications ORDER BY id DESC")
            headers = [d[0] for d in cursor.description]
            rows = cursor.fetchall()

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        return path
