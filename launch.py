#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import urllib.request
import webbrowser

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_SCRIPT = os.path.join(PROJECT_DIR, "backend", "server.py")
PORT = 18420
URL = f"http://127.0.0.1:{PORT}"

def is_server_running():
    try:
        with urllib.request.urlopen(f"{URL}/api/status", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False

def start_backend():
    if is_server_running():
        print(f"✓ CookieLauncher API zaten http://127.0.0.1:{PORT} üzerinde çalışıyor.")
        return None
    print("🚀 CookieLauncher arka plan servisi başlatılıyor...")
    proc = subprocess.Popen([sys.executable, BACKEND_SCRIPT], cwd=PROJECT_DIR)
    # Sunucunun ayağa kalkmasını bekle (en fazla 4 saniye)
    for _ in range(20):
        time.sleep(0.2)
        if is_server_running():
            print(f"✓ Sunucu hazır: {URL}")
            return proc
    print("⚠️ Sunucu yanıt vermedi, yine de devam ediliyor...")
    return proc

def open_app_window():
    print(f"🌐 CookieLauncher GUI açılıyor: {URL}")
    
    # 1. Chrome / Chromium App Modu dene (Frameless pencereli görünüm)
    for browser in ["google-chrome", "chromium", "chromium-browser", "brave"]:
        try:
            subprocess.Popen([browser, f"--app={URL}", "--window-size=1100,750"])
            return
        except FileNotFoundError:
            pass

    # 2. Firefox Yeni Pencere dene
    try:
        subprocess.Popen(["firefox", "--new-window", URL])
        return
    except FileNotFoundError:
        pass

    # 3. Varsayılan sistem tarayıcısı
    webbrowser.open(URL)

def main():
    print("=" * 60)
    print("🍪 COOKIELAUNCHER TAURI v2.0 - AŞIRI ESTETİK & OPTİMİZE")
    print("=" * 60)
    backend_proc = start_backend()
    open_app_window()
    print("\n💡 İpucu: Bu projeyi Windows'ta veya Linux'ta tam native (.exe / .app)")
    print("   olarak derlemek isterseniz 'npm run tauri:build' komutunu kullanabilirsiniz.")
    print("   Kapatmak için Ctrl+C tuşlarına basabilirsiniz.")
    
    if backend_proc:
        try:
            backend_proc.wait()
        except KeyboardInterrupt:
            print("\nKapatılıyor...")
            backend_proc.terminate()

if __name__ == "__main__":
    main()
