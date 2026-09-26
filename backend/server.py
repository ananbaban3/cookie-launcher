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
import struct
import base64
import shutil
import socket
import threading
import subprocess
import traceback
import http.server
import socketserver
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

# Linux ortaminda DNS / IPv6 takilmalarini engellemek icin IPv4 zorla
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

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

SKINS_DIR = os.path.join(APP_DATA_DIR, "skins")
os.makedirs(SKINS_DIR, exist_ok=True)

API_VERSION = 2


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


# ==================== OFFLINE SKIN YARDIMCILARI ====================
def sanitize_username(username):
    safe = re.sub(r"[^\w\-]", "_", str(username or "Steve").strip())
    return safe or "Steve"


def get_skin_path(username):
    return os.path.join(SKINS_DIR, f"{sanitize_username(username)}.png")


def png_dimensions(raw):
    if not raw or len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        width, height = struct.unpack(">II", raw[16:24])
        return width, height
    except Exception:
        return None


def save_skin_bytes(username, raw):
    dims = png_dimensions(raw)
    if not dims:
        return None
    width, height = dims
    valid_size = (
        (width >= 64 and height == width)
        or (width >= 64 and height * 2 == width)
    )
    if not valid_size or len(raw) > 2 * 1024 * 1024:
        return None
    path = get_skin_path(username)
    try:
        with open(path, "wb") as f:
            f.write(raw)
        return path
    except Exception:
        return None


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
    _cache = {}
    _cache_lock = threading.Lock()

    @classmethod
    def load_cache(cls):
        with cls._cache_lock:
            if os.path.exists(MODS_CACHE_FILE):
                try:
                    with open(MODS_CACHE_FILE, "r", encoding="utf-8") as f:
                        cls._cache = json.load(f)
                except Exception:
                    cls._cache = {}
            return dict(cls._cache)

    @classmethod
    def save_cache(cls):
        try:
            with cls._cache_lock:
                with open(MODS_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cls._cache, f, indent=2)
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
            add_log(f"Modrinth arama yaniti beklenmedik (HTTP {resp.status_code}), bos liste donduruluyor.")
        except Exception as e:
            add_log(f"Modrinth arama uyarisi (sessizce gecildi): {e}")

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
                            with cls._cache_lock:
                                cls._cache[cache_key] = res
                            cls.save_cache()
                            return res
        except Exception as e:
            add_log(f"Modrinth mod bilgisi uyarisi ({project_slug}): {e}")

        with cls._cache_lock:
            cls._cache[cache_key] = None
        cls.save_cache()
        return None

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
def get_complete_version_manifest():
    """Mojang manifestini ceker; ag hatasinda onbellek, olmazsa küratör listeye duser."""
    try:
        url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Freesm/CookieLauncher/2.0.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
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
            return items
    except Exception as e:
        add_log(f"Mojang manifesti anlik cekilemedi, onbellege donuluyor: {e}")

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


