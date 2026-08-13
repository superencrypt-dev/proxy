# Spesifikasi Desain: Universal Proxy Scraper, Health Checker & Management TUI

**Tanggal:** 2026-08-14  
**Status:** Approved  
**Bahasa/Stack:** Python 3.10+ (asyncio, rich, questionary, aiohttp, pyyaml) + sing-box core  
**UI/UX:** Terminal User Interface (TUI) berbasis Clean Text (Tanpa Emoji)  

---

## 1. Ikhtisar Sistem (System Overview)

Aplikasi ini adalah tool komprehensif berbasis TUI (Terminal User Interface) untuk mengumpulkan (*scrape*), memvalidasi kelayakan koneksi (*health check* riil), menyaring node aktif (*filter alive*), membuang node mati (*purge dead*), mengelompokkan metadata GeoIP, mengekspor ke berbagai format klien proxy, serta menjalankan proxy lokal (SOCKS5/HTTP) di localhost.

### Prinsip Desain & Batasan
1. **Dukungan Protokol Lengkap**: VMess, VLESS (termasuk Reality & Vision), Trojan, Shadowsocks (AEAD/SIP002), TUIC (v5), Hysteria 1 & Hysteria 2.
2. **Validasi Koneksi Riil (Real Handshake & HTTP 204)**: Tidak hanya mengecek port/ping TCP, melainkan menjalankan micro-instance backend `sing-box` untuk melakukan HTTP GET request riil ke endpoint uji (`http://cp.cloudflare.com/generate_204`).
3. **Pembersihan Otomatis**: Node yang gagal melakukan handshake atau berstatus mati langsung disaring keluar dari database aktif.
4. **Antarmuka Bersih Bebas Emoji**: Seluruh tampilan menu, tabel, log, dan penamaan node menggunakan teks ASCII/Rich profesional dan kode ISO negara 2 huruf (contoh: `[ID]`, `[SG]`, `[US]`) tanpa karakter emoji.
5. **Skalabilitas & Konkurensi**: Memanfaatkan `asyncio` pool dengan concurrency terkontrol (default 25-50 workers) untuk menguji ratusan/ribuan node dalam waktu singkat.

---

## 2. Struktur Direktori Proyek

```text
/root/proyek/proxy/
├── main.py                     # Entry point TUI interaktif
├── requirements.txt            # Dependensi Python
├── config.json                 # Konfigurasi aplikasi default
├── core/
│   ├── __init__.py
│   ├── binary_manager.py       # Auto-download & deteksi arsitektur binary sing-box
│   ├── models.py               # Data class & struktur data node/hasil cek
│   ├── parsers/                # Parser URI link ke format universal & sing-box outbound
│   │   ├── __init__.py
│   │   ├── base.py             # Base abstract parser
│   │   ├── vmess.py
│   │   ├── vless.py
│   │   ├── trojan.py
│   │   ├── shadowsocks.py
│   │   ├── tuic.py
│   │   └── hysteria.py
│   ├── collector.py            # Aggregator sumber publik, custom URL, file, dan paste
│   ├── checker.py              # Engine pengujian paralel via sing-box micro instances
│   ├── geoip.py                # Resolver IP -> Negara ISO & Nama Negara (Offline cache / fast API)
│   ├── exporter.py             # Generator Raw Links, Base64 Sub, Clash YAML, Sing-box JSON
│   ├── runner.py               # Local SOCKS5 / HTTP proxy daemon manager
│   └── scheduler.py            # Background periodic auto-check runner
├── tui/
│   ├── __init__.py
│   ├── menu.py                 # Menu interaktif Questionary (panah atas/bawah, select)
│   ├── views.py                # Rich components: tabel, panel status, live progress bar
│   └── themes.py               # Color schemes & clean ASCII banners
├── data/
│   ├── bin/                    # Direktori penyimpanan binary sing-box
│   ├── sources.json            # Daftar upstream URL scraper publik
│   ├── proxies_raw.txt         # Cache raw proxies yang belum difilter
│   ├── proxies_active.json     # Database terstruktur proxy aktif yang sudah terverifikasi
│   └── exports/                # Direktori output file export
└── tests/
    ├── __init__.py
    ├── test_parsers.py
    ├── test_collector.py
    └── test_exporter.py
```

---

## 3. Spesifikasi Protokol & Parsing

Setiap parser mengubah string URI menjadi objek `ProxyNode` dan menghasilkan dictionary outbound konfigurasi resmi `sing-box`.

### Struktur Model Data (`core/models.py`)
```python
@dataclass
class ProxyNode:
    id: str                 # Unique hash deduplication (protocol:server:port:creds:sni)
    protocol: str           # vmess | vless | trojan | shadowsocks | tuic | hysteria | hysteria2
    name: str               # Original / standardized name (e.g. "[ID] VLESS-Reality - 85ms")
    server: str             # IP address or domain host
    port: int               # Port number
    raw_uri: str            # Original raw link
    config: dict            # Sing-box outbound configuration dict
    country_code: str = "XX"# ISO 2-character code (e.g. ID, SG, US)
    country_name: str = "Unknown"
    latency: int = -1       # Round-trip latency in ms (-1 = dead/untested)
    is_alive: bool = False  # True if HTTP 204 succeeded
    last_checked: str = ""  # ISO timestamp
```

