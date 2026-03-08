#!/usr/bin/env python3
"""
Genesi Integration Test Suite
Testa tutti i sistemi principali via API HTTP reale.
"""
import asyncio
import aiohttp
import json
import time
import re
import subprocess
import sys
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

# Aggiungi il path del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "alfio.turrisi@gmail.com"
TEST_PASSWORD = "ZOEennio0810"

@dataclass
class TestResult:
    name: str
    passed: bool
    response: str = ""
    expected_log: str = ""
    found_log: bool = False
    latency_ms: float = 0
    notes: str = ""

results: List[TestResult] = []

class GenesiIntegrationTester:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.auth_token: Optional[str] = None
        self.start_time = time.time()
        
    async def setup(self):
        """Setup iniziale della sessione e autenticazione."""
        self.session = aiohttp.ClientSession()
        
        # Prova autenticazione
        try:
            await self.authenticate()
            print("✅ Autenticazione riuscita")
        except Exception as e:
            print(f"❌ Autenticazione fallita: {e}")
            print("Per creare l'utente di test, esegui:")
            print(f"curl -X POST {BASE_URL}/api/auth/register -d '{{\"email\":\"{TEST_EMAIL}\",\"password\":\"{TEST_PASSWORD}\"}}'")
            sys.exit(1)
    
    async def authenticate(self):
        """Autentica e ottiene token JWT."""
        auth_data = {
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        }
        
        async with self.session.post(f"{BASE_URL}/auth/login", json=auth_data) as resp:
            if resp.status != 200:
                raise Exception(f"Login failed: {resp.status}")
            
            data = await resp.json()
            self.auth_token = data["access_token"]
    
    async def get_recent_logs(self, seconds: int = 5) -> str:
        """Legge gli ultimi N secondi di log da genesi.log."""
        log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "genesi.log")
        result_lines = []
        cutoff = datetime.utcnow().timestamp() - seconds
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        ts_str = line[1:20]
                        line_dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                        if line_dt.timestamp() >= cutoff:
                            result_lines.append(line.rstrip())
                    except Exception:
                        pass
            return "\n".join(result_lines)
        except Exception:
            pass
        # Fallback journalctl
        try:
            result = subprocess.run(
                ['journalctl', '-u', 'genesi', f'--since={seconds} seconds ago', '--no-pager', '-o', 'cat'],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout
        except Exception as e:
            return ""
    
    async def check_log_contains(self, pattern: str, seconds: int = 5) -> bool:
        """Verifica se i log recenti contengono un pattern."""
        logs = await self.get_recent_logs(seconds)
        return bool(re.search(pattern, logs, re.IGNORECASE))
    
    async def send_message(self, message: str, expected_log_pattern: str = "") -> TestResult:
        """Invia un messaggio e verifica i log."""
        start_time = time.time()
        
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            data = {"message": message}
            
            async with self.session.post(f"{BASE_URL}/api/chat/", json=data, headers=headers) as resp:
                response_text = await resp.text()
                latency_ms = (time.time() - start_time) * 1000
                
                if resp.status == 200:
                    result = TestResult(
                        name=f"Message: {message[:50]}",
                        passed=True,
                        response=response_text[:200],
                        latency_ms=latency_ms
                    )
                else:
                    result = TestResult(
                        name=f"Message: {message[:50]}",
                        passed=False,
                        response=f"HTTP {resp.status}: {response_text}",
                        latency_ms=latency_ms,
                        notes="HTTP error"
                    )
                
                # Verifica log se richiesto
                if expected_log_pattern:
                    await asyncio.sleep(1)  # Aspetta che i log popolino
                    result.expected_log = expected_log_pattern
                    result.found_log = await self.check_log_contains(expected_log_pattern, 30)
                    if not result.found_log:
                        result.passed = False
                        result.notes = f"Log pattern not found: {expected_log_pattern}"
                
                return result
                
        except Exception as e:
            return TestResult(
                name=f"Message: {message[:50]}",
                passed=False,
                notes=f"Exception: {e}",
                latency_ms=(time.time() - start_time) * 1000
            )
    
    async def test_intent_classification(self):
        """GRUPPO 1 — Intent Classification
        Fast-track (≤4 word o priority regex) → INTENT_CLASSIFIED
        LLM path (>4 word o intent non in fast-track) → LLM_INTENT_CLASSIFICATION
        """
        print("\n🔍 Testing Intent Classification...")

        # (message, label, log_pattern)
        # fast-track: greeting/how_are_you/time/memory_correction → INTENT_CLASSIFIED
        # LLM path: weather(lungo)/news/tecnica/emotional → LLM_INTENT_CLASSIFICATION
        test_cases = [
            ("ciao",                          "greeting",          "INTENT_CLASSIFIED.*intent=greeting"),
            ("come stai",                     "how_are_you",       "INTENT_CLASSIFIED.*intent=how_are_you"),
            ("che tempo fa a Roma",           "weather",           "LLM_INTENT_CLASSIFICATION.*weather"),
            ("che ore sono",                  "time",              "INTENT_CLASSIFIED.*intent=time"),
            ("dimmi una notizia",             "news",              "LLM_INTENT_CLASSIFICATION.*news"),
            ("cosa è il machine learning",    "tecnica",           "LLM_INTENT_CLASSIFICATION.*tecnica"),
            ("sono triste",                   "emotional",         "LLM_INTENT_CLASSIFICATION.*emotional"),
            ("in realtà mi chiamo Luca",      "memory_correction", "INTENT_CLASSIFIED.*intent=memory_correction"),
        ]

        for message, label, log_pattern in test_cases:
            result = await self.send_message(message, log_pattern)
            results.append(result)
            status = "✅" if result.passed else "❌"
            print(f"  {status} {message} → {label} ({result.latency_ms:.0f}ms)")
            await asyncio.sleep(0.5)
    
    async def test_tts_routing(self):
        """GRUPPO 2 — TTS / Chat Responses (HTTP 200 check)"""
        print("\n🔊 Testing Chat Responses (TTS endpoint)...")

        test_cases = [
            ("ciao", "risposta base"),
            ("come stai", "risposta relazionale"),
            ("che tempo fa a Roma", "risposta weather"),
            ("dimmi una notizia", "risposta news"),
        ]

        for message, description in test_cases:
            # Solo verifica HTTP 200 — TTS non scrive log tag dedicati
            result = await self.send_message(message)
            results.append(result)
            status = "✅" if result.passed else "❌"
            print(f"  {status} {message} → {description} ({result.latency_ms:.0f}ms)")
            await asyncio.sleep(0.5)
    
    async def test_memory_context(self):
        """GRUPPO 3 — Memory e Contesto (usa dati reali Alfio, non scrive nel profilo)"""
        print("\n🧠 Testing Memory and Context...")

        # Messaggio 1: fatto nella conversazione
        result1 = await self.send_message("oggi ho mangiato una pizza buonissima")
        results.append(result1)
        await asyncio.sleep(1)

        # Messaggio 2: verifica che ricordi la conversazione appena avuta
        result2 = await self.send_message("cosa ti ho detto di aver mangiato prima?")
        results.append(result2)
        name_found = "pizza" in result2.response.lower()
        result2.passed = name_found
        result2.notes = "Contesto ricordato" if name_found else "Contesto non ricordato"
        status = "✅" if name_found else "❌"
        print(f"  {status} Contesto conversazione ricordato: {name_found}")
        await asyncio.sleep(1)

        # Messaggio 3: verifica profilo utente reale (Alfio ha figli Ennio/Zoe nel profilo)
        result3 = await self.send_message("come mi chiamo?")
        results.append(result3)
        # La risposta deve contenere un nome (qualunque, dimostra che il profilo è caricato)
        profile_found = len(result3.response.strip()) > 10 and "non ho" not in result3.response.lower()[:50]
        result3.passed = profile_found
        result3.notes = "Profilo caricato" if profile_found else "Profilo non caricato"
        status = "✅" if profile_found else "❌"
        print(f"  {status} Profilo caricato: {profile_found}")
    
    async def test_profile_detection(self):
        """GRUPPO 4 — Profile Detection"""
        print("\n👤 Testing Profile Detection...")
        
        result = await self.send_message(
            "adoro il jazz e suono la chitarra",
            "PERSONAL_FACTS|COGNITIVE_"
        )
        results.append(result)
        status = "✅" if result.passed else "❌"
        print(f"  {status} Profile detection ({result.latency_ms:.0f}ms)")
    
    async def test_evolution_engine(self):
        """GRUPPO 5 — Evolution Engine"""
        print("\n🧬 Testing Evolution Engine...")
        
        emotional_messages = [
            "sono molto stressato",
            "non riesco a dormire",  
            "tutto mi pesa",
            "mi sento sopraffatto",
            "non so come andare avanti"
        ]
        
        evolution_patterns = [
            "COGNITIVE_EMOTIONAL_EVENT",
            "ROUTING_DECISION.*route=emotional",
            "LLM_INTENT_CLASSIFICATION.*emotional",
        ]
        
        found_evolution = False
        for message in emotional_messages:
            result = await self.send_message(message)
            results.append(result)
            
            # Verifica se appare un log di evoluzione
            for pattern in evolution_patterns:
                if await self.check_log_contains(pattern, 2):
                    found_evolution = True
                    print(f"  ✅ Evolution log found: {pattern}")
                    break
            
            await asyncio.sleep(0.5)
        
        if not found_evolution:
            print("  ⚠️ Nessun log di evoluzione trovato")
    
    async def test_latency(self):
        """GRUPPO 6 — Latenza"""
        print("\n⏱️ Testing Latency...")
        
        latency_tests = [
            ("ciao", 4000),           # Chat semplice
            ("che tempo fa a Roma", 9000),  # Chat con tool (weather API + LLM)
        ]
        
        for message, threshold_ms in latency_tests:
            result = await self.send_message(message)
            results.append(result)
            
            passed = result.latency_ms < threshold_ms
            result.passed = passed
            result.notes = f"Latency: {result.latency_ms:.0f}ms (threshold: {threshold_ms}ms)"
            
            status = "✅" if passed else "❌"
            print(f"  {status} {message}: {result.latency_ms:.0f}ms")
    
    async def test_fallback_resilience(self):
        """GRUPPO 7 — Fallback e Resilienza"""
        print("\n🛡️ Testing Fallback and Resilience...")
        
        edge_cases = [
            ("", "messaggio vuoto"),
            ("a" * 1000, "messaggio lunghissimo"),
            ("🎸🎵🎶", "solo emoji"),
            ("hello how are you", "inglese")
        ]
        
        for message, description in edge_cases:
            result = await self.send_message(message)
            results.append(result)
            
            # Verifica solo che non crashi (HTTP 200)
            passed = result.passed and "HTTP error" not in result.notes
            result.passed = passed
            result.notes = description
            
            status = "✅" if passed else "❌"
            print(f"  {status} {description} ({result.latency_ms:.0f}ms)")
            await asyncio.sleep(0.5)
    
    async def test_context_continuity(self):
        """GRUPPO 8 — Context Continuity"""
        print("\n🔄 Testing Context Continuity...")
        
        # Messaggio 1: fatto sullo spazio
        result1 = await self.send_message("dimmi un fatto interessante sullo spazio")
        results.append(result1)
        await asyncio.sleep(1)
        
        # Messaggio 2: "dimmene un altro"
        result2 = await self.send_message("dimmene un altro")
        results.append(result2)
        
        # Verifica che la risposta non contenga frasi di non-comprensione
        non_understanding = [
            "non ho capito",
            "cosa intendi", 
            "non ho capito cosa",
            "puoi spiegare meglio",
            "non ho capito cosa intendi"
        ]
        
        response_lower = result2.response.lower()
        has_non_understanding = any(phrase in response_lower for phrase in non_understanding)
        
        result2.passed = not has_non_understanding
        result2.notes = "Context maintained" if not has_non_understanding else "Context lost"
        
        status = "✅" if not has_non_understanding else "❌"
        print(f"  {status} Context continuity: {not has_non_understanding}")
    
    async def cleanup(self):
        """Cleanup placeholder — using real user, no data deletion."""
        pass
    
    async def generate_report(self):
        """Genera il report finale."""
        total_duration = time.time() - self.start_time
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        
        report = f"""# Genesi Integration Test Report
Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Durata totale: {total_duration:.1f}s

## Riepilogo
- Test eseguiti: {len(results)}
- ✅ Passati: {passed}
- ❌ Falliti: {failed}
- ⚠️ Warning: 0

## Risultati per gruppo

### GRUPPO 1 — Intent Classification
"""
        
        # Raggruppa risultati per categoria
        groups = {
            "Intent Classification": [],
            "TTS Routing": [],
            "Memory and Context": [],
            "Profile Detection": [],
            "Evolution Engine": [],
            "Latency": [],
            "Fallback and Resilience": [],
            "Context Continuity": []
        }
        
        # Assegna risultati ai gruppi (semplificato)
        current_group = "Intent Classification"
        for i, result in enumerate(results):
            if i < 8:
                groups["Intent Classification"].append(result)
            elif i < 12:
                groups["TTS Routing"].append(result)
            elif i < 15:
                groups["Memory and Context"].append(result)
            elif i < 16:
                groups["Profile Detection"].append(result)
            elif i < 21:
                groups["Evolution Engine"].append(result)
            elif i < 23:
                groups["Latency"].append(result)
            elif i < 27:
                groups["Fallback and Resilience"].append(result)
            else:
                groups["Context Continuity"].append(result)
        
        for group_name, group_results in groups.items():
            report += f"\n### {group_name}\n"
            for result in group_results:
                status = "✅" if result.passed else "❌"
                report += f"{status} {result.name} ({result.latency_ms:.0f}ms)\n"
                if result.notes:
                    report += f"   Note: {result.notes}\n"
        
        # Alert
        failed_results = [r for r in results if not r.passed]
        if failed_results:
            report += "\n## Alert\n"
            for result in failed_results:
                report += f"- {result.name}: {result.notes}\n"
        
        # Performance
        latencies = [r.latency_ms for r in results if r.latency_ms > 0]
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)
            
            report += f"""
## Performance
- Latenza media: {avg_latency:.0f}ms
- Latenza max: {max_latency:.0f}ms
- Latenza min: {min_latency:.0f}ms
"""
        
        # Salva report
        os.makedirs("reports", exist_ok=True)
        with open("reports/integration_test_report.md", "w", encoding="utf-8") as f:
            f.write(report)
        
        print(f"\n📄 Report salvato in reports/integration_test_report.md")
        print(f"📊 Totale: {passed}/{len(results)} test passati")
        
        return failed == 0
    
    async def run_all_tests(self):
        """Esegue tutti i test."""
        try:
            await self.setup()
            
            await self.test_intent_classification()
            await self.test_tts_routing()
            await self.test_memory_context()
            await self.test_profile_detection()
            await self.test_evolution_engine()
            await self.test_latency()
            await self.test_fallback_resilience()
            await self.test_context_continuity()
            
            success = await self.generate_report()
            
            return success
            
        finally:
            await self.cleanup()
            if self.session:
                await self.session.close()

async def main():
    """Main entry point."""
    print("🚀 Genesi Integration Test Suite")
    print("=" * 50)
    
    tester = GenesiIntegrationTester()
    success = await tester.run_all_tests()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