# ==================== OYUN BASLATMA THREADI (NON-BLOCKING) ====================
def run_game_background_task(params):
    """
    Uzun suren indirme/kurulum/baslatma islerinin tamami burada, arka planda calisir.
    HTTP istegi bu fonksiyonu beklemez; aninda 200 OK donulmustur.
    """
    add_log("🚀 Arka plan başlatma görevi başladı.")

    try:
        username = (params.get("username") or "Steve").strip() or "Steve"
        raw_version = (params.get("version") or "1.20.4").strip()
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
        if instance_id:
            inst_cfg = load_instance_config(instance_id)
            if not inst_cfg:
                raise RuntimeError("Seçili profil bulunamadı. Lütfen profili yeniden seçin.")
            instance_id = inst_cfg.get("id")
            clean_v = clean_minecraft_version(inst_cfg.get("version") or clean_v)
            loader = (inst_cfg.get("loader") or loader).lower()
            pack_launch_version = str(inst_cfg.get("launch_version") or "").strip()
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

        # 4. Yukleyici Kurulumu (Fabric / Forge) - modpack ise zaten kurulu
        if not pack_launch_version and loader == "fabric":
            update_state(
                status=f"Fabric Loader ({clean_v}) yapılandırılıyor...",
                detail="Fabric kütüphaneleri kuruluyor...",
                percent=72,
                progress=0.72,
            )
            try:
                minecraft_launcher_lib.fabric.install_fabric(
                    clean_v, minecraft_directory, callback=make_progress_callbacks(70, 10), java=java_exec
                )
                installed_vers = [v["id"] for v in minecraft_launcher_lib.utils.get_installed_versions(minecraft_directory)]
                fabric_candidates = [
                    v for v in installed_vers if "fabric-loader" in v and v.endswith(f"-{clean_v}")
                ]
                if fabric_candidates:
                    version_to_run = sorted(fabric_candidates)[-1]
                    add_log(f"Fabric sürümü bağlandı: {version_to_run}")
            except Exception as fe:
                add_log(f"Fabric kurulum notu: {fe}. Vanilla ile devam edilebilir.")

        elif not pack_launch_version and loader == "forge":
            update_state(
                status=f"Forge ({clean_v}) doğrulanıyor...",
                detail="Forge kütüphaneleri taranıyor...",
                percent=72,
                progress=0.72,
            )
            try:
                forge_v = minecraft_launcher_lib.forge.find_forge_version(clean_v)
                if forge_v:
                    minecraft_launcher_lib.forge.install_forge_version(
                        forge_v, minecraft_directory, callback=make_progress_callbacks(70, 10), java=java_exec
                    )
                    version_to_run = forge_v
                else:
                    add_log(f"Forge {clean_v} için uygun yükleyici bulunamadı, Vanilla ile devam ediliyor.")
            except Exception as fge:
                add_log(f"Forge kurulum notu: {fge}")

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
                })
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
                    add_log(f"Surum manifesti hatasi (sessizce gecildi): {e}")

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

                self.send_json({"success": True, "versions": versions, "installed": installed})
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

            # 7. Offline Skin Bilgisi
            if path == "/skin/info":
                username = query.get("username", ["Steve"])[0]
                safe = sanitize_username(username)
                fp = get_skin_path(safe)
                has_skin = os.path.isfile(fp)
                self.send_json({
                    "success": True,
                    "username": safe,
                    "has_skin": has_skin,
                    "skin_url": f"/api/skin/{safe}.png" if has_skin else None,
                })
                return

            # 8. Offline Skin Dosyasi Sunumu
            if path.startswith("/skin/") and path.endswith(".png"):
                safe = re.sub(r"[^\w\-]", "", path[len("/skin/"):-4])
                fp = get_skin_path(safe) if safe else None
                if fp and os.path.isfile(fp):
                    try:
                        with open(fp, "rb") as f:
                            skin_bytes = f.read()
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Content-Length", str(len(skin_bytes)))
                        self.end_headers()
                        self.wfile.write(skin_bytes)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                else:
                    self.send_json({"success": False, "error": "Skin bulunamadı."}, 404)
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

            # 2. Modrinth Mod Kurulumu (Kullanicinin Secili Profiline Kurulur)
            if path in ("/modrinth/install", "/modrinth/install/"):
                slug = (body.get("slug") or "").strip()
                raw_ver = (body.get("version") or "1.20.4").strip()
                loader = (body.get("loader") or "fabric").lower()
                instance_id = body.get("instance_id")

                if not slug:
                    self.send_json({"success": False, "error": "Mod kimliği (slug) belirtilmedi."})
                    return

                clean_v = clean_minecraft_version(raw_ver)
                target_label = f"Genel .minecraft (MC {clean_v})"

                if instance_id:
                    inst = load_instance_config(instance_id)
                    if not inst:
                        self.send_json({"success": False, "error": "Hedef profil bulunamadı."})
                        return
                    clean_v = clean_minecraft_version(inst.get("version") or raw_ver)
                    loader = (inst.get("loader") or loader).lower()
                    target_mods = os.path.join(get_instance_dir(instance_id), "mods")
                    target_label = f"{inst.get('name')} profili (MC {clean_v} • {loader})"
                else:
                    target_mods = os.path.join(minecraft_directory, "mods", clean_v)

                os.makedirs(target_mods, exist_ok=True)

                try:
                    info = None
                    curated_key = (clean_v, loader)
                    if curated_key in CURATED_OPTIMIZATION_MAP:
                        for item in CURATED_OPTIMIZATION_MAP[curated_key]:
                            if item["slug"] == slug:
                                info = item
                                break

                    if not info:
                        info = ModrinthFetcher.get_latest_mod_jar(slug, clean_v, loader=loader)

                    if info and info.get("url"):
                        fname = info["filename"]
                        dest = os.path.join(target_mods, fname)
                        if not os.path.exists(dest):
                            add_log(f"📥 Modrinth'ten indiriliyor: {fname} → {target_label}")
                            ModrinthFetcher.download_file(info["url"], dest)
                            add_log(f"✓ Başarıyla kuruldu: {fname}")
                        self.send_json({
                            "success": True,
                            "filename": fname,
                            "target": target_label,
                            "message": f"{fname} → {target_label} kuruldu.",
                        })
                    else:
                        self.send_json({
                            "success": False,
                            "error": f"'{slug}' modu Minecraft {clean_v} ({loader}) ile uyumlu bir sürüme sahip değil.",
                        })
                except Exception as e:
                    add_log(f"Mod kurulum hatasi ({slug}): {e}")
                    self.send_json({"success": False, "error": f"Mod kurulamadı: {e}"})
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

            # 7. Offline Skin Kaydetme (dosya/base64 veya URL)
            if path in ("/skin/save", "/skin/save/"):
                username = sanitize_username(body.get("username") or "Steve")
                data_url = str(body.get("data_url") or "")
                image_url = str(body.get("url") or "").strip()
                raw = None

                if data_url.startswith("data:image") and "," in data_url:
                    try:
                        raw = base64.b64decode(data_url.split(",", 1)[1])
                    except Exception:
                        raw = None
                elif image_url:
                    try:
                        resp = requests.get(image_url, timeout=10, headers=ModrinthFetcher.HEADERS)
                        if resp.status_code == 200:
                            raw = resp.content
                    except Exception:
                        raw = None

                saved = save_skin_bytes(username, raw)
                if saved:
                    add_log(f"🎨 Skin kaydedildi: {username}")
                    self.send_json({"success": True, "skin_url": f"/api/skin/{username}.png"})
                else:
                    self.send_json({
                        "success": False,
                        "error": "Geçerli bir PNG skin bulunamadı (64x64 / 64x32 / 128x128, max 2MB).",
                    })
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