### Aturan Parsing Protokol
1. **VMess (`vmess://`)**: Mendukung encoding Base64 JSON (standar V2RayN) dengan parameter `add`, `port`, `id`, `aid`, `net` (tcp/ws/grpc), `type`, `host`, `path`, `tls`, `sni`.
2. **VLESS (`vless://`)**: Format URI `vless://uuid@server:port?type=ws/grpc/tcp&security=reality/tls&pbk=...&sni=...&fp=...#name`. Mendukung Reality parameters (`pbk`, `sid`, `spx`) dan flow `xtls-rprx-vision`.
3. **Trojan (`trojan://`)**: Format `trojan://password@server:port?security=tls&sni=...&type=ws/tcp#name`.
4. **Shadowsocks (`ss://`)**: Mendukung format SIP002 (`ss://user:pass@host:port#name`) dan Base64 legacy (`ss://BASE64(method:pass@host:port)#name`).
5. **TUIC (`tuic://`)**: Mendukung `tuic://uuid:password@server:port?congestion_control=bbr&alpn=h3&sni=...#name`.
6. **Hysteria 1 & 2 (`hysteria://`, `hysteria2://`, `hy2://`)**: Mendukung port hopping, auth token/password, obfs (salamander), SNI, dan `insecure=1`.

---

## 4. Manajemen Binary `sing-box` (`core/binary_manager.py`)

Aplikasi secara otomatis mendeteksi arsitektur sistem (`linux-amd64`, `linux-arm64`, dll.) dan memastikan binary `sing-box` versi stabil terbaru tersedia di `data/bin/sing-box`.
- Jika binary belum ada, sistem akan mendownload rilis resmi dari GitHub Releases `SagerNet/sing-box` dan memberikan izin eksekusi (`chmod +x`).
- Menggunakan perintah `sing-box version` untuk memverifikasi kesiapan core.

---

## 5. Mesin Pengumpul (Collector) & Deduplikasi (`core/collector.py`)

### Sumber Pengambilan
1. **Upstream Repositori Publik (`data/sources.json`)**:
   - Sumber publik terverifikasi yang diperbarui berkala (koleksi raw proxy publik dari repositori GitHub dan open subscription feeds).
   - Mendukung parsing format plain-text URI baris per baris dan subscription yang di-encode Base64.
2. **Custom URL Subscription**: Pengguna dapat memasukkan URL custom subscription milik sendiri.
3. **Import File**: Membaca file lokal `.txt`, `.yaml` (Clash), atau `.json`.
4. **Input Direct Paste**: Memasukkan satu atau banyak link sekaligus melalui prompt TUI.

### Algoritma Deduplikasi Cerdas
Menghitung hash SHA-256 berdasarkan atribut inti:
`hash(f"{protocol}:{server.lower()}:{port}:{credentials}:{sni.lower()}:{path}")`
Node dengan konfigurasi identik namun label `#name` berbeda akan digabungkan sehingga tidak ada pengujian duplikat yang membuang bandwidth.

---

## 6. Mesin Health Checker Asinkron (`core/checker.py`)

### Alur Kerja Pengujian
1. **Worker Pool Concurrency**:
   - Membagi daftar proxy menjadi antrean tugas dengan worker paralel `asyncio.Semaphore(concurrency)` (default: 30 workers).
2. **Ephemeral Micro-Instance Sing-box**:
   - Setiap worker membuat konfigurasi JSON sing-box minimal sementara dengan:
     - Inbound: SOCKS5/HTTP pada port lokal ephemeral (acak dari range 20000 - 45000).
     - Outbound: Node proxy yang sedang diuji.
   - Menjalankan subprocess: `sing-box run -c <temp_config.json>`.
3. **Pengujian HTTP 204 Nyata**:
   - Melakukan HTTP GET request via client `aiohttp` yang diarahkan ke proxy lokal ephemeral tersebut.
   - Endpoint target: `http://cp.cloudflare.com/generate_204` (fallback `https://www.gstatic.com/generate_204`).
   - Timeout: 5000 ms (dapat diatur di konfigurasi).
4. **Pencatatan Hasil**:
   - Jika status code = 204 dan waktu respon < timeout: Catat latensi (ms), tandai `is_alive = True`.
   - Jika timeout, connection refused, atau handshake error: Tandai `is_alive = False`, catat status `DEAD`.
5. **Cleanup Subprocess**:
   - Segera menghentikan (kill) subprocess sing-box dan menghapus file konfigurasi sementara untuk mencegah kebocoran memori / port zombie.

---

## 7. GeoIP Resolver & Standardisasi Nama Node (`core/geoip.py`)

