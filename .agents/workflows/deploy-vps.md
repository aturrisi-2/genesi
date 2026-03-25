---
description: Deploy Genesi to VPS (gold-faro-stable)
---

## Deploy rapido

1. Commit e push
```powershell
git add .
git commit -m "descrizione modifica"
git push origin gold-faro-stable
```

2. Pull e restart sul VPS
```powershell
ssh luca@87.106.30.193 "cd /opt/genesi && git pull origin gold-faro-stable && sudo systemctl restart genesi"
```

3. Verifica salute (aspetta 5 secondi prima di eseguire)
```powershell
ssh luca@87.106.30.193 "curl -s http://localhost:8000/health && curl -s http://localhost:8000/api/widget/ping -H 'X-Widget-Key: demo_cplace_2026'"
```

---

## Checklist pre-deploy (per modifiche a file critici)

Prima di fare push di modifiche a questi file, verificare:

| File modificato | Controllo obbligatorio |
|----------------|------------------------|
| `api/widget.py` | Nessuna chiamata LLM interna usa `_call_with_protection` — usare sempre `_call_model` |
| `core/proactor.py` | Stessa regola sopra. Testare routing 56/56 dopo la modifica |
| `core/intent_classifier.py` | Stesso. Nessun `import re` locale dentro le funzioni |
| `api/chat.py` | `_extract_and_save_identity` deve restare DOPO `simple_chat_handler` |
| Qualsiasi file che usa `chat_memory` | Chiavi corrette: `user_message` / `system_response` (NON `role` / `content`) |

---

## Dopo ogni sessione di test intensiva

I test neurali e di routing possono corrompere il profilo di Alfio. Resettare sempre:

```powershell
ssh luca@87.106.30.193 "cd /opt/genesi && python3 scripts/fix_profile_alfio.py"
```

---

## Log in tempo reale

```powershell
ssh luca@87.106.30.193 "sudo journalctl -u genesi -f"
```

## Ultimi 50 log

```powershell
ssh luca@87.106.30.193 "sudo journalctl -u genesi -n 50 -o cat"
```

## Ricerca tag specifico nei log

```powershell
ssh luca@87.106.30.193 "grep 'WIDGET_' /opt/genesi/genesi.log | tail -20"
```
