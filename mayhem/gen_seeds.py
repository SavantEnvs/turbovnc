#!/usr/bin/env python3
"""Regenerates mayhem/rfb_server/testsuite: complete RFB client streams for the Xvnc harness."""
import os
import struct
import sys

HS = b"RFB 003.008\n"
NONE = b"\x01"
INIT = b"\x01"


def pixfmt(bpp, depth, big, tc, rmax, gmax, bmax, rs, gs, bs):
    return struct.pack(">BBBBHHHBBB3x", bpp, depth, big, tc, rmax, gmax, bmax, rs, gs, bs)


def set_pixel_format(*a):
    return b"\x00\x00\x00\x00" + pixfmt(*a)


def set_encodings(*encs):
    return struct.pack(">BxH", 2, len(encs)) + b"".join(struct.pack(">i", e) for e in encs)


def fb_request(inc, x, y, w, h):
    return struct.pack(">BBHHHH", 3, inc, x, y, w, h)


def key(down, sym):
    return struct.pack(">BBxxI", 4, down, sym)


def pointer(mask, x, y):
    return struct.pack(">BBHH", 5, mask, x, y)


def cut_text(s):
    return struct.pack(">B3xI", 6, len(s)) + s


def ws_frame(payload, opcode=2, mask=b"\x12\x34\x56\x78"):
    n = len(payload)
    hdr = bytes([0x80 | opcode, 0x80 | n]) if n < 126 else bytes([0x80 | opcode, 0x80 | 126]) + struct.pack(">H", n)
    return hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


WS_UPGRADE = (b"GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
              b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n"
              b"Sec-WebSocket-Protocol: binary\r\nOrigin: http://localhost\r\n\r\n")

RGB888 = (32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
RGB565 = (16, 16, 0, 1, 31, 63, 31, 11, 5, 0)
RGB233 = (8, 8, 0, 1, 7, 7, 3, 0, 3, 6)

seeds = {
    "raw": HS + NONE + INIT + set_encodings(0) + fb_request(0, 0, 0, 320, 240),
    "tight_jpeg": HS + NONE + INIT + set_pixel_format(*RGB888)
    + set_encodings(7, -23, -32, -224, -223, -258)
    + fb_request(0, 0, 0, 320, 240) + pointer(1, 40, 40) + pointer(0, 50, 60)
    + fb_request(1, 0, 0, 320, 240),
    "zrle_rgb565": HS + NONE + INIT + set_pixel_format(*RGB565) + set_encodings(16, 0, 1, 5)
    + fb_request(0, 0, 0, 320, 240) + key(1, 0x61) + key(0, 0x61) + fb_request(1, 0, 0, 320, 240),
    "hextile_8bpp": HS + NONE + INIT + set_pixel_format(*RGB233) + set_encodings(5, 2, 1, 0)
    + fb_request(0, 10, 10, 100, 100) + cut_text(b"clipboard text"),
    "input_events": HS + NONE + INIT + set_encodings(0, -239, -240, -224)
    + b"".join(key(1, 0xFF00 + i) + key(0, 0xFF00 + i) for i in range(0x50, 0x58))
    + b"".join(pointer(m, 10 * m, 20 * m) for m in (0, 1, 2, 4, 8, 16))
    + fb_request(0, 0, 0, 320, 240),
    "old_version": b"RFB 003.003\n" + INIT + set_encodings(0) + fb_request(0, 0, 0, 16, 16),
    "websocket_rfb": WS_UPGRADE + ws_frame(HS) + ws_frame(NONE + INIT)
    + ws_frame(set_encodings(7, 0) + fb_request(0, 0, 0, 320, 240) + key(1, 0x41)),
    "tight_security": HS + b"\x10" + struct.pack(">I", 1) + INIT + set_encodings(7, -32) + fb_request(0, 0, 0, 64, 64),
    "handshake_only": HS + NONE + INIT,
}

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "rfb_server", "testsuite")
os.makedirs(out, exist_ok=True)
for name, data in seeds.items():
    with open(os.path.join(out, name), "wb") as f:
        f.write(data)