- **Lookup Negara**: Menyelesaikan IP server (apabila berupa domain, di-resolve terlebih dahulu) dan mencari lokasi negara via database lokal ringan atau API GeoIP berkecepatan tinggi dengan sistem caching.
- **Standardisasi Nama (Clean Text)**:
  - Format baku: `[{COUNTRY_CODE}] {PROTOCOL_UPPER}-{TAG} - {LATENCY}ms`
  - Contoh:
    - `[ID] VLESS-Reality - 68ms`
    - `[SG] HY2-Hysteria2 - 45ms`
    - `[US] VMESS-WS - 180ms`
  - Tidak ada karakter emoji pada nama maupun metadata.

---

## 8. Modul Ekspor (`core/exporter.py`)

Menghasilkan file konfigurasi siap pakai ke dalam direktori `data/exports/`:
1. **Raw Links (`proxies_clean.txt`)**: Daftar link URI murni baris per baris.
2. **Base64 Subscription (`subscription.txt`)**: String Base64 dari kumpulan raw links (cocok untuk import subscription URL v2rayN/NekoBox).
3. **Clash / Mihomo YAML (`clash_config.yaml`)**:
   - Dilengkapi `proxies`, `proxy-groups` (Auto-Fallback, Select Group, Load-Balance), dan basic routing rules.
4. **Sing-box JSON (`singbox_config.json`)**:
   - Konfigurasi lengkap `inbounds` (SOCKS/HTTP/TUN), `outbounds` (semua proxy aktif + URLTest auto-select), dan `route` rule-sets.

### Filter Ekspor
Pengguna dapat memfilter ekspor berdasarkan:
- Kode Negara (contoh: hanya `ID`, `SG`)
- Jenis Protokol (contoh: hanya `VLESS`, `HYSTERIA2`)
- Maksimum Latensi (contoh: hanya node dengan latensi < 150ms)

---

## 9. Local Proxy Runner & Auto-Scheduler

### Local Proxy Runner (`core/runner.py`)
- Memungkinkan pengguna memilih 1 node aktif terbaik dari daftar.
- Menjalankan instance daemon `sing-box` di latar belakang dengan inbound:
  - SOCKS5: `127.0.0.1:1080`
  - HTTP: `127.0.0.1:1081`
- Menampilkan dashboard status: Status proses, Port aktif, Node yang dipakai, Latensi, dan opsi Stop.

### Auto-Scheduler (`core/scheduler.py`)
- Background thread/timer yang dapat diaktifkan untuk melakukan auto-scrape dan auto-check secara berkala (misal tiap 60 menit).
- Memperbarui database aktif dan file export secara otomatis tanpa intervensi manual.

---

## 10. Navigasi Menu TUI & Visualisasi (`tui/`)

### Desain Menu Utama (Clean ASCII Style)
```text
========================================================================
             UNIVERSAL PROXY SCRAPER & HEALTH CHECKER TUI               
========================================================================
[1] Scrape & Auto-Check Semua Sumber (One-Click Update)
[2] Kumpulkan Proxy (Scrape Publik / Input Custom URL / File)
[3] Jalankan Health Check & Filter Proxy Aktif
[4] Lihat Daftar Proxy Aktif (Tabel Rapi, Sorting & Detail)
[5] Ekspor Proxy (Raw Links, Base64 Sub, Clash/Mihomo, Sing-box)
[6] Jalankan Local Proxy Server (SOCKS5/HTTP di Localhost)
[7] Auto-Scheduler (Jalankan Pengecekan Berkala Otomatis)
[8] Pengaturan & Kelola Sumber Upstream
[0] Keluar
========================================================================
```

### Format Tampilan Tabel Proxy Aktif (`Rich Table`)
```text
+----+---------+------------+--------------------+-------+----------+---------+
| No | Negara  | Protokol   | Server Host        | Port  | Latensi  | Status  |
+----+---------+------------+--------------------+-------+----------+---------+
| 1  | [ID] ID | VLESS      | sg1.speednode.net  | 443   | 48 ms    | ALIVE   |
| 2  | [SG] SG | HYSTERIA2  | hy2.cloudfast.org  | 8443  | 52 ms    | ALIVE   |
| 3  | [JP] JP | TROJAN     | jp-tokyo.free.io   | 2053  | 95 ms    | ALIVE   |
| 4  | [US] US | VMESS      | us-east.v2node.com | 80    | 185 ms   | ALIVE   |
+----+---------+------------+--------------------+-------+----------+---------+
Total Aktif: 4 node | Proxy Mati Dihapus: 18 node
```

---

## 11. Strategi Pengujian (Testing Strategy)

1. **Unit Test Parsers (`tests/test_parsers.py`)**:
   - Uji parsing string URI untuk setiap protokol (vmess, vless, trojan, ss, tuic, hy2) dan verifikasi bahwa dictionary sing-box outbound yang dihasilkan valid.
2. **Unit Test Collector & Deduplikasi (`tests/test_collector.py`)**:
   - Verifikasi penggabungan link dari berbagai sumber dan eliminasi duplikasi link.
3. **Unit Test Exporter (`tests/test_exporter.py`)**:
   - Verifikasi kevalidan sintaks YAML untuk Clash dan sintaks JSON untuk Sing-box.
4. **Integration Test Checker**:
   - Uji verifikasi status ALIVE/DEAD dengan mock server atau endpoint live.
