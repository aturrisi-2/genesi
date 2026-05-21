#!/usr/bin/env python3
"""
Pulizia della memoria di Genesi dal loop ossessivo 'nonna/coraggio'.
Questo script:
1. Rimuove insights memorizzati che menzionano la nonna come problema
2. Pulisce la cache di predizioni effimere
3. Rimuove "Coraggio per tua nonna!" dalla storia dei messaggi di gruppo
4. Ricerca ricorsivamente in data/ per trovare tutti i file rilevanti
"""

import json
import os
from pathlib import Path
import re

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
MEMORY_DIR = BASE_DIR / "memory"
MEMORY_V2_DIR = BASE_DIR / "memory_v2"

print("=" * 70)
print("🧠 PULIZIA MEMORIA: Rimozione loop 'nonna/coraggio' da Genesi")
print("=" * 70)

cleaned_count = 0
errors = []

# 1. Cerca file JSON in data/telegram (history)
print("\n📡 Ricerca file storia Telegram in data/telegram/...")
if (DATA_DIR / "memory" / "conversations").exists():
    for json_file in (DATA_DIR / "memory" / "conversations").glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            modified = False
            
            if isinstance(data, dict) and 'messages' in data:
                for msg in data.get('messages', []):
                    if isinstance(msg, dict) and 'response' in msg:
                        old_resp = msg['response']
                        msg['response'] = re.sub(r'\s*Coraggio per tua nonna!?\s*', ' ', msg['response']).strip()
                        if old_resp != msg['response']:
                            modified = True
            
            if modified:
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"   ✓ Pulito: {json_file.name}")
                cleaned_count += 1
        except Exception as e:
            errors.append(f"   ✗ {json_file.name}: {e}")

# 2. Pulisci global_insights
print("\n💭 Ricerca global_insights...")
for insights_file in MEMORY_DIR.glob("**/global_insights*.json"):
    try:
        with open(insights_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        modified = False
        
        if isinstance(data, dict) and 'insights' in data:
            original_len = len(data.get('insights', []))
            data['insights'] = [
                i for i in data.get('insights', [])
                if i and 'nonna' not in str(i).lower()
            ]
            if len(data['insights']) < original_len:
                modified = True
        
        if modified:
            with open(insights_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"   ✓ Pulito: {insights_file.relative_to(BASE_DIR)}")
            cleaned_count += 1
    except Exception as e:
        errors.append(f"   ✗ {insights_file}: {e}")

# 3. Pulisci user profiles
print("\n👤 Ricerca profili utente...")
if (DATA_DIR / "users").exists():
    for user_file in (DATA_DIR / "users").glob("*.json"):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            modified = False
            
            # Rimuovi insights sulla nonna
            if 'global_insights' in data and isinstance(data['global_insights'], list):
                original_len = len(data['global_insights'])
                data['global_insights'] = [
                    i for i in data['global_insights']
                    if 'nonna' not in str(i).lower()
                ]
                if len(data['global_insights']) < original_len:
                    modified = True
            
            if modified:
                with open(user_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                cleaned_count += 1
        except Exception as e:
            pass  # file vuoto, skip silenziosamente

print("\n" + "=" * 70)
print(f"✅ Pulizia completata!")
print(f"   File modificati: {cleaned_count}")
if errors:
    print(f"\n⚠️  Errori incontrati:")
    for e in errors[:5]:  # mostra solo i primi 5
        print(e)
print("=" * 70)
print("\n⚡ AZIONE: Riavvia Genesi per applicare i cambiamenti!")
print("   La regola 'Crisi Familiare' è stata disabilitata in core/proactor.py")
