from __future__ import annotations

import argparse
import getpass
import uuid

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify INTOPIA DSS database and file persistence through the deployed API.")
    parser.add_argument("url", help="Render URL, for example https://intopia-dss.onrender.com")
    parser.add_argument("--user", default="intopia", help="Shared-link username")
    args = parser.parse_args()
    password = getpass.getpass("Shared-link password: ")
    base = args.url.rstrip("/")
    token = uuid.uuid4().hex

    with httpx.Client(base_url=base, auth=(args.user, password), timeout=90, follow_redirects=True) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        print("Health:", health.json())

        fact = client.post(
            "/api/facts",
            json={"quarter": "Q1", "source_type": "persistence-check", "metric": f"verify-{token}"},
        )
        fact.raise_for_status()
        fact_id = fact.json()["id"]

        uploaded = client.post(
            "/api/uploads",
            data={"quarter": "Setup", "category": "בדיקת persistence", "notes": "Safe to delete"},
            files={"file": (f"verify-{token}.txt", token.encode(), "text/plain")},
        )
        uploaded.raise_for_status()
        upload_id = uploaded.json()["id"]
        try:
            downloaded = client.get(f"/api/uploads/{upload_id}/download")
            downloaded.raise_for_status()
            if downloaded.content != token.encode():
                raise RuntimeError("Downloaded file content differs from uploaded content.")
            print("Database persistence: OK")
            print("Storage persistence: OK")
        finally:
            client.delete(f"/api/facts/{fact_id}").raise_for_status()
            client.delete(f"/api/uploads/{upload_id}").raise_for_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
