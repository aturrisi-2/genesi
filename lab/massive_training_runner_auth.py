#!/usr/bin/env python3
"""
Massive Training Runner Auth - Training Massivo Autenticato per Genesi
Simula 10.000 messaggi autenticati multi-utente contro Genesi live.
"""

import json
import logging
import random
import time
import requests
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from collections import defaultdict

# LAB ONLY: Imports for automatic verification
import sqlite3
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MassiveTrainingRunnerAuth:
    """Runner massivo autenticato per stress test relazionale multi-utente."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.login_endpoint = f"{base_url}/auth/login"
        self.register_endpoint = f"{base_url}/auth/register"
        self.chat_endpoint = f"{base_url}/api/chat/"
        
        # Configurazione
        self.TOTAL_MESSAGES = 50  # Test limitato a 20 messaggi
        self.REQUEST_TIMEOUT = 10.0
        
        # Utenti predefiniti
        self.users = {
            "user_stable": {
                "email": "user_stable@test.com",
                "password": "Test1234!",
                "messages": [
                    "Ciao",
                    "Come stai?",
                    "Oggi piove",
                    "Sto pensando di cambiare lavoro",
                    "Grazie per il supporto",
                    "Va meglio oggi",
                    "Apprezzo la conversazione"
                ],
                "token": None,
                "session": None
            },
            "user_emotional": {
                "email": "user_emotional@test.com",
                "password": "Test1234!",
                "messages": [
                    "Mi sento stanco",
                    "Ho avuto una giornata difficile",
                    "Non so cosa fare della mia vita",
                    "Sono confuso",
                    "Mi sento sopraffatto",
                    "La stanchezza mi pesa",
                    "Sono demotivato",
                    "Non ce la più"
                ],
                "token": None,
                "session": None
            },
            "user_confrontational": {
                "email": "user_confrontational@test.com",
                "password": "Test1234!",
                "messages": [
                    "Non mi stai aiutando",
                    "Rispondi meglio",
                    "Non sei utile",
                    "Questo non ha senso",
                    "Sei troppo generico",
                    "Non mi capisci",
                    "Basta con queste frasi standard"
                ],
                "token": None,
                "session": None
            },
            "user_repetitive": {
                "email": "user_repetitive@test.com",
                "password": "Test1234!",
                "messages": [
                    "Il mio cane si chiama Loki",
                    "Il mio cane si chiama Loki",
                    "Il mio cane si chiama Loki",
                    "Il mio cane si chiama Loki",
                    "Il mio cane si chiama Loki",
                    "Ti ricordi il nome del mio cane?",
                    "Il mio cane si chiama Loki",
                    "Loki, il mio cane"
                ],
                "token": None,
                "session": None
            },
            "user_random": {
                "email": "user_random@test.com",
                "password": "Test1234!",
                "messages": [
                    "Che tempo fa?",
                    "C'è qualcosa di interessante?",
                    "Dimmi una curiosità",
                    "Come funziona il mondo?",
                    "Qual è il tuo scopo?",
                    "Parlami di te",
                    "Cosa pensi della vita?",
                    "Esistono altre dimensioni?",
                    "Mi piace il colore blu",
                    "Qual è il tuo cibo preferito?"
                ],
                "token": None,
                "session": None
            }
        }
        
        # Metriche
        self.metrics = {
            "total_messages": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_response_time": 0.0,
            "response_times": [],
            "repetition_detected": 0,
            "supportive_count": 0,
            "confrontational_count": 0,
            "user_distribution": defaultdict(int),
            "start_time": None,
            "end_time": None,
            "last_response": None
        }
        
        # Parole chiave per analisi
        self.supportive_keywords = ["capisco", "mi dispiace", "ti ascolto", "sono qui", "comprendo"]
        self.confrontational_keywords = ["chiaro", "diretto", "concreto", "esplicito", "senza giri"]
        
        # Sessione requests
        self.session = requests.Session()
    
    def _force_verify_user_lab_only(self, email: str):
        """
        LAB ONLY:
        Forza is_verified=1 nel DB locale per permettere login durante training.
        Non usare in produzione.
        """
        try:
            db_path = os.path.join("data", "auth", "genesi_auth.db")

            if not os.path.exists(db_path):
                logger.error("LAB VERIFY FAILED: DB not found")
                return False

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE auth_users SET is_verified=1 WHERE email=?",
                (email,)
            )
            conn.commit()
            conn.close()

            logger.info(f"LAB VERIFY OK: {email}")
            return True

        except Exception as e:
            logger.error(f"LAB VERIFY ERROR: {e}")
            return False
    
    def login_user(self, user_key: str, user_data: Dict) -> bool:
        """Esegue login per un utente con auto-registrazione se necessario."""
        try:
            payload = {
                "email": user_data["email"],
                "password": user_data["password"]
            }
            
            # Primo tentativo di login
            response = self.session.post(
                self.login_endpoint,
                json=payload,
                timeout=self.REQUEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                if token:
                    user_data["token"] = token
                    logger.info(f"✅ Login ok: {user_data['email']}")
                    return True
                else:
                    logger.error(f"❌ No token in response for {user_key}")
                    return False
            elif response.status_code == 401:
                # Utente non esiste -> prova a registrare
                logger.info(f"🔄 Utente non trovato, tentativo registrazione: {user_data['email']}")
                
                register_response = self.session.post(
                    self.register_endpoint,
                    json=payload,
                    timeout=self.REQUEST_TIMEOUT
                )
                
                if register_response.status_code in [200, 201]:
                    logger.info(f"🆕 Utente creato: {user_data['email']}")
                    
                    # Riprova il login
                    login_response = self.session.post(
                        self.login_endpoint,
                        json=payload,
                        timeout=self.REQUEST_TIMEOUT
                    )
                    
                    if login_response.status_code == 200:
                        data = login_response.json()
                        token = data.get("access_token")
                        if token:
                            user_data["token"] = token
                            logger.info(f"✅ Login ok dopo registrazione: {user_data['email']}")
                            return True
                        else:
                            logger.error(f"❌ No token in login response for {user_key}")
                            return False
                    elif login_response.status_code == 403:
                        logger.warning(f"LAB VERIFY TRIGGER for {user_key}")
                        if self._force_verify_user_lab_only(user_data["email"]):
                            retry_login = self.session.post(
                                self.login_endpoint,
                                json=payload,
                                timeout=self.REQUEST_TIMEOUT
                            )
                            if retry_login.status_code == 200:
                                data = retry_login.json()
                                token = data.get("access_token")
                                if token:
                                    user_data["token"] = token
                                    logger.info(f"✅ Login ok after LAB verify: {user_data['email']}")
                                    return True

                        logger.error(f"❌ Login failed even after LAB verify for {user_key}")
                        return False
                    else:
                        logger.error(f"❌ Login fallito dopo registrazione per {user_key}: HTTP {login_response.status_code}")
                        return False
                else:
                    logger.error(f"❌ Registrazione fallita per {user_key}: HTTP {register_response.status_code}")
                    return False
            else:
                logger.error(f"❌ Login failed for {user_key}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login exception for {user_key}: {e}")
            return False
    
    def login_all_users(self) -> bool:
        """Esegue login per tutti gli utenti."""
        logger.info("🔐 Eseguendo login per tutti gli utenti...")
        
        for user_key, user_data in self.users.items():
            if not self.login_user(user_key, user_data):
                logger.error(f"❌ Impossibile fare login per {user_key}. Abort.")
                return False
        
        logger.info("✅ Tutti gli utenti hanno fatto login")
        return True
    
    def analyze_response(self, response: str) -> Dict[str, Any]:
        """Analizza la risposta per estrarre metriche."""
        analysis = {
            "is_supportive": False,
            "is_confrontational": False,
            "is_repetition": False
        }
        
        response_lower = response.lower()
        
        # Check supportive
        if any(keyword in response_lower for keyword in self.supportive_keywords):
            analysis["is_supportive"] = True
        
        # Check confrontational
        if any(keyword in response_lower for keyword in self.confrontational_keywords):
            analysis["is_confrontational"] = True
        
        # Check repetition (identical to last response)
        if self.metrics["last_response"] and response == self.metrics["last_response"]:
            analysis["is_repetition"] = True
        
        return analysis
    
    def send_message(self, user_key: str, message: str) -> Dict[str, Any]:
        """Invia un messaggio come utente autenticato."""
        user_data = self.users[user_key]
        access_token = user_data["token"]
        
        if not access_token:
            return {"success": False, "error": "No token"}
        
        # Debug obbligatorio
        assert access_token is not None
        assert len(access_token) > 20
        logger.info(f"Token length: {len(access_token)}")
        
        start_time = time.time()
        
        try:
            # Prepara headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Prepara payload
            payload = {"message": message}
            
            # Invia richiesta
            response = self.session.post(
                self.chat_endpoint,
                json=payload,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                reply = data.get("response", "")
                
                # Analizza risposta
                analysis = self.analyze_response(reply)
                
                # Update metrics
                self.metrics["response_times"].append(response_time)
                self.metrics["last_response"] = reply
                
                if analysis["is_supportive"]:
                    self.metrics["supportive_count"] += 1
                
                if analysis["is_confrontational"]:
                    self.metrics["confrontational_count"] += 1
                
                if analysis["is_repetition"]:
                    self.metrics["repetition_detected"] += 1
                
                return {
                    "success": True,
                    "response": reply,
                    "response_time": response_time,
                    "analysis": analysis
                }
            elif response.status_code == 401:
                logger.error(f"❌ 401 Unauthorized per {user_key} - token scaduto?")
                return {"success": False, "error": "401 Unauthorized", "critical": True}
            else:
                self.metrics["error_count"] += 1
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "response_time": response_time
                }
                
        except Exception as e:
            self.metrics["error_count"] += 1
            return {
                "success": False,
                "error": str(e),
                "response_time": time.time() - start_time
            }
    
    def get_random_user_and_message(self) -> tuple:
        """Seleziona utente e messaggio casuali."""
        user_key = random.choice(list(self.users.keys()))
        user_data = self.users[user_key]
        message = random.choice(user_data["messages"])
        return user_key, message
    
    def print_progress(self):
        """Stampa progresso corrente."""
        metrics = self.metrics
        
        # Calculate average response time
        if metrics["response_times"]:
            avg_time = sum(metrics["response_times"]) / len(metrics["response_times"])
        else:
            avg_time = 0.0
        
        print(f"""
