#!/usr/bin/env bash
# ============================================================
#  GENESI WIDGET — Installer automatico
#  Uso: bash install_widget.sh --key TUA_API_KEY [--dir /percorso/sito]
#
#  Lo script trova tutti i file .html nella cartella indicata
#  e inietta il widget prima di </body> in ciascuno.
#  Se il widget è già presente in un file, lo salta.
# ============================================================

set -e

# ── Colori ────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}OK${RESET}  $1"; }
err()  { echo -e "  ${RED}ERR${RESET} $1"; }
info() { echo -e "  ${DIM}$1${RESET}"; }
sep()  { echo -e "${DIM}------------------------------------------------------------${RESET}"; }

# ── Default ───────────────────────────────────────────────────
WIDGET_SERVER="https://genesi.lucadigitale.eu"
API_KEY=""
SITE_DIR="."
USER_NAME=""
USER_ROLE=""

# ── Argomenti ─────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --key)      API_KEY="$2";      shift 2 ;;
    --dir)      SITE_DIR="$2";     shift 2 ;;
    --server)   WIDGET_SERVER="$2"; shift 2 ;;
    --user)     USER_NAME="$2";    shift 2 ;;
    --role)     USER_ROLE="$2";    shift 2 ;;
    *) echo "Opzione sconosciuta: $1"; exit 1 ;;
  esac
done

# ── Validazione ───────────────────────────────────────────────
if [[ -z "$API_KEY" ]]; then
  echo -e "\n${RED}Errore: --key obbligatorio.${RESET}"
  echo    "  Esempio: bash install_widget.sh --key demo_cplace_2026 --dir /var/www/html"
  exit 1
fi

if [[ ! -d "$SITE_DIR" ]]; then
  echo -e "\n${RED}Errore: cartella '$SITE_DIR' non trovata.${RESET}"
  exit 1
fi

SITE_DIR=$(realpath "$SITE_DIR")

# ── Banner ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}============================================================"
echo -e "  GENESI WIDGET — Installazione automatica"
echo -e "============================================================${RESET}"
echo -e "  Server  : $WIDGET_SERVER"
echo -e "  API key : $API_KEY"
echo -e "  Cartella: $SITE_DIR"
sep

# ── Step 1: Verifica connessione ──────────────────────────────
echo -e "\n${BOLD}[1]${RESET} Verifica connessione al server Genesi"

if curl -sf "$WIDGET_SERVER/api/widget/ping" -H "X-Widget-Key: $API_KEY" -o /dev/null; then
  ok "Server raggiungibile, API key valida"
else
  err "Server non raggiungibile o API key non valida"
  err "Verifica URL e chiave, poi riprova."
  exit 1
fi

# ── Step 2: Scarica configurazione visuale ────────────────────
echo -e "\n${BOLD}[2]${RESET} Download configurazione widget dal server"

CONFIG=$(curl -sf "$WIDGET_SERVER/api/widget/config" -H "X-Widget-Key: $API_KEY" 2>/dev/null || echo "")

if [[ -n "$CONFIG" ]]; then
  WIDGET_NAME=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name','Assistente'))" 2>/dev/null || echo "Assistente")
  WIDGET_COLOR=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('color','#7c3aed'))" 2>/dev/null || echo "#7c3aed")
  ok "Configurazione scaricata: nome='$WIDGET_NAME' colore='$WIDGET_COLOR'"
else
  info "Configurazione non disponibile, uso defaults"
fi

# ── Step 3: Trova i file HTML ──────────────────────────────────
echo -e "\n${BOLD}[3]${RESET} Ricerca file HTML in $SITE_DIR"

HTML_FILES=$(find "$SITE_DIR" -name "*.html" -not -path "*/node_modules/*" -not -path "*/.git/*")
FILE_COUNT=$(echo "$HTML_FILES" | grep -c . || echo 0)

