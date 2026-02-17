"""
Genesi Lab v1 - Adaptive Prompt Builder
Sistema per miglioramento automatico dei prompt globali basato su metriche
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .metrics_schema import ConversationMetrics


class AdaptivePromptBuilder:
    """
    Costruttore adattivo di prompt globali basato su metriche qualitative.
    
    Analizza le metriche delle conversazioni e genera miglioramenti
    specifici al system prompt per ottimizzare le performance.
    """
    
    def __init__(self, prompt_file: str = "lab/global_prompt.json"):
        """
        Inizializza il builder adattivo.
        
        Args:
            prompt_file: Path del file JSON per salvare prompt migliorati
        """
        self.prompt_file = Path(prompt_file)
        self.prompt_file.parent.mkdir(parents=True, exist_ok=True)
        
        # System prompt base di partenza
        self.base_system_prompt = """Sei un assistente AI conversazionale avanzato che aiuta gli utenti con informazioni e supporto personalizzato.

Principi guida:
- Rispondi in modo chiaro, specifico e utile
- Usa il contesto e la memoria per personalizzare le risposte
- Mantieni un tono naturale e conversazionale
- Evita ripetizioni e frasi robotiche
- Sii onesto sulle limitazioni e incertezze
- Adatta lo stile di comunicazione all'utente

