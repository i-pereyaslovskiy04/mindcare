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
# Полное руководство (все части одним документом) — для печати и заказчика.
python3 scripts/combine_help.py "$SRC" > "$SRC/.full.md"
pandoc "$SRC/.full.md" -f markdown -t html5 --standalone --template="$SRC/template.html" \
  --toc --toc-depth=2 --resource-path="$SRC" -M date="$DATE" -M pdf=full.pdf -o "$OUT/full.html"
"$CHROME" --headless --no-sandbox --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$PWD/$OUT/full.pdf" "file://$PWD/$OUT/full.html" 2>/dev/null
if [ -n "${HELP_DOCX:-}" ]; then      # Word-версия для заказчика (по запросу)
  pandoc "$SRC/.full.md" -f markdown -t docx --toc --toc-depth=2 --resource-path="$SRC" \
    -M date="$DATE" -o "$HELP_DOCX"
fi
rm -f "$SRC/.full.md"
echo "built full"
pandoc "$SRC/index.md" -f markdown -t html5 --standalone --template="$SRC/template.html" \
  -M date="$DATE" -o "$OUT/index.html"
echo "built index"
