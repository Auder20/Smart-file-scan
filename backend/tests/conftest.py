"""
tests/conftest.py
-----------------
Configuración global de pytest y fixtures compartidas.
"""
import os
import sys
import tempfile
import pytest

# Asegurar que el directorio backend esté en el path de Python
# para que los imports de `app.*` funcionen sin instalar el paquete
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """
    Aísla las variables de entorno relevantes para cada test.
    Sin esto, HOST_ROOT de la máquina del CI podría afectar los resultados.
    """
    monkeypatch.delenv("HOST_ROOT",    raising=False)
    monkeypatch.delenv("HOST_ROOT_RW", raising=False)
    yield


@pytest.fixture
def temp_dir_with_files():
    """
    Devuelve un directorio temporal con una estructura de archivos de prueba:
        /root/
          docs/
            report.pdf
            notes.txt
          images/
            photo.jpg
          code/
            script.py
          duplicate1.txt   ← mismo contenido que duplicate2.txt
          duplicate2.txt
    """
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "docs"))
        os.makedirs(os.path.join(root, "images"))
        os.makedirs(os.path.join(root, "code"))

        files = {
            "docs/report.pdf":   b"PDF content here",
            "docs/notes.txt":    b"Some notes",
            "images/photo.jpg":  b"JPEG binary data",
            "code/script.py":    b"print('hello')",
            "duplicate1.txt":    b"I am a duplicate",
            "duplicate2.txt":    b"I am a duplicate",  # mismo contenido
        }
        for rel_path, content in files.items():
            full = os.path.join(root, rel_path)
            with open(full, "wb") as f:
                f.write(content)

        yield root


@pytest.fixture
def empty_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d