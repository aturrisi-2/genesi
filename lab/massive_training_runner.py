#!/usr/bin/env python3
"""
Massive Training Runner - Stress Test Relazionale per Genesi
Simula 10.000 messaggi multi-utente per testare stabilità e evoluzione relazionale.
"""

import asyncio
import json
import logging
import random
import time
import requests
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from collections import Counter, defaultdict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MassiveTrainingRunner:
    """Runner massivo per stress test relazionale multi-utente."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.api_endpoint = f"{base_url}/api/chat/"
        
        # Configurazione
        self.TOTAL_MESSAGES = 10000
        self.SLEEP_BETWEEN = 0.05
        
        # Profili utenti
        self.user_profiles = {
            "user_stable": {
                "messages": [
                    "Ciao come stai?",
                    "Come va oggi?",
                    "Grazie per il supporto",
                    "Va tutto bene",
                    "Apprezzo la conversazione"
                ],
                "pattern": "stable"
            },
            "user_emotional": {
                "messages": [
                    "Mi sento stanco",
                    "Ho avuto una giornata difficile",
                    "Mi sento sopraffatto",
                    "Sono molto esausto",
                    "Non ce la più",
                    "La stanchezza mi pesa",
                    "Mi sento giù",
                    "Sono demotivato"
                ],
                "pattern": "emotional"
            },
            "user_repetitive": {
                "messages": [
                    "Non so cosa fare",
                    "Non so cosa fare",
                    "Non so cosa fare",
                    "Non so cosa fare",
                    "Non so cosa fare",
                    "Aiutami",
                    "Aiutami",
                    "Aiutami"
                ],
                "pattern": "repetitive"
            },
            "user_confrontational": {
                "messages": [
                    "Non mi stai capendo",
                    "Questa risposta non serve",
                    "Sei troppo generico",
                    "Non mi aiuti per niente",
                    "Rispondi in modo utile",
                    "Basta con queste frasi standard"
                ],
                "pattern": "confrontational"
            },
            "user_random": {
                "messages": [
                    "Che tempo fa?",
                    "C'è qualcosa di interessante?",
                    "Dimmi una curiosità",
                    "Come funziona il mondo?",
                    "Qual è il tuo scopo?",
                    "Parlami di te",
                    "Cosa pensi della vita?",
                    "Esistono altre dimensioni?"
                ],
                "pattern": "random"
            }
        }
        
        # Metriche
        self.metrics = {
            "total_messages": 0,
            "repetition_detected": 0,
            "emotional_responses": 0,
            "confrontational_responses": 0,
            "supportive_responses": 0,
            "avg_response_time": 0.0,
            "response_times": [],
            "errors": 0,
            "user_distribution": defaultdict(int),
            "state_estimates": defaultdict(int),
            "start_time": None,
            "end_time": None
        }
        
        # Parole chiave per analisi risposta
        self.response_keywords = {
            "supportive": ["capisco", "comprendo", "sono qui", "ti supporto", "contenimento", "empatico"],
            "confrontational": ["diretto", "chiaro", "concreto", "senza giri", "esplicito"],
            "repetitive": ["già detto", "ripeti", "stessa cosa", "di nuovo"],
            "emotional": ["sentire", "emozione", "sentito", "emotivo"],
            "question": ["cosa", "come", "perché", "quando", "dove"],
            "template": ["vuoi parlarne", "dimmi", "raccontami", "non posso decidere"]
        }
    
    def estimate_relational_state(self, response: str) -> str:
        """Stima lo stato relazionale basandosi sulla risposta."""
        response_lower = response.lower()
        
        # Count keyword matches
        keyword_counts = {}
        for category, keywords in self.response_keywords.items():
            count = sum(1 for keyword in keywords if keyword in response_lower)
            keyword_counts[category] = count
        
        # Simple heuristic for state estimation
        if keyword_counts["confrontational"] > 0:
            return "confrontational"
        elif keyword_counts["supportive"] >= 2:
            return "supportive_deep"
        elif keyword_counts["emotional"] > 0 and keyword_counts["supportive"] > 0:
            return "attuned"
        elif keyword_counts["question"] > 0:
            return "engaged"
        elif keyword_counts["repetitive"] > 0:
            return "confrontational"
        else:
            return "neutral"
    
    def analyze_response(self, response: str, user_pattern: str) -> Dict[str, Any]:
        """Analizza la risposta per estrarre metriche."""
        analysis = {
            "response_length": len(response),
            "has_question": "?" in response,
            "estimated_state": self.estimate_relational_state(response),
            "keyword_matches": {}
        }
        
        # Count keyword matches
        for category, keywords in self.response_keywords.items():
            matches = [kw for kw in keywords if kw in response.lower()]
            analysis["keyword_matches"][category] = matches
        
        # Specific analysis based on user pattern
        if user_pattern == "emotional":
            if any(kw in response.lower() for kw in self.response_keywords["supportive"]):
                analysis["is_supportive"] = True
            else:
                analysis["is_supportive"] = False
                
        elif user_pattern == "repetitive":
            if any(kw in response.lower() for kw in self.response_keywords["repetitive"]):
                analysis["repetition_detected"] = True
            else:
                analysis["repetition_detected"] = False
        
        return analysis
    
    async def send_message(self, user_id: str, message: str) -> Dict[str, Any]:
        """Invia un messaggio a Genesi e analizza la risposta."""
        start_time = time.time()
        
        try:
            # Prepara payload
            payload = {
                "message": message,
                "user_id": user_id
            }
            
            # Invia richiesta
            response = requests.post(
                self.api_endpoint,
                json=payload,
                timeout=10.0,
                headers={"Content-Type": "application/json"}
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                reply = data.get("response", "")
                
                # Analizza risposta
                user_profile = self.user_profiles[user_id]
                analysis = self.analyze_response(reply, user_profile["pattern"])
                
                # Update metrics
                self.metrics["response_times"].append(response_time)
                self.metrics["state_estimates"][analysis["estimated_state"]] += 1
                
                if analysis["estimated_state"] == "supportive_deep":
                    self.metrics["supportive_responses"] += 1
                elif analysis["estimated_state"] == "confrontational":
                    self.metrics["confrontational_responses"] += 1
                
                if analysis.get("repetition_detected", False):
                    self.metrics["repetition_detected"] += 1
                
                return {
                    "success": True,
                    "response": reply,
                    "response_time": response_time,
                    "analysis": analysis
                }
            else:
                self.metrics["errors"] += 1
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "response_time": response_time
                }
                
        except Exception as e:
            self.metrics["errors"] += 1
            return {
                "success": False,
                "error": str(e),
                "response_time": time.time() - start_time
            }
    
    def get_random_user_and_message(self) -> tuple:
        """Seleziona utente e messaggio casuali."""
        user_id = random.choice(list(self.user_profiles.keys()))
        user_profile = self.user_profiles[user_id]
        message = random.choice(user_profile["messages"])
        return user_id, message
    
    def print_progress(self):
        """Stampa progresso corrente."""
        metrics = self.metrics
        
        # Calculate average response time
        if metrics["response_times"]:
            avg_time = sum(metrics["response_times"]) / len(metrics["response_times"])
        else:
            avg_time = 0.0
        
        print(f"""
