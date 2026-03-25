#!/bin/bash
# Genera widget.min.js offuscato dal sorgente
# Richiede Node.js: npm install -g terser

set -e

SRC="../static/widget.js"
OUT="static/widget.min.js"

if ! command -v terser &> /dev/null; then
  echo "Installo terser..."
  npm install -g terser
fi

echo "==> Minificazione + offuscamento..."
terser "$SRC" \
  --compress \
  --mangle \
  --mangle-props "regex=/^_/" \
  --output "$OUT"

SIZE_SRC=$(wc -c < "$SRC")
SIZE_OUT=$(wc -c < "$OUT")
echo "✓ $SRC ($SIZE_SRC bytes) → $OUT ($SIZE_OUT bytes)"
echo "  Riduzione: $(( (SIZE_SRC - SIZE_OUT) * 100 / SIZE_SRC ))%"
