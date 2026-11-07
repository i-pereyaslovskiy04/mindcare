#!/usr/bin/env bash
# Руководства пользователя: help-src/*.md → public/help/<guide>.html + .pdf.
# Нужны pandoc и chromium. Результат коммитится (на сервере сборка не нужна).
#   bash scripts/build_help.sh
set -euo pipefail
cd "$(dirname "$0")/.."
SRC=help-src
OUT=public/help
mkdir -p "$OUT/img"
cp "$SRC/help.css" "$OUT/"
cp "$SRC"/img/*.png "$OUT/img/"
DATE="${HELP_DATE:-$(date +%d.%m.%Y)}"
CHROME="${CHROME:-chromium}"
for guide in campaigns methodologies participant; do
  toc=(--toc --toc-depth=2)
  [ "$guide" = participant ] && toc=()
  pandoc "$SRC/$guide.md" -f markdown -t html5 --standalone --template="$SRC/template.html" \
    "${toc[@]}" -M date="$DATE" -M pdf="$guide.pdf" -o "$OUT/$guide.html"
  "$CHROME" --headless --no-sandbox --disable-gpu --no-pdf-header-footer \
    --print-to-pdf="$PWD/$OUT/$guide.pdf" "file://$PWD/$OUT/$guide.html" 2>/dev/null
  echo "built $guide"
done
pandoc "$SRC/index.md" -f markdown -t html5 --standalone --template="$SRC/template.html" \
  -M date="$DATE" -o "$OUT/index.html"
echo "built index"
