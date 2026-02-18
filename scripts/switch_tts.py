#!/usr/bin/env python3
"""
TTS Switch Utility - Genesi Cognitive System
Script CLI per switchare provider TTS tramite config/tts_config.json
"""

import json
import sys
import os
from pathlib import Path

CONFIG_PATH = Path("config/tts_config.json")


def load_config():
    """Carica configurazione TTS."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8-sig') as f:  # Use utf-8-sig to handle BOM
            return json.load(f)
    except FileNotFoundError:
        print(f"ERRORE: File config non trovato: {CONFIG_PATH}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERRORE: JSON invalido in config: {e}")
        sys.exit(1)


def save_config(config):
    """Salva configurazione TTS."""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"ERRORE: Impossibile salvare config: {e}")
        return False


def show_status():
    """Mostra provider attivo."""
    config = load_config()
    active = config.get("active_provider", "sconosciuto")
    providers = config.get("providers", {})
    
    print(f"Provider attivo: {active}")
    print("Provider disponibili:")
    for name, cfg in providers.items():
        status = "✓" if cfg.get("enabled", False) else "✗"
        print(f"  {status} {name}")
    
    if active not in providers:
        print(f"ATTENZIONE: Provider attivo '{active}' non è nella configurazione!")


def switch_provider(provider_name):
    """Switcha al provider specificato."""
    config = load_config()
    providers = config.get("providers", {})
    
    if provider_name not in providers:
        print(f"ERRORE: Provider '{provider_name}' non è configurato")
        print("Provider disponibili:", ", ".join(providers.keys()))
        sys.exit(1)
    
    if not providers[provider_name].get("enabled", False):
        print(f"ERRORE: Provider '{provider_name}' è disabilitato")
        sys.exit(1)
    
    old_provider = config.get("active_provider")
    config["active_provider"] = provider_name
    
    if save_config(config):
        print(f"Switch TTS: {old_provider} -> {provider_name}")
        print("Provider cambiato con successo!")
    else:
        print("ERRORE: Impossibile salvare la configurazione")
        sys.exit(1)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Uso: python switch_tts.py <piper|edge_tts|openai|status>")
        print("Comandi:")
        print("  piper    - Switcha a Piper TTS")
        print("  edge_tts - Switcha a Edge TTS")
        print("  openai   - Switcha a OpenAI TTS")
        print("  status   - Mostra provider attivo")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "status":
        show_status()
    elif command in ["piper", "edge_tts", "openai"]:
        switch_provider(command)
    else:
        print(f"ERRORE: Comando non riconosciuto: {command}")
        print("Comandi validi: piper, edge_tts, openai, status")
        sys.exit(1)


if __name__ == "__main__":
    main()
