#!/usr/bin/env python3
"""
Script de diagnóstico: simula exactamente lo que hace el frontend JavaFX.
Ejecutar desde la carpeta del proyecto con el backend corriendo:
  python3 test_scan.py
"""
import requests
import json
import time
import sys

BASE = "http://localhost:8000"

# 1. Health check
print("1. Verificando backend...")
try:
    r = requests.get(f"{BASE}/api/health", timeout=5)
    print(f"   ✓ Backend OK: {r.json()}")
except Exception as e:
    print(f"   ✗ Backend NO responde: {e}")
    sys.exit(1)

# 2. Validate path
test_path = sys.argv[1] if len(sys.argv) > 1 else "."
print(f"\n2. Validando ruta: {test_path}")
try:
    import urllib.parse
    encoded = urllib.parse.quote(test_path)
    r = requests.get(f"{BASE}/api/explorer/validate-path?path={encoded}", timeout=5)
    print(f"   Status: {r.status_code}")
    print(f"   Body: {r.text}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# 3. Start scan
print(f"\n3. Iniciando scan de: {test_path}")
try:
    payload = {"path": test_path, "max_depth": 5, "include_hidden": False}
    r = requests.post(f"{BASE}/api/scan", json=payload, timeout=10)
    print(f"   Status HTTP: {r.status_code}")
    print(f"   Body: {r.text}")
    if r.status_code != 202:
        print("   ✗ El backend rechazó el scan!")
        sys.exit(1)
    scan_id = r.json()["scan_id"]
    print(f"   ✓ scan_id: {scan_id}")
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

# 4. Poll progress 10 veces
print(f"\n4. Polling progreso cada 0.5s (10 intentos)...")
for i in range(10):
    time.sleep(0.5)
    try:
        r = requests.get(f"{BASE}/api/scan/{scan_id}/progress", timeout=5)
        if r.status_code == 200:
            p = r.json()
            print(f"   [{i+1:2d}] status={p.get('status')} progress={p.get('progress')}% "
                  f"files={p.get('files_found')} msg={p.get('message','')[:60]}")
            if p.get("status") in ("completed", "failed"):
                print("   ✓ Scan terminó!")
                break
        else:
            print(f"   [{i+1:2d}] HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"   [{i+1:2d}] Error: {e}")

print("\nDiagnóstico completo.")