===== PROGRESS =====
Messages: {metrics['total_messages']}/{self.TOTAL_MESSAGES}
Avg Response Time: {avg_time:.3f}s
Supportive: {metrics['supportive_responses']}
Confrontational: {metrics['confrontational_responses']}
Repetition Detected: {metrics['repetition_detected']}
Errors: {metrics['errors']}
User Distribution: {dict(metrics['user_distribution'])}
State Estimates: {dict(metrics['state_estimates'])}
==================
""")
    
    async def run_massive_training(self) -> Dict[str, Any]:
        """Esegue il training massivo."""
        logger.info(f"🚀 Avvio Massive Training Runner - {self.TOTAL_MESSAGES} messaggi")
        
        self.metrics["start_time"] = datetime.now().isoformat()
        
        for i in range(self.TOTAL_MESSAGES):
            # Seleziona utente e messaggio
            user_id, message = self.get_random_user_and_message()
            self.metrics["user_distribution"][user_id] += 1
            
            # Invia messaggio
            result = await self.send_message(user_id, message)
            
            self.metrics["total_messages"] += 1
            
            # Progress logging
            if (i + 1) % 100 == 0:
                self.print_progress()
            
            # Sleep tra messaggi
            if self.SLEEP_BETWEEN > 0:
                await asyncio.sleep(self.SLEEP_BETWEEN)
        
        self.metrics["end_time"] = datetime.now().isoformat()
        
        # Calculate final metrics
        if self.metrics["response_times"]:
            self.metrics["avg_response_time"] = sum(self.metrics["response_times"]) / len(self.metrics["response_times"])
        
        # Calculate duration
        if self.metrics["start_time"] and self.metrics["end_time"]:
            start = datetime.fromisoformat(self.metrics["start_time"])
            end = datetime.fromisoformat(self.metrics["end_time"])
            self.metrics["duration_seconds"] = (end - start).total_seconds()
        
        logger.info("✅ Massive Training completato")
        return self.generate_report()
    
    def generate_report(self) -> Dict[str, Any]:
        """Genera il report finale."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "configuration": {
                "total_messages": self.TOTAL_MESSAGES,
                "sleep_between": self.SLEEP_BETWEEN,
                "base_url": self.base_url
            },
            "metrics": {
                "total_messages": self.metrics["total_messages"],
                "successful_messages": self.metrics["total_messages"] - self.metrics["errors"],
                "error_rate": (self.metrics["errors"] / max(1, self.metrics["total_messages"])) * 100,
                "avg_response_time": self.metrics["avg_response_time"],
                "supportive_responses": self.metrics["supportive_responses"],
                "confrontational_responses": self.metrics["confrontational_responses"],
                "repetition_detected": self.metrics["repetition_detected"],
                "errors": self.metrics["errors"],
                "duration_seconds": self.metrics.get("duration_seconds", 0)
            },
            "user_analysis": {
                "distribution": dict(self.metrics["user_distribution"]),
                "patterns_used": list(set(profile["pattern"] for profile in self.user_profiles.values()))
            },
            "relational_states": dict(self.metrics["state_estimates"]),
            "performance": {
                "messages_per_second": self.metrics["total_messages"] / max(1, self.metrics.get("duration_seconds", 1)),
                "success_rate": ((self.metrics["total_messages"] - self.metrics["errors"]) / max(1, self.metrics["total_messages"])) * 100
            }
        }
        
        return report
    
    def save_report(self, report: Dict[str, Any], filename: str = None) -> str:
        """Salva il report su file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"lab/massive_training_report_{timestamp}.json"
        
        Path("lab").mkdir(exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📄 Report salvato: {filename}")
        return filename

async def main():
    """Main function."""
    runner = MassiveTrainingRunner()
    
    try:
        report = await runner.run_massive_training()
        filename = runner.save_report(report)
        
        # Print summary
        print("\n" + "="*60)
        print("🎯 MASSIVE TRAINING REPORT")
        print("="*60)
        
        metrics = report["metrics"]
        print(f"Total Messages: {metrics['total_messages']}")
        print(f"Success Rate: {metrics['success_rate']:.1f}%")
        print(f"Error Rate: {metrics['error_rate']:.1f}%")
        print(f"Avg Response Time: {metrics['avg_response_time']:.3f}s")
        print(f"Supportive Responses: {metrics['supportive_responses']}")
        print(f"Confrontational Responses: {metrics['confrontational_responses']}")
        print(f"Duration: {metrics['duration_seconds']:.1f}s")
        print(f"Messages/Second: {report['performance']['messages_per_second']:.1f}")
        
        print(f"\n📄 Report completo salvato in: {filename}")
        
    except KeyboardInterrupt:
        logger.info("🛑 Training interrotto dall'utente")
    except Exception as e:
        logger.error(f"❌ Errore durante training: {e}")

if __name__ == "__main__":
    asyncio.run(main())
