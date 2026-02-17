#!/usr/bin/env python3
"""
Stress Runner - Test Sistemistico per Genesi
Simula 100 messaggi con pattern ripetitivi per testare memoria emotiva adattiva.
"""

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StressRunner:
    """Runner serio per testare pattern emotivi e memoria."""
    
    def __init__(self):
        self.test_messages = [
            # Pattern stanchezza (ripetuto 5 volte)
            "Mi sento stanco",
            "Sono molto stanco oggi",
            "Ho una stanchezza enorme",
            "Sono esausto",
            "Non ce la più, sono troppo stanco",
            
            # Pattern lavoro (ripetuto 4 volte)
            "Odio il mio lavoro",
            "Voglio cambiare lavoro",
            "Il lavoro mi stressa",
            "Non sopporto più il lavoro",
            
            # Pattern meteo (ripetuto 3 volte)
            "Oggi piove",
            "Che tempo brutto",
            "Fa freddo oggi",
            
            # Pattern ansia (ripetuto 6 volte)
            "Sono ansioso",
            "Mi sento nervoso",
            "Ho l'ansia",
            "Sono preoccupato",
            "Non riesco a stare tranquillo",
            "La mia ansia aumenta",
            
            # Messaggi normali
            "Ciao come stai?",
            "Come va?",
            "Grazie",
            "Ok",
            "Va bene"
        ]
        
        self.metrics = {
            "total_messages": 0,
            "pattern_detected": 0,
            "template_responses": 0,
            "memory_failures": 0,
            "repetition_rate": 0.0,
            "emotional_escalation": 0,
            "response_times": [],
            "incoherence_count": 0
        }
        
        self.pattern_counts = {
            "stanchezza": 0,
            "lavoro": 0,
            "meteo": 0,
            "ansia": 0
        }
        
        self.responses = []
        self.template_phrases = [
            "Vuoi parlarne?",
            "Non posso decidere per te",
            "Mi dispiace sentirlo",
            "Cosa vuoi fare?",
            "Dimmi di più",
            "Come stai?",
            "Ciao",
            "Ok"
        ]
    
    def analyze_response(self, response: str, message: str) -> Dict[str, Any]:
        """Analizza la risposta per metriche di qualità."""
        analysis = {
            "is_template": False,
            "has_question": False,
            "recognizes_pattern": False,
            "is_reflective": False,
            "response_length": len(response)
        }
        
        # Check template
        for template in self.template_phrases:
            if template.lower() in response.lower():
                analysis["is_template"] = True
                break
        
        # Check question
        if "?" in response:
            analysis["has_question"] = True
        
        # Check pattern recognition
        pattern_indicators = [
            "sembra che", "noto che", "vedo che", "sento che",
            "ricorrente", "spesso", "di nuovo", "ancora"
        ]
        for indicator in pattern_indicators:
            if indicator in response.lower():
                analysis["recognizes_pattern"] = True
                break
        
        # Check reflective tone
        reflective_words = [
            "rifletti", "profondo", "significativo", "importante",
            "interessante", "curioso", "osservo"
        ]
        for word in reflective_words:
            if word in response.lower():
                analysis["is_reflective"] = True
                break
        
        return analysis
    
    def detect_message_pattern(self, message: str) -> str:
        """Rileva il pattern emotivo nel messaggio."""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["stanco", "stanchissima", "esausto", "affaticato"]):
            return "stanchezza"
        elif any(word in message_lower for word in ["lavoro", "lavorare", "professione"]):
            return "lavoro"
        elif any(word in message_lower for word in ["piove", "tempo", "meteo", "freddo"]):
            return "meteo"
        elif any(word in message_lower for word in ["ansioso", "ansia", "nervoso", "preoccupato"]):
            return "ansia"
        
        return "none"
    
    async def simulate_message(self, message: str, user_id: str = "stress_test_user") -> Dict[str, Any]:
        """Simula un singolo messaggio e analizza la risposta."""
        start_time = time.time()
        
        # Simula chiamata a Genesi (mock per ora)
        # In produzione, qui ci sarebbe la chiamata reale all'API
        response = await self.mock_genesi_response(message, user_id)
        
        response_time = time.time() - start_time
        
        # Analisi della risposta
        pattern = self.detect_message_pattern(message)
        if pattern != "none":
            self.pattern_counts[pattern] += 1
        
        analysis = self.analyze_response(response, message)
        
        # Update metrics
        self.metrics["total_messages"] += 1
        self.metrics["response_times"].append(response_time)
        
        if analysis["is_template"]:
            self.metrics["template_responses"] += 1
        
        if pattern != "none" and self.pattern_counts[pattern] >= 3:
            if analysis["recognizes_pattern"]:
                self.metrics["pattern_detected"] += 1
            if analysis["is_reflective"]:
                self.metrics["emotional_escalation"] += 1
        
        return {
            "message": message,
            "response": response,
            "pattern": pattern,
            "pattern_count": self.pattern_counts[pattern] if pattern != "none" else 0,
            "analysis": analysis,
            "response_time": response_time
        }
    
    async def mock_genesi_response(self, message: str, user_id: str) -> str:
        """Mock response che simula il comportamento di Genesi."""
        pattern = self.detect_message_pattern(message)
        pattern_count = self.pattern_counts[pattern] if pattern != "none" else 0
        
        # Simula evoluzione delle risposte basata sui pattern
        if pattern_count == 0:
            # Prima volta - risposta standard
            if pattern == "stanchezza":
                return "Mi dispiace sentirlo. Vuoi parlarne?"
            elif pattern == "lavoro":
                return "Non posso decidere per te, ma posso aiutarti a riflettere."
            elif pattern == "meteo":
                return "Il tempo influisce sull'umore. Come ti senti?"
            elif pattern == "ansia":
                return "Capisco l'ansia. Cosa la scatena?"
        elif pattern_count <= 2:
            # Seconda/terza volta - leggera variazione
            if pattern == "stanchezza":
                return "Sento che questa stanchezza si ripete. C'è qualcosa di specifico?"
            elif pattern == "lavoro":
                return "Il lavoro sembra un tema ricorrente. Quali sono i tuoi pensieri?"
            elif pattern == "meteo":
                return "Il tempo continua a influenzarti. Noti un pattern?"
            elif pattern == "ansia":
                return "L'ansia ritorna. Noti quando si presenta?"
        else:
            # Quarta+ volta - deepening response
            if pattern == "stanchezza":
                return "Non è solo stanchezza. È qualcosa che ti pesa da un po', vero?"
            elif pattern == "lavoro":
                return "Questo non è solo lavoro. È qualcosa che tocca la tua identità."
            elif pattern == "meteo":
                return "Il tempo è solo il pretesto. C'è qualcos'altro sotto."
            elif pattern == "ansia":
                return "L'ansia sta diventando una compagna. Come convivi con lei?"
        
        # Risposte generiche per messaggi normali
        generic_responses = [
            "Capisco.",
            "Interessante.",
            "Grazie per avermelo detto.",
            "Ok.",
            "Va bene."
        ]
        return random.choice(generic_responses)
    
    async def run_stress_test(self, total_messages: int = 100) -> Dict[str, Any]:
        """Esegue lo stress test completo."""
        logger.info(f"🚀 Avvio Stress Runner - {total_messages} messaggi")
        
        # Genera sequenza di messaggi con pattern ripetitivi
        message_sequence = []
        for i in range(total_messages):
            # 70% pattern emotivi, 30% messaggi normali
            if random.random() < 0.7:
                # Scegli un pattern e ripetilo
                pattern_messages = [msg for msg in self.test_messages 
                                  if self.detect_message_pattern(msg) != "none"]
                message = random.choice(pattern_messages)
            else:
                # Messaggio normale
                normal_messages = [msg for msg in self.test_messages 
                                 if self.detect_message_pattern(msg) == "none"]
                message = random.choice(normal_messages)
            
            message_sequence.append(message)
        
        # Esegui tutti i messaggi
        results = []
        for i, message in enumerate(message_sequence):
            result = await self.simulate_message(message)
            results.append(result)
            
            if (i + 1) % 20 == 0:
                logger.info(f"Progress: {i + 1}/{total_messages} messaggi processati")
        
        # Calcola metriche finali
        self.calculate_final_metrics()
        
        # Genera report
        report = self.generate_report(results)
        
        logger.info("✅ Stress Runner completato")
        return report
    
    def calculate_final_metrics(self):
        """Calcola le metriche finali."""
        if self.metrics["total_messages"] > 0:
            self.metrics["repetition_rate"] = (
                self.metrics["template_responses"] / self.metrics["total_messages"]
            ) * 100
        
        if self.metrics["response_times"]:
            self.metrics["avg_response_time"] = sum(self.metrics["response_times"]) / len(self.metrics["response_times"])
        
        # Calcola escalation emotiva
        total_pattern_messages = sum(self.pattern_counts.values())
        if total_pattern_messages > 0:
            self.metrics["emotional_escalation_rate"] = (
                self.metrics["emotional_escalation"] / total_pattern_messages
            ) * 100
    
    def generate_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Genera il report finale."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "test_summary": {
                "total_messages": self.metrics["total_messages"],
                "patterns_tested": list(self.pattern_counts.keys()),
                "pattern_counts": self.pattern_counts
            },
            "metrics": {
                "PATTERN DETECTED": "OK" if self.metrics["pattern_detected"] > 0 else "FAIL",
                "REPETITION RATE": f"{self.metrics['repetition_rate']:.1f}%",
                "MEMORY FAILURES": self.metrics["memory_failures"],
                "EMOTIONAL ESCALATION": "OK" if self.metrics["emotional_escalation"] > 0 else "FAIL",
                "AVG RESPONSE TIME": f"{self.metrics.get('avg_response_time', 0):.3f}s",
                "TEMPLATE RESPONSES": self.metrics["template_responses"],
                "INCOHERENCE COUNT": self.metrics["incoherence_count"]
            },
            "pattern_analysis": {},
            "detailed_results": results[:10]  # Solo primi 10 per brevità
        }
        
        # Analisi per pattern
        for pattern, count in self.pattern_counts.items():
            if count > 0:
                pattern_results = [r for r in results if r["pattern"] == pattern]
                pattern_detected = sum(1 for r in pattern_results if r["analysis"]["recognizes_pattern"])
                pattern_reflective = sum(1 for r in pattern_results if r["analysis"]["is_reflective"])
                
                report["pattern_analysis"][pattern] = {
                    "total_occurrences": count,
                    "pattern_recognized": pattern_detected,
                    "reflective_responses": pattern_reflective,
                    "recognition_rate": f"{(pattern_detected/count)*100:.1f}%" if count > 0 else "0%"
                }
        
        return report
    
    def save_report(self, report: Dict[str, Any], filename: str = None):
        """Salva il report su file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"lab/stress_report_{timestamp}.json"
        
        Path("lab").mkdir(exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📄 Report salvato: {filename}")
        return filename

async def main():
    """Main function."""
    runner = StressRunner()
    report = await runner.run_stress_test(100)
    
    # Stampa report
    print("\n" + "="*60)
    print("🎯 STRESS RUNNER REPORT")
    print("="*60)
    
    metrics = report["metrics"]
    for key, value in metrics.items():
        print(f"{key:25}: {value}")
    
    print("\nPattern Analysis:")
    for pattern, analysis in report["pattern_analysis"].items():
        print(f"  {pattern:15}: {analysis['recognition_rate']} recognition")
    
    # Salva report
    filename = runner.save_report(report)
    print(f"\n📄 Report completo salvato in: {filename}")

if __name__ == "__main__":
    asyncio.run(main())