Obiettivo: Fornire assistenza di alta qualità che sia sia accurata che piacevole da usare."""
        
        # Regole di miglioramento basate su metriche
        self.improvement_rules = {
            'clarity': {
                'threshold': 0.6,
                'instruction': "Rispondi in modo specifico e dettagliato. Evita risposte vaghe o generiche. Usa esempi concreti quando possibile. Struttura le risposte in modo chiaro e logico.",
                'priority': 'high'
            },
            'memory_usage': {
                'threshold': 0.6,
                'instruction': "Integra sempre le informazioni dal profilo utente e dalla memoria contestuale. Fai riferimento a conversazioni precedenti quando rilevante. Personalizza le risposte basandoti sulle preferenze e caratteristiche dell'utente.",
                'priority': 'high'
            },
            'naturalness': {
                'threshold': 0.6,
                'instruction': "Usa un linguaggio naturale e conversazionale. Evita frasi robotiche come 'come intelligenza artificiale' o 'sono programmato per'. Esprimiti come farebbe una persona empatica e intelligente.",
                'priority': 'medium'
            },
            'redundancy': {
                'threshold': 0.6,
                'instruction': "Evita ripetizioni inutili. Ogni frase deve aggiungere valore e nuove informazioni. Sii conciso ma completo. Varia il vocabolario e la struttura delle frasi.",
                'priority': 'medium'
            },
            'coherence': {
                'threshold': 0.6,
                'instruction': "Mantieni coerenza logica in tutta la risposta. Evita contraddizioni. Assicurati che le diverse parti della risposta siano collegate in modo logico.",
                'priority': 'medium'
            },
            'hallucination_risk': {
                'threshold': 0.6,
                'instruction': "Sii prudente con affermazioni assolute. Usa espressioni come 'secondo le mie informazioni', 'generalmente', 'tendenzialmente' quando appropriato. Ammetti quando non hai informazioni sufficienti.",
                'priority': 'high'
            }
        }
        
        # 🆕 Regole speciali per soglie basse
        self.special_rules = {
            'human_likeness_low': {
                'threshold': 0.6,
                'instruction': "Evita risposte template o frasi standardizzate. Trasforma ogni risposta tecnica in frase conversazionale. Integra sempre una connessione emotiva o contestuale.",
                'metric': 'human_likeness'
            },
            'contextual_memory_low': {
                'threshold': 0.5,
                'instruction': "Fai sempre riferimento esplicito ad almeno un elemento della conversazione recente quando l'utente chiede continuità.",
                'metric': 'contextual_memory'
            }
        }
    
    def build_adaptive_prompt(self, metrics_list: List[ConversationMetrics]) -> Dict[str, Any]:
        """
        Costruisce prompt adattivo basato su metriche delle conversazioni.
        
        Args:
            metrics_list: Lista di metriche da analizzare
            
        Returns:
            Dict[str, Any]: Prompt migliorato con metadati
        """
        # Calcola medie delle metriche
        avg_metrics = self._calculate_average_metrics(metrics_list)
        
        # Identifica aree di miglioramento
        improvement_areas = self._identify_improvement_areas(avg_metrics)
        
        # Genera istruzioni aggiuntive
        additional_instructions = self._generate_additional_instructions(improvement_areas)
        
        # Costruisci prompt migliorato
        improved_prompt = self._build_improved_prompt(additional_instructions)
        
        # Prepara risultato
        result = {
            "date": datetime.now().isoformat(),
            "metrics_average": avg_metrics,
            "improvement_areas": improvement_areas,
            "additional_instructions": additional_instructions,
            "system_prompt": improved_prompt,
            "base_prompt": self.base_system_prompt,
            "evaluations_analyzed": len(metrics_list)
        }
        
        # Salva su file
        self._save_prompt(result)
        
        return result
    
    def _calculate_average_metrics(self, metrics_list: List[ConversationMetrics]) -> Dict[str, float]:
        """
        Calcola medie delle metriche.
        
        Args:
            metrics_list: Lista di metriche
            
        Returns:
            Dict[str, float]: Metriche medie
        """
        if not metrics_list:
            return {}
        
        return {
            'clarity_score': sum(m.clarity_score for m in metrics_list) / len(metrics_list),
            'coherence_score': sum(m.coherence_score for m in metrics_list) / len(metrics_list),
            'contextual_memory_score': sum(m.contextual_memory_score for m in metrics_list) / len(metrics_list),
            'human_likeness_score': sum(m.human_likeness_score for m in metrics_list) / len(metrics_list),
            'redundancy_score': sum(m.redundancy_score for m in metrics_list) / len(metrics_list),
            'hallucination_risk': sum(m.hallucination_risk for m in metrics_list) / len(metrics_list),
            'overall_score': sum(m.overall_score for m in metrics_list) / len(metrics_list)
        }
    
    def _identify_improvement_areas(self, avg_metrics: Dict[str, float]) -> List[str]:
        """
        Identifica aree di miglioramento basate su soglie.
        
        🆕 Modificato per includere regole speciali per soglie basse.
        """
        improvement_areas = []
        
        # Regole standard
        for area, rule in self.improvement_rules.items():
            metric_name = f"{area}_score"
            if metric_name in avg_metrics and avg_metrics[metric_name] < rule['threshold']:
                improvement_areas.append(area)
        
        # 🆕 Regole speciali per soglie basse
        for rule_name, rule in self.special_rules.items():
            metric_name = rule['metric']
            if metric_name in avg_metrics and avg_metrics[metric_name] < rule['threshold']:
                improvement_areas.append(rule_name)
        
        return improvement_areas
    
    def _map_area_to_metric(self, area: str) -> str:
        """
        Mappa area di miglioramento al nome della metrica corrispondente.
        
        Args:
            area: Area di miglioramento
            
        Returns:
            str: Nome della metrica
        """
        mapping = {
            'clarity': 'clarity_score',
            'memory_usage': 'contextual_memory_score',
            'naturalness': 'human_likeness_score',
            'redundancy': 'redundancy_score',
            'coherence': 'coherence_score',
            'hallucination_risk': 'hallucination_risk'
        }
        return mapping.get(area, area)
    
    def _generate_additional_instructions(self, improvement_areas: List[str]) -> List[str]:
        """
        Genera istruzioni aggiuntive basate su aree di miglioramento.
        
        🆕 Modificato per includere regole speciali.
        """
        instructions = []
        
        for area in improvement_areas:
            if area in self.improvement_rules:
                rule = self.improvement_rules[area]
                instructions.append(rule['instruction'])
            elif area in self.special_rules:
                rule = self.special_rules[area]
                instructions.append(rule['instruction'])
        
        return instructions
    
    def _build_improved_prompt(self, additional_instructions: List[str]) -> str:
        """
        Costruisce prompt migliorato aggiungendo istruzioni specifiche.
        
        Args:
            additional_instructions: Istruzioni aggiuntive da includere
            
        Returns:
            str: Prompt migliorato
        """
        improved_prompt = self.base_system_prompt
        
        if additional_instructions:
            improved_prompt += "\n\nIstruzioni specifiche per miglioramento:\n"
            for i, instruction in enumerate(additional_instructions, 1):
                improved_prompt += f"\n{i}. {instruction}"
        
        # Aggiungi nota di contesto
        improved_prompt += f"\n\nQuesto prompt è stato generato automaticamente il {datetime.now().strftime('%d/%m/%Y %H:%M')} basato su analisi qualitativa delle conversazioni."
        
        return improved_prompt
    
    def _save_prompt(self, prompt_data: Dict[str, Any]) -> None:
        """
        Salva il prompt migliorato su file JSON.
        
        Args:
            prompt_data: Dati del prompt da salvare
        """
        try:
            with open(self.prompt_file, 'w', encoding='utf-8') as f:
                json.dump(prompt_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save adaptive prompt: {e}")
    
    def load_latest_prompt(self) -> Optional[Dict[str, Any]]:
        """
        Carica l'ultimo prompt salvato.
        
        Returns:
            Optional[Dict[str, Any]]: Dati del prompt o None se non esiste
        """
        if not self.prompt_file.exists():
            return None
        
        try:
            with open(self.prompt_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load adaptive prompt: {e}")
            return None
    
    def get_improvement_history(self) -> List[Dict[str, Any]]:
        """
        Recupera storico dei miglioramenti (se implementato).
        
        Returns:
            List[Dict[str, Any]]: Storico dei miglioramenti
        """
        # Per ora ritorna solo l'ultimo prompt
        # In futuro potrebbe implementare storico completo
        latest = self.load_latest_prompt()
        return [latest] if latest else []
    
    def compare_prompts(self, old_prompt: str, new_prompt: str) -> Dict[str, Any]:
        """
        Confronta due prompt e analizza le differenze.
        
        Args:
            old_prompt: Prompt originale
            new_prompt: Prompt migliorato
            
        Returns:
            Dict[str, Any]: Analisi delle differenze
        """
        old_lines = set(old_prompt.strip().split('\n'))
        new_lines = set(new_prompt.strip().split('\n'))
        
        added_lines = new_lines - old_lines
        removed_lines = old_lines - new_lines
        common_lines = old_lines & new_lines
        
        return {
            "old_prompt_length": len(old_prompt),
            "new_prompt_length": len(new_prompt),
            "lines_added": len(added_lines),
            "lines_removed": len(removed_lines),
            "lines_common": len(common_lines),
            "expansion_ratio": len(new_prompt) / len(old_prompt) if old_prompt else 0,
            "added_content": list(added_lines)[:5],  # Prime 5 linee aggiunte
            "removed_content": list(removed_lines)[:5]  # Prime 5 linee rimosse
        }
