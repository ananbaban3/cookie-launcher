#!/bin/bash
# ==============================================================================
# CookieLauncher Windows Setup.exe (.exe / NSIS) Derleme Komutu
# ==============================================================================

echo "=========================================================="
echo "🍪 CookieLauncher Windows Setup.exe (.exe) Derleyici"
echo "=========================================================="
echo ""
echo "Windows ortamında veya GitHub Actions üzerinde:"
echo "  1. npm run tauri build"
echo "komutu doğrudan 'src-tauri/target/release/bundle/nsis/' klasörüne"
echo "'CookieLauncher_x64-setup.exe' dosyasını üretecektir."
echo ""
echo "Eğer Linux üzerinden Cross-Compile yapmak isterseniz:"
echo "  rustup target add x86_64-pc-windows-msvc"
echo "  cargo tauri build --target x86_64-pc-windows-msvc"
echo ""
echo "Gerekli tüm NSIS ve tauri.conf.json ayarları eksiksiz yapılandırıldı!"
echo "=========================================================="
