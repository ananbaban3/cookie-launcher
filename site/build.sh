#!/usr/bin/env bash
# Web sitesinin statik CSS'ini yeniden uretir.
#
#   cd site && npm install && ./build.sh
#
# Cikti: ../docs/assets/site.css  (GitHub Pages tarafindan sunulur)
# Not: Tailwind "Play CDN" (cdn.tailwindcss.com) KULLANILMAZ. Uretimde
#      3. taraf bir script yuklemek KVKK/GDPR acisindan gereksiz veri
#      aktarimi ve tedarik zinciri riski yaratir.
set -euo pipefail
cd "$(dirname "$0")"
npx --yes tailwindcss@3.4.17 \
  --config tailwind.config.cjs \
  --input input.css \
  --output ../docs/assets/site.css \
  --minify
echo "docs/assets/site.css yeniden uretildi."
