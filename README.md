# CookieLauncher 🍪 (Tauri v2.0)

Aşırı estetik, modern, akıcı ve yüksek performanslı Minecraft başlatıcısı.

---

## ✨ Özellikler

- **🎨 Catppuccin Mocha Tasarım:** Özel başlık çubuğu (frameless window), cam efektleri (glassmorphism), akıcı geçiş animasyonları ve karanlık tema.
- **⚡ Yüksek Performans & Optimizasyon:** Minimum bellek tüketimi (~30 MB RAM) ve anında tepki süresi.
- **🌐 Dahili Modrinth Mağazası:**
  - Canlı arama, kategori filtreleri (Modlar, Shaderlar, Doku Paketleri, Modpackler).
  - Yüksek çözünürlüklü mod logoları, indirme & beğeni sayaçları.
  - Tek tıkla otomatik bağımlılık çözümlü indirme.
  - Sürüm inceleme modalı.
- **🚀 Akıllı Oyun Motoru:**
  - Tüm resmi sürümler (103+ sürüm) ve Fabric desteği.
  - Eksik veya bozuk dosyaları (JAR, kütüphane, doku) otomatik algılayıp indirme.
  - Java kurulu olmayan sistemler (Windows / Linux) için Mojang'ın resmi Java ortamını otomatik kurma.
  - Otomatik FullBright (gece görüşü / daimi aydınlık) ayarı.
  - RAM slider'ı (2 GB - 16 GB) ve çözünürlük ayarı.
- **📦 Yüklü İçerik Yöneticisi:**
  - Modları, dokuları ve shaderları tek tıkla devre dışı bırakma (.disabled) veya silme.
  - Klasörleri doğrudan işletim sistemi dosya yöneticisinde açma.
- **📜 Canlı Terminal / Konsol:**
  - Oyunun tüm Java çıktılarını ve çökme raporlarını gerçek zamanlı izleme.

---

## 🚀 Çalıştırma

### Hızlı Başlatma (Hemen Kullan):
```bash
cd cookie-launcher-tauri
./start.sh
# veya
python3 launch.py
```

### Tauri Olarak Yerel Derleme & Geliştirme:
```bash
cd cookie-launcher-tauri
npm install
npm run tauri:dev
```

### Standart Kurulum Paketi Oluşturma (.exe / .deb / .AppImage):
```bash
npm run tauri:build
```
Windows üzerinde `cookie-launcher.exe` veya Linux üzerinde bağımsız paket üretir.

> Windows setup dosyası, Python gerektirmeden çalışan gömülü çekirdeği (PyInstaller ile derlenen `cookielauncher-core.exe`) içerir. Otomatik derleme `.github/workflows/release.yml` üzerinden yapılır.

---

## 📁 Proje Yapısı

```
cookie-launcher-tauri/
├── backend/server.py        # Python çekirdek (HTTP API, indirme, başlatma)
├── src/                     # Vanilla JS / HTML / CSS arayüz
├── src-tauri/               # Tauri (Rust) kabuğu, capabilities ve derleme ayarları
└── .github/workflows/       # Windows / Linux otomatik setup derlemesi
```

---

## 📄 Lisans

Bu proje **GNU GPL-3.0** lisansı ile açık kaynak olarak dağıtılmaktadır. Detaylar için [LICENSE](LICENSE) dosyasına bakın.
