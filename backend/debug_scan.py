#!/usr/bin/env python3
"""
Ejecutar desde backend/ con el venv activado:
  python debug_scan.py /ruta/a/escanear
  
Muestra exactamente qué hace scan_directory y _run_scan paso a paso.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Simular variables de entorno de modo local
os.environ.setdefault("HOST_ROOT", "")
os.environ.setdefault("DB_PATH", "/tmp/sfo_debug.db")

from app.core.path_utils import normalize_scan_path
from app.core.scanner import scan_directory
from app.models.file_info import ScanRequest, FileInfo

path = sys.argv[1] if len(sys.argv) > 1 else "."
print(f"=== DEBUG SCAN ===")
print(f"Ruta original : {path}")

resolved = normalize_scan_path(path)
print(f"Ruta resuelta : {resolved}")
print(f"Existe        : {os.path.exists(resolved)}")
print(f"Es directorio : {os.path.isdir(resolved)}")
print()

# Test request
try:
    req = ScanRequest(path=path, max_depth=3)
    print(f"ScanRequest OK: path={req.path}")
except Exception as e:
    print(f"ScanRequest FALLO: {type(e).__name__}: {e}")
    sys.exit(1)

print()
print("Corriendo scan_directory...")
count = 0
events = 0
start = time.time()

try:
    for event in scan_directory(req):
        events += 1
        if isinstance(event, FileInfo):
            count += 1
            if count <= 3:
                print(f"  FileInfo: {event.name} ({event.size} bytes)")
            elif count == 4:
                print(f"  ... (mostrando solo primeros 3)")
        elif isinstance(event, dict):
            etype = event.get("type", "?")
            print(f"  Dict event: type={etype} count={event.get('count','?')} "
                  f"msg={event.get('message','')[:50]}")
        
        if time.time() - start > 10:
            print("  TIMEOUT: 10 segundos sin terminar")
            break
except Exception as e:
    print(f"  EXCEPCION en scan_directory: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

elapsed = time.time() - start
print()
print(f"=== RESULTADO ===")
print(f"Archivos encontrados : {count}")
print(f"Eventos totales      : {events}")
print(f"Tiempo               : {elapsed:.2f}s")

if count == 0 and events == 0:
    print()
    print(">>> PROBLEMA: el scanner no generó NINGÚN evento.")
    print(">>> Causas posibles:")
    print("    1. La ruta no existe o no tiene permisos")
    print("    2. os.scandir() falla silenciosamente")
    print("    3. Todos los archivos son ocultos y include_hidden=False")