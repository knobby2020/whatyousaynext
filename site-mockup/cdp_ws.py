"""Minimal RFC 6455 client, standing in for websocket-client when it is absent.

Chrome's DevTools endpoint is plain ws:// on loopback, so this only needs the
handshake, masked client frames, and reassembly of large server frames (a
captureScreenshot reply is a multi-megabyte base64 payload). The public surface
is deliberately limited to what responsive_qa.py and section_qa.py already call:
create_connection(url, origin=..., timeout=...), .send(), .recv(), .close().
"""

import base64
import os
import socket
import struct
from urllib.parse import urlparse

TEXT, BINARY, CLOSE, PING, PONG = 0x1, 0x2, 0x8, 0x9, 0xA


class WebSocket:
    def __init__(self, sock):
        self._sock = sock
        self._buf = b""

    def _read(self, count):
        while len(self._buf) < count:
            chunk = self._sock.recv(max(65536, count - len(self._buf)))
            if not chunk:
                raise ConnectionError("websocket closed by peer")
            self._buf += chunk
        out, self._buf = self._buf[:count], self._buf[count:]
        return out

    def _read_frame(self):
        head = self._read(2)
        fin = bool(head[0] & 0x80)
        opcode = head[0] & 0x0F
        masked = bool(head[1] & 0x80)
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read(8))[0]
        mask = self._read(4) if masked else None
        payload = self._read(length) if length else b""
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return fin, opcode, payload

    def send(self, data, opcode=TEXT):
        payload = data.encode() if isinstance(data, str) else data
        header = bytearray([0x80 | opcode])
        size = len(payload)
        if size < 126:
            header.append(0x80 | size)
        elif size < 1 << 16:
            header.append(0x80 | 126)
            header += struct.pack(">H", size)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", size)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def recv(self):
        while True:
            fin, opcode, payload = self._read_frame()
            while not fin:
                fin, _continuation, extra = self._read_frame()
                payload += extra
            if opcode == PING:
                self.send(payload, opcode=PONG)
                continue
            if opcode == CLOSE:
                raise ConnectionError("websocket closed by peer")
            if opcode in (TEXT, BINARY):
                return payload.decode("utf-8", "replace")

    def close(self):
        try:
            self.send(b"", opcode=CLOSE)
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass


def create_connection(url, origin=None, timeout=None, **_ignored):
    parts = urlparse(url)
    port = parts.port or 80
    sock = socket.create_connection((parts.hostname, port), timeout=timeout)
    sock.settimeout(timeout)
    path = parts.path + (("?" + parts.query) if parts.query else "")
    lines = [
        f"GET {path or '/'} HTTP/1.1",
        f"Host: {parts.hostname}:{port}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}",
        "Sec-WebSocket-Version: 13",
    ]
    if origin:
        lines.append(f"Origin: {origin}")
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())

    header = b""
    while b"\r\n\r\n" not in header:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("websocket handshake truncated")
        header += byte
    status = header.split(b"\r\n", 1)[0].decode("latin-1")
    if "101" not in status:
        raise ConnectionError(f"websocket handshake refused: {status}")
    return WebSocket(sock)
