"""
tests/test_scanner_api.py
-------------------------
Tests de integración para los endpoints del scanner.

Usa TestClient de FastAPI/httpx para probar rutas reales sin levantar
un servidor. Cubre los casos que fallaban silenciosamente antes del fix.
"""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app)


@pytest.fixture
def temp_dir():
    """Directorio temporal con algunos archivos de prueba."""
    with tempfile.TemporaryDirectory() as d:
        # Crear archivos de muestra
        (open(os.path.join(d, "file1.txt"), "w")).write("hello world")
        (open(os.path.join(d, "file2.py"),  "w")).write("print('test')")
        (open(os.path.join(d, "image.jpg"), "w")).write("fake image data")
        yield d


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_endpoint(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ── Scanner ───────────────────────────────────────────────────────────────────

class TestScannerEndpoints:

    def test_start_scan_invalid_path(self, client):
        r = client.post("/api/scan", json={"path": "/ruta/que/no/existe/xyzxyz"})
        assert r.status_code == 422  # Pydantic validation error

    def test_start_scan_valid(self, client, temp_dir):
        r = client.post("/api/scan", json={"path": temp_dir, "max_depth": 3})
        assert r.status_code == 202
        data = r.json()
        assert "scan_id" in data
        assert data["status"] == "accepted"

    def test_get_progress_unknown_scan(self, client):
        r = client.get("/api/scan/unknownid99/progress")
        assert r.status_code == 404

    def test_list_all_scans_returns_list(self, client):
        r = client.get("/api/scan/all")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_delete_nonexistent_scan(self, client):
        r = client.delete("/api/scan/nonexistent123")
        assert r.status_code == 200  # delete es idempotente


# ── Explorer ──────────────────────────────────────────────────────────────────

class TestExplorerEndpoints:

    def test_drives_returns_list(self, client):
        r = client.get("/api/explorer/drives")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_folders_valid_path(self, client, temp_dir):
        r = client.get(f"/api/explorer/folders?path={temp_dir}")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_folders_nonexistent_path(self, client):
        r = client.get("/api/explorer/folders?path=/ruta/no/existe/xyzxyz")
        assert r.status_code == 404

    def test_validate_path_valid(self, client, temp_dir):
        r = client.get(f"/api/explorer/validate-path?path={temp_dir}")
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_validate_path_nonexistent(self, client):
        r = client.get("/api/explorer/validate-path?path=/no/existe/xyzxyz")
        assert r.status_code == 200
        assert r.json()["valid"] is False


# ── Duplicates — seguridad ─────────────────────────────────────────────────────

class TestDeleteSecurity:

    def test_delete_traversal_path_rejected(self, client):
        """Una ruta con ../ debe ser rechazada con 422 o devolver en 'failed'."""
        r = client.request(
            "DELETE",
            "/api/duplicates/files",
            json={"paths": ["/home/user/../../etc/passwd"], "use_recycle": False},
        )
        # Puede devolver 200 con la ruta en 'failed', o 422 según validación
        if r.status_code == 200:
            assert "/home/user/../../etc/passwd" in r.json()["failed"]
        else:
            assert r.status_code in (422, 400)

    def test_delete_too_many_paths_rejected(self, client):
        """Más de MAX_DELETE_PATHS rutas deben ser rechazadas por Pydantic."""
        paths = [f"/tmp/file_{i}.txt" for i in range(501)]
        r = client.request(
            "DELETE",
            "/api/duplicates/files",
            json={"paths": paths, "use_recycle": False},
        )
        assert r.status_code == 422

    def test_delete_empty_paths_rejected(self, client):
        r = client.request(
            "DELETE",
            "/api/duplicates/files",
            json={"paths": [], "use_recycle": False},
        )
        assert r.status_code == 422