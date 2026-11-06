import base64
import hashlib
import json
import socket
import struct
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def exact(conn, length):
    data = b""
    while len(data) < length:
        part = conn.recv(length - len(data))
        if not part:
            raise EOFError("WebSocket closed early")
        data += part
    return data


def receive(conn):
    first, second = exact(conn, 2)
    length = second & 127
    if length == 126:
        length = struct.unpack("!H", exact(conn, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", exact(conn, 8))[0]
    mask = exact(conn, 4) if second & 128 else b""
    data = exact(conn, length)
    if mask:
        data = bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))
    return first & 15, data


def send(conn, value, opcode=1):
    data = json.dumps(value).encode() if opcode == 1 else value
    header = bytes([128 | opcode])
    header += bytes([len(data)]) if len(data) < 126 else bytes([126]) + struct.pack("!H", len(data))
    conn.sendall(header + data)


def gateway(listener, failures):
    try:
        for attempt in range(2):
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(5)
                request = b""
                while not request.endswith(b"\r\n\r\n"):
                    request += exact(conn, 1)
                headers = dict(line.split(": ", 1) for line in request.decode().split("\r\n")[1:] if ": " in line)
                accept = base64.b64encode(hashlib.sha1((headers["Sec-WebSocket-Key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
                conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + accept + "\r\n\r\n").encode())
                send(conn, {"op": 10, "d": {"heartbeat_interval": 100}})
                opcode, raw = receive(conn)
                auth = json.loads(raw)
                assert opcode == 1 and auth["op"] == (2 if attempt == 0 else 6), auth
                assert auth["d"]["token"] == "dummy-token"
                if attempt == 0:
                    send(conn, {"op": 0, "s": 42, "t": "READY", "d": {"session_id": "mock-session", "resume_gateway_url": "wss://gateway.discord.gg"}})
                    opcode, raw = receive(conn)
                    heartbeat = json.loads(raw)
                    assert opcode == 1 and heartbeat == {"op": 1, "d": 42}, heartbeat
                    send(conn, {"op": 11, "d": None})
                    send(conn, {"op": 7, "d": None})
                    opcode, raw = receive(conn)
                    assert opcode == 8 and struct.unpack("!H", raw[:2])[0] == 4000
                    send(conn, raw, 8)
                else:
                    assert auth["d"]["session_id"] == "mock-session" and auth["d"]["seq"] == 42
                    send(conn, struct.pack("!H", 4004), 8)
                    receive(conn)
    except Exception as error:
        failures.append(error)


class Rest(BaseHTTPRequestHandler):
    failures = []
    seen = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body == {"name": "ping", "description": "Test command", "type": 1}
            index = int(self.path.removeprefix("/"))
            status = [200, 401, 403, 429, 503][index]
            self.seen.append(status)
            data = b'{"retry_after":1.25}' if status == 429 else b'{}'
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)
        except Exception as error:
            self.failures.append(error)
            self.send_error(500)


def main():
    executable = Path(sys.argv[1]).resolve()
    failures = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(10)
        rest = ThreadingHTTPServer(("127.0.0.1", 0), Rest)
        gateway_thread = threading.Thread(target=gateway, args=(listener, failures), daemon=True)
        rest_thread = threading.Thread(target=rest.serve_forever, daemon=True)
        gateway_thread.start()
        rest_thread.start()
        try:
            subprocess.run([str(executable), "ws://127.0.0.1:" + str(listener.getsockname()[1]), "http://127.0.0.1:" + str(rest.server_port) + "/"], check=True, timeout=20)
            gateway_thread.join(6)
            assert not gateway_thread.is_alive(), "Gateway mock did not finish"
            assert not failures, failures
            assert not Rest.failures, Rest.failures
            assert Rest.seen == [200, 401, 403, 429, 503], Rest.seen
        finally:
            rest.shutdown()
            rest.server_close()
    print("Native mock checks passed: Identify, READY, heartbeat/ACK, reconnect, Resume, fatal close, REST 200/401/403/429/503")


if __name__ == "__main__":
    main()
