import struct, zlib, os, sys

def chunk(name, data):
    c = zlib.crc32(name + data) & 0xffffffff
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", c)

out = sys.argv[1] if len(sys.argv) > 1 else "icon.png"
w = h = 256
raw = b""
for y in range(h):
    raw += b"\x00"
    for x in range(w):
        cx, cy = x - 128, y - 128
        r = (cx*cx + cy*cy) ** 0.5
        if r < 100:   raw += bytes([79, 142, 247, 255])
        elif r < 110: raw += bytes([30, 30, 50, 255])
        else:         raw += bytes([17, 17, 20, 255])
compressed = zlib.compress(raw, 9)
ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
        chunk(b"IDAT", compressed) + chunk(b"IEND", b""))
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
open(out, "wb").write(data)
print("Icono OK:", out)