"""
Genesi Lab v1 - Prompt Versioning System
Sistema di versioning e rollback automatico per prompt globali
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import shutil


class PromptVersioning:
    """
    Sistema di versioning per prompt globali con rollback automatico.
    
    Gestisce salvataggio versionato, confronto punteggi e ripristino.
    """
    
    def __init__(self, lab_dir: str = "lab"):
        """
        Inizializza il sistema di versioning.
        
        Args:
            lab_dir: Directory principale del laboratorio
        """
        self.lab_dir = Path(lab_dir)
        self.history_dir = self.lab_dir / "prompt_history"
        self.current_prompt_file = self.lab_dir / "global_prompt.json"
        
        # Crea directory history se non esiste
        self.history_dir.mkdir(parents=True, exist_ok=True)
    
    def save_new_prompt_version(self, prompt_data: Dict[str, Any]) -> str:
        """
        Salva nuova versione in lab/prompt_history/
        
        Args:
            prompt_data: Dati del prompt da salvare
            
        Returns:
            str: Path del file salvato
        """
        # Genera nome file con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"prompt_{timestamp}.json"
        filepath = self.history_dir / filename
        
        # Aggiungi metadata di versioning
        versioned_data = prompt_data.copy()
        versioned_data.update({
            "version_info": {
                "saved_at": datetime.now().isoformat(),
                "version_file": filename,
                "previous_score": self._get_previous_score()
            }
        })
        
        # Salva file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(versioned_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Prompt versione salvato: {filepath}")
            return str(filepath)
            
        except Exception as e:
            print(f"❌ Errore salvataggio versione: {e}")
            raise
    
    def get_latest_prompt_version(self) -> Optional[Dict[str, Any]]:
        """
        Carica ultima versione salvata dalla history.
        
        Returns:
            Optional[Dict[str, Any]]: Dati ultima versione o None
        """
        if not self.history_dir.exists():
            return None
        
        # Lista file version e ordina per nome (timestamp)
        version_files = sorted(
            [f for f in self.history_dir.glob("prompt_*.json")],
            key=lambda x: x.name,
            reverse=True
        )
        
        if not version_files:
            return None
        
        latest_file = version_files[0]
        
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"📂 Caricata ultima versione: {latest_file.name}")
            return data
            
        except Exception as e:
            print(f"❌ Errore caricamento versione: {e}")
            return None
    
    def should_accept_new_prompt(self, new_score: float, previous_score: float) -> bool:
        """
        Accetta nuovo prompt solo se:
        new_score >= previous_score - 0.02 (Tolleranza 2%)
        
        Args:
            new_score: Score del nuovo prompt
            previous_score: Score del prompt precedente
            
        Returns:
            bool: True se accettare nuovo prompt
        """
        tolerance = 0.02
        min_acceptable_score = previous_score - tolerance
        
        should_accept = new_score >= min_acceptable_score
        
        print(f"📊 Confronto punteggi:")
        print(f"   - Score precedente: {previous_score:.3f}")
        print(f"   - Score nuovo: {new_score:.3f}")
        print(f"   - Minimo accettabile: {min_acceptable_score:.3f}")
        print(f"   - Risultato: {'✅ ACCETTATO' if should_accept else '❌ RIFIUTATO'}")
        
        return should_accept
    
    def rollback_to_previous(self) -> Optional[str]:
        """
        Ripristina versione precedente come global_prompt.json
        
        Returns:
            Optional[str]: Path del file ripristinato o None
        """
        # Carica ultima versione dalla history
        latest_version = self.get_latest_prompt_version()
        
        if not latest_version:
            print("❌ Nessuna versione precedente trovata per rollback")
            return None
        
        try:
            # Rimuovi metadata di versioning per salvataggio pulito
            clean_data = latest_version.copy()
            if "version_info" in clean_data:
                del clean_data["version_info"]
            
            # Salva come current prompt
            with open(self.current_prompt_file, 'w', encoding='utf-8') as f:
                json.dump(clean_data, f, indent=2, ensure_ascii=False)
            
            print(f"🔄 Rollback completato: {self.current_prompt_file}")
            return str(self.current_prompt_file)
            
        except Exception as e:
            print(f"❌ Errore rollback: {e}")
            return None
    
    def get_version_history(self) -> List[Dict[str, Any]]:
        """
        Ottiene lista di tutte le versioni disponibili.
        
        Returns:
            List[Dict[str, Any]]: Lista versioni con metadata
        """
        if not self.history_dir.exists():
            return []
        
        versions = []
        
        for file in sorted(self.history_dir.glob("prompt_*.json"), reverse=True):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                versions.append({
                    "filename": file.name,
                    "filepath": str(file),
                    "saved_at": data.get("version_info", {}).get("saved_at"),
                    "overall_score": data.get("metrics_average", {}).get("overall_score"),
                    "improvement_areas": data.get("improvement_areas", [])
                })
                
            except Exception as e:
                print(f"⚠️ Errore lettura versione {file.name}: {e}")
                continue
        
        return versions
    
    def _get_previous_score(self) -> Optional[float]:
        """
        Ottiene score del prompt corrente.
        
        Returns:
            Optional[float]: Score precedente o None
        """
        if not self.current_prompt_file.exists():
            return None
        
        try:
            with open(self.current_prompt_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data.get("metrics_average", {}).get("overall_score")
            
        except Exception:
            return None
    
    def get_versioning_stats(self) -> Dict[str, Any]:
        """
        Ottiene statistiche del sistema di versioning.
        
        Returns:
            Dict[str, Any]: Statistiche complete
        """
        versions = self.get_version_history()
        
        stats = {
            "total_versions": len(versions),
            "latest_version": versions[0]["filename"] if versions else None,
            "oldest_version": versions[-1]["filename"] if versions else None,
            "current_prompt_exists": self.current_prompt_file.exists(),
            "history_dir_exists": self.history_dir.exists(),
            "recent_scores": []
        }
        
        # Ultimi 5 score
        for version in versions[:5]:
            if version["overall_score"] is not None:
                stats["recent_scores"].append({
                    "version": version["filename"],
                    "score": version["overall_score"],
                    "date": version["saved_at"]
                })
        
        return stats


# Funzioni globali per compatibilità
def save_new_prompt_version(prompt_data: dict) -> str:
    """Wrapper globale per save_new_prompt_version"""
    versioning = PromptVersioning()
    return versioning.save_new_prompt_version(prompt_data)


def get_latest_prompt_version() -> Optional[dict]:
    """Wrapper globale per get_latest_prompt_version"""
    versioning = PromptVersioning()
    return versioning.get_latest_prompt_version()


def should_accept_new_prompt(new_score: float, previous_score: float) -> bool:
    """Wrapper globale per should_accept_new_prompt"""
    versioning = PromptVersioning()
    return versioning.should_accept_new_prompt(new_score, previous_score)


def rollback_to_previous() -> Optional[str]:
    """Wrapper globale per rollback_to_previous"""
    versioning = PromptVersioning()
    return versioning.rollback_to_previous()