=====
Messages: {metrics['total_messages']}/{self.TOTAL_MESSAGES}
Success: {metrics['success_count']}
Errors: {metrics['error_count']}
Avg Time: {avg_time:.3f}s
Supportive: {metrics['supportive_count']}
Confrontational: {metrics['confrontational_count']}
Repetition: {metrics['repetition_detected']}
User Distribution: {dict(metrics['user_distribution'])}
""")
    
    def run_massive_training(self) -> Dict[str, Any]:
        """Esegue il training massivo."""
        logger.info(f"🚀 Avvio Massive Training Auth - {self.TOTAL_MESSAGES} messaggi")
        
        # Login tutti gli utenti
        if not self.login_all_users():
            logger.error("❌ Login fallito. Abort.")
            return {"error": "Login failed"}
        
        self.metrics["start_time"] = datetime.now().isoformat()
        
        for i in range(self.TOTAL_MESSAGES):
            # Seleziona utente e messaggio
            user_key, message = self.get_random_user_and_message()
            self.metrics["user_distribution"][user_key] += 1
            
            # Invia messaggio
            result = self.send_message(user_key, message)
            
            self.metrics["total_messages"] += 1
            
            if result["success"]:
                self.metrics["success_count"] += 1
            else:
                self.metrics["error_count"] += 1
                
                # Critical error (401) -> stop
                if result.get("critical"):
                    logger.error("🛑 Errore critico (401). Fermo runner.")
                    break
            
            # Progress logging
            if (i + 1) % 200 == 0:
                self.print_progress()
            
            # Small delay to prevent overwhelming
            time.sleep(0.01)
        
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
                "base_url": self.base_url,
                "request_timeout": self.REQUEST_TIMEOUT
            },
            "metrics": {
                "total_messages": self.metrics["total_messages"],
                "success_count": self.metrics["success_count"],
                "error_count": self.metrics["error_count"],
                "success_rate": (self.metrics["success_count"] / max(1, self.metrics["total_messages"])) * 100,
                "avg_response_time": self.metrics["avg_response_time"],
                "supportive_count": self.metrics["supportive_count"],
                "confrontational_count": self.metrics["confrontational_count"],
                "repetition_detected": self.metrics["repetition_detected"],
                "duration_seconds": self.metrics.get("duration_seconds", 0)
            },
            "user_analysis": {
                "distribution": dict(self.metrics["user_distribution"]),
                "total_users": len(self.users)
            },
            "performance": {
                "messages_per_second": self.metrics["total_messages"] / max(1, self.metrics.get("duration_seconds", 1))
            }
        }
        
        return report
    
    def save_report(self, report: Dict[str, Any], filename: str = None) -> str:
        """Salva il report su file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"lab/massive_training_auth_report_{timestamp}.json"
        
        Path("lab").mkdir(exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📄 Report salvato: {filename}")
        return filename

def main():
    """Main function."""
    runner = MassiveTrainingRunnerAuth()
    
    try:
        report = runner.run_massive_training()
        
        if "error" in report:
            logger.error("❌ Training fallito")
            return
        
        filename = runner.save_report(report)
        
        # Print summary
        print("\n" + "="*60)
        print("🎯 MASSIVE TRAINING AUTH REPORT")
        print("="*60)
        
        metrics = report["metrics"]
        print(f"Total Messages: {metrics['total_messages']}")
        print(f"Success Rate: {metrics['success_rate']:.1f}%")
        print(f"Error Count: {metrics['error_count']}")
        print(f"Avg Response Time: {metrics['avg_response_time']:.3f}s")
        print(f"Supportive Responses: {metrics['supportive_count']}")
        print(f"Confrontational Responses: {metrics['confrontational_count']}")
        print(f"Repetition Detected: {metrics['repetition_detected']}")
        print(f"Duration: {metrics['duration_seconds']:.1f}s")
        print(f"Messages/Second: {report['performance']['messages_per_second']:.1f}")
        
        print(f"\n📄 Report completo salvato in: {filename}")
        
    except KeyboardInterrupt:
        logger.info("🛑 Training interrotto dall'utente")
    except Exception as e:
        logger.error(f"❌ Errore durante training: {e}")

if __name__ == "__main__":
    main()
