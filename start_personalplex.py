#!/usr/bin/env python3
"""
Script avvio PersonalPlex 7B Server
Avvia il servizio LLM locale per Genesi
"""

import os
import sys
import subprocess
import time
import signal
import requests
from pathlib import Path

def check_dependencies():
    """Verifica dipendenze necessarie"""
    
    print("🔍 Verifica dipendenze PersonalPlex 7B...")
    
    required_packages = [
        "torch",
        "transformers", 
        "fastapi",
        "uvicorn",
        "pydantic",
        "requests"
    ]
    
    missing = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} - MANCANTE")
            missing.append(package)
    
    if missing:
        print(f"\n❌ Installare dipendenze mancanti:")
        print(f"pip install {' '.join(missing)}")
        return False
    
    print("✅ Tutte le dipendenze presenti")
    return True

def check_gpu():
    """Verifica disponibilità GPU"""
    
    try:
        import torch
        
        print("🔍 Verifica GPU...")
        
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"   ✅ GPU: {gpu_name}")
            print(f"   ✅ Memoria: {gpu_memory:.1f} GB")
            return True
        else:
            print("   ⚠️ CUDA non disponibile - userò CPU")
            print("   ⚠️ Performance ridotta su CPU")
            return True  # Allow CPU fallback
            
    except Exception as e:
        print(f"   ❌ Errore verifica GPU: {e}")
        return False

def start_server():
    """Avvia il server PersonalPlex"""
    
    print("\n🚀 Avvio PersonalPlex 7B Server...")
    
    # Path dello script
    script_path = Path(__file__).parent / "personalplex_server.py"
    
    if not script_path.exists():
        print(f"❌ File non trovato: {script_path}")
        return False
    
    # Avvia il server
    try:
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        print(f"✅ Server avviato (PID: {process.pid})")
        
        # Attendi che il server sia pronto
        print("⏳ Atteso avvio server...")
        
        for i in range(60):  # Max 60 secondi
            try:
                response = requests.get("http://localhost:8001/health", timeout=2)
                if response.status_code == 200:
                    health_data = response.json()
                    if health_data.get("status") == "ok":
                        print("✅ PersonalPlex 7B pronto!")
                        print(f"   Model: {health_data.get('model', 'unknown')}")
                        print(f"   Device: {health_data.get('device', 'unknown')}")
                        print(f"   Status: {health_data.get('model_loaded', False)}")
                        return process
            except:
                pass
            
            # Mostra output del server
            if process.poll() is not None:
                print("❌ Server terminato durante avvio")
                for line in process.stdout:
                    print(f"   {line.strip()}")
                return False
            
            time.sleep(1)
            print(f"   Attendo... ({i+1}/60)")
        
        print("❌ Timeout avvio server")
        return False
        
    except Exception as e:
        print(f"❌ Errore avvio server: {e}")
        return False

def monitor_server(process):
    """Monitora il server e gestisce segnali"""
    
    def signal_handler(signum, frame):
        print(f"\n🛑 Ricevuto segnale {signum} - spegnimento server...")
        if process:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print("Forzando terminazione...")
                process.kill()
        sys.exit(0)
    
    # Registra handler per segnali
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("📡 PersonalPlex 7B in esecuzione")
    print("   Health: http://localhost:8001/health")
    print("   Analyze: http://localhost:8001/analyze")
    print("   Generate: http://localhost:8001/generate")
    print("\nPremi Ctrl+C per fermare il server")
    
    try:
        # Monitora output del server
        for line in process.stdout:
            line = line.strip()
            if line:
                print(f"[PERSONALPLEX] {line}")
        
        # Se il processo termina
        return_code = process.wait()
        print(f"\n❌ Server terminato (return code: {return_code})")
        
    except KeyboardInterrupt:
        print("\n🛑 Interruzione utente")
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

def main():
    """Funzione principale"""
    
    print("🎯 AVVIO PERSONALPLEX 7B SERVER")
    print("=" * 50)
    
    # Verifica dipendenze
    if not check_dependencies():
        sys.exit(1)
    
    # Verifica GPU
    if not check_gpu():
        sys.exit(1)
    
    # Avvia server
    process = start_server()
    if not process:
        sys.exit(1)
    
    # Monitora server
    monitor_server(process)

if __name__ == "__main__":
    main()
