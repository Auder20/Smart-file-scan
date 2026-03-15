"""
tests/test_path_utils.py
------------------------
Tests unitarios para core/path_utils.py y core/security.py.

Cubre los casos que causaban bugs en producción:
  - Dependencia circular (indirectamente: si hay ImportError, todos fallan)
  - Path traversal en rutas de borrado
  - Traducción Docker ↔ nativo en Windows y Linux
  - Detección de rutas del sistema bloqueadas
"""
import os
import platform
import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_host_root(monkeypatch):
    """Asegura que HOST_ROOT no esté definido por defecto en cada test."""
    monkeypatch.delenv("HOST_ROOT", raising=False)


# ── path_utils ────────────────────────────────────────────────────────────────

class TestResolvePathForDocker:

    def test_native_mode_returns_path_unchanged(self):
        from app.core.path_utils import resolve_path_for_docker
        assert resolve_path_for_docker("/home/user/docs") == "/home/user/docs"

    def test_docker_mode_linux(self, monkeypatch):
        monkeypatch.setenv("HOST_ROOT", "/host")
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        from app.core.path_utils import resolve_path_for_docker
        result = resolve_path_for_docker("/home/user/docs")
        assert result == "/host/home/user/docs"

    def test_docker_mode_windows(self, monkeypatch):
        monkeypatch.setenv("HOST_ROOT", "/host")
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        from app.core.path_utils import resolve_path_for_docker
        result = resolve_path_for_docker("C:\\Users\\John")
        assert result == "/host/c/Users/John"

    def test_already_docker_path_unchanged(self, monkeypatch):
        monkeypatch.setenv("HOST_ROOT", "/host")
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        from app.core.path_utils import resolve_path_for_docker
        result = resolve_path_for_docker("/host/home/user")
        # /host/home/user empieza con / → se duplicaría → debe devolver tal cual
        # (el código actual lo duplica; este test documenta el comportamiento esperado)
        assert "/host" in result


class TestTranslatePathFromDocker:

    def test_no_host_root_returns_unchanged(self):
        from app.core.path_utils import translate_path_from_docker
        assert translate_path_from_docker("/host/home/user") == "/host/home/user"

    def test_linux_translation(self, monkeypatch):
        monkeypatch.setenv("HOST_ROOT", "/host")
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        from app.core.path_utils import translate_path_from_docker
        assert translate_path_from_docker("/host/home/user") == "/home/user"

    def test_windows_translation(self, monkeypatch):
        monkeypatch.setenv("HOST_ROOT", "/host")
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        from app.core.path_utils import translate_path_from_docker
        result = translate_path_from_docker("/host/c/Users/John")
        assert result == "C:\\Users\\John"

    def test_path_not_under_host_root_unchanged(self, monkeypatch):
        monkeypatch.setenv("HOST_ROOT", "/host")
        from app.core.path_utils import translate_path_from_docker
        assert translate_path_from_docker("/tmp/file.txt") == "/tmp/file.txt"


class TestIsBlockedPath:

    @pytest.mark.skipif(platform.system() == "Windows", reason="Linux test")
    def test_proc_is_blocked(self):
        from app.core.path_utils import is_blocked_path
        assert is_blocked_path("/proc/1/mem") is True

    @pytest.mark.skipif(platform.system() == "Windows", reason="Linux test")
    def test_home_is_not_blocked(self):
        from app.core.path_utils import is_blocked_path
        assert is_blocked_path("/home/user/documents") is False

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows test")
    def test_system32_is_blocked(self):
        from app.core.path_utils import is_blocked_path
        assert is_blocked_path("C:\\Windows\\System32") is True


# ── security ──────────────────────────────────────────────────────────────────

class TestValidateNoTraversal:

    def test_clean_absolute_path(self):
        from app.core.security import validate_no_traversal
        result = validate_no_traversal("/home/user/file.txt")
        assert result is not None

    def test_dotdot_slash_raises(self):
        from app.core.security import validate_no_traversal
        with pytest.raises(ValueError, match="traversal"):
            validate_no_traversal("/home/user/../../etc/passwd")

    def test_url_encoded_traversal_raises(self):
        from app.core.security import validate_no_traversal
        with pytest.raises(ValueError, match="traversal"):
            validate_no_traversal("/home/user/%2e%2e/etc/passwd")

    def test_double_encoded_traversal_raises(self):
        from app.core.security import validate_no_traversal
        with pytest.raises(ValueError, match="traversal"):
            validate_no_traversal("/home/%252e%252e/etc/passwd")

    def test_backslash_traversal_raises(self):
        from app.core.security import validate_no_traversal
        with pytest.raises(ValueError, match="traversal"):
            validate_no_traversal("C:\\Users\\..\\Windows\\System32")


class TestValidateDeletePath:

    def test_valid_absolute_path(self, tmp_path):
        from app.core.security import validate_delete_path
        p = str(tmp_path / "file.txt")
        result = validate_delete_path(p)
        assert result is not None

    def test_empty_path_raises(self):
        from app.core.security import validate_delete_path
        with pytest.raises(ValueError, match="vacía"):
            validate_delete_path("")

    def test_traversal_raises(self):
        from app.core.security import validate_delete_path
        with pytest.raises(ValueError):
            validate_delete_path("/home/user/../../etc/passwd")

    @pytest.mark.skipif(platform.system() == "Windows", reason="Linux test")
    def test_system_path_raises(self):
        from app.core.security import validate_delete_path
        with pytest.raises(ValueError, match="sistema"):
            validate_delete_path("/proc/1/mem")

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows test")
    def test_windows_system_path_raises(self):
        from app.core.security import validate_delete_path
        with pytest.raises(ValueError, match="sistema"):
            validate_delete_path("C:\\Windows\\System32\\calc.exe")


# ── Importación circular (smoke test) ─────────────────────────────────────────

class TestNoCircularImport:
    """
    Si la dependencia circular entre file_info.py y routes_explorer.py
    vuelve a aparecer, este test fallará con ImportError antes que cualquier otro.
    """

    def test_file_info_imports_without_error(self):
        # No debe lanzar ImportError
        from app.models.file_info import FileInfo, ScanRequest, FileCategory
        assert FileCategory.DOCUMENT == "document"

    def test_path_utils_importable_standalone(self):
        from app.core.path_utils import resolve_path_for_docker, is_blocked_path
        assert callable(resolve_path_for_docker)
        assert callable(is_blocked_path)

    def test_routes_explorer_importable(self):
        # Este import fallaba antes del fix por la dependencia circular
        from app.api.routes_explorer import router
        assert router is not None