"""Pytest bootstrap for the campus recommender tests.

Every pytest run gets a *fresh, isolated* SQLite database in the system temp
directory (never tests/test.db), so runs and test cases cannot pollute each
other.  The environment variable must be set before ``app.main`` is imported,
which is why this happens at module level instead of inside a fixture.
"""
import os
import tempfile
import time
from pathlib import Path

_DB = Path(tempfile.gettempdir()) / f"campus_recommender_test_{os.getpid()}_{int(time.time() * 1000)}.db"
# Force an isolated SQLite database even when the developer .env file points
# DATABASE_URL/MYSQL_PASSWORD at a local MySQL server (app.main.url() checks
# DATABASE_URL first, then MYSQL_PASSWORD, then CAMPUS_DB).
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["MYSQL_PASSWORD"] = ""
os.environ["CAMPUS_DB"] = str(_DB)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(_DB) + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

# Tests must never send campus or student data to a live model.
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["ACADEMIC_UPLOAD_DIR"] = str(Path(tempfile.gettempdir()) / f"academic_uploads_{os.getpid()}")

os.environ["JWT_SECRET"] = "academic-test-only-secret-at-least-32-characters"
