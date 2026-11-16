#!/usr/bin/env python3
"""Known-answer test for Xvnc: runs the server on a loopback socket (-inetd), speaks RFB to it and
checks the handshake, ServerInit and the encoded framebuffer bytes against fixed expectations.
Usage: kat.py <path-to-Xvnc>. Prints one `PASS|FAIL <name>` line per check; exit 1 if any failed."""
import socket
import struct
import subprocess
import sys

XVNC = sys.argv[1]
W, H, NAME = 320, 240, b"turbovnc-kat"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f": {detail}"), flush=True)


def recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        d = s.recv(n - len(buf))
        if not d:
            raise EOFError(f"connection closed after {len(buf)} of {n} bytes")
        buf += d
    return buf


class Session:
    def __init__(self):
        lst = socket.socket()
        lst.bind(("127.0.0.1", 0))
        lst.listen(1)
        self.sock = socket.create_connection(lst.getsockname())
        srv, _ = lst.accept()
        lst.close()
        self.proc = subprocess.Popen(
            [XVNC, "-inetd", "-nolock", "-nolisten", "tcp", "-nolisten", "local",
             "-securitytypes", "none", "-geometry", f"{W}x{H}", "-depth", "24",
             "-desktop", NAME.decode(), "-ac"],
            stdin=srv, stdout=srv, stderr=subprocess.PIPE)
        srv.close()
        self.sock.settimeout(30)

    def close(self):
        self.sock.close()
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.proc.stderr.close()


def handshake(s):
    s.sock.settimeout(30)
    check("version banner", recv_exact(s.sock, 12) == b"RFB 003.008\n", "bad banner")
    s.sock.sendall(b"RFB 003.008\n")
    (nsec,) = recv_exact(s.sock, 1)
    sec = recv_exact(s.sock, nsec)
    check("security types offer None", 1 in sec, repr(sec))
    s.sock.sendall(b"\x01")
    res = recv_exact(s.sock, 4)
    check("security result OK", res == b"\x00\x00\x00\x00", repr(res))
    s.sock.sendall(b"\x01")
    w, h = struct.unpack(">HH", recv_exact(s.sock, 4))
    pf = recv_exact(s.sock, 16)
    (nlen,) = struct.unpack(">I", recv_exact(s.sock, 4))
    name = recv_exact(s.sock, nlen)
    check("ServerInit geometry", (w, h) == (W, H), f"{w}x{h}")
    check("ServerInit pixel format 32bpp/depth24", pf[0] == 32 and pf[1] == 24, repr(pf))
    check("ServerInit desktop name", name == NAME, repr(name))


def set_format(sock, bpp, depth, rmax, gmax, bmax, rs, gs, bs):
    sock.sendall(b"\x00\x00\x00\x00" + struct.pack(">BBBBHHHBBB3x", bpp, depth, 0, 1, rmax, gmax, bmax, rs, gs, bs))


def set_encodings(sock, *encs):
    sock.sendall(struct.pack(">BxH", 2, len(encs)) + b"".join(struct.pack(">i", e) for e in encs))


def update(sock):
    sock.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, W, H))
    hdr = recv_exact(sock, 4)
    assert hdr[0] == 0, f"message type {hdr[0]}"
    (nrects,) = struct.unpack(">H", hdr[2:])
    return nrects, recv_exact(sock, 12)


def main():
    s = Session()
    try:
        handshake(s)
        sock = s.sock
        set_format(sock, 16, 16, 31, 63, 31, 11, 5, 0)
        set_encodings(sock, 0)
        nrects, rect = update(sock)
        x, y, w, h, enc = struct.unpack(">HHHHi", rect)
        check("Raw update rect", (nrects, x, y, w, h, enc) == (1, 0, 0, W, H, 0), repr((nrects, x, y, w, h, enc)))
        pix = recv_exact(sock, W * H * 2)
        check("Raw RGB565 payload is a uniform black root window", pix == b"\x00" * (W * H * 2), repr(pix[:16]))

        set_encodings(sock, 5)
        nrects, rect = update(sock)
        x, y, w, h, enc = struct.unpack(">HHHHi", rect)
        check("Hextile update rect", (nrects, x, y, w, h, enc) == (1, 0, 0, W, H, 5), repr((nrects, x, y, w, h, enc)))
        tiles = ((W + 15) // 16) * ((H + 15) // 16)
        body = recv_exact(sock, 1 + 2 + (tiles - 1))
        check("Hextile body: one background tile then empty tiles",
              body == b"\x02" + b"\x00\x00" + b"\x00" * (tiles - 1), repr(body[:8]))
    except (EOFError, OSError, AssertionError) as e:
        check("session", False, repr(e))
    finally:
        s.close()
    passed = results.count(True)
    failed = results.count(False)
    print(f"KAT passed={passed} failed={failed}")
    return 0 if failed == 0 and passed > 0 else 1


sys.exit(main())
