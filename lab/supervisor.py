"""
Genesi Lab v1 - Supervisor Engine
Sistema di valutazione qualitativa euristico delle conversazioni
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from .metrics_schema import ConversationMetrics


class SupervisorEngine:
    """
    Supervisore qualitativo per la valutazione delle conversazioni.
    
    Implementa valutazione euristica basata su pattern linguistici
    e indicatori qualitativi, senza utilizzo di LLM.
    """
    
    def __init__(self, log_file: str = "lab/supervisor_logs.json"):
        """
        Inizializza il supervisore.
        
        Args:
            log_file: Path del file di log append-only
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Pattern per identificare risposte problematiche
        self.vague_patterns = [
            r"cosa intendi",
            r"puoi essere più specifico",
            r"non ho capito bene",
            r"potresti chiarire",
            r"che cosa esattamente",
            r"spiega meglio",
        ]
        
        self.robotic_patterns = [
            r"come intelligenza artificiale",
            r"sono programmato per",
            r"non ho opinioni personali",
            r"come sistema",
            r"secondo i miei parametri",
            r"basandomi sui dati",
            r"algoritmo",
            # 🆕 Pattern per penalizzare fallback template
            r"servizio",
            r"al momento non ho accesso",
            r"il servizio è temporaneamente",
        ]
        
        self.contradiction_indicators = [
            r"tuttavia",
            r"ma d'altra parte",
            r"in contrasto",
            r"contraddice",
            r"sebbene.*tuttavia",
        ]
        
        self.memory_usage_indicators = [
            r"ricordo che",
            r"so che",
            r"hai detto che",
            r"secondo il tuo profilo",
            r"come menzionato prima",
            r"so che ti piace",
        ]
        
        # 🆕 Pattern per identificare riferimenti alla memoria contestuale
        self.contextual_memory_patterns = [
            r"trasferimento",
            r"stanchezza", 
            r"cane",
            r"loki",  # nome cane specifico
            r"prima",
            r"precedente",
            r"ricordi",
        ]
    
    def evaluate(self, user_message: str, assistant_response: str) -> ConversationMetrics:
        """
        Valuta una conversazione e calcola le metriche.
        
        Args:
            user_message: Messaggio dell'utente
            assistant_response: Risposta dell'assistente
            
        Returns:
            ConversationMetrics: Metriche calcolate
        """
        # Calcolo score individuali
        clarity = self._evaluate_clarity(assistant_response)
        coherence = self._evaluate_coherence(assistant_response)
        memory_score = self._evaluate_memory_usage(user_message, assistant_response)  # 🆕 Pass user_message
        human_likeness = self._evaluate_human_likeness(assistant_response)
        redundancy = self._evaluate_redundancy(assistant_response)
        hallucination_risk = self._evaluate_hallucination_risk(user_message, assistant_response)
        
        # Calcolo overall score ponderato
        weights = {
            'clarity': 0.2,
            'coherence': 0.2,
            'memory': 0.15,
            'human_likeness': 0.2,
            'redundancy': 0.15,
            'hallucination_risk': 0.1
        }
        
        overall = (
            clarity * weights['clarity'] +
            coherence * weights['coherence'] +
            memory_score * weights['memory'] +
            human_likeness * weights['human_likeness'] +
            redundancy * weights['redundancy'] +
            hallucination_risk * weights['hallucination_risk']
        )
        
        metrics = ConversationMetrics(
            clarity_score=clarity,
            coherence_score=coherence,
            contextual_memory_score=memory_score,
            human_likeness_score=human_likeness,
            redundancy_score=redundancy,
            hallucination_risk=hallucination_risk,
            overall_score=overall
        )
        
        # Log append-only
        self._log_evaluation(user_message, assistant_response, metrics)
        
        return metrics
    
    def _evaluate_clarity(self, response: str) -> float:
        """
        Valuta la chiarezza della risposta.
        
        Penalizza risposte vaghe o che chiedono chiarimenti.
        """
        response_lower = response.lower()
        
        # Conta pattern vaghi
        vague_count = sum(1 for pattern in self.vague_patterns 
                         if re.search(pattern, response_lower))
        
        # Penalità per vaghezza
        if vague_count > 0:
            return max(0.3, 1.0 - (vague_count * 0.3))
        
        # Bonus per risposte specifiche e concrete
        specific_indicators = [
            r"\d+",  # numeri
            r"[.!?]",  # punteggiatura completa
            r"\b(perché|come|quando|dove|chi)\b",  # risposte a domande
        ]
        
        specific_count = sum(1 for pattern in specific_indicators 
                           if re.search(pattern, response))
        
        return min(1.0, 0.6 + (specific_count * 0.1))
    
    def _evaluate_coherence(self, response: str) -> float:
        """
        Valuta la coerenza logica.
        
        Penalizza contraddizioni e frasi sconnesse.
        """
        response_lower = response.lower()
        
        # Conta indicatori di contraddizione
        contradiction_count = sum(1 for pattern in self.contradiction_indicators 
                                if re.search(pattern, response_lower))
        
        # Penalità per contraddizioni
        if contradiction_count > 0:
            return max(0.4, 1.0 - (contradiction_count * 0.2))
        
        # Valuta lunghezza e struttura
        sentences = re.split(r'[.!?]+', response)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) == 0:
            return 0.0
        
        # Bonus per coerenza strutturale
        if len(sentences) == 1:
            return 0.8  # Risposta breve e diretta
        elif 2 <= len(sentences) <= 3:
            return 0.9  # Risposta bilanciata
        else:
            return 0.7  # Risposta lunga ma coerente
    
    def _evaluate_memory_usage(self, user_message: str, response: str) -> float:
        """
        Valuta l'uso corretto della memoria contestuale.
        
        🆕 Modificato per valutare riferimenti specifici alla conversazione recente.
        """
        response_lower = response.lower()
        user_lower = user_message.lower()
        
        # Conta indicatori di uso memoria generici
        memory_count = sum(1 for pattern in self.memory_usage_indicators 
                          if re.search(pattern, response_lower))
        
        # 🆕 Penalità contextual memory: se utente chiede continuità ma risposta non include riferimenti
        continuity_questions = [
            r"cosa abbiamo detto prima",
            r"ti ricordi",
            r"ricordi cosa",
            r"cosa abbiamo parlato",
        ]
        
        is_continuity_question = any(re.search(pattern, user_lower) for pattern in continuity_questions)
        
        if is_continuity_question:
            # Conta riferimenti a elementi contestuali specifici
            context_count = sum(1 for pattern in self.contextual_memory_patterns 
                              if re.search(pattern, response_lower))
            
            if context_count == 0:
                return max(0.0, 0.3 - 0.2)  # 🆕 Penalità -0.2 per memoria contestuale mancante
            else:
                return 1.0
        
        # Logica standard per altri casi
        if memory_count > 0:
            return 1.0
        else:
            return 0.3
    
    def _evaluate_human_likeness(self, response: str) -> float:
        """
        Valuta la naturalità e umanità del linguaggio.
        
        🆕 Penalità aggiuntiva per risposte template e ripetizioni.
        """
        response_lower = response.lower()
        
        # Conta pattern robotici (inclusi nuovi pattern fallback)
        robotic_count = sum(1 for pattern in self.robotic_patterns 
                          if re.search(pattern, response_lower))
        
        # 🆕 Penalità -0.15 per risposte template/fallback
        if robotic_count > 0:
            return max(0.2, 1.0 - (robotic_count * 0.4) - 0.15)
        
        # Bonus per indicatori di naturalezza
        natural_indicators = [
            r"\b(certo|certamente|assolutamente)\b",
            r"\b(secondo me|penso che)\b",
            r"\b(davvero|veramente)\b",
            r"!\s*\w+",  # Esclamazioni
        ]
        
        natural_count = sum(1 for pattern in natural_indicators 
                          if re.search(pattern, response_lower))
        
        return min(1.0, 0.5 + (natural_count * 0.15))
    
    def _evaluate_redundancy(self, response: str) -> float:
        """
        Valuta il livello di ridondanza.
        
        🆕 Penalità -0.2 per risposte identiche ripetute o template ricorrenti.
        """
        words = response.lower().split()
        if len(words) < 5:
            return 1.0  # Risposte brevi non sono ridondanti
        
        # Calcola parole uniche
        unique_words = set(words)
        redundancy_ratio = len(unique_words) / len(words)
        
        # 🆕 Penalità per template ricorrenti
        template_patterns = [
            r"non ho accesso",
            r"servizio.*non.*disponibile",
            r"al momento non riesco",
            r"posso aiutarti",
        ]
        
        template_count = sum(1 for pattern in template_patterns 
                           if re.search(pattern, response.lower()))
        
        if template_count > 0:
            return max(0.0, (redundancy_ratio * 1.2) - 0.2)  # 🆕 Penalità -0.2
        
        # Converti in score dove 1 = no ridondanza
        return min(1.0, redundancy_ratio * 1.2)
    
    def _evaluate_hallucination_risk(self, user_message: str, response: str) -> float:
        """
        Valuta il rischio di invenzioni (hallucination).
        
        1.0 = basso rischio, 0.0 = alto rischio.
        """
        response_lower = response.lower()
        
        # Indicatori di alto rischio
        risk_patterns = [
            r"sono assolutamente certo",
            r"garantisco che",
            r"senza dubbio",
            r"certamente",
            r"positivamente",
        ]
        
        risk_count = sum(1 for pattern in risk_patterns 
                        if re.search(pattern, response_lower))
        
        if risk_count > 0:
            return max(0.3, 1.0 - (risk_count * 0.3))
        
        # Indicatori di basso rischio
        safe_patterns = [
            r"secondo le mie informazioni",
            r"per quanto ne so",
            r"generalmente",
            r"solitamente",
            r"tendenzialmente",
        ]
        
        safe_count = sum(1 for pattern in safe_patterns 
                        if re.search(pattern, response_lower))
        
        return min(1.0, 0.6 + (safe_count * 0.1))
    
    def _log_evaluation(self, user_message: str, assistant_response: str, 
                       metrics: ConversationMetrics) -> None:
        """
        Salva valutazione in log append-only.
        
        Args:
            user_message: Messaggio utente
            assistant_response: Risposta assistente
            metrics: Metriche calcolate
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_message": user_message[:200],  # Truncate for readability
            "assistant_response": assistant_response[:200],
            "metrics": metrics.to_dict(),
            "quality_level": metrics.get_quality_level(),
            "improvement_areas": metrics.get_improvement_areas()
        }
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"Warning: Failed to write supervisor log: {e}")
    
    def get_metrics_summary(self, n_last: int = 100) -> Dict[str, Any]:
        """
        Calcola statistiche aggregate dalle ultime n valutazioni.
        
        Args:
            n_last: Numero di valutazioni recenti da considerare
            
        Returns:
            Dict[str, Any]: Statistiche aggregate
        """
        if not self.log_file.exists():
            return {"error": "No log file found"}
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Prendi ultimi n lines
            recent_lines = lines[-n_last:] if len(lines) > n_last else lines
            
            if not recent_lines:
                return {"error": "No evaluations found"}
            
            # Parse metrics
            all_metrics = []
            for line in recent_lines:
                try:
                    entry = json.loads(line.strip())
                    metrics = ConversationMetrics.from_dict(entry['metrics'])
                    all_metrics.append(metrics)
                except Exception:
                    continue
            
            if not all_metrics:
                return {"error": "No valid metrics found"}
            
            # Calcola medie
            avg_metrics = {
                'clarity_score': sum(m.clarity_score for m in all_metrics) / len(all_metrics),
                'coherence_score': sum(m.coherence_score for m in all_metrics) / len(all_metrics),
                'contextual_memory_score': sum(m.contextual_memory_score for m in all_metrics) / len(all_metrics),
                'human_likeness_score': sum(m.human_likeness_score for m in all_metrics) / len(all_metrics),
                'redundancy_score': sum(m.redundancy_score for m in all_metrics) / len(all_metrics),
                'hallucination_risk': sum(m.hallucination_risk for m in all_metrics) / len(all_metrics),
                'overall_score': sum(m.overall_score for m in all_metrics) / len(all_metrics),
            }
            
            # Calcola distribuzione quality levels
            quality_distribution = {}
            for metrics in all_metrics:
                level = metrics.get_quality_level()
                quality_distribution[level] = quality_distribution.get(level, 0) + 1
            
            return {
                'evaluations_count': len(all_metrics),
                'average_metrics': avg_metrics,
                'quality_distribution': quality_distribution,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Failed to analyze logs: {e}"}
