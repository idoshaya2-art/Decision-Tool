from __future__ import annotations

import hashlib
import io
import zipfile

from backup_service import APP_VERSION


def test_health_and_cloud_configuration(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["backend"] == "memory"
    assert response.json()["storage"] == "ok"

    home = client.get("/")
    assert home.status_code == 200
    assert "EMBA TAU Simulation" in home.text
    assert client.get("/static/app.js").status_code == 200


def test_autosave_survives_new_app_client(client):
    saved = client.put(
        "/api/settings",
        json={"company_name": "Persistence Test", "cash_buffer_sf": 123456, "selected_quarter": "Q4"},
    )
    assert saved.status_code == 200
    assert saved.json()["company_name"] == "Persistence Test"

    finance = client.put("/api/finance/Q4", json={"revenue_sf": 500000, "ending_cash_sf": 123456})
    assert finance.status_code == 200

    # A new HTTP client reads the same cloud store, equivalent to a web process restart.
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as second_client:
        assert second_client.get("/api/settings").json()["company_name"] == "Persistence Test"
        assert second_client.get("/api/finance/Q4").json()["revenue_sf"] == 500000


def test_upload_metadata_checksum_download_and_delete(client):
    content = b"quarter-report-content"
    response = client.post(
        "/api/uploads",
        data={"quarter": "Q3", "category": "דוח רבעוני", "notes": "test"},
        files={"file": ("Q3 report.pdf", content, "application/pdf")},
    )
    assert response.status_code == 200
    record = response.json()
    assert record["storage_bucket"] == "intopia-files"
    assert record["storage_path"].startswith("q3/")
    assert record["sha256"] == hashlib.sha256(content).hexdigest()
    assert record["size_bytes"] == len(content)
    assert record["metadata"]["app_version"] == APP_VERSION

    download = client.get(f"/api/uploads/{record['id']}/download")
    assert download.status_code == 200
    assert download.content == content

    assert client.delete(f"/api/uploads/{record['id']}").status_code == 204
    assert client.get("/api/uploads").json() == []


def test_complete_backup_and_replace_restore(client):
    client.put("/api/settings", json={"company_name": "Backup Company", "selected_quarter": "Q5"})
    client.put("/api/finance/Q5", json={"revenue_sf": 999, "net_profit_sf": 111})
    upload = client.post(
        "/api/uploads",
        data={"quarter": "Setup", "category": "אסטרטגיה ראשונית"},
        files={"file": ("strategy.txt", b"cloud strategy", "text/plain")},
    ).json()

    backup = client.get("/api/backup")
    assert backup.status_code == 200
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        assert {"manifest.json", "database.json"}.issubset(archive.namelist())
        assert any(name.startswith(f"files/{upload['id']}/") for name in archive.namelist())

    assert client.post("/api/admin/reset", json={"confirmation": "RESET"}).status_code == 200
    assert client.get("/api/settings").json()["company_name"] == ""
    assert client.get("/api/uploads").json() == []

    restored = client.post(
        "/api/restore",
        data={"mode": "replace", "confirmation": "RESTORE"},
        files={"file": ("backup.zip", backup.content, "application/zip")},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored_files"] == 1
    assert client.get("/api/settings").json()["company_name"] == "Backup Company"
    restored_upload = client.get("/api/uploads").json()[0]
    assert client.get(f"/api/uploads/{restored_upload['id']}/download").content == b"cloud strategy"


def test_restore_rejects_invalid_archive(client):
    response = client.post(
        "/api/restore",
        data={"mode": "replace", "confirmation": "RESTORE"},
        files={"file": ("bad.zip", b"not-a-zip", "application/zip")},
    )
    assert response.status_code == 400


def test_unit_economics_endpoint_returns_pricing_recommendation(client):
    response = client.post(
        "/api/economics/calculate",
        json={
            "price_lc": 100,
            "base_demand_units": 1000,
            "available_units": 1000,
            "manufacturing_cost_lc": 55,
            "variable_selling_cost_lc": 5,
            "fixed_cost_lc": 10000,
            "elasticity": 1.2,
            "target_operating_margin": 0.2,
            "price_step_lc": 5,
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["price_floors"]["cash_floor_lc"] == 60
    assert result["recommendation"]["recommended_price_lc"] > 0
    assert result["pricing_grid"]
