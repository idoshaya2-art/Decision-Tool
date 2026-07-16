from pathlib import Path


def test_runtime_has_no_sqlite_or_local_upload_persistence():
    root = Path(__file__).resolve().parents[1]
    runtime = "\n".join((root / name).read_text(encoding="utf-8") for name in ("main.py", "db.py", "cloud.py"))
    forbidden = ("import sqlite3", "intopia.db", "UPLOAD_DIR", "write_bytes(", "FileResponse(")
    for marker in forbidden:
        assert marker not in runtime


def test_secret_files_are_ignored():
    root = Path(__file__).resolve().parents[1]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "*.sqlite" in gitignore
