import socket
import time
import struct
import json
import logging
import random
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

UDP_PORT = 50005
WEB_PORT = 8080
BUFFER_SIZE = 4096

# Typy pakietów protokołu UDP
TYPE_AUDIO = 0x01
TYPE_PING = 0x02
TYPE_PONG = 0x03
TYPE_HEARTBEAT = 0x04
TYPE_GET_ROOMS = 0x05
TYPE_ROOM_LIST = 0x06
TYPE_CREATE_ROOM = 0x07
TYPE_DELETE_ROOM = 0x08
TYPE_ROOM_DELETED = 0x09
TYPE_LEAVE_ROOM = 0x0A
TYPE_ROOM_MEMBERS = 0x0B

# Bufor ostatnich logów do wyświetlenia w panelu WWW
web_logs = []
MAX_LOG_ENTRIES = 50

def log_event(msg: str):
    timestamp = time.strftime('%H:%M:%S')
    entry = f"[{timestamp}] {msg}"
    logging.info(msg)
    web_logs.append(entry)
    if len(web_logs) > MAX_LOG_ENTRIES:
        web_logs.pop(0)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("server_activity.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

# rooms = {
#    room_id: {
#        "name": str,
#        "has_password": bool,
#        "admin_ip": str,
#        "clients": { client_ip: { "last_seen": float, "nickname": str } }
#    }
# }
rooms = {}

server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_sock.bind(("0.0.0.0", UDP_PORT))
server_sock.settimeout(1.0)  # Umożliwia natychmiastowe zatrzymanie skrótem Ctrl+C

def java_hash_code(s: str) -> int:
    h = 0
    for c in s:
        h = (31 * h + ord(c)) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    return h

def generate_unique_guest_nick(room_id: int) -> str:
    existing_nicks = set()
    if room_id in rooms:
        existing_nicks = {c["nickname"] for c in rooms[room_id]["clients"].values()}
    while True:
        num = random.randint(10000, 99999)
        nick = f"guest{num}"
        if nick not in existing_nicks:
            return nick

def broadcast_room_members(room_id: int):
    if room_id not in rooms:
        return
    room = rooms[room_id]
    members = []
    for ip, data in room["clients"].items():
        is_admin = (ip == room["admin_ip"])
        members.append({
            "nick": data["nickname"],
            "isAdmin": is_admin
        })
    
    payload = json.dumps(members).encode('utf-8')
    packet = bytes([TYPE_ROOM_MEMBERS]) + payload
    for client_ip in room["clients"].keys():
        try:
            server_sock.sendto(packet, (client_ip, UDP_PORT))
        except Exception:
            pass

def cleanup_inactive_clients():
    now = time.time()
    for room_id in list(rooms.keys()):
        room = rooms[room_id]
        inactive_ips = [ip for ip, data in room["clients"].items() if now - data["last_seen"] > 15]
        members_changed = False
        for ip in inactive_ips:
            nick = room["clients"][ip]["nickname"]
            del room["clients"][ip]
            log_event(f"[TIMEOUT] {nick} ({ip}) usunięty z pokoju '{room['name']}'")
            members_changed = True
        
        if room["clients"] and room["admin_ip"] not in room["clients"]:
            new_admin_ip = next(iter(room["clients"].keys()))
            room["admin_ip"] = new_admin_ip
            log_event(f"[NOWY ADMIN] Nowym adminem pokoju '{room['name']}' został {room['clients'][new_admin_ip]['nickname']} ({new_admin_ip})")
            members_changed = True

        if not room["clients"]:
            log_event(f"[POKÓJ USUNIĘTY] Pokój '{room['name']}' jest pusty i został usunięty.")
            del rooms[room_id]
        elif members_changed:
            broadcast_room_members(room_id)

# ==========================================
# SERWER WEBOWY HTTP (PANEL ZARZĄDZANIA)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Walkie-Talkie Server Dashboard</title>
    <style>
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: #0f172a; color: #e2e8f0; margin: 0; padding: 24px; }
        .container { max-width: 1100px; margin: 0 auto; }
        header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 24px; }
        h1 { margin: 0; font-size: 22px; color: #f8fafc; }
        .badge { background: #22c55e; color: #052e16; padding: 4px 10px; border-radius: 999px; font-weight: bold; font-size: 12px; }
        .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 24px; }
        .card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
        .card h2 { margin-top: 0; font-size: 16px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
        .room-item { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
        .room-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .room-title { font-size: 18px; font-weight: bold; color: #38bdf8; }
        .btn-danger { background: #ef4444; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 12px; }
        .btn-danger:hover { background: #dc2626; }
        .btn-kick { background: #eab308; color: #422006; border: none; padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold; }
        .btn-kick:hover { background: #ca8a04; }
        table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
        th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #64748b; }
        .log-box { background: #020617; border-radius: 8px; padding: 12px; height: 380px; overflow-y: auto; font-family: monospace; font-size: 12px; color: #a5f3fc; border: 1px solid #1e293b; }
        .log-entry { margin-bottom: 4px; }
        .empty-state { text-align: center; color: #64748b; padding: 40px 0; }
    </style>
    <script>
        async function updateDashboard() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                renderRooms(data.rooms);
                renderLogs(data.logs);
            } catch (e) {
                console.error(e);
            }
        }

        function renderRooms(rooms) {
            const container = document.getElementById('rooms-container');
            if (Object.keys(rooms).length === 0) {
                container.innerHTML = '<div class="empty-state">Brak aktywnych pokojów na serwerze.</div>';
                return;
            }

            let html = '';
            for (const [rId, room] of Object.entries(rooms)) {
                const lockIcon = room.has_password ? '🔒 Hasło' : '🌐 Publiczny';
                html += `
                <div class="room-item">
                    <div class="room-header">
                        <div>
                            <span class="room-title">${escapeHtml(room.name)}</span>
                            <span style="font-size:12px; color:#94a3b8; margin-left:8px;">(${lockIcon} • ${Object.keys(room.clients).length} online)</span>
                        </div>
                        <button class="btn-danger" onclick="deleteRoom(${rId})">Usuń pokój</button>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Użytkownik</th>
                                <th>IP</th>
                                <th>Rola</th>
                                <th>Akcja</th>
                            </tr>
                        </thead>
                        <tbody>`;
                for (const [ip, c] of Object.entries(room.clients)) {
                    const isAdmin = (ip === room.admin_ip);
                    const roleBadge = isAdmin ? '<span style="color:#f59e0b; font-weight:bold;">👑 Admin</span>' : '<span style="color:#94a3b8;">👤 Uczestnik</span>';
                    html += `
                            <tr>
                                <td><b>${escapeHtml(c.nickname)}</b></td>
                                <td><code>${ip}</code></td>
                                <td>${roleBadge}</td>
                                <td><button class="btn-kick" onclick="kickUser(${rId}, '${ip}')">Wyrzuć (Kick)</button></td>
                            </tr>`;
                }
                html += `
                        </tbody>
                    </table>
                </div>`;
            }
            container.innerHTML = html;
        }

        function renderLogs(logs) {
            const box = document.getElementById('log-box');
            box.innerHTML = logs.map(l => `<div class="log-entry">${escapeHtml(l)}</div>`).join('');
            box.scrollTop = box.scrollHeight;
        }

        function escapeHtml(str) {
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        async function deleteRoom(roomId) {
            if (!confirm('Czy na pewno chcesz usunąć ten pokój? Wszyscy uczestnicy zostaną rozłączeni.')) return;
            await fetch(`/api/delete_room?room_id=${roomId}`, { method: 'POST' });
            updateDashboard();
        }

        async function kickUser(roomId, ip) {
            if (!confirm(`Czy na pewno chcesz wyrzucić użytkownika ${ip}?`)) return;
            await fetch(`/api/kick_user?room_id=${roomId}&ip=${encodeURIComponent(ip)}`, { method: 'POST' });
            updateDashboard();
        }

        setInterval(updateDashboard, 2000);
        window.onload = updateDashboard;
    </script>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Walkie-Talkie Server Dashboard</h1>
                <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">Port UDP: <b>50005</b> • Port WWW: <b>8080</b></div>
            </div>
            <span class="badge">● SERWER AKTYWNY</span>
        </header>

        <div class="grid">
            <div class="card">
                <h2>Aktywne Pokoje & Użytkownicy</h2>
                <div id="rooms-container">
                    <div class="empty-state">Wczytywanie...</div>
                </div>
            </div>

            <div class="card">
                <h2>Dziennik Zdarzeń (Live Logs)</h2>
                <div id="log-box" class="log-box"></div>
            </div>
        </div>
    </div>
</body>
</html>
"""

class WebAdminHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
        elif parsed.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "rooms": rooms,
                "logs": web_logs
            }
            self.wfile.write(json.dumps(data).encode('utf-8'))
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/api/delete_room":
            room_id = int(params.get("room_id", [0])[0])
            if room_id in rooms:
                room_name = rooms[room_id]["name"]
                deleted_packet = bytes([TYPE_ROOM_DELETED])
                for target_ip in rooms[room_id]["clients"].keys():
                    try:
                        server_sock.sendto(deleted_packet, (target_ip, UDP_PORT))
                    except Exception:
                        pass
                del rooms[room_id]
                log_event(f"[WEB ADMIN] Usunięto pokój '{room_name}' przez panel WWW.")
            self.send_response(200)
            self.end_headers()

        elif parsed.path == "/api/kick_user":
            room_id = int(params.get("room_id", [0])[0])
            ip = params.get("ip", [""])[0]
            if room_id in rooms and ip in rooms[room_id]["clients"]:
                nick = rooms[room_id]["clients"][ip]["nickname"]
                del rooms[room_id]["clients"][ip]
                
                try:
                    server_sock.sendto(bytes([TYPE_ROOM_DELETED]), (ip, UDP_PORT))
                except Exception:
                    pass

                log_event(f"[WEB ADMIN] Wyrzucono {nick} ({ip}) z pokoju '{rooms[room_id]['name']}' przez panel WWW.")
                
                if rooms[room_id]["clients"]:
                    if rooms[room_id]["admin_ip"] == ip:
                        new_admin_ip = next(iter(rooms[room_id]["clients"].keys()))
                        rooms[room_id]["admin_ip"] = new_admin_ip
                    broadcast_room_members(room_id)
                else:
                    del rooms[room_id]

            self.send_response(200)
            self.end_headers()
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass

def start_web_server():
    httpd = HTTPServer(("0.0.0.0", WEB_PORT), WebAdminHandler)
    httpd.serve_forever()

web_thread = threading.Thread(target=start_web_server, daemon=True)
web_thread.start()

print(f"\n==================================================", flush=True)
print(f"[*] Serwer Walkie-Talkie (UDP): port {UDP_PORT}", flush=True)
print(f"[*] Panel WWW Administracyjny: http://localhost:{WEB_PORT}", flush=True)
print(f"[*] Oczekiwanie na zapytania...", flush=True)
print(f"==================================================\n", flush=True)

# ==========================================
# PĘTLA GŁÓWNA UDP Z OBSŁUGĄ CTRL+C
# ==========================================
try:
    while True:
        try:
            data, addr = server_sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            cleanup_inactive_clients()
            continue

        if len(data) < 1:
            continue

        msg_type = data[0]
        now = time.time()
        client_ip = addr[0]
        cleanup_inactive_clients()

        # 1. POBIERANIE LISTY POKOI
        if msg_type == TYPE_GET_ROOMS:
            room_list = []
            for r_id, r_info in rooms.items():
                room_list.append({
                    "id": r_id,
                    "name": r_info["name"],
                    "has_password": r_info["has_password"],
                    "users": len(r_info["clients"])
                })
            payload = json.dumps(room_list).encode('utf-8')
            resp = bytes([TYPE_ROOM_LIST]) + payload
            server_sock.sendto(resp, addr)
            log_event(f"[LISTA POKOI] Wysłano listę ({len(room_list)} aktywnych) do {client_ip}")

        # 2. TWORZENIE POKOJU
        elif msg_type == TYPE_CREATE_ROOM:
            has_pwd = bool(data[1])
            nick_len = struct.unpack("!H", data[2:4])[0]
            nick = data[4:4+nick_len].decode('utf-8', errors='ignore').strip()
            room_name = data[4+nick_len:].decode('utf-8', errors='ignore').strip()
            room_id = java_hash_code(room_name)

            if not nick:
                nick = generate_unique_guest_nick(room_id)

            rooms[room_id] = {
                "name": room_name,
                "has_password": has_pwd,
                "admin_ip": client_ip,
                "clients": {client_ip: {"last_seen": now, "nickname": nick}}
            }
            log_event(f"[NOWY POKÓJ] '{room_name}' utworzony przez {nick} ({client_ip}) [ADMIN]")
            broadcast_room_members(room_id)

        # 3. HEARTBEAT
        elif msg_type == TYPE_HEARTBEAT and len(data) >= 5:
            room_id = struct.unpack("!i", data[1:5])[0]
            nick = data[5:].decode('utf-8', errors='ignore').strip() if len(data) > 5 else ""

            if room_id in rooms:
                is_new_user = client_ip not in rooms[room_id]["clients"]
                if not nick:
                    nick = generate_unique_guest_nick(room_id)

                rooms[room_id]["clients"][client_ip] = {"last_seen": now, "nickname": nick}
                
                if is_new_user:
                    log_event(f"[DOŁĄCZONO] {nick} ({client_ip}) wszedł do pokoju '{rooms[room_id]['name']}'")
                    broadcast_room_members(room_id)

        # 4. OPUSZCZENIE POKOJU
        elif msg_type == TYPE_LEAVE_ROOM and len(data) >= 5:
            room_id = struct.unpack("!i", data[1:5])[0]
            if room_id in rooms and client_ip in rooms[room_id]["clients"]:
                nick = rooms[room_id]["clients"][client_ip]["nickname"]
                del rooms[room_id]["clients"][client_ip]
                log_event(f"[OPUSZCZONO] {nick} ({client_ip}) opuścił pokój '{rooms[room_id]['name']}'")

                if room_id in rooms:
                    if rooms[room_id]["clients"]:
                        if rooms[room_id]["admin_ip"] == client_ip:
                            new_admin_ip = next(iter(rooms[room_id]["clients"].keys()))
                            rooms[room_id]["admin_ip"] = new_admin_ip
                            log_event(f"[NOWY ADMIN] Nowym adminem pokoju '{rooms[room_id]['name']}' został {rooms[room_id]['clients'][new_admin_ip]['nickname']}")
                        broadcast_room_members(room_id)
                    else:
                        log_event(f"[POKÓJ USUNIĘTY] Pokój '{rooms[room_id]['name']}' został usunięty.")
                        del rooms[room_id]

        # 5. AUDIO RELAY
        elif msg_type == TYPE_AUDIO and len(data) >= 5:
            room_id = struct.unpack("!i", data[1:5])[0]
            if room_id in rooms:
                if client_ip in rooms[room_id]["clients"]:
                    rooms[room_id]["clients"][client_ip]["last_seen"] = now
                for target_ip in rooms[room_id]["clients"].keys():
                    if target_ip != client_ip:
                        server_sock.sendto(data, (target_ip, UDP_PORT))

        # 6. USUWANIE POKOJU PRZEZ ADMINA Z TELEFONU
        elif msg_type == TYPE_DELETE_ROOM and len(data) >= 5:
            room_id = struct.unpack("!i", data[1:5])[0]
            if room_id in rooms:
                if rooms[room_id]["admin_ip"] == client_ip or len(rooms[room_id]["clients"]) <= 1:
                    room_name = rooms[room_id]["name"]
                    log_event(f"[USUNIĘTO POKÓJ] Pokój '{room_name}' usunięty przez admina ({client_ip}).")
                    deleted_packet = bytes([TYPE_ROOM_DELETED])
                    for target_ip in list(rooms[room_id]["clients"].keys()):
                        try:
                            server_sock.sendto(deleted_packet, (target_ip, UDP_PORT))
                            server_sock.sendto(deleted_packet, (target_ip, UDP_PORT))
                        except Exception:
                            pass
                    del rooms[room_id]

except KeyboardInterrupt:
    print("\n[!] Zatrzymywanie serwera Walkie-Talkie...")
finally:
    server_sock.close()
    print("[*] Serwer został pomyślnie wyłączony.")