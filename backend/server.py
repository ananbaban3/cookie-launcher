#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
COOKIELAUNCHER - CORE ENGINE BACKEND (FREESM / PRISM SPECIFICATION)
Non-Blocking Launch, CORS-Native (Tauri uyumlu), Tolerant Network,
Per-Version Isolated Mods, Otomatik Java Runtime ve Canli MB Ilerlemesi
==============================================================================
"""

import os
import sys
import json
import re
import time
import shutil
import socket
import threading
import subprocess
import traceback
import http.server
import socketserver
from collections import OrderedDict
from urllib.parse import urlparse, parse_qs

try:
    import requests
    import urllib.request
    import urllib.parse
    import minecraft_launcher_lib
    import urllib3.util.connection as urllib3_cn
except Exception as _import_error:
    # Kullaniciya anlasilir hata birakmak icin log dosyasina yaz
    try:
        _err_dir = os.path.join(os.path.expanduser("~"), ".cookie_launcher")
        os.makedirs(_err_dir, exist_ok=True)
        with open(os.path.join(_err_dir, "backend_error.log"), "w", encoding="utf-8") as _f:
            _f.write(
                "CookieLauncher backend baslatilamadi.\n"
                f"Eksik Python bagimliligi: {_import_error}\n\n"
                "Cozum: pip install requests minecraft-launcher-lib urllib3\n"
            )
    except Exception:
        pass
    raise

# Linux ortaminda DNS / IPv6 takilmalarini engellemek icin IPv4 zorla.
# ONEMLI: Bu yama yalnizca Linux icindir; macOS'ta IPv6-only aglarda
# baglantiyi bozabildigi icin orada UYGULANMAZ.
if sys.platform.startswith("linux"):
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

# ==================== SSL / KOK SERTIFIKA (macOS kritik) ====================
# macOS'ta sistem Python'u veya paketlenmis Python, macOS Keychain kok
# sertifikalarini goremeyebilir -> CERTIFICATE_VERIFY_FAILED. Bu durumda
# istekler sessizce basarisiz olup listeler bos geliyordu. certifi'nin kendi
# CA demeti kullanilir ve ortam degiskenleriyle requests/curl katmanina da
# bildirilir.
CERTIFI_PATH = ""
try:
    import certifi as _certifi
    CERTIFI_PATH = _certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", CERTIFI_PATH)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", CERTIFI_PATH)
    os.environ.setdefault("CURL_CA_BUNDLE", CERTIFI_PATH)
except Exception:
    CERTIFI_PATH = ""

try:
    import ssl as _ssl
    if CERTIFI_PATH:
        SSL_CONTEXT = _ssl.create_default_context(cafile=CERTIFI_PATH)
    else:
        SSL_CONTEXT = _ssl.create_default_context()
except Exception:
    SSL_CONTEXT = None

# Son ag hatasi / manifest hatasi (UI + /api/net-test icin)
NET_LAST_ERROR = {}
LAST_MANIFEST_ERROR = ""


def log_error(msg):
    """Hatalari HEM konsol gecmisine HEM stderr'e yazar.

    macOS'ta paketlenmis uygulamada stdout kaybolabilir; stderr log dosyasina
    ve terminale gider, boylece 'sessizce bos donen' hatalar gorunur olur.
    """
    line = f"⛔ {msg}"
    try:
        print(line, file=sys.stderr, flush=True)
    except Exception:
        pass
    add_log(line)


# ==================== DIZIN YAPILANDIRMASI ====================
APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".cookie_launcher")
os.makedirs(APP_DATA_DIR, exist_ok=True)

DEFAULT_MINECRAFT_DIR = minecraft_launcher_lib.utils.get_minecraft_directory()
minecraft_directory = DEFAULT_MINECRAFT_DIR
os.makedirs(minecraft_directory, exist_ok=True)

INSTANCES_DIR = os.path.join(minecraft_directory, "instances")
os.makedirs(INSTANCES_DIR, exist_ok=True)

MODS_QUARANTINE_DIR = os.path.join(minecraft_directory, "mods_quarantine")
os.makedirs(MODS_QUARANTINE_DIR, exist_ok=True)

MODS_CACHE_FILE = os.path.join(APP_DATA_DIR, "mod_cache.json")
VERSIONS_CACHE_FILE = os.path.join(APP_DATA_DIR, "versions_manifest_cache.json")

# Onbellek sinirlari: sinirsiz buyumeyi (bellek + disk) engeller.
# Modrinth arama/surum onbellegi LRU ile kirpilir; mod meta onbellegi de
# guncellenen/silinen modlar icin kalici kayit biriktirmemelidir.
MODRINTH_CACHE_MAX = 600
CONTENT_META_CACHE_MAX = 2000
CACHE_SAVE_MIN_INTERVAL = 30.0  # saniye: ardisik disk yazimlarini birlestir

# NOT: Yeni bir API endpoint'i eklendiginde bu surumu ARTIR ve
# src-tauri/src/main.rs ile src/app.js icindeki kontrolu de guncelle!
API_VERSION = 12


# ==================== PROFIL (INSTANCE) YARDIMCILARI ====================
def get_instance_dir(inst_id):
    """Guvenli instance klasoru yolu dondurur (path traversal korumali)."""
    safe = re.sub(r"[^\w\-]", "", str(inst_id or ""))
    if not safe:
        return None
    base = os.path.abspath(INSTANCES_DIR)
    inst_dir = os.path.abspath(os.path.join(base, safe))
    if inst_dir != base and not inst_dir.startswith(base + os.sep):
        return None
    return inst_dir


def count_instance_mods(inst_id):
    """Profilin mods klasorundeki jar sayisini dondurur."""
    inst_dir = get_instance_dir(inst_id)
    if not inst_dir:
        return 0
    mods_dir = os.path.join(inst_dir, "mods")
    if not os.path.isdir(mods_dir):
        return 0
    try:
        return sum(1 for f in os.listdir(mods_dir) if f.lower().endswith(".jar"))
    except Exception:
        return 0


def load_instance_config(inst_id):
    """Profil config'ini okur; yoksa None dondurur."""
    inst_dir = get_instance_dir(inst_id)
    if not inst_dir:
        return None
    cfg_path = os.path.join(inst_dir, "instance.json")
    if not os.path.exists(cfg_path):
        return None
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["id"] = os.path.basename(inst_dir)
        cfg["mod_count"] = count_instance_mods(cfg["id"])
        return cfg
    except Exception:
        return None


def list_instances():
    """Tum profilleri mod sayilariyla birlikte listeler."""
    insts = []
    if os.path.exists(INSTANCES_DIR):
        for d in os.listdir(INSTANCES_DIR):
            cfg = load_instance_config(d)
            if cfg:
                insts.append(cfg)
    insts.sort(key=lambda c: c.get("created_at", ""))
    return insts


# ==================== KONSOL GUNLUK & DURUM YONETIMI ====================
MAX_LOG_HISTORY = 1000
console_logs = []
logs_lock = threading.Lock()
state_lock = threading.RLock()

launch_state = {
    "is_installing": False,
    "is_running": False,
    "progress": 0.0,
    "percent": 0,
    "status": "Core Hazır",
    "detail": "",
    "current_file": "",
    "downloaded_bytes": 0,
    "downloaded_mb": 0.0,
    "error": None,
    "minecraft_pid": None,
    "started_at": None,
}


def add_log(msg):
    """Konsol gecmisine ve stdout'a log yazar (thread-safe)."""
    t_str = time.strftime("[%H:%M:%S]")
    line = f"{t_str} {msg}"
    with logs_lock:
        console_logs.append(line)
        if len(console_logs) > MAX_LOG_HISTORY:
            console_logs.pop(0)
    try:
        print(line, flush=True)
    except Exception:
        pass


def update_state(**fields):
    """launch_state'i kilit altinda gunceller."""
    with state_lock:
        launch_state.update(fields)


def get_state_snapshot():
    """Durumun kilitli, guvenli bir kopyasini dondurur."""
    with state_lock:
        return dict(launch_state)


def add_downloaded_bytes(size):
    """Indirilen toplam bayti ve MB degerini gunceller."""
    try:
        size = max(0, int(size))
    except Exception:
        return
    if size <= 0:
        return
    with state_lock:
        launch_state["downloaded_bytes"] = int(launch_state.get("downloaded_bytes", 0)) + size
        launch_state["downloaded_mb"] = round(launch_state["downloaded_bytes"] / (1024 * 1024), 1)


# ==================== INDIRME TAKIP SISTEMI (CANLI MB) ====================
def install_download_tracker():
    """
    minecraft_launcher_lib icindeki tum download_file fonksiyonlarini sarar.
    Boylece vanilla jar, kutuphaneler, assetler, Java runtime ve loader
    indirmeleri canli olarak MB cinsinden izlenebilir.
    """
    try:
        original = minecraft_launcher_lib._helper.download_file
    except Exception:
        return
    if getattr(original, "_cookie_size_tracked", False):
        return

    def tracked_download_file(url, path, *args, **kwargs):
        result = original(url, path, *args, **kwargs)
        if result:
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            if size > 0:
                add_downloaded_bytes(size)
        return result

    tracked_download_file._cookie_size_tracked = True

    for module_name, module in list(sys.modules.items()):
        if module is None:
            continue
        if module_name == "minecraft_launcher_lib" or module_name.startswith("minecraft_launcher_lib."):
            try:
                if getattr(module, "download_file", None) is original:
                    setattr(module, "download_file", tracked_download_file)
            except Exception:
                pass


# ==================== ILERLEME CALLBACK FABRIKASI ====================
def translate_status(text):
    """minecraft_launcher_lib'in Ingilizce durum mesajlarini Turkceye cevirir."""
    text = (text or "").strip()
    if text.startswith("Download "):
        filename = os.path.basename(text[len("Download "):].strip())
        with state_lock:
            launch_state["current_file"] = filename
        return f"📥 İndiriliyor: {filename}"
    if text.startswith("Extract "):
        return f"📦 Çıkarılıyor: {os.path.basename(text[8:].strip())}"
    low = text.lower()
    if low.startswith("running fabric installer"):
        return "🧵 Fabric yükleyici çalıştırılıyor..."
    if low.startswith("installing"):
        return f"⚙️ {text}"
    return text


def make_progress_callbacks(base_pct=0.0, span_pct=100.0):
    """
    Belirtilen yuzde araligina eslenen ilerleme callback'leri uretir.
    Boylece Java -> Vanilla -> Loader asamalari tek bir akista ilerler.
    """
    tracker = {"max": 100, "val": 0}

    def recompute():
        ratio = tracker["val"] / max(1, tracker["max"])
        ratio = max(0.0, min(1.0, ratio))
        pct = max(0.0, min(100.0, base_pct + ratio * span_pct))
        with state_lock:
            launch_state["percent"] = int(round(pct))
            launch_state["progress"] = round(min(1.0, pct / 100.0), 4)

    def set_status(s):
        text = translate_status(str(s))
        with state_lock:
            launch_state["status"] = text
            launch_state["detail"] = text
        add_log(text)

    def set_progress(p):
        try:
            tracker["val"] = int(p)
        except Exception:
            tracker["val"] = 0
        recompute()

    def set_max(m):
        try:
            tracker["max"] = max(1, int(m))
        except Exception:
            tracker["max"] = 1
        tracker["val"] = 0
        recompute()

    return {"setStatus": set_status, "setProgress": set_progress, "setMax": set_max}


# ==================== SISTEM RAM VE OPTIMIZASYON ====================
def get_total_system_memory_gb():
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 * 1024), 1)
        elif sys.platform == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return round(stat.ullTotalPhys / (1024 ** 3), 1)
        elif sys.platform == "darwin":
            # macOS: hw.memsize bayt cinsinden toplam RAM'i verir
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=3)
            return round(int(out.strip()) / (1024 ** 3), 1)
    except Exception:
        pass
    return 8.0


def get_optimal_ram_allocation():
    total_ram = get_total_system_memory_gb()
    if total_ram >= 32:
        return 8
    elif total_ram >= 16:
        return 6
    elif total_ram >= 8:
        return 4
    elif total_ram >= 6:
        return 3
    else:
        return 2


def find_system_java_binary(required_major=21):
    """Sistemde bulunan Java'lari tarar; bulunan en uygun olani dondurur."""
    candidates = []

    if "JAVA_HOME" in os.environ:
        jh = os.environ["JAVA_HOME"]
        cand = os.path.join(jh, "bin", "java.exe" if sys.platform == "win32" else "java")
        if os.path.exists(cand):
            candidates.append(cand)

    sys_java = shutil.which("java")
    if sys_java:
        candidates.append(sys_java)

    if sys.platform.startswith("linux"):
        common_paths = [
            f"/usr/lib/jvm/java-{required_major}-openjdk/bin/java",
            f"/usr/lib/jvm/java-{required_major}-openjdk-amd64/bin/java",
            f"/usr/lib/jvm/java-{required_major}/bin/java",
            "/usr/lib/jvm/default/bin/java",
            "/usr/bin/java",
        ]
        for p in common_paths:
            if os.path.exists(p) and p not in candidates:
                candidates.append(p)
    elif sys.platform == "win32":
        for drv in ["C:\\Program Files\\Java", "C:\\Program Files\\Eclipse Adoptium"]:
            if os.path.exists(drv):
                for item in os.listdir(drv):
                    cand = os.path.join(drv, item, "bin", "java.exe")
                    if os.path.exists(cand) and cand not in candidates:
                        candidates.append(cand)
    elif sys.platform == "darwin":
        # macOS: Homebrew (arm64/intel), Temurin ve Oracle kurulumlari.
        # Not: /usr/bin/java bir "stub"tir; JDK yoksa kurulum penceresi acar,
        # bu yuzden bilerek listeye eklenmez (shutil.which zaten bulursa
        # asagidaki -version kontrolunde elenir).
        mac_paths = [
            f"/opt/homebrew/opt/openjdk@{required_major}/bin/java",
            f"/usr/local/opt/openjdk@{required_major}/bin/java",
            f"/Library/Java/JavaVirtualMachines/temurin-{required_major}.jdk/Contents/Home/bin/java",
            f"/Library/Java/JavaVirtualMachines/jdk-{required_major}.jdk/Contents/Home/bin/java",
            "/Library/Java/JavaVirtualMachines/current/Contents/Home/bin/java",
            "/opt/homebrew/bin/java",
            "/usr/local/bin/java",
        ]
        for p in mac_paths:
            if os.path.exists(p) and p not in candidates:
                candidates.append(p)

    for cand in candidates:
        try:
            out = subprocess.check_output([cand, "-version"], stderr=subprocess.STDOUT, text=True, timeout=3)
            m = re.search(r'version "(\d+)', out)
            if m:
                major = int(m.group(1))
                if major >= 17:
                    return cand
            else:
                return cand
        except Exception:
            continue

    return sys_java or "java"


def resolve_java_executable(version_id, custom_java="", callback=None):
    """
    Surume ait javaVersion bilgisini okur, Minecraft'in kendi Java runtime'ini
    kurar/kullanir; olmazsa sistemdeki dogru major surumlu Java'yi secer.
    Boylece 'Unsupported class file version' kaynakli baslatma hatalari onlenir.
    """
    if custom_java and os.path.exists(custom_java):
        add_log(f"Ozel Java yurutucusu kullaniliyor: {custom_java}")
        return custom_java

    info = None
    try:
        info = minecraft_launcher_lib.runtime.get_version_runtime_information(version_id, minecraft_directory)
    except Exception as e:
        add_log(f"Java surum bilgisi alinamadi ({version_id}): {e}")

    if info:
        component = info.get("name")
        major = info.get("javaMajorVersion", 21)

        # 1. Minecraft'in kendi runtime'i zaten kurulu mu?
        try:
            existing = minecraft_launcher_lib.runtime.get_executable_path(component, minecraft_directory)
            if existing and os.path.exists(existing):
                add_log(f"✓ Minecraft Java runtime hazir: {component}")
                return existing
        except Exception:
            pass

        # 2. Runtime'i otomatik indir (Prism/Freesm davranisi)
        try:
            add_log(f"Java {major} calisma ortami ({component}) kontrol ediliyor...")
            minecraft_launcher_lib.runtime.install_jvm_runtime(component, minecraft_directory, callback=callback)
            existing = minecraft_launcher_lib.runtime.get_executable_path(component, minecraft_directory)
            if existing and os.path.exists(existing):
                add_log(f"✓ Java {major} runtime hazir.")
                return existing
        except Exception as e:
            add_log(f"Java runtime indirilemedi, sistem Java'sina geciliyor: {e}")

        # 3. Sistemde ayni major surume sahip Java ara
        try:
            for jinfo in minecraft_launcher_lib.java_utils.find_system_java_versions_information():
                ver_match = re.search(r"(\d+)", str(jinfo.get("version", "")))
                if ver_match and int(ver_match.group(1)) == int(major):
                    java_path = jinfo.get("java_path")
                    if java_path and os.path.exists(java_path):
                        add_log(f"✓ Sistem Java {major} bulundu: {java_path}")
                        return java_path
        except Exception:
            pass

    fallback = find_system_java_binary(21)
    add_log(f"Java runtime cozulemedi, varsayilan Java kullaniliyor: {fallback}")
    return fallback


# ==================== COOKIE LAUNCHER OPTIMIZE VERILERI ====================
OPTIMIZED_VERSIONS_LIST = [
    "26.3", "26.2", "26.1", "1.21.4", "1.21.3", "1.21.2", "1.21.1", "1.21",
    "1.20.6", "1.20.4", "1.20.2", "1.20.1", "1.20",
    "1.19.4", "1.19.2", "1.18.2", "1.17.1", "1.16.5",
    "1.12.2", "1.8.9", "1.7.10",
]

FALLBACK_CURATED_RELEASES = [
    "26.3", "26.2", "26.1.2", "26.1.1", "26.1",
    "1.21.4", "1.21.3", "1.21.2", "1.21.1", "1.21",
    "1.20.4", "1.20.2", "1.20.1", "1.20",
    "1.19.4", "1.19.2", "1.18.2", "1.17.1", "1.16.5",
    "1.12.2", "1.8.9", "1.7.10",
]

# Sik kullanilan kararli surumler icin dogrudan yuksek hizli CDN indeksi
CURATED_OPTIMIZATION_MAP = {
    ("26.1.2", "fabric"): [
        {
            "slug": "fabric-api",
            "filename": "fabric-api-0.155.2+26.1.2.jar",
            "url": "https://cdn.modrinth.com/data/P7dR8mSH/versions/uLkEd5dr/fabric-api-0.155.2%2B26.1.2.jar",
        },
        {
            "slug": "sodium",
            "filename": "sodium-fabric-0.9.2-beta.1+mc26.1.2.jar",
            "url": "https://cdn.modrinth.com/data/AANobbMI/versions/l25R3slV/sodium-fabric-0.9.2-beta.1%2Bmc26.1.2.jar",
        },
    ],
    ("26.2", "fabric"): [
        {
            "slug": "fabric-api",
            "filename": "fabric-api-0.161.0+26.2.jar",
            "url": "https://cdn.modrinth.com/data/P7dR8mSH/versions/Fq2YV1f0/fabric-api-0.161.0%2B26.2.jar",
        },
        {
            "slug": "sodium",
            "filename": "sodium-fabric-0.9.2+mc26.2.jar",
            "url": "https://cdn.modrinth.com/data/AANobbMI/versions/xJZxADzI/sodium-fabric-0.9.2%2Bmc26.2.jar",
        },
    ],
    ("26.3", "fabric"): [
        {
            "slug": "sodium",
            "filename": "sodium-fabric-0.9.3-alpha.1+mc26.3.jar",
            "url": "https://cdn.modrinth.com/data/AANobbMI/versions/v4PSXean/sodium-fabric-0.9.3-alpha.1%2Bmc26.3.jar",
        }
    ],
    ("1.21.11", "fabric"): [
        {
            "slug": "sodium",
            "filename": "sodium-fabric-0.8.14+mc1.21.11.jar",
            "url": "https://cdn.modrinth.com/data/AANobbMI/versions/rkdTcxoT/sodium-fabric-0.8.14%2Bmc1.21.11.jar",
        }
    ],
    ("1.21.1", "fabric"): [
        {
            "slug": "fabric-api",
            "filename": "fabric-api-0.102.0+1.21.1.jar",
            "url": "https://cdn.modrinth.com/data/P7dR8mSH/versions/P7U70xkn/fabric-api-0.102.0%2B1.21.1.jar",
        },
        {
            "slug": "sodium",
            "filename": "sodium-fabric-0.5.11+mc1.21.1.jar",
            "url": "https://cdn.modrinth.com/data/AANobbMI/versions/3PnHeviJ/sodium-fabric-0.5.11%2Bmc1.21.1.jar",
        },
    ],
    ("1.20.4", "fabric"): [
        {
            "slug": "fabric-api",
            "filename": "fabric-api-0.97.0+1.20.4.jar",
            "url": "https://cdn.modrinth.com/data/P7dR8mSH/versions/B1qGgJkM/fabric-api-0.97.0%2B1.20.4.jar",
        },
        {
            "slug": "sodium",
            "filename": "sodium-fabric-0.5.8+mc1.20.4.jar",
            "url": "https://cdn.modrinth.com/data/AANobbMI/versions/P9a3wR0c/sodium-fabric-0.5.8%2Bmc1.20.4.jar",
        },
    ],
    ("1.20.1", "fabric"): [
        {
            "slug": "fabric-api",
            "filename": "fabric-api-0.92.2+1.20.1.jar",
            "url": "https://cdn.modrinth.com/data/P7dR8mSH/versions/1u6rqpaW/fabric-api-0.92.2%2B1.20.1.jar",
        },
        {
            "slug": "sodium",
            "filename": "sodium-fabric-0.5.8+mc1.20.1.jar",
            "url": "https://cdn.modrinth.com/data/AANobbMI/versions/94cQvtWq/sodium-fabric-0.5.8%2Bmc1.20.1.jar",
        },
    ],
}


def is_version_cookie_optimized(version_id):
    if not version_id:
        return False
    vid = str(version_id).strip()
    return any(opt_v in vid for opt_v in OPTIMIZED_VERSIONS_LIST)


def clean_minecraft_version(v):
    if not v:
        return "1.20.4"
    s = str(v).strip()
    s = re.sub(r"\(⚡.*?\)", "", s).strip()
    s = re.sub(r"\[⚡.*?\]", "", s).strip()
    m_paren = re.search(r"\(([\w\.\-]+)\)", s)
    if m_paren:
        cand = m_paren.group(1)
        if any(c.isdigit() for c in cand):
            return cand
    return s.split()[0].strip()


# ==================== MODRINTH VE NATIVE INDIRME MOTORU ====================
class ModrinthFetcher:
    BASE_URL = "https://api.modrinth.com/v2"
    HEADERS = {
        "User-Agent": "Freesm/CookieLauncher/2.0.0 (https://github.com/cookie-launcher; support@cookielauncher.app)"
    }
    # Arama + surum cozumleme onbellegi. OrderedDict + ust sinir ile LRU
    # davranisi uygulanir; aksi hâlde her farkli arama kalici olarak birikir
    # (bellek ve mod_cache.json sinirsiz buyur).
    _cache = OrderedDict()
    _cache_lock = threading.Lock()
    _last_save = 0.0
    _loaded = False

    @classmethod
    def _trim(cls):
        """Ust siniri asan en eski kayitlari atar. Cagiran kilit tutmalidir."""
        while len(cls._cache) > MODRINTH_CACHE_MAX:
            cls._cache.popitem(last=False)

    @classmethod
    def load_cache(cls):
        with cls._cache_lock:
            if not cls._loaded:
                cls._loaded = True
                if os.path.exists(MODS_CACHE_FILE):
                    try:
                        with open(MODS_CACHE_FILE, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if isinstance(data, dict):
                            # Diskte birikmis negatif (None) kayitlari temizle:
                            # kalici negatif onbellek, bir mod sonradan yayinlansa
                            # bile asla yeniden sorgulanmamasina yol acar.
                            cls._cache = OrderedDict(
                                (k, v) for k, v in data.items() if v is not None
                            )
                    except Exception:
                        cls._cache = OrderedDict()
                cls._trim()
            return dict(cls._cache)

    @classmethod
    def _remember(cls, key, value, persist=True):
        """Onbellege kayit ekler, sinirlari uygular ve (gerekirse) diske yazar."""
        with cls._cache_lock:
            cls._cache.pop(key, None)
            cls._cache[key] = value
            cls._trim()
        if persist:
            cls.save_cache()

    @classmethod
    def save_cache(cls, force=False):
        """Onbellegi atomik olarak yazar. Yazimlar birlestirilir (throttle),
        boylece her arama tum dosyanin yeniden yazilmasina yol acmaz.
        Negatif kayitlar diske YAZILMAZ (yalnizca oturum icinde gecerlidir)."""
        now = time.time()
        with cls._cache_lock:
            if not force and (now - cls._last_save) < CACHE_SAVE_MIN_INTERVAL:
                return
            cls._last_save = now
            tmp_path = MODS_CACHE_FILE + ".tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump({k: v for k, v in cls._cache.items() if v is not None}, f, indent=2)
                os.replace(tmp_path, MODS_CACHE_FILE)
            except Exception:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

    @classmethod
    def search(cls, query="", project_type="mod", game_version="", loader="", index="downloads", limit=20, offset=0):
        facets = []
        if project_type:
            facets.append([f"project_type:{project_type}"])
        if game_version and game_version != "Tümü":
            clean_gv = clean_minecraft_version(game_version)
            if clean_gv:
                facets.append([f"versions:{clean_gv}"])
        if loader and loader != "Tümü" and project_type in ["mod", "modpack"]:
            facets.append([f"categories:{loader.lower()}"])

        params = {"query": query.strip(), "limit": limit, "offset": offset, "index": index}
        if facets:
            params["facets"] = json.dumps(facets)

        try:
            resp = requests.get(f"{cls.BASE_URL}/search", params=params, headers=cls.HEADERS, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and isinstance(data.get("hits"), list):
                    return data
            msg = f"Modrinth arama yaniti beklenmedik (HTTP {resp.status_code})"
            add_log(f"{msg}, bos liste donduruluyor.")
            return {"hits": [], "total_hits": 0, "limit": limit, "offset": offset, "error": msg}
        except Exception as e:
            # macOS'ta SSL/dogrulama hatalari burada olusur; sessizce bos
            # donmek yerine hatayi kaydet, stderr'e yaz ve yanitta bildir.
            set_net_error("modrinth_search", e)
            log_error(
                f"Modrinth aramasi basarisiz ({type(e).__name__}: {e}). "
                f"certifi: {CERTIFI_PATH or 'YOK'} | platform: {sys.platform}"
            )
            return {
                "hits": [], "total_hits": 0, "limit": limit, "offset": offset,
                "error": f"Modrinth bağlantı hatası: {type(e).__name__}: {e}",
            }

        return {"hits": [], "total_hits": 0, "limit": limit, "offset": offset}

    @classmethod
    def get_latest_mod_jar(cls, project_slug, game_version, loader="fabric"):
        cache = cls.load_cache()
        clean_gv = clean_minecraft_version(game_version)
        cache_key = f"{project_slug}::{clean_gv}::{loader.lower()}"

        if cache_key in cache:
            cached_item = cache[cache_key]
            if cached_item is None or (isinstance(cached_item, dict) and cached_item.get("url")):
                return cached_item

        try:
            params = {
                "game_versions": json.dumps([clean_gv]),
                "loaders": json.dumps([loader.lower()]),
            }
            resp = requests.get(
                f"{cls.BASE_URL}/project/{project_slug}/version",
                params=params,
                headers=cls.HEADERS,
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list):
                    for v in data:
                        gvs = v.get("game_versions", [])
                        if clean_gv not in gvs:
                            continue
                        loaders = [l.lower() for l in v.get("loaders", [])]
                        if loader.lower() not in loaders:
                            continue
                        files = v.get("files", [])
                        primary_file = next((f for f in files if f.get("primary")), files[0] if files else None)
                        if primary_file and primary_file.get("url"):
                            res = {
                                "filename": primary_file.get("filename"),
                                "url": primary_file.get("url"),
                                "size": primary_file.get("size", 0),
                                "version_number": v.get("version_number"),
                            }
                            cls._remember(cache_key, res)
                            return res
        except Exception as e:
            add_log(f"Modrinth mod bilgisi uyarisi ({project_slug}): {e}")

        cls._remember(cache_key, None, persist=False)
        return None

    @classmethod
    def get_project_file(cls, project_slug, game_version, project_type="shader", loader="", allow_fallback=False):
        """
        Modrinth projesinin dosyasini bulur.
        - mod: yukleyici + oyun surumu tam eslesme aranir.
        - shader/resourcepack: once tam eslesme, yoksa (allow_fallback) en yeni surum.
        Donen sozlukte exact_match alani bulunur.
        """
        clean_gv = clean_minecraft_version(game_version)
        cache_key = f"file::{project_slug}::{clean_gv}::{project_type}::{loader.lower()}"
        cache = cls.load_cache()
        if cache_key in cache:
            cached = cache[cache_key]
            if cached is None or isinstance(cached, dict):
                return cached

        chosen = None
        try:
            resp = requests.get(
                f"{cls.BASE_URL}/project/{project_slug}/version",
                headers=cls.HEADERS,
                timeout=8,
            )
            if resp.status_code == 200:
                versions = resp.json()
                if isinstance(versions, list):
                    exact = None
                    fallback = None
                    for v in versions:
                        files = v.get("files") or []
                        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
                        if not primary or not primary.get("url"):
                            continue

                        if project_type == "mod":
                            loaders = [str(l).lower() for l in (v.get("loaders") or [])]
                            if loader and loader.lower() not in loaders:
                                continue

                        gvs = v.get("game_versions") or []
                        entry = {
                            "filename": primary.get("filename"),
                            "url": primary.get("url"),
                            "size": primary.get("size", 0),
                            "version_number": v.get("version_number"),
                            "game_versions": gvs,
                            "exact_match": clean_gv in gvs,
                        }
                        if entry["exact_match"]:
                            exact = entry
                            break
                        if fallback is None:
                            fallback = entry

                    chosen = exact or (fallback if allow_fallback else None)
        except Exception as e:
            add_log(f"Modrinth dosya bilgisi uyarisi ({project_slug}): {e}")

        if chosen:
            cls._remember(cache_key, chosen)
        return chosen

    @classmethod
    def download_file(cls, url, dest_path):
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        part_path = dest_path + ".part"
        with requests.get(url, headers=cls.HEADERS, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(part_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=32768):
                    if chunk:
                        f.write(chunk)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(part_path, dest_path)
        add_downloaded_bytes(os.path.getsize(dest_path))
        return dest_path


# ==================== KOK MODLARI KARANTINAYA ALMA ====================
def quarantine_root_mods():
    """
    Kok .minecraft/mods klasorunde basibos bulunan jar dosyalarini karantinaya tasir.
    Boylece farkli surumlerden kalan eski modlar oyunu asla cokertemez.
    """
    root_mods_dir = os.path.join(minecraft_directory, "mods")
    if not os.path.exists(root_mods_dir):
        return

    for item in os.listdir(root_mods_dir):
        item_path = os.path.join(root_mods_dir, item)
        if os.path.isfile(item_path) and item.lower().endswith(".jar"):
            try:
                dest = os.path.join(MODS_QUARANTINE_DIR, item)
                shutil.move(item_path, dest)
                add_log(f"🛡️ Başıboş kök mod karantinaya alındı: {item}")
            except Exception:
                pass


# ==================== OTOMATIK MOD ENJEKTORU ====================
def inject_cookie_optimization_mods(version_str, target_mods_dir, loader="fabric"):
    """
    Cookie Launcher Ozel Optimize Motoru:
    - Surume ozel klasore (`mods/<version>/`) izole eder.
    - Surumle birebir uyumlu olmayan HICBIR modu indirmez veya enjekte etmez.
    - Bilinen surumler icin dogrudan CDN onbellegini kullanir.
    """
    clean_v = clean_minecraft_version(version_str)
    os.makedirs(target_mods_dir, exist_ok=True)
    add_log(f"⚡ [COOKIE LAUNCHER OPTİMİZE] Enjektörü devrede (MC {clean_v}, {loader})...")

    curated_key = (clean_v, loader.lower())
    if curated_key in CURATED_OPTIMIZATION_MAP:
        add_log(f"⚡ {clean_v} için doğrulanmış optimize mod profili bulundu.")
        for item in CURATED_OPTIMIZATION_MAP[curated_key]:
            fname = item["filename"]
            dest = os.path.join(target_mods_dir, fname)
            if not os.path.exists(dest):
                try:
                    add_log(f"📥 İndiriliyor: {fname}...")
                    ModrinthFetcher.download_file(item["url"], dest)
                    add_log(f"✓ Başarıyla kuruldu: {fname}")
                except Exception as e:
                    add_log(f"⚠️ İndirme uyarısı ({fname}): {e}")
        return

    target_slugs = ["fabric-api", "sodium"] if loader.lower() == "fabric" else ["embeddium", "ferrite-core"]

    for slug in target_slugs:
        try:
            info = ModrinthFetcher.get_latest_mod_jar(slug, clean_v, loader=loader)
            if info and info.get("url"):
                fname = info["filename"]
                dest = os.path.join(target_mods_dir, fname)
                if not os.path.exists(dest):
                    add_log(f"📥 İndiriliyor ({clean_v} uyumlu): {fname}...")
                    ModrinthFetcher.download_file(info["url"], dest)
                    add_log(f"✓ Başarıyla kuruldu: {fname}")
            else:
                add_log(f"⚡ {slug} modu {clean_v} ({loader}) için henüz mevcut değil, atlandı.")
        except Exception as e:
            add_log(f"Mod enjekte uyarısı ({slug}): {e}")


# ==================== MODPACK (.mrpack) PROFIL KURULUMU ====================
def fetch_modrinth_project(slug):
    try:
        resp = requests.get(f"{ModrinthFetcher.BASE_URL}/project/{slug}", headers=ModrinthFetcher.HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                return data
    except Exception as e:
        add_log(f"Modrinth proje bilgisi alinamadi ({slug}): {e}")
    return {}


def fetch_modrinth_versions(slug):
    try:
        resp = requests.get(f"{ModrinthFetcher.BASE_URL}/project/{slug}/version", headers=ModrinthFetcher.HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
    except Exception as e:
        add_log(f"Modrinth surum listesi alinamadi ({slug}): {e}")
    return []


# Profil detay cekmecesi icin proje detay onbellegi (LRU + TTL, disk yazimi yok)
_PROJECT_DETAIL_CACHE = OrderedDict()
_PROJECT_DETAIL_LOCK = threading.Lock()
_PROJECT_DETAIL_TTL = 600.0
_PROJECT_DETAIL_MAX = 120


def fetch_modrinth_project_detail(slug):
    """Modrinth projesinin detayli bilgisini (surumler + bagimliliklar) dondurur."""
    safe_slug = re.sub(r"[^a-zA-Z0-9\-_]", "", str(slug or ""))
    if not safe_slug:
        return {"success": False, "error": "Geçersiz proje kimliği."}

    now = time.time()
    with _PROJECT_DETAIL_LOCK:
        hit = _PROJECT_DETAIL_CACHE.get(safe_slug)
        if hit and (now - hit[0]) < _PROJECT_DETAIL_TTL:
            _PROJECT_DETAIL_CACHE.move_to_end(safe_slug)
            return hit[1]

    try:
        resp = requests.get(
            f"{ModrinthFetcher.BASE_URL}/project/{safe_slug}",
            headers=ModrinthFetcher.HEADERS,
            timeout=8,
        )
        project = resp.json() if resp.status_code == 200 else {}
        if not isinstance(project, dict) or not project:
            msg = f"Modrinth proje bilgisi alınamadı (HTTP {resp.status_code})."
            set_net_error("modrinth_project", Exception(msg))
            log_error(f"Modrinth proje detayı hatası ({safe_slug}): {msg}")
            return {"success": False, "error": msg}

        v_resp = requests.get(
            f"{ModrinthFetcher.BASE_URL}/project/{safe_slug}/version",
            headers=ModrinthFetcher.HEADERS,
            timeout=8,
        )
        raw_versions = v_resp.json() if v_resp.status_code == 200 else []
        if not isinstance(raw_versions, list):
            raw_versions = []

        versions = []
        for v in raw_versions[:40]:
            versions.append({
                "version_number": v.get("version_number") or v.get("name") or "",
                "game_versions": [str(g) for g in (v.get("game_versions") or [])],
                "loaders": [str(l).lower() for l in (v.get("loaders") or [])],
                "date": v.get("date_published") or "",
            })

        # Bagimlilik adlarini en yeni surumden topla, gerekiyorsa toplu sorgula
        latest_deps = (raw_versions[0].get("dependencies") or []) if raw_versions else []
        dep_ids = []
        for dep in latest_deps:
            pid = dep.get("project_id")
            if pid and pid not in dep_ids:
                dep_ids.append(pid)

        dep_names = {}
        for i in range(0, min(len(dep_ids), 60), 20):
            batch = dep_ids[i:i + 20]
            try:
                b = requests.get(
                    f"{ModrinthFetcher.BASE_URL}/projects",
                    params={"ids": json.dumps(batch)},
                    headers=ModrinthFetcher.HEADERS,
                    timeout=8,
                )
                if b.status_code == 200:
                    for item in (b.json() or []):
                        if isinstance(item, dict):
                            dep_names[item.get("id")] = item.get("title") or item.get("slug") or ""
            except Exception:
                pass

        dependencies = []
        seen = set()
        for dep in latest_deps:
            pid = dep.get("project_id") or ""
            dtype = dep.get("dependency_type") or "required"
            key = (pid, dtype)
            if key in seen:
                continue
            seen.add(key)
            dependencies.append({
                "name": dep_names.get(pid) or dep.get("file_name") or pid or "Bilinmeyen",
                "project_id": pid,
                "dependency_type": dtype,
            })

        summary = {
            "success": True,
            "slug": safe_slug,
            "title": project.get("title") or safe_slug,
            "description": project.get("body") or project.get("description") or "",
            "categories": [str(c) for c in (project.get("categories") or [])],
            "icon_url": project.get("icon_url") or "",
            "downloads": project.get("downloads", 0),
            "follows": project.get("followers", 0),
            "source_url": project.get("source_url") or "",
            "versions": versions,
            "dependencies": dependencies,
        }
    except Exception as e:
        set_net_error("modrinth_project", e)
        log_error(f"Modrinth proje detayı başarısız ({safe_slug}): {type(e).__name__}: {e}")
        return {"success": False, "error": f"Modrinth bağlantı hatası: {type(e).__name__}: {e}"}

    with _PROJECT_DETAIL_LOCK:
        _PROJECT_DETAIL_CACHE[safe_slug] = (time.time(), summary)
        while len(_PROJECT_DETAIL_CACHE) > _PROJECT_DETAIL_MAX:
            _PROJECT_DETAIL_CACHE.popitem(last=False)
    return summary


def pick_modpack_version(versions, preferred_game_version=""):
    preferred = clean_minecraft_version(preferred_game_version) if preferred_game_version else ""
    candidates = []
    for v in versions:
        files = v.get("files") or []
        mr_file = next((f for f in files if str(f.get("filename", "")).lower().endswith(".mrpack")), None)
        if not mr_file:
            continue
        gvs = v.get("game_versions") or []
        if preferred and preferred not in gvs:
            continue
        candidates.append((v, mr_file))
    if not candidates and preferred:
        return pick_modpack_version(versions, "")
    return candidates[0] if candidates else (None, None)


def update_instance_config(inst_id, updates):
    inst_dir = get_instance_dir(inst_id)
    if not inst_dir:
        return None
    cfg_path = os.path.join(inst_dir, "instance.json")
    if not os.path.exists(cfg_path):
        return None
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.update(updates)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        cfg["id"] = os.path.basename(inst_dir)
        cfg["mod_count"] = count_instance_mods(cfg["id"])
        return cfg
    except Exception:
        return None


def register_installed_mod(inst_id, slug, filename, version=""):
    """Geriye donuk uyumluluk: mod kaydini icerik manifestine yazar."""
    register_installed_content(inst_id, "mod", slug, filename, version)


# ==================== ICERIK (MOD/SHADER/DOKU) YONETIMI ====================
CATEGORY_DIRS = {
    "mod": "mods",
    "shader": "shaderpacks",
    "resourcepack": "resourcepacks",
}


def normalize_category(category):
    c = str(category or "mod").strip().lower()
    if c in ("shader", "shaderpack", "shaderpacks", "shaders"):
        return "shader"
    if c in ("resourcepack", "resourcepacks", "texturepack", "texturepacks", "texture"):
        return "resourcepack"
    return "mod"


def load_content_manifest(inst_id):
    inst_dir = get_instance_dir(inst_id)
    data = {"mod": {}, "shader": {}, "resourcepack": {}}
    if not inst_dir:
        return data

    path = os.path.join(inst_dir, "content_manifest.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for cat in data:
                    entries = raw.get(cat)
                    if isinstance(entries, dict):
                        data[cat] = entries
        except Exception:
            pass

    # Eski mods_manifest.json dosyasini da birlestir
    legacy = os.path.join(inst_dir, "mods_manifest.json")
    if os.path.exists(legacy):
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for slug, entry in raw.items():
                    data["mod"].setdefault(slug, entry)
        except Exception:
            pass

    return data


def save_content_manifest(inst_id, data):
    inst_dir = get_instance_dir(inst_id)
    if not inst_dir:
        return
    try:
        with open(os.path.join(inst_dir, "content_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def register_installed_content(inst_id, category, slug, filename, version="", project_id="", version_id=""):
    """Profile kurulan mod/shader/doku paketini content_manifest.json'a kaydeder."""
    inst_dir = get_instance_dir(inst_id)
    if not inst_dir or not slug:
        return
    cat = normalize_category(category)
    data = load_content_manifest(inst_id)
    data.setdefault(cat, {})
    entry = {
        "filename": filename,
        "version": version,
        "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if project_id:
        entry["project_id"] = project_id
    if version_id:
        entry["version_id"] = version_id
    data[cat][str(slug)] = entry
    save_content_manifest(inst_id, data)


# ==================== MODRINTH KURULUM INDEKSI ====================
# Per-instance kucuk indeks: {slug: {filename, project_id, version_id}}.
# Eksik bagimlilik taramasinda modlarin Modrinth projesini TAHMIN etmeden
# kesin olarak cozmek icin kurulum aninda yazilir.
MODRINTH_INDEX_FILE = ".modrinth_index.json"


def load_modrinth_index(inst_id):
    inst_dir = get_instance_dir(inst_id)
    if not inst_dir:
        return {}
    path = os.path.join(inst_dir, MODRINTH_INDEX_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}


def save_modrinth_index(inst_id, data):
    inst_dir = get_instance_dir(inst_id)
    if not inst_dir or not isinstance(data, dict):
        return
    try:
        with open(os.path.join(inst_dir, MODRINTH_INDEX_FILE), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def register_modrinth_index(inst_id, slug, filename, project_id="", version_id=""):
    if not inst_id or not slug:
        return
    data = load_modrinth_index(inst_id)
    data[str(slug)] = {
        "filename": filename or "",
        "project_id": project_id or "",
        "version_id": version_id or "",
    }
    save_modrinth_index(inst_id, data)


def unregister_modrinth_index(inst_id, filenames):
    """Verilen dosya adlarina ait indeks kayitlarini temizler."""
    data = load_modrinth_index(inst_id)
    if not data:
        return
    targets = {str(f).lower() for f in (filenames or []) if f}
    if not targets:
        return
    changed = False
    for slug in [s for s, e in data.items()
                 if isinstance(e, dict) and str(e.get("filename", "")).lower() in targets]:
        data.pop(slug, None)
        changed = True
    if changed:
        save_modrinth_index(inst_id, data)


# ==================== MOD BAGIMLILIK COZUCU ====================
DEPENDENCY_MAX_DEPTH = 3


def fetch_modrinth_version(version_id):
    """GET /version/{id}; version nesnesini ya da None dondurur."""
    safe = re.sub(r"[^a-zA-Z0-9\-_]", "", str(version_id or ""))
    if not safe:
        return None
    try:
        resp = requests.get(
            f"{ModrinthFetcher.BASE_URL}/version/{safe}",
            headers=ModrinthFetcher.HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                return data
        set_net_error("modrinth_version", Exception(f"HTTP {resp.status_code}"))
    except Exception as e:
        set_net_error("modrinth_version", e)
        log_error(f"Modrinth sürüm bilgisi alınamadı ({safe}): {type(e).__name__}: {e}")
    return None


def fetch_modrinth_project_versions(project_id, game_version, loader):
    """Projenin MC sürümü + yükleyici ile filtrelenmiş sürümlerini (en yeni önce) döndürür."""
    safe = re.sub(r"[^a-zA-Z0-9\-_]", "", str(project_id or ""))
    if not safe:
        return []
    try:
        params = {
            "game_versions": json.dumps([clean_minecraft_version(game_version)]),
            "loaders": json.dumps([str(loader or "").lower()]),
        }
        resp = requests.get(
            f"{ModrinthFetcher.BASE_URL}/project/{safe}/version",
            params=params,
            headers=ModrinthFetcher.HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
        set_net_error("modrinth_versions", Exception(f"HTTP {resp.status_code}"))
    except Exception as e:
        set_net_error("modrinth_versions", e)
        log_error(f"Modrinth sürüm listesi alınamadı ({safe}): {type(e).__name__}: {e}")
    return []


def fetch_modrinth_projects_batch(project_ids):
    """Proje kimlikleri icin {id: proje} sozlugu dondurur (20'lik gruplar)."""
    result = {}
    ids = [str(i) for i in (project_ids or []) if i]
    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]
        try:
            resp = requests.get(
                f"{ModrinthFetcher.BASE_URL}/projects",
                params={"ids": json.dumps(chunk)},
                headers=ModrinthFetcher.HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                for item in (resp.json() or []):
                    if isinstance(item, dict) and item.get("id"):
                        result[item["id"]] = item
        except Exception as e:
            set_net_error("modrinth_projects", e)
            log_error(f"Modrinth proje toplu sorgusu başarısız: {type(e).__name__}: {e}")
    return result


def _version_primary_file(version):
    files = (version or {}).get("files") or []
    if not files:
        return None
    return next((f for f in files if f.get("primary")), files[0])


def _version_has_game_loader(version, game_version, loader):
    gvs = [str(g) for g in (version.get("game_versions") or [])]
    loaders = [str(l).lower() for l in (version.get("loaders") or [])]
    if clean_minecraft_version(game_version) not in gvs:
        return False
    if loader and str(loader).lower() not in loaders:
        return False
    return True


def resolve_dependency_version(dep, game_version, loader):
    """Bagimlilik kaydini kurulabilir version nesnesine cozer: (version, None) | (None, sebep)."""
    version_id = str(dep.get("version_id") or "").strip()
    if version_id:
        version = fetch_modrinth_version(version_id)
        if not version:
            return None, "sürüm bilgisi alınamadı"
        return version, None

    project_id = str(dep.get("project_id") or "").strip()
    if not project_id:
        return None, "proje kimliği yok"

    for version in fetch_modrinth_project_versions(project_id, game_version, loader):
        if _version_has_game_loader(version, game_version, loader):
            return version, None
    return None, "uygun sürüm yok"


def install_required_dependencies(inst_id, target_dir, game_version, loader,
                                  root_project_id="", root_version_id="", root_slug=""):
    """Ana modun yalnizca 'required' bagimliliklarini ozyinelemeli kurar.

    Derinlik siniri DEPENDENCY_MAX_DEPTH, dongu korumasi project_id tabanli
    visited set ile saglanir. Donen sozluk UI yanitina eklenir.
    """
    result = {
        "installed_dependencies": [],
        "failed_dependencies": [],
        "optional_dependencies": [],
        "skipped_existing": [],
    }
    project_cache = {}
    seen_optional = set()

    index = load_modrinth_index(inst_id)
    installed_pids = set()
    installed_vids = set()
    for entry in index.values():
        if not isinstance(entry, dict):
            continue
        if entry.get("project_id"):
            installed_pids.add(str(entry["project_id"]))
        if entry.get("version_id"):
            installed_vids.add(str(entry["version_id"]))
    installed_files = set()
    if os.path.isdir(target_dir):
        try:
            installed_files = {f.lower() for f in os.listdir(target_dir)}
        except Exception:
            installed_files = set()

    visited = set()
    if root_project_id:
        visited.add(str(root_project_id))

    def project_info(project_id):
        pid = str(project_id or "")
        if not pid:
            return {}
        if pid not in project_cache:
            project_cache[pid] = fetch_modrinth_project(pid) or {}
        return project_cache[pid]

    def already_installed(project_id, version_id, filename):
        pid, vid = str(project_id or ""), str(version_id or "")
        if pid and pid in installed_pids:
            for entry in index.values():
                if isinstance(entry, dict) and str(entry.get("project_id")) == pid:
                    return str(entry.get("filename") or filename or "")
            return filename or ""
        if vid and vid in installed_vids:
            for entry in index.values():
                if isinstance(entry, dict) and str(entry.get("version_id")) == vid:
                    return str(entry.get("filename") or filename or "")
            return filename or ""
        if filename and str(filename).lower() in installed_files:
            return str(filename)
        return None

    def record_optional(dep):
        pid = str(dep.get("project_id") or "")
        if not pid and dep.get("version_id"):
            ver = fetch_modrinth_version(dep["version_id"])
            pid = str((ver or {}).get("project_id") or "")
        if not pid or pid in seen_optional:
            return
        seen_optional.add(pid)
        info = project_info(pid)
        result["optional_dependencies"].append({
            "title": info.get("title") or dep.get("file_name") or pid,
            "slug": info.get("slug") or pid,
        })

    def walk(version, depth):
        for dep in (version or {}).get("dependencies") or []:
            if not isinstance(dep, dict):
                continue
            dtype = str(dep.get("dependency_type") or "required")
            if dtype == "optional":
                record_optional(dep)
                continue
            if dtype != "required":
                continue  # incompatible / embedded atlanir

            project_id = str(dep.get("project_id") or "")
            if project_id and project_id in visited:
                continue  # dongu korumasi

            dep_version, reason = resolve_dependency_version(dep, game_version, loader)
            real_pid = str((dep_version or {}).get("project_id") or project_id)
            if real_pid and real_pid in visited:
                continue

            info = project_info(real_pid) if real_pid else {}
            slug = info.get("slug") or real_pid or dep.get("file_name") or "bilinmeyen"
            title = info.get("title") or slug

            if dep_version is None:
                result["failed_dependencies"].append({"slug": slug, "reason": reason or "uygun sürüm yok"})
                add_log(f"⚠️ Bağımlılık kurulamadı ({slug}): {reason}")
                continue

            if str(info.get("project_type") or dep_version.get("project_type") or "mod") == "modpack":
                add_log(f"ℹ️ Modpack tipi bağımlılık atlandı: {slug}")
                continue

            primary = _version_primary_file(dep_version)
            if not primary or not primary.get("url"):
                result["failed_dependencies"].append({"slug": slug, "reason": "indirilebilir dosya yok"})
                continue

            fname = primary.get("filename") or dep.get("file_name") or ""
            if not fname:
                result["failed_dependencies"].append({"slug": slug, "reason": "dosya adı yok"})
                continue

            existing = already_installed(real_pid, dep_version.get("id"), fname)
            if existing is not None:
                if real_pid:
                    visited.add(real_pid)
                result["skipped_existing"].append({"slug": slug, "filename": existing or fname})
                continue

            dest = os.path.join(target_dir, fname)
            if os.path.exists(dest):
                installed_files.add(fname.lower())
                if real_pid:
                    visited.add(real_pid)
                result["skipped_existing"].append({"slug": slug, "filename": fname})
                continue

            try:
                ModrinthFetcher.download_file(primary["url"], dest)
            except Exception as e:
                set_net_error("modrinth_dependency_download", e)
                log_error(f"Bağımlılık indirme hatası ({slug}): {type(e).__name__}: {e}")
                result["failed_dependencies"].append({"slug": slug, "reason": f"indirme hatası: {e}"})
                continue

            version_number = str(dep_version.get("version_number") or "")
            register_installed_content(
                inst_id, "mod", slug, fname, version_number,
                project_id=real_pid, version_id=str(dep_version.get("id") or ""),
            )
            register_modrinth_index(inst_id, slug, fname, real_pid, str(dep_version.get("id") or ""))
            installed_files.add(fname.lower())
            if real_pid:
                installed_pids.add(real_pid)
                visited.add(real_pid)
            if dep_version.get("id"):
                installed_vids.add(str(dep_version["id"]))
            result["installed_dependencies"].append({
                "title": title,
                "slug": slug,
                "version_number": version_number,
                "filename": fname,
            })
            add_log(f"📥 Bağımlılık kuruldu: {title} ({fname})")

            if depth < DEPENDENCY_MAX_DEPTH:
                walk(dep_version, depth + 1)
            else:
                add_log(f"ℹ️ Bağımlılık derinlik sınırı ({DEPENDENCY_MAX_DEPTH}) aşıldı: {slug}")

    root_version = fetch_modrinth_version(root_version_id) if root_version_id else None
    if root_version is None and root_project_id:
        for candidate in fetch_modrinth_project_versions(root_project_id, game_version, loader):
            if _version_has_game_loader(candidate, game_version, loader):
                root_version = candidate
                break
    if root_version is not None:
        walk(root_version, 1)
    elif root_project_id or root_version_id:
        add_log(f"ℹ️ {root_slug or root_project_id} için bağımlılık bilgisi alınamadı.")
    return result


def compute_missing_dependencies(inst_id):
    """Profilde kurulu modlarin zorunlu bagimliliklarindan eksik olanlari listeler."""
    inst = load_instance_config(inst_id)
    if not inst:
        return {"success": False, "error": "Profil bulunamadı."}

    game_version = clean_minecraft_version(inst.get("version") or "")
    loader = str(inst.get("loader") or "fabric").lower()
    inst_dir = get_instance_dir(inst_id)
    mods_dir = os.path.join(inst_dir, "mods")
    manifest = load_content_manifest(inst_id).get("mod") or {}
    index = load_modrinth_index(inst_id)

    by_filename = {}
    for slug, entry in manifest.items():
        if isinstance(entry, dict) and entry.get("filename"):
            by_filename[str(entry["filename"]).lower()] = (str(slug), entry)

    installed_files = set()
    mod_files = []
    if os.path.isdir(mods_dir):
        try:
            for f in os.listdir(mods_dir):
                fp = os.path.join(mods_dir, f)
                if os.path.isfile(fp) and f.lower().endswith((".jar", ".jar.disabled")):
                    installed_files.add(f.lower())
                    mod_files.append(f)
        except Exception:
            pass

    installed_pids = set()
    installed_vids = set()
    for entry in index.values():
        if isinstance(entry, dict):
            if entry.get("project_id"):
                installed_pids.add(str(entry["project_id"]))
            if entry.get("version_id"):
                installed_vids.add(str(entry["version_id"]))

    unidentified = 0
    checked_pids = set()
    missing_pids = {}

    for fname in mod_files:
        base = fname[:-len(".disabled")] if fname.lower().endswith(".disabled") else fname
        slug_info = by_filename.get(base.lower())
        if not slug_info:
            unidentified += 1  # kurulum kaydi yok: projeyi tahmin etme, atla
            continue
        slug, entry = slug_info
        index_entry = index.get(slug)
        index_entry = index_entry if isinstance(index_entry, dict) else {}
        project_id = str(index_entry.get("project_id") or entry.get("project_id") or "")
        version_id = str(index_entry.get("version_id") or entry.get("version_id") or "")

        if not project_id:
            project = fetch_modrinth_project(slug)
            project_id = str(project.get("id") or "")
        if not project_id:
            unidentified += 1
            continue
        if project_id in checked_pids:
            continue
        checked_pids.add(project_id)
        installed_pids.add(project_id)

        version = fetch_modrinth_version(version_id) if version_id else None
        if version is None:
            candidates = fetch_modrinth_project_versions(project_id, game_version, loader)
            wanted = str(entry.get("version") or "")
            if wanted:
                version = next(
                    (v for v in candidates if str(v.get("version_number") or "") == wanted),
                    None,
                )
            if version is None and candidates:
                version = candidates[0]
        if version is None:
            unidentified += 1
            continue

        for dep in version.get("dependencies") or []:
            if not isinstance(dep, dict):
                continue
            if str(dep.get("dependency_type") or "required") != "required":
                continue
            dep_pid = str(dep.get("project_id") or "")
            dep_vid = str(dep.get("version_id") or "")
            if not dep_pid and dep_vid:
                dep_version = fetch_modrinth_version(dep_vid)
                if dep_version:
                    dep_pid = str(dep_version.get("project_id") or "")
            if not dep_pid:
                continue
            if dep_pid in installed_pids:
                continue
            if dep_vid and dep_vid in installed_vids:
                continue
            dep_file = str(dep.get("file_name") or "")
            if dep_file and dep_file.lower() in installed_files:
                continue
            missing_pids[dep_pid] = True

    projects = fetch_modrinth_projects_batch(list(missing_pids.keys()))
    missing = []
    for pid in missing_pids:
        info = projects.get(pid) or {}
        missing.append({
            "slug": info.get("slug") or pid,
            "title": info.get("title") or info.get("slug") or pid,
            "project_id": pid,
        })

    return {
        "success": True,
        "instance": inst_id,
        "missing": missing,
        "unidentified": unidentified,
    }


# (dosya_yolu, mtime, boyut) -> meta. OrderedDict + ust sinir (LRU) kullanilir;
# aksi hâlde her guncellenen veya silinen mod icin kalici bir kayit birikir.
_CONTENT_META_CACHE = OrderedDict()
_content_meta_lock = threading.Lock()


def cache_content_metadata(cache_key, meta):
    """Meta onbellegine yazar; sinir asilinca once silinmis dosyalarin
    kayitlarini, yetmezse en eski girdileri temizler."""
    with _content_meta_lock:
        _CONTENT_META_CACHE.pop(cache_key, None)
        _CONTENT_META_CACHE[cache_key] = meta
        if len(_CONTENT_META_CACHE) > CONTENT_META_CACHE_MAX:
            for k in [k for k in _CONTENT_META_CACHE if not os.path.exists(k[0])]:
                _CONTENT_META_CACHE.pop(k, None)
            while len(_CONTENT_META_CACHE) > CONTENT_META_CACHE_MAX:
                _CONTENT_META_CACHE.popitem(last=False)


def read_content_metadata(file_path, category):
    """
    Jar/zip iceriginden gorunen mod adi, mod id, aciklama ve ikon girdisini cikarir.
    Fabric (fabric.mod.json), Quilt (quilt.mod.json), Forge/NeoForge (META-INF/mods.toml)
    ve doku paketleri (pack.mcmeta / pack.png) desteklenir. Sonuc (mtime,size) ile onbelleklenir.
    """
    try:
        st = os.stat(file_path)
        cache_key = (file_path, int(st.st_mtime), st.st_size)
    except OSError:
        return {}

    with _content_meta_lock:
        cached = _CONTENT_META_CACHE.get(cache_key)
        if cached is not None:
            _CONTENT_META_CACHE.move_to_end(cache_key)
    if cached is not None:
        return cached

    meta = {
        "display_name": "",
        "mod_id": "",
        "version": "",
        "description": "",
        "icon_entry": "",
        "has_icon": False,
    }

    try:
        import zipfile
        with zipfile.ZipFile(file_path) as zf:
            names = set(zf.namelist())

            if category == "mod":
                if "fabric.mod.json" in names:
                    try:
                        data = json.loads(zf.read("fabric.mod.json").decode("utf-8", "replace"))
                    except Exception:
                        data = {}
                    if isinstance(data, dict):
                        meta["mod_id"] = str(data.get("id") or "")
                        meta["display_name"] = str(data.get("name") or data.get("id") or "")
                        meta["version"] = str(data.get("version") or "")
                        desc = data.get("description")
                        if isinstance(desc, str):
                            meta["description"] = desc
                        icon = data.get("icon")
                        if isinstance(icon, dict) and icon:
                            try:
                                icon = icon.values()
                                icon = sorted(icon, key=lambda v: len(str(v)))[0]
                            except Exception:
                                icon = ""
                        if isinstance(icon, str):
                            meta["icon_entry"] = icon.lstrip("/")
                elif "quilt.mod.json" in names:
                    try:
                        data = json.loads(zf.read("quilt.mod.json").decode("utf-8", "replace"))
                    except Exception:
                        data = {}
                    loader_meta = (data.get("quilt_loader") or {}) if isinstance(data, dict) else {}
                    qmeta = loader_meta.get("metadata") or {}
                    meta["mod_id"] = str(loader_meta.get("id") or "")
                    meta["display_name"] = str(qmeta.get("name") or loader_meta.get("id") or "")
                    meta["version"] = str(loader_meta.get("version") or "")
                    if isinstance(qmeta.get("description"), str):
                        meta["description"] = qmeta.get("description")
                    if isinstance(qmeta.get("icon"), str):
                        meta["icon_entry"] = qmeta.get("icon").lstrip("/")

                if not meta["display_name"] and "META-INF/mods.toml" in names:
                    text = zf.read("META-INF/mods.toml").decode("utf-8", "replace")
                    m = re.search(r'displayName\s*=\s*["\']([^"\']+)["\']', text)
                    if m:
                        meta["display_name"] = m.group(1)
                    m = re.search(r'modId\s*=\s*["\']([^"\']+)["\']', text)
                    if m:
                        meta["mod_id"] = m.group(1)
                    m = re.search(r'logoFile\s*=\s*["\']([^"\']+)["\']', text)
                    if m:
                        meta["icon_entry"] = m.group(1).lstrip("/")
                    m = re.search(r'description\s*=\s*["\']([^"\']+)["\']', text)
                    if m:
                        meta["description"] = m.group(1)
                    m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', text, re.M)
                    if m:
                        meta["version"] = m.group(1)

                if not meta["icon_entry"] and meta["mod_id"]:
                    for cand in (
                        f"assets/{meta['mod_id']}/icon.png",
                        f"assets/{meta['mod_id']}/logo.png",
                        "icon.png",
                    ):
                        if cand in names:
                            meta["icon_entry"] = cand
                            break

            elif category == "resourcepack":
                if "pack.png" in names:
                    meta["icon_entry"] = "pack.png"
                if "pack.mcmeta" in names:
                    try:
                        mcmeta = json.loads(zf.read("pack.mcmeta").decode("utf-8", "replace"))
                        desc = (mcmeta.get("pack") or {}).get("description")
                        if isinstance(desc, dict):
                            desc = desc.get("text") or desc.get("translate") or ""
                        if desc:
                            meta["display_name"] = str(desc)[:80]
                            meta["description"] = str(desc)
                    except Exception:
                        pass

            meta["has_icon"] = bool(meta["icon_entry"] and meta["icon_entry"] in names)
    except Exception:
        pass

    cache_content_metadata(cache_key, meta)
    return meta


def extract_content_icon(file_path, category, meta):
    """Icerikten ikon baytlarini ve MIME tipini dondurur."""
    entry = (meta or {}).get("icon_entry") or ""
    if not entry and category == "resourcepack":
        entry = "pack.png"
    if not entry:
        return None, None

    try:
        import zipfile
        with zipfile.ZipFile(file_path) as zf:
            if entry not in zf.namelist():
                return None, None
            raw = zf.read(entry)
    except Exception:
        return None, None

    if not raw:
        return None, None

    lower = entry.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return raw, "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return raw, "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return raw, "image/jpeg"
    return None, None


def get_instance_content(inst_id):
    """Profilin mods / shaderpacks / resourcepacks icerigini listeler."""
    inst_dir = get_instance_dir(inst_id)
    manifest = load_content_manifest(inst_id)
    content = {}

    for cat, subdir in CATEGORY_DIRS.items():
        files = []
        by_filename = {}
        for slug, entry in (manifest.get(cat) or {}).items():
            if isinstance(entry, dict) and entry.get("filename"):
                by_filename[str(entry["filename"]).lower()] = (slug, entry.get("version", ""))

        folder = os.path.join(inst_dir, subdir) if inst_dir else None
        if folder and os.path.isdir(folder):
            try:
                for f in sorted(os.listdir(folder)):
                    fp = os.path.join(folder, f)
                    is_dir = os.path.isdir(fp)
                    if not is_dir and not os.path.isfile(fp):
                        continue
                    try:
                        st = os.stat(fp)
                    except OSError:
                        continue

                    # Devre disi icerikler <ad>.disabled olarak durur
                    enabled = not f.lower().endswith(".disabled")
                    base_name = f[:-len(".disabled")] if not enabled else f
                    slug, version = by_filename.get(base_name.lower(), ("", ""))

                    item = {
                        "name": f,
                        "enabled": enabled,
                        "is_dir": is_dir,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "slug": slug,
                        "version": version,
                        "display_name": "",
                        "mod_id": "",
                        "description": "",
                        "has_icon": False,
                    }

                    # Mod ve doku paketlerinde gorunen ad / ikon bilgisini dosyadan cikar
                    # (devre disi olsa bile zip okunabilir; temel ad uzerinden bakilir)
                    if (not is_dir) and base_name.lower().endswith((".jar", ".zip")):
                        meta = read_content_metadata(fp, cat)
                        item["display_name"] = meta.get("display_name", "")
                        item["mod_id"] = meta.get("mod_id", "")
                        item["description"] = meta.get("description", "")
                        item["has_icon"] = bool(meta.get("has_icon"))
                        if not version and meta.get("version"):
                            item["version"] = meta.get("version")

                    files.append(item)
            except Exception:
                pass

        content[cat] = {"dir": subdir, "files": files}

    return content


def delete_instance_content(inst_id, category, name):
    """Profildeki tek bir icerik dosyasini siler ve manifesti gunceller."""
    inst_dir = get_instance_dir(inst_id)
    if not inst_dir:
        return False, "Profil bulunamadı."

    raw_name = str(name or "").strip()
    safe = os.path.basename(raw_name)
    if not safe or safe != raw_name:
        return False, "Geçersiz dosya adı."

    cat = normalize_category(category)
    target = os.path.join(inst_dir, CATEGORY_DIRS[cat], safe)
    if os.path.isdir(target):
        try:
            shutil.rmtree(target)
        except Exception as e:
            return False, f"Klasör silinemedi: {e}"
    elif os.path.isfile(target):
        try:
            os.remove(target)
        except Exception as e:
            return False, f"Dosya silinemedi: {e}"
    else:
        return False, "Dosya bulunamadı."

    data = load_content_manifest(inst_id)
    entries = data.get(cat) or {}
    safe_lower = safe.lower()
    base_lower = safe_lower[:-len(".disabled")] if safe_lower.endswith(".disabled") else safe_lower
    for slug in [s for s, e in entries.items()
                 if isinstance(e, dict) and str(e.get("filename", "")).lower() in (safe_lower, base_lower)]:
        entries.pop(slug, None)
    save_content_manifest(inst_id, data)
    unregister_modrinth_index(inst_id, [safe_lower, base_lower])
    return True, safe


def toggle_instance_content(inst_id, category, name):
    """Icerigi etkinlestirir/devre disi birakir: <ad> <-> <ad>.disabled.

    Mod, doku paketi ve shader dosyalari ile shader klasorlerini destekler.
    Donen: (basarili, dosya_adi_veya_hata, etkin_mi)
    """
    inst_dir = get_instance_dir(inst_id)
    if not inst_dir:
        return False, "Profil bulunamadı.", False

    raw_name = str(name or "").strip()
    safe = os.path.basename(raw_name)
    if not safe or safe != raw_name or safe in (".", ".."):
        return False, "Geçersiz dosya adı.", False

    cat = normalize_category(category)
    folder = os.path.join(inst_dir, CATEGORY_DIRS[cat])
    src = os.path.join(folder, safe)
    if not os.path.exists(src):
        return False, "İçerik bulunamadı.", False

    try:
        if safe.lower().endswith(".disabled"):
            target_name = safe[:-len(".disabled")]
            if not target_name:
                return False, "Geçersiz dosya adı.", False
            target = os.path.join(folder, target_name)
            if os.path.exists(target):
                return False, f"'{target_name}' zaten etkin.", False
            os.rename(src, target)
            return True, target_name, True

        target_name = safe + ".disabled"
        target = os.path.join(folder, target_name)
        if os.path.exists(target):
            return False, f"'{target_name}' zaten devre dışı.", False
        os.rename(src, target)
        return True, target_name, False
    except Exception as e:
        return False, f"İçerik güncellenemedi: {e}", False


def get_instance_mod_manifest(inst_id):
    """Geriye donuk uyumluluk: mod manifesti + jar dosya adlari."""
    content = get_instance_content(inst_id)
    manifest = load_content_manifest(inst_id).get("mod", {})
    files = [f["name"] for f in content.get("mod", {}).get("files", [])]
    return manifest, files


def install_modpack_background(inst_id, pack_url):
    add_log(f"📦 Modpack profili kuruluyor: {inst_id}")
    tmp_path = os.path.join(APP_DATA_DIR, f"tmp_{inst_id}.mrpack")
    update_instance_config(inst_id, {
        "install_status": "installing",
        "install_progress": 3,
        "install_detail": "Paket indiriliyor...",
    })

    try:
        ModrinthFetcher.download_file(pack_url, tmp_path)
    except Exception as e:
        update_instance_config(inst_id, {"install_status": "failed", "install_detail": f"Paket indirilemedi: {e}"})
        add_log(f"Modpack indirme hatasi ({inst_id}): {e}")
        return

    tracker = {"max": 100, "val": 0, "last_pct": -10}
    inst_dir = get_instance_dir(inst_id)

    def push_progress(force=False):
        pct = int((tracker["val"] / max(1, tracker["max"])) * 100)
        if force or abs(pct - tracker["last_pct"]) >= 3:
            tracker["last_pct"] = pct
            update_instance_config(inst_id, {"install_progress": min(99, max(1, pct))})

    def set_status(s):
        update_instance_config(inst_id, {"install_detail": translate_status(str(s))})

    def set_progress(p):
        try:
            tracker["val"] = int(p)
        except Exception:
            tracker["val"] = 0
        push_progress()

    def set_max(m):
        try:
            tracker["max"] = max(1, int(m))
        except Exception:
            tracker["max"] = 1
        tracker["val"] = 0
        push_progress(force=True)

    callback = {"setStatus": set_status, "setProgress": set_progress, "setMax": set_max}

    try:
        minecraft_launcher_lib.mrpack.install_mrpack(
            tmp_path,
            minecraft_directory,
            modpack_directory=inst_dir,
            callback=callback,
        )
        launch_version = ""
        try:
            launch_version = minecraft_launcher_lib.mrpack.get_mrpack_launch_version(tmp_path) or ""
        except Exception as e:
            add_log(f"Modpack baslatma surumu okunamadi: {e}")
        update_instance_config(inst_id, {
            "install_status": "ready",
            "install_progress": 100,
            "install_detail": "Hazır",
            "launch_version": launch_version,
        })
        add_log(f"✓ Modpack kuruldu: {inst_id} (başlatma sürümü: {launch_version or 'yok'})")
    except Exception as e:
        update_instance_config(inst_id, {"install_status": "failed", "install_detail": str(e)})
        add_log(f"Modpack kurulum hatasi ({inst_id}): {e}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


# ==================== MOJANG SURUMLER MANIFESTI ====================
def set_net_error(where, exc):
    """Son ag hatasini kaydeder (UI ve /api/net-test bunu gosterebilir)."""
    global NET_LAST_ERROR
    NET_LAST_ERROR = {
        "where": where,
        "error": f"{type(exc).__name__}: {exc}",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return NET_LAST_ERROR


def get_complete_version_manifest():
    """Mojang manifestini ceker; ag hatasinda onbellek, olmazsa küratör listeye duser."""
    global LAST_MANIFEST_ERROR
    try:
        url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Freesm/CookieLauncher/2.0.0"})
        # macOS'ta sistem kok sertifikalari bulunamazsa burasi patlar; certifi
        # tabanli SSL_CONTEXT ile dogru CA demeti kullanilir.
        with urllib.request.urlopen(req, timeout=8, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode())
            items = []
            for item in data.get("versions", []):
                vid = item["id"]
                items.append({
                    "id": vid,
                    "type": item.get("type", "release"),
                    "releaseTime": item.get("releaseTime", ""),
                    "is_optimized": is_version_cookie_optimized(vid),
                })
        if items:
            try:
                with open(VERSIONS_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(items, f, indent=2)
            except Exception:
                pass
            LAST_MANIFEST_ERROR = ""
            return items
    except Exception as e:
        LAST_MANIFEST_ERROR = f"{type(e).__name__}: {e}"
        set_net_error("mojang_manifest", e)
        log_error(
            f"Mojang sürüm manifesti çekilemedi ({LAST_MANIFEST_ERROR}). "
            f"Python: {sys.version.split()[0]} | certifi: {CERTIFI_PATH or 'YOK'} | platform: {sys.platform}"
        )

    if os.path.exists(VERSIONS_CACHE_FILE):
        try:
            with open(VERSIONS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass

    fallback = []
    for r in FALLBACK_CURATED_RELEASES:
        fallback.append({
            "id": r,
            "type": "release",
            "releaseTime": "",
            "is_optimized": is_version_cookie_optimized(r),
        })
    return fallback


def run_net_selftest():
    """Dis API'lere gercek baglanti testi.

    macOS'ta "listeler bos geliyor" sorununu tek istekte teshis etmek icin:
    hem requests (certifi) hem urllib yolunu dener ve tam hata metnini doner.
    """
    targets = [
        ("modrinth", "https://api.modrinth.com/v2/tag/game_version"),
        ("mojang_piston", "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"),
        ("mojang_launchermeta", "https://launchermeta.mojang.com/mc/game/version_manifest.json"),
        ("fabric_meta", "https://meta.fabricmc.net/v2/versions/loader"),
    ]
    results = []
    for name, url in targets:
        t0 = time.time()
        entry = {"name": name, "url": url}
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Freesm/CookieLauncher/2.0.0"})
            entry["ok"] = r.status_code == 200
            entry["http"] = r.status_code
        except Exception as e:
            entry["ok"] = False
            entry["error"] = f"{type(e).__name__}: {e}"
        entry["ms"] = int((time.time() - t0) * 1000)
        results.append(entry)

    # Mojang manifesti urllib ile cekiliyor: onu da ayrica test et
    urllib_entry = {"name": "urllib_piston", "url": targets[1][1]}
    try:
        req = urllib.request.Request(targets[1][1], headers={"User-Agent": "Freesm/CookieLauncher/2.0.0"})
        with urllib.request.urlopen(req, timeout=8, context=SSL_CONTEXT) as resp:
            urllib_entry["ok"] = getattr(resp, "status", 200) == 200
            urllib_entry["http"] = getattr(resp, "status", 200)
    except Exception as e:
        urllib_entry["ok"] = False
        urllib_entry["error"] = f"{type(e).__name__}: {e}"
    results.append(urllib_entry)

    return {
        "success": True,
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "certifi": CERTIFI_PATH or None,
        "ssl_source": "certifi" if CERTIFI_PATH else "system",
        "last_error": NET_LAST_ERROR,
        "manifest_error": LAST_MANIFEST_ERROR,
        "results": results,
    }


# ==================== OYUN BASLATMA THREADI (NON-BLOCKING) ====================
def run_game_background_task(params):
    """
    Uzun suren indirme/kurulum/baslatma islerinin tamami burada, arka planda calisir.
    HTTP istegi bu fonksiyonu beklemez; aninda 200 OK donulmustur.
    """
    add_log("🚀 Arka plan başlatma görevi başladı.")

    try:
        username = (params.get("username") or "Steve").strip() or "Steve"
        # Profil secilmeden ve acik bir surum verilmeden baslatma YOK.
        # Aksi hâlde global .minecraft klasorune rastgele bir surum indirilip
        # oyun baslatiliyordu (kullanicinin "profil yokken 26.3 indirdi" hatasi).
        if not str(params.get("instance_id") or "").strip() and not str(params.get("version") or "").strip():
            raise RuntimeError(
                "Profil seçilmedi. Başlatmak için önce bir profil oluşturun veya seçin."
            )
        raw_version = str(params.get("version") or "").strip()
        loader = (params.get("loader") or "fabric").lower()
        cookie_opt = params.get("cookie_optimized", True)
        ram_gb = int(params.get("ram", get_optimal_ram_allocation()))
        custom_java = (params.get("custom_java") or "").strip()
        jvm_preset = params.get("jvm_preset", "aikar")

        clean_v = clean_minecraft_version(raw_version)
        if not clean_v:
            clean_v = "1.20.4"

        # 1. Gercek Surum Izolasyonu (Prism Launcher / MultiMC Mimarisi)
        # Profil seciliyse surum/loader profil config'inden okunur; modlar profile kurulur.
        instance_id = params.get("instance_id")
        pack_launch_version = ""
        loader_version = ""
        if instance_id:
            inst_cfg = load_instance_config(instance_id)
            if not inst_cfg:
                raise RuntimeError("Seçili profil bulunamadı. Lütfen profili yeniden seçin.")
            instance_id = inst_cfg.get("id")
            clean_v = clean_minecraft_version(inst_cfg.get("version") or clean_v)
            loader = (inst_cfg.get("loader") or loader).lower()
            pack_launch_version = str(inst_cfg.get("launch_version") or "").strip()
            loader_version = str(inst_cfg.get("loader_version") or "").strip()
            if inst_cfg.get("install_status") == "installing":
                raise RuntimeError("Bu profil hâlâ kuruluyor. Lütfen kurulum tamamlanana kadar bekleyin.")
            game_dir = os.path.join(INSTANCES_DIR, instance_id)
            mods_dir = os.path.join(game_dir, "mods")
            add_log(f"🗂️ Profil: {inst_cfg.get('name')} (MC {clean_v} • {loader})")
        else:
            game_dir = minecraft_directory
            mods_dir = os.path.join(minecraft_directory, "mods", clean_v)

        os.makedirs(game_dir, exist_ok=True)
        os.makedirs(mods_dir, exist_ok=True)

        quarantine_root_mods()

        add_log(f"🚀 Başlatma Talebi: Sürüm: {clean_v} | Yükleyici: {loader} | RAM: {ram_gb} GB | Optimize: {cookie_opt}")
        add_log(f"📁 İzole Mod Klasörü: {mods_dir}")

        # 2. Vanilla Minecraft Dosyalarini Dogrula / Indir
        update_state(
            status=f"Minecraft {clean_v} indiriliyor/doğrulanıyor...",
            detail="Mojang sunucularından kütüphaneler ve varlıklar senkronize ediliyor...",
            percent=15,
            progress=0.15,
        )
        try:
            minecraft_launcher_lib.install.install_minecraft_version(
                clean_v, minecraft_directory, callback=make_progress_callbacks(15, 50)
            )
        except minecraft_launcher_lib.exceptions.VersionNotFound:
            raise RuntimeError(
                f"Minecraft '{clean_v}' sürümü bulunamadı. Lütfen sürüm adını kontrol edin (örn: 1.20.4)."
            )
        except Exception as install_error:
            raise RuntimeError(f"Minecraft {clean_v} indirilemedi/doğrulanamadı: {install_error}")

        version_to_run = clean_v

        # Modpack profilleri kendi yukleyici sürümünü zaten kurmuştur
        if pack_launch_version:
            version_to_run = pack_launch_version
            add_log(f"📦 Modpack başlatma sürümü kullanılıyor: {version_to_run}")

        # 3. Java Runtime Cozumu (Surume ozel dogru Java surumu)
        update_state(
            status=f"Java {clean_v} için doğrulanıyor...",
            detail="Minecraft ile uyumlu Java çalışma ortamı hazırlanıyor...",
            percent=66,
            progress=0.66,
        )
        java_exec = resolve_java_executable(
            version_to_run, custom_java=custom_java, callback=make_progress_callbacks(5, 10)
        )
        add_log(f"Seçilen Java Yürütücüsü: {java_exec}")

        # 4. Yukleyici Kurulumu (Fabric / Forge / NeoForge / Quilt) - modpack ise zaten kurulu
        #    Birlesik mod_loader API'si kullanilir: profil icin kayitli loader surumu
        #    varsa o, yoksa bu Minecraft surumu icin ONERILEN (stable) surum kurulur.
        if not pack_launch_version and loader in ("fabric", "forge", "neoforge", "quilt"):
            loader_label = LOADER_LABELS.get(loader, loader.capitalize())
            update_state(
                status=f"{loader_label} yükleyicisi ({clean_v}) hazırlanıyor...",
                detail=f"{loader_label} kütüphaneleri kuruluyor...",
                percent=72,
                progress=0.72,
            )
            try:
                ml = minecraft_launcher_lib.mod_loader.get_mod_loader(loader)
                # Yukleyicinin kabul ettigi MC surum adi (orn. NeoForge 26.3 -> 1.26.3)
                loader_mc = resolve_loader_mc_version(ml, clean_v)
                lv = loader_version
                if not lv and loader_mc:
                    try:
                        lv = ml.get_latest_loader_version(loader_mc) or ""
                    except Exception:
                        lv = ""
                if lv:
                    add_log(f"{loader_label} {lv} kuruluyor (MC {clean_v})...")
                else:
                    add_log(f"{loader_label}: önerilen sürüm bulunamadı, kütüphane varsayılanı denenecek.")
                installed_id = install_loader_version(
                    ml,
                    clean_v,
                    minecraft_directory,
                    lv,
                    make_progress_callbacks(70, 10),
                    java_exec,
                )
                if installed_id:
                    version_to_run = installed_id
                elif lv:
                    fallback_id = ml.get_installed_version(clean_v, lv)
                    if fallback_id:
                        version_to_run = fallback_id
                add_log(f"{loader_label} hazır: {version_to_run}")
            except Exception as le:
                add_log(f"{loader_label} kurulum uyarısı: {le}. Vanilla ile devam ediliyor.")
                version_to_run = clean_v

        # 5. COOKIE LAUNCHER OZEL OPTIMIZE ENJEKTORU
        if cookie_opt:
            update_state(
                status="⚡ Cookie Launcher Optimize Modları Kontrol Ediliyor...",
                detail="Sürüme özel optimize modlar senkronize ediliyor...",
                percent=85,
                progress=0.85,
            )
            inject_cookie_optimization_mods(clean_v, mods_dir, loader=loader)
            update_state(percent=94, progress=0.94)

        # 6. Fullbright (Maksimum Parlaklik) Ayari
        try:
            options_path = os.path.join(game_dir, "options.txt")
            if os.path.exists(options_path):
                with open(options_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "gamma:" in content:
                    content = re.sub(r"gamma:[^\n]+", "gamma:100.0", content)
                else:
                    content += "\ngamma:100.0\n"
                with open(options_path, "w", encoding="utf-8") as f:
                    f.write(content)
        except Exception:
            pass

        # 7. JVM Argumanlari
        jvm_args = [
            f"-Xmx{ram_gb}G",
            f"-Xms{max(1, ram_gb // 2)}G",
        ]

        if jvm_preset == "aikar":
            jvm_args.extend([
                "-XX:+UseG1GC",
                "-XX:+ParallelRefProcEnabled",
                "-XX:MaxGCPauseMillis=200",
                "-XX:+UnlockExperimentalVMOptions",
                "-XX:+DisableExplicitGC",
                "-XX:+AlwaysPreTouch",
                "-XX:G1NewSizePercent=30",
                "-XX:G1MaxNewSizePercent=40",
                "-XX:G1ReservePercent=20",
                "-XX:G1HeapWastePercent=5",
                "-XX:G1MixedGCCountTarget=4",
                "-XX:InitiatingHeapOccupancyPercent=15",
                "-XX:G1MixedGCLiveThresholdPercent=90",
                "-XX:G1RSetUpdatingPauseTimePercent=5",
                "-XX:SurvivorRatio=32",
            ])

        # Fabric loader icin mod klasorunu KESINLIKLE izole et
        if loader == "fabric":
            jvm_args.append(f"-Dfabric.modsFolder={mods_dir}")

        options = {
            "username": username,
            "uuid": "00000000-0000-0000-0000-000000000000",
            "token": "0",
            "gameDirectory": game_dir,
            "jvmArguments": jvm_args,
            "executablePath": java_exec,
            "launcherName": "CookieLauncher",
            "launcherVersion": "2.0.0",
        }

        update_state(
            status="Oyun komutu oluşturuluyor...",
            detail="Başlatma argümanları hazırlanıyor...",
            percent=97,
            progress=0.97,
        )
        command = minecraft_launcher_lib.command.get_minecraft_command(version_to_run, minecraft_directory, options)

        update_state(
            status="🚀 Minecraft Başlatılıyor...",
            detail="Oyun penceresi birazdan açılacak...",
            percent=100,
            progress=1.0,
        )
        add_log(f"Komut çalıştırılıyor: {command[0]}")

        proc = subprocess.Popen(
            command,
            cwd=game_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        update_state(
            is_installing=False,
            is_running=True,
            minecraft_pid=proc.pid,
            status="✨ Oyun Başarıyla Açıldı!",
            detail="İyi oyunlar!",
            error=None,
            started_at=time.time(),
        )

        def log_streamer():
            try:
                for line in iter(proc.stdout.readline, ""):
                    if line:
                        add_log(line.strip())
            except Exception:
                pass
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

            ret = proc.wait()
            with state_lock:
                launch_state["is_running"] = False
                launch_state["is_installing"] = False
                launch_state["minecraft_pid"] = None
                launch_state["progress"] = 0.0
                launch_state["percent"] = 0
                if ret != 0:
                    launch_state["status"] = "Oyun beklenmedik şekilde kapandı."
                    launch_state["detail"] = f"Çıkış kodu: {ret}. Konsol sekmesini kontrol edin."
                    if not launch_state.get("error"):
                        launch_state["error"] = f"Oyun beklenmedik şekilde kapandı (Çıkış kodu: {ret})."
                else:
                    launch_state["status"] = "Oyun kapandı."
                    launch_state["detail"] = ""
            add_log(f"Minecraft süreci kapandı (Çıkış Kodu: {ret})")

        threading.Thread(target=log_streamer, daemon=True).start()

    except Exception as e:
        tb = traceback.format_exc()
        add_log(f"HATA: {e}")
        add_log(tb)
        update_state(
            is_installing=False,
            is_running=False,
            minecraft_pid=None,
            progress=0.0,
            percent=0,
            status="Başlatma Hatası!",
            detail=str(e),
            error=str(e),
        )


# ==================== HTTP REST API SUNUCUSU ====================
class CookieLauncherHTTPHandler(http.server.SimpleHTTPRequestHandler):
    server_version = "CookieLauncherCore/2.0"

    def __init__(self, *args, **kwargs):
        static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
        super().__init__(*args, directory=static_dir, **kwargs)

    def log_message(self, format, *args):
        pass

    # --- CORS: Tauri (tauri://localhost) ve tarayici istemcileri icin zorunlu ---
    def end_headers(self):
        try:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
            self.send_header("Access-Control-Max-Age", "86400")
            self.send_header("Cache-Control", "no-store")
        except Exception:
            pass
        super().end_headers()

    def do_OPTIONS(self):
        # Preflight istegine aninda 204 ile yanit ver (Load Failed kok cozumu)
        self.send_response(204)
        self.end_headers()

    def send_json(self, data, status_code=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        except Exception:
            body = b'{"success": false, "error": "serialization_error"}'
            status_code = 200
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass

    def get_post_body(self):
        try:
            content_len = int(self.headers.get("Content-Length", 0))
        except Exception:
            content_len = 0
        if content_len <= 0:
            return {}
        try:
            post_bytes = self.rfile.read(content_len)
            return json.loads(post_bytes.decode("utf-8"))
        except Exception:
            return {}

    @staticmethod
    def normalize_api_path(path):
        if path.startswith("/api/"):
            return path[4:]
        if path == "/api":
            return "/"
        return path

    def do_GET(self):
        url = urlparse(self.path)
        path = self.normalize_api_path(url.path)
        query = parse_qs(url.query)

        try:
            # 0. Saglik / Surum Kontrolu (eski backend sureclerini ayirt etmek icin)
            if path == "/health":
                self.send_json({
                    "success": True,
                    "app": "CookieLauncher",
                    "version": "2.0.0",
                    "api_version": API_VERSION,
                    "features": ["instances", "modpack", "instance_mods", "content_manage",
                                 "content_icons", "loader_versions", "net_test",
                                 "profile_detail", "content_toggle", "mod_deps"],
                })
                return

            # 0b. Yukleyici (Loader) Surumleri: onerilen + tum surumler
            if path == "/loaders/versions":
                loader_id = (query.get("loader", ["fabric"])[0] or "fabric")
                mc_version = (query.get("version", [""])[0] or "")
                self.send_json(get_loader_version_info(loader_id, mc_version))
                return

            # 0c. Modpack surumleri (Yeni Profil > Mod Paketleri alt bari)
            if path == "/modrinth/pack/versions":
                slug = query.get("slug", [""])[0]
                self.send_json(fetch_modpack_game_versions(slug))
                return

            # 1. Durum Sorgusu
            if path == "/status":
                self.send_json(get_state_snapshot())
                return

            # 2. Canli Konsol Loglari
            if path == "/logs":
                with logs_lock:
                    self.send_json({"success": True, "logs": list(console_logs)})
                return

            # 3. Mojang & Yerel Surum Manifesti (ASLA 500 DONMEZ)
            if path == "/versions":
                versions = []
                installed = []
                try:
                    versions = get_complete_version_manifest()
                except Exception as e:
                    set_net_error("version_manifest", e)
                    log_error(f"Sürüm manifesti hatası: {type(e).__name__}: {e}")

                try:
                    installed = [
                        v["id"] for v in minecraft_launcher_lib.utils.get_installed_versions(minecraft_directory)
                    ]
                except Exception:
                    installed = []

                if not isinstance(versions, list):
                    versions = []

                for v in versions:
                    try:
                        v["is_installed"] = v.get("id") in installed
                    except Exception:
                        pass

                payload = {"success": True, "versions": versions, "installed": installed}
                # Manifest canli cekilemediyse (onbellek/kuratör listeyle
                # idare ediliyorsa) UI bunu kullaniciya soyleyebilsin.
                if LAST_MANIFEST_ERROR:
                    payload["error"] = f"Mojang sürüm listesi güncellenemedi: {LAST_MANIFEST_ERROR}"
                    payload["cached"] = os.path.exists(VERSIONS_CACHE_FILE)
                self.send_json(payload)
                return

            # 3b. Ag teshisi: dis API'lere gercek baglanti testi
            if path == "/net-test":
                self.send_json(run_net_selftest())
                return

            # 4. Modrinth Arama API (ASLA 500 DONMEZ)
            if path == "/modrinth/search":
                try:
                    q = query.get("q", [""])[0]
                    ptype = query.get("type", ["mod"])[0]
                    ver = query.get("version", [""])[0]
                    loader = query.get("loader", [""])[0]
                    sort_idx = query.get("sort", ["downloads"])[0]
                    limit = int(query.get("limit", ["20"])[0])
                    offset = int(query.get("offset", ["0"])[0])
                except Exception:
                    q, ptype, ver, loader, sort_idx, limit, offset = "", "mod", "", "", "downloads", 20, 0

                try:
                    res = ModrinthFetcher.search(
                        query=q, project_type=ptype, game_version=ver,
                        loader=loader, index=sort_idx, limit=limit, offset=offset,
                    )
                except Exception as e:
                    add_log(f"Modrinth arama hatasi (sessizce gecildi): {e}")
                    res = {}

                if not isinstance(res, dict):
                    res = {}
                res.setdefault("hits", [])
                res.setdefault("total_hits", 0)
                res.setdefault("limit", limit)
                res.setdefault("offset", offset)
                res["success"] = True
                self.send_json(res)
                return

            # 4b. Modrinth Proje Detayi (profil detay cekmecesi)
            if path == "/modrinth/project":
                slug = (query.get("slug", [""])[0] or "").strip()
                if not slug:
                    self.send_json({"success": False, "error": "slug gerekli"})
                    return
                self.send_json(fetch_modrinth_project_detail(slug))
                return

            # 4c. Modrinth Surum Uyum Kontrolu (shader/doku icin yumusak)
            if path == "/modrinth/check":
                slug = query.get("slug", [""])[0].strip()
                gv = query.get("version", [""])[0]
                ptype = normalize_category(query.get("type", ["mod"])[0])
                loader = query.get("loader", ["fabric"])[0]

                if not slug:
                    self.send_json({"success": False, "error": "slug gerekli"})
                    return

                info = None
                try:
                    if ptype == "mod":
                        info = ModrinthFetcher.get_latest_mod_jar(slug, gv, loader=loader)
                    else:
                        info = ModrinthFetcher.get_project_file(
                            slug, gv, project_type=ptype, loader=loader, allow_fallback=True
                        )
                except Exception:
                    info = None

                exact = bool(info and (ptype == "mod" or info.get("exact_match")))
                self.send_json({
                    "success": True,
                    "has_file": bool(info),
                    "exact_match": exact,
                    "matched_game_version": (info.get("game_versions") or [""])[0] if info else "",
                    "filename": (info or {}).get("filename", ""),
                })
                return

            # 5. Oyun Ici Ekran Goruntuleri
            if path == "/screenshots":
                sc_dir = os.path.join(minecraft_directory, "screenshots")
                shots = []
                if os.path.exists(sc_dir):
                    for f in sorted(os.listdir(sc_dir), reverse=True):
                        if f.lower().endswith(".png"):
                            fp = os.path.join(sc_dir, f)
                            try:
                                st = os.stat(fp)
                                shots.append({"name": f, "size": st.st_size, "mtime": st.st_mtime})
                            except Exception:
                                pass
                self.send_json({"success": True, "screenshots": shots})
                return

            # 6. Instances (Profiller) Listesi
            if path == "/instances":
                self.send_json({"success": True, "instances": list_instances()})
                return

            # 6b. Profildeki Kurulu Modlar (manifest + jar dosyalari)
            if path == "/instances/mods":
                inst_id = query.get("instance_id", [""])[0]
                manifest, files = get_instance_mod_manifest(inst_id)
                self.send_json({
                    "success": True,
                    "instance_id": inst_id,
                    "manifest": manifest,
                    "files": files,
                })
                return

            # 6c. Profildeki Tum Icerik (mod / shader / doku paketi)
            if path == "/instances/content":
                inst_id = query.get("instance_id", [""])[0] or query.get("instance", [""])[0]
                self.send_json({
                    "success": True,
                    "instance_id": inst_id,
                    "categories": get_instance_content(inst_id),
                })
                return

            # 6c-2. Profildeki Eksik Zorunlu Mod Bagimliliklari
            if path == "/instances/missing-deps":
                inst_id = query.get("instance", [""])[0] or query.get("instance_id", [""])[0]
                self.send_json(compute_missing_dependencies(inst_id))
                return

            # 6d. Icerik Ikonu (jar/zip icinden cikarilir)
            if path == "/instances/content/icon":
                inst_id = query.get("instance_id", [""])[0] or query.get("instance", [""])[0]
                category = query.get("category", ["mod"])[0]
                raw_name = query.get("name", [""])[0].strip()
                safe = os.path.basename(raw_name)
                inst_dir = get_instance_dir(inst_id)
                cat = normalize_category(category)

                if not inst_dir or not safe or safe != raw_name:
                    self.send_json({"success": False, "error": "Geçersiz istek."}, 404)
                    return

                fp = os.path.join(inst_dir, CATEGORY_DIRS[cat], safe)
                if not os.path.isfile(fp):
                    self.send_json({"success": False, "error": "Dosya bulunamadı."}, 404)
                    return

                icon_meta = read_content_metadata(fp, cat)
                raw, mime = extract_content_icon(fp, cat, icon_meta)
                if not raw:
                    self.send_json({"success": False, "error": "İkon bulunamadı."}, 404)
                    return

                try:
                    self.send_response(200)
                    self.send_header("Content-Type", mime or "image/png")
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            # Bilinmeyen /api yollari JSON 404 dondurur (HTML degil!)
            if path.startswith("/api") or url.path.startswith("/api"):
                self.send_json({"success": False, "error": "Bilinmeyen API yolu"}, 404)
                return
        except Exception as e:
            add_log(f"GET isleme hatasi ({url.path}): {e}")
            try:
                self.send_json({"success": False, "error": str(e)})
            except Exception:
                pass
            return

        # Statik Dosyalari Sun (HTML, CSS, JS)
        try:
            super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        url = urlparse(self.path)
        path = self.normalize_api_path(url.path)

        try:
            body = self.get_post_body()

            # 1. Non-Blocking Oyun Baslatma (ANINDA 200 OK doner!)
            if path in ("/launch", "/launch/"):
                instance_id = body.get("instance_id")
                if instance_id and not load_instance_config(instance_id):
                    self.send_json({
                        "success": False,
                        "error": "Seçili profil bulunamadı. Lütfen profili yeniden seçin.",
                    })
                    return

                with state_lock:
                    already_busy = bool(launch_state["is_installing"] or launch_state["is_running"])
                if already_busy:
                    self.send_json({
                        "success": False,
                        "error": "Oyun zaten çalışıyor veya hazırlanıyor. Lütfen bekleyin.",
                    })
                    return

                # Durumu HTTP handler icinde senkron olarak isaretle:
                # Boylece frontend polling'i ilk turda bile 'is_installing' gorur.
                with state_lock:
                    launch_state.update({
                        "is_installing": True,
                        "is_running": False,
                        "progress": 0.02,
                        "percent": 2,
                        "status": "Başlatma isteği alındı...",
                        "detail": "Arka plan iş parçacığı hazırlanıyor...",
                        "current_file": "",
                        "downloaded_bytes": 0,
                        "downloaded_mb": 0.0,
                        "error": None,
                        "minecraft_pid": None,
                        "started_at": time.time(),
                    })

                threading.Thread(target=run_game_background_task, args=(body,), daemon=True).start()
                add_log("✓ /api/launch istegi alindi, islem arka plan thread'ine devredildi.")
                self.send_json({
                    "success": True,
                    "status": "started",
                    "message": "Oyun hazırlama süreci arka planda başarıyla başlatıldı.",
                })
                return

            # 2. Modrinth Icerik Kurulumu (mod / shader / doku paketi)
            if path in ("/modrinth/install", "/modrinth/install/"):
                slug = (body.get("slug") or "").strip()
                raw_ver = (body.get("version") or "1.20.4").strip()
                loader = (body.get("loader") or "fabric").lower()
                instance_id = body.get("instance_id")
                project_type = normalize_category(body.get("project_type") or body.get("content_type") or "mod")
                force = bool(body.get("force"))
                install_dependencies = bool(body.get("install_dependencies"))
                category_dir = CATEGORY_DIRS[project_type]

                if not slug:
                    self.send_json({"success": False, "error": "İçerik kimliği (slug) belirtilmedi."})
                    return

                clean_v = clean_minecraft_version(raw_ver)
                target_label = "Genel .minecraft"

                if instance_id:
                    inst = load_instance_config(instance_id)
                    if not inst:
                        self.send_json({"success": False, "error": "Hedef profil bulunamadı."})
                        return
                    clean_v = clean_minecraft_version(inst.get("version") or raw_ver)
                    loader = (inst.get("loader") or loader).lower()
                    target_dir = os.path.join(get_instance_dir(instance_id), category_dir)
                    target_label = f"{inst.get('name')} profili (MC {clean_v} • {loader})"
                else:
                    if project_type == "mod":
                        target_dir = os.path.join(minecraft_directory, "mods", clean_v)
                        target_label = f"Genel .minecraft (MC {clean_v})"
                    else:
                        target_dir = os.path.join(minecraft_directory, category_dir)

                os.makedirs(target_dir, exist_ok=True)

                try:
                    info = None

                    if project_type == "mod":
                        curated_key = (clean_v, loader)
                        if curated_key in CURATED_OPTIMIZATION_MAP:
                            for item in CURATED_OPTIMIZATION_MAP[curated_key]:
                                if item["slug"] == slug:
                                    info = item
                                    break
                        if not info:
                            info = ModrinthFetcher.get_latest_mod_jar(slug, clean_v, loader=loader)
                    else:
                        # shader / doku paketi: tam eslesme yoksa en yeni surume dus
                        info = ModrinthFetcher.get_project_file(
                            slug, clean_v, project_type=project_type, loader=loader, allow_fallback=True
                        )

                    if not info or not info.get("url"):
                        type_label = {
                            "mod": "modu",
                            "shader": "shader paketi",
                            "resourcepack": "doku paketi",
                        }[project_type]
                        self.send_json({
                            "success": False,
                            "error": f"'{slug}' {type_label} Minecraft {clean_v} ({loader}) ile uyumlu bir sürüme sahip değil.",
                        })
                        return

                    exact_match = bool(info.get("exact_match", True))

                    # Tam uyumlu degilse once kullanicidan onay iste
                    if not exact_match and not force:
                        matched = (info.get("game_versions") or [""])[0]
                        self.send_json({
                            "success": False,
                            "needs_confirm": True,
                            "exact_match": False,
                            "matched_game_version": matched,
                            "filename": info.get("filename"),
                            "message": (
                                f"Bu paket mevcut oyun sürümünüzle (MC {clean_v}) tam eşleşmiyor "
                                f"(en yakın: {matched or 'bilinmiyor'}). Çoğu zaman sorunsuz çalışır."
                            ),
                        })
                        return

                    fname = info["filename"]
                    dest = os.path.join(target_dir, fname)
                    if not os.path.exists(dest):
                        add_log(f"📥 Modrinth'ten indiriliyor: {fname} → {target_label}")
                        ModrinthFetcher.download_file(info["url"], dest)
                        add_log(f"✓ Başarıyla kuruldu: {fname}")

                    # CDN URL'inden proje/surum kimliklerini cikar (bagimlilik cozumu icin)
                    main_pid, main_vid = "", ""
                    url_match = re.search(r"/data/([^/]+)/versions/([^/]+)/", str(info.get("url") or ""))
                    if url_match:
                        main_pid, main_vid = url_match.group(1), url_match.group(2)

                    deps_result = None

                    if instance_id:
                        register_installed_content(
                            instance_id, project_type, slug, fname,
                            info.get("version_number") or "",
                            project_id=main_pid, version_id=main_vid,
                        )
                        if main_pid or main_vid:
                            register_modrinth_index(instance_id, slug, fname, main_pid, main_vid)

                        if install_dependencies and project_type == "mod":
                            add_log(
                                f"🔗 {slug} için zorunlu bağımlılıklar çözülüyor "
                                f"(MC {clean_v} • {loader})..."
                            )
                            try:
                                deps_result = install_required_dependencies(
                                    instance_id, target_dir, clean_v, loader,
                                    root_project_id=main_pid,
                                    root_version_id=main_vid,
                                    root_slug=slug,
                                )
                            except Exception as dep_err:
                                set_net_error("modrinth_dependencies", dep_err)
                                log_error(
                                    f"Bağımlılık çözümleme hatası ({slug}): "
                                    f"{type(dep_err).__name__}: {dep_err}"
                                )
                                deps_result = {
                                    "installed_dependencies": [],
                                    "failed_dependencies": [{
                                        "slug": slug,
                                        "reason": f"bağımlılık çözümleyici hatası: {dep_err}",
                                    }],
                                    "optional_dependencies": [],
                                    "skipped_existing": [],
                                }

                    response = {
                        "success": True,
                        "filename": fname,
                        "target": target_label,
                        "category": project_type,
                        "exact_match": exact_match,
                        "matched_game_version": (info.get("game_versions") or [""])[0] if info.get("game_versions") else "",
                        "message": f"{fname} → {target_label} kuruldu.",
                    }
                    if deps_result is not None:
                        response.update(deps_result)
                    self.send_json(response)
                except Exception as e:
                    add_log(f"Icerik kurulum hatasi ({slug}): {e}")
                    self.send_json({"success": False, "error": f"Kurulamadı: {e}"})
                return

            # 2b. Modpack (.mrpack) -> Yeni Profil Olarak Kur
            if path in ("/modrinth/modpack/install", "/modrinth/modpack/install/"):
                slug = (body.get("slug") or "").strip()
                preferred_gv = body.get("game_version") or ""
                if not slug:
                    self.send_json({"success": False, "error": "Modpack kimliği belirtilmedi."})
                    return

                project = fetch_modrinth_project(slug)
                versions = fetch_modrinth_versions(slug)
                chosen, mr_file = pick_modpack_version(versions, preferred_gv)

                if not chosen or not mr_file:
                    self.send_json({
                        "success": False,
                        "error": f"'{slug}' için uygun .mrpack sürümü bulunamadı.",
                    })
                    return

                title = str(project.get("title") or chosen.get("name") or slug).strip()
                icon = str(project.get("icon_url") or "")
                gvs = chosen.get("game_versions") or []
                mc_version = clean_minecraft_version(gvs[0]) if gvs else "1.20.1"
                loaders = [str(l).lower() for l in (chosen.get("loaders") or [])]
                loader = next((l for l in ["fabric", "forge", "neoforge", "quilt"] if l in loaders), "fabric")
                pack_name = f"{title} ({mc_version})"

                base_id = re.sub(r"[^\w\-]", "_", pack_name.lower())[:50].strip("_") or f"pack_{int(time.time())}"
                inst_id = base_id
                suffix = 2
                while True:
                    existing = get_instance_dir(inst_id)
                    if not existing or not os.path.isdir(existing):
                        break
                    inst_id = f"{base_id}_{suffix}"
                    suffix += 1

                inst_dir = get_instance_dir(inst_id)
                os.makedirs(os.path.join(inst_dir, "mods"), exist_ok=True)
                cfg = {
                    "id": inst_id,
                    "name": pack_name,
                    "version": mc_version,
                    "loader": loader,
                    "icon": icon,
                    "pack_slug": slug,
                    "pack_version_id": chosen.get("id"),
                    "install_status": "installing",
                    "install_progress": 1,
                    "install_detail": "Kurulum sıraya alındı...",
                    "launch_version": "",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                with open(os.path.join(inst_dir, "instance.json"), "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
                cfg["mod_count"] = 0
                add_log(f"📦 Modpack profili oluşturuldu: {pack_name}")
                threading.Thread(
                    target=install_modpack_background,
                    args=(inst_id, mr_file["url"]),
                    daemon=True,
                ).start()
                self.send_json({"success": True, "instance": cfg})
                return

            # 3. Klasor Acma
            if path in ("/open-folder", "/open-folder/"):
                base = os.path.abspath(minecraft_directory)
                target = base
                folder = body.get("folder", "")
                if folder:
                    target = os.path.abspath(os.path.join(base, folder))
                    if target != base and not target.startswith(base + os.sep):
                        self.send_json({"success": False, "error": "Geçersiz klasör yolu."})
                        return
                try:
                    os.makedirs(target, exist_ok=True)
                except Exception:
                    pass

                try:
                    if sys.platform.startswith("linux"):
                        subprocess.Popen(["xdg-open", target])
                    elif sys.platform == "win32":
                        os.startfile(target)
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", target])
                    self.send_json({"success": True})
                except Exception as e:
                    self.send_json({"success": False, "error": str(e)})
                return

            # 4. Instance (Profil) Olusturma
            if path in ("/instances/create", "/instances/create/"):
                name = (body.get("name") or "Yeni Profil").strip()
                ver = (body.get("version") or "1.20.4").strip()
                loader = (body.get("loader") or "fabric").lower()
                # Opsiyonel: kullanicinin gelismis menuden sectigi loader surumu.
                # Bos ise kurulum sirasinda Minecraft surumune uygun ONERILEN
                # (stable) surum otomatik secilir.
                loader_version = str(body.get("loader_version") or "").strip()
                inst_id = re.sub(r"[^\w\-]", "_", name.lower()) or f"profil_{int(time.time())}"
                inst_dir = get_instance_dir(inst_id)
                if not inst_dir:
                    self.send_json({"success": False, "error": "Geçersiz profil adı."})
                    return
                os.makedirs(os.path.join(inst_dir, "mods"), exist_ok=True)
                cfg = {
                    "id": inst_id,
                    "name": name,
                    "version": ver,
                    "loader": loader,
                    "loader_version": loader_version,
                    "icon": str(body.get("icon") or "").strip(),
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                with open(os.path.join(inst_dir, "instance.json"), "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
                cfg["mod_count"] = count_instance_mods(inst_id)
                add_log(f"🗂️ Yeni profil oluşturuldu: {name} (MC {ver} • {loader})")
                self.send_json({"success": True, "instance": cfg})
                return

            # 5. Instance (Profil) Guncelleme
            if path in ("/instances/update", "/instances/update/"):
                inst_dir = get_instance_dir(body.get("id", ""))
                cfg_path = os.path.join(inst_dir, "instance.json") if inst_dir else None
                if not cfg_path or not os.path.exists(cfg_path):
                    self.send_json({"success": False, "error": "Profil bulunamadı."})
                    return
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    if body.get("name"):
                        new_name = str(body["name"]).strip()
                        if new_name:
                            cfg["name"] = new_name
                    if body.get("version"):
                        cfg["version"] = clean_minecraft_version(str(body["version"]).strip())
                    if body.get("loader"):
                        cfg["loader"] = str(body["loader"]).strip().lower()
                    if "icon" in body:
                        cfg["icon"] = str(body.get("icon") or "").strip()
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=2)
                    cfg["id"] = os.path.basename(inst_dir)
                    cfg["mod_count"] = count_instance_mods(cfg["id"])
                    self.send_json({"success": True, "instance": cfg})
                except Exception as e:
                    self.send_json({"success": False, "error": f"Profil güncellenemedi: {e}"})
                return

            # 6. Instance (Profil) Silme
            if path in ("/instances/delete", "/instances/delete/"):
                inst_dir = get_instance_dir(body.get("id", ""))
                if not inst_dir or not os.path.isdir(inst_dir):
                    self.send_json({"success": False, "error": "Profil bulunamadı."})
                    return
                try:
                    shutil.rmtree(inst_dir, ignore_errors=True)
                    add_log(f"🗑️ Profil silindi: {os.path.basename(inst_dir)}")
                    self.send_json({"success": True, "message": "Profil silindi."})
                except Exception as e:
                    self.send_json({"success": False, "error": f"Profil silinemedi: {e}"})
                return

            # 7b. Profil Icerigi Silme (mod / shader / doku paketi)
            if path in ("/instances/content/delete", "/instances/content/delete/"):
                inst_id = body.get("instance_id")
                category = body.get("category") or "mod"
                name = body.get("name")
                ok, msg = delete_instance_content(inst_id, category, name)
                if ok:
                    add_log(f"🗑️ İçerik silindi ({normalize_category(category)}): {msg}")
                    self.send_json({"success": True, "deleted": msg})
                else:
                    self.send_json({"success": False, "error": msg})
                return

            # 7c. Profil Icerigi Ac/Kapa (<ad> <-> <ad>.disabled)
            if path in ("/instances/content/toggle", "/instances/content/toggle/"):
                inst_id = body.get("instance") or body.get("instance_id")
                category = body.get("category") or "mod"
                name = body.get("name")
                ok, msg, enabled = toggle_instance_content(inst_id, category, name)
                if ok:
                    action = "etkinleştirildi" if enabled else "devre dışı bırakıldı"
                    add_log(f"🔁 İçerik {action}: {msg}")
                    self.send_json({"success": True, "name": msg, "enabled": enabled})
                else:
                    self.send_json({"success": False, "error": msg})
                return

            # 8. Hata Durumunu Temizle (frontend hatayi bir kez gosterdikten sonra cagirir)
            if path in ("/clear-error", "/clear-error/"):
                update_state(error=None)
                self.send_json({"success": True})
                return

        except Exception as e:
            add_log(f"POST isleme hatasi ({url.path}): {e}")
            try:
                self.send_json({"success": False, "error": str(e)})
            except Exception:
                pass
            return

        self.send_json({"success": False, "error": "Bilinmeyen API yolu"}, 404)


# ==================== YUKLEYICI (LOADER) SURUM COZUMLEME ====================
# Yeni Profil ekrani icin: secilen Minecraft surumune uygun ONERILEN (stable)
# loader surumu + gelismis secim icin tum surumler. Ag cagrisi tekrarlanmasin
# diye 10 dakika onbelleklenir (LRU, ust sinirli).
LOADER_LABELS = {
    "vanilla": "Vanilla",
    "fabric": "Fabric",
    "forge": "Forge",
    "neoforge": "NeoForge",
    "quilt": "Quilt",
}
_LOADER_CACHE = OrderedDict()          # (loader, mc_version) -> (zaman, veri)
_LOADER_CACHE_LOCK = threading.Lock()
_LOADER_CACHE_TTL = 600.0
_LOADER_CACHE_MAX = 120

# Modpack -> destekledigi Minecraft surumleri / yukleyiciler (Yeni Profil alt bari)
_PACK_VERSIONS_CACHE = OrderedDict()
_PACK_VERSIONS_LOCK = threading.Lock()
_PACK_VERSIONS_TTL = 900.0
_PACK_VERSIONS_MAX = 60


def fetch_modpack_game_versions(slug):
    """Bir Modrinth modpack'inin destekledigi MC surumlerini ve yukleyicilerini dondurur."""
    safe_slug = re.sub(r"[^a-zA-Z0-9\-_]", "", str(slug or ""))
    if not safe_slug:
        return {"success": False, "error": "Geçersiz paket.", "game_versions": [], "versions": []}

    now = time.time()
    with _PACK_VERSIONS_LOCK:
        hit = _PACK_VERSIONS_CACHE.get(safe_slug)
        if hit and (now - hit[0]) < _PACK_VERSIONS_TTL:
            _PACK_VERSIONS_CACHE.move_to_end(safe_slug)
            return hit[1]

    try:
        resp = requests.get(
            f"{ModrinthFetcher.BASE_URL}/project/{safe_slug}/version",
            headers=ModrinthFetcher.HEADERS,
            timeout=10,
        )
        raw = resp.json() if resp.status_code == 200 else []
        game_versions = []
        items = []
        if isinstance(raw, list):
            for v in raw:
                gvs = v.get("game_versions") or []
                for g in gvs:
                    if g not in game_versions:
                        game_versions.append(g)
                items.append({
                    "name": v.get("name"),
                    "version_number": v.get("version_number"),
                    "game_versions": gvs,
                    "loaders": [str(l).lower() for l in (v.get("loaders") or [])],
                })
        data = {
            "success": True,
            "slug": safe_slug,
            "game_versions": game_versions,
            "versions": items[:80],
            "loaders": sorted({l for it in items for l in it["loaders"]}),
        }
    except Exception as e:
        add_log(f"Modpack sürüm sorgusu hatası ({safe_slug}): {e}")
        data = {"success": False, "error": str(e), "slug": safe_slug,
                "game_versions": [], "versions": [], "loaders": []}

    with _PACK_VERSIONS_LOCK:
        _PACK_VERSIONS_CACHE[safe_slug] = (time.time(), data)
        while len(_PACK_VERSIONS_CACHE) > _PACK_VERSIONS_MAX:
            _PACK_VERSIONS_CACHE.popitem(last=False)
    return data


def resolve_loader_mc_version(ml, mc_version):
    """Yukleyicinin kabul ettigi Minecraft surum adini dondurur.

    Bazi yukleyiciler yeni Minecraft surumlerini farkli adlandirir:
    manifestte "26.3" olan surum, NeoForge maven'inde "1.26.3" dalina karsilik
    gelir (kutuphane de basina "1." ekleyerek normalize eder). Once gercek adi,
    sonra "1." onekli/oneksiz varyantini dener. Bulunamazsa None doner.
    """
    candidates = [mc_version]
    if re.match(r"^\d", mc_version) and not mc_version.startswith("1."):
        candidates.append("1." + mc_version)        # 26.3 -> 1.26.3
    elif mc_version.startswith("1.") and re.match(r"^1\.\d", mc_version):
        candidates.append(mc_version[2:])           # 1.26.3 -> 26.3
    for cand in candidates:
        try:
            if ml.is_minecraft_version_supported(cand):
                return cand
        except Exception:
            continue
    return None


def install_loader_version(ml, mc_version, minecraft_directory, loader_version, callback, java):
    """Yukleyiciyi kurar ve baslatilacak surum kimligini dondurur.

    Kutuphanenin public install() sarmalayicisi, Minecraft'in kendi ic adi
    (orn. 26.3) ile yukleyicinin bekledigi ad (orn. 1.26.3) farkli oldugunda
    UnsupportedVersion firlatir. Bu nedenle resmi akisin aynisini dogru MC
    surum adiyla biz yuruturuz: vanilla kur -> yukleyiciyi kur -> yukleyici
    surum jsonunu kur. _base bulunamazsa public API'ye geri donulur.
    """
    base = getattr(ml, "_base", None)
    if base is None or not loader_version:
        return ml.install(
            mc_version, minecraft_directory,
            loader_version=(loader_version or None), callback=callback, java=java,
        )
    minecraft_launcher_lib.install.install_minecraft_version(
        mc_version, minecraft_directory, callback=callback
    )
    base.install(mc_version, str(minecraft_directory), callback, str(java), loader_version)
    installed_id = ml.get_installed_version(mc_version, loader_version)
    minecraft_launcher_lib.install.install_minecraft_version(
        installed_id, minecraft_directory, callback=callback
    )
    return installed_id


def get_loader_version_info(loader_id, mc_version):
    """Bir Minecraft surumu icin onerilen ve tum yukleyici surumlerini dondurur."""
    loader_id = (loader_id or "").lower().strip()
    mc_version = (mc_version or "").strip()

    if loader_id in ("", "vanilla", "none", "hicbiri", "hiçbiri"):
        return {"success": True, "loader": "vanilla", "version": mc_version,
                "supported": True, "recommended": None, "versions": [], "stable_only": []}
    if loader_id not in LOADER_LABELS:
        return {"success": False, "error": f"Desteklenmeyen yükleyici: {loader_id}"}
    if not mc_version:
        return {"success": False, "error": "Minecraft sürümü gerekli.", "loader": loader_id}

    key = (loader_id, mc_version)
    now = time.time()
    with _LOADER_CACHE_LOCK:
        hit = _LOADER_CACHE.get(key)
        if hit and (now - hit[0]) < _LOADER_CACHE_TTL:
            _LOADER_CACHE.move_to_end(key)
            return hit[1]

    try:
        ml = minecraft_launcher_lib.mod_loader.get_mod_loader(loader_id)
        # Yukleyicinin kabul ettigi ad (orn. NeoForge icin 26.3 -> 1.26.3)
        loader_mc = resolve_loader_mc_version(ml, mc_version)
        supported = bool(loader_mc)
        mc_alias = loader_mc if (loader_mc and loader_mc != mc_version) else None

        if not supported:
            data = {"success": True, "loader": loader_id, "version": mc_version,
                    "supported": False, "recommended": None, "versions": [], "stable_only": []}
        else:
            try:
                recommended = ml.get_latest_loader_version(loader_mc)
            except Exception:
                recommended = None
            try:
                all_versions = list(ml.get_loader_versions(loader_mc, stable_only=False) or [])
            except Exception:
                all_versions = []
            try:
                stable_versions = list(ml.get_loader_versions(loader_mc, stable_only=True) or [])
            except Exception:
                stable_versions = []
            data = {
                "success": True,
                "loader": loader_id,
                "label": LOADER_LABELS.get(loader_id, loader_id),
                "version": mc_version,
                "supported": True,
                "recommended": recommended,
                # ONEMLI: Kesinlikle sinirlama yok. Kullanici gecmis ve guncel TUM
                # loader surumlerini gorebilmeli (orn. Fabric icin 23 "stable"
                # yerine 253 surumun tamami). Sirasi: en yeni -> en eski.
                "stable_only": stable_versions,
                "versions": all_versions,
                "total_versions": len(all_versions),
                "stable_count": len(stable_versions),
                # Yukleyici bu MC surumunu farkli adlandiriyorsa (orn. 1.26.3)
                "mc_alias": mc_alias,
            }
    except Exception as e:
        add_log(f"Loader sürüm sorgusu hatası ({loader_id} {mc_version}): {e}")
        data = {"success": False, "error": str(e), "loader": loader_id,
                "version": mc_version, "recommended": None, "versions": [], "stable_only": []}

    with _LOADER_CACHE_LOCK:
        _LOADER_CACHE[key] = (time.time(), data)
        while len(_LOADER_CACHE) > _LOADER_CACHE_MAX:
            _LOADER_CACHE.popitem(last=False)
    return data


# ==================== SUNUCU (THREADED) ====================
class CookieLauncherServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Her istegi ayri thread'de karsilar; boylece uzun indirmeler status polling'i kilitleyemez."""
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


tracker_installed = False


def ensure_download_tracker():
    global tracker_installed
    if not tracker_installed:
        install_download_tracker()
        tracker_installed = True


def start_server(port=18420):
    ensure_download_tracker()
    handler = CookieLauncherHTTPHandler
    for p in [port, 18421, 18422, 18423, 0]:
        try:
            httpd = CookieLauncherServer(("127.0.0.1", p), handler)
            actual_port = httpd.server_address[1]
            add_log(f"CookieLauncher Arka Plan Servisi http://127.0.0.1:{actual_port} üzerinde hazır.")
            print(f"CookieLauncher Core Backend: http://127.0.0.1:{actual_port}", flush=True)
            return httpd, actual_port
        except OSError:
            continue
    raise RuntimeError("Uygun port bulunamadı!")


if __name__ == "__main__":
    server, port = start_server(18420)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCookieLauncher Backend kapatılıyor...")
        server.server_close()