if [[ "$FILE_COUNT" -eq 0 ]]; then
  err "Nessun file .html trovato in $SITE_DIR"
  exit 1
fi

ok "$FILE_COUNT file HTML trovati"

# ── Step 4: Inietta snippet ───────────────────────────────────
echo -e "\n${BOLD}[4]${RESET} Installazione widget nei file HTML"

# Costruisce lo snippet
if [[ -n "$USER_NAME" && -n "$USER_ROLE" ]]; then
  SNIPPET="  <script
    src=\"$WIDGET_SERVER/widget.js\"
    data-api-key=\"$API_KEY\"
    data-user-name=\"$USER_NAME\"
    data-user-role=\"$USER_ROLE\"
    data-page-context=\"true\">
  </script>"
elif [[ -n "$USER_NAME" ]]; then
  SNIPPET="  <script
    src=\"$WIDGET_SERVER/widget.js\"
    data-api-key=\"$API_KEY\"
    data-user-name=\"$USER_NAME\"
    data-page-context=\"true\">
  </script>"
else
  SNIPPET="  <script
    src=\"$WIDGET_SERVER/widget.js\"
    data-api-key=\"$API_KEY\"
    data-page-context=\"true\">
  </script>"
fi

INSTALLED=0
SKIPPED=0
ERRORS=0

# Scrivi script Python in file temporaneo (evita heredoc dentro while loop che consuma stdin)
INJECT_PY=$(mktemp /tmp/widget_inject_XXXXXX.py)
cat > "$INJECT_PY" << 'PYEOF'
import sys, re
filepath = sys.argv[1]
snippet  = sys.argv[2]
with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()
new_content = re.sub(r'(</body>)', snippet + '\n\\1', content, count=1, flags=re.IGNORECASE)
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(new_content)
PYEOF

while IFS= read -r FILE; do
  if grep -q "widget.js" "$FILE" 2>/dev/null; then
    info "Saltato (già installato): $(basename "$FILE")"
    ((SKIPPED++))
    continue
  fi

  if grep -qi "</body>" "$FILE"; then
    cp "$FILE" "${FILE}.bak"
    python3 "$INJECT_PY" "$FILE" "$SNIPPET"
    if [[ $? -eq 0 ]]; then
      ok "Installato: $(basename "$FILE")"
      ((INSTALLED++))
      rm -f "${FILE}.bak"
    else
      err "Errore su: $(basename "$FILE")"
      mv "${FILE}.bak" "$FILE"
      ((ERRORS++))
    fi
  else
    info "Saltato (no </body>): $(basename "$FILE")"
    ((SKIPPED++))
  fi
done <<< "$HTML_FILES"

rm -f "$INJECT_PY"

# ── Step 5: Riepilogo ─────────────────────────────────────────
echo ""
sep
echo -e "\n${BOLD}  INSTALLAZIONE COMPLETATA${RESET}"
echo -e "  ${GREEN}Installato : $INSTALLED file${RESET}"
[[ $SKIPPED -gt 0 ]] && echo -e "  ${DIM}Saltati    : $SKIPPED file${RESET}"
[[ $ERRORS -gt 0 ]]  && echo -e "  ${RED}Errori     : $ERRORS file${RESET}"
echo ""

if [[ $INSTALLED -gt 0 ]]; then
  echo -e "  ${GREEN}${BOLD}Il widget Genesi e' ora attivo sul tuo sito.${RESET}"
  echo -e "  ${DIM}Ricarica le pagine nel browser per vederlo apparire.${RESET}"
  echo ""
  if [[ -z "$USER_NAME" ]]; then
    echo -e "  ${CYAN}Suggerimento: se il tuo CMS gestisce gli utenti loggati,"
    echo -e "  aggiungi data-user-name=\"{{nome_utente}}\" allo script${RESET}"
    echo -e "  ${DIM}per personalizzare il widget per ogni utente.${RESET}"
  fi
fi

sep
echo ""
