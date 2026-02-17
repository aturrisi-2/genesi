"""
Genesi Lab v1 - Auto Runner
Esecuzione automatica e report sintetico dei cicli di laboratorio
"""

from datetime import datetime
from typing import Dict, Any
from . import run_lab_cycle
from .prompt_versioning import PromptVersioning


def run_daily_cycle() -> Dict[str, Any]:
    """
    Esegue run_lab_cycle() e stampa report sintetico.
    
    Returns:
        Dict[str, Any]: Report completo del ciclo
    """
    print("🚀 Genesi Lab - Auto Runner")
    print(f"📅 Data esecuzione: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # Esegui ciclo completo
    report = run_lab_cycle(n_conversations=50)
    
    # Estrai informazioni chiave per report sintetico
    cycle_info = report.get("cycle_info", {})
    quality_metrics = report.get("quality_metrics", {})
    versioning_results = report.get("versioning_results", {})
    
    overall_score = quality_metrics.get("average_scores", {}).get("overall", 0)
    previous_score = versioning_results.get("previous_score")
    new_score = versioning_results.get("new_score")
    version_accepted = versioning_results.get("version_accepted", False)
    rollback_performed = versioning_results.get("rollback_performed", False)
    total_versions = versioning_results.get("total_versions", 0)
    
    # Stampa report sintetico
    print("\n" + "=" * 50)
    print("📊 REPORT SINTETICO")
    print("=" * 50)
    
    print(f"📈 Overall Score: {overall_score:.3f}")
    
    if previous_score is not None:
        score_change = new_score - previous_score
        change_symbol = "📈" if score_change > 0 else "📉" if score_change < 0 else "➡️"
        print(f"{change_symbol} Variazione: {score_change:+.3f}")
        print(f"📋 Precedente: {previous_score:.3f}")
    
    # Status versione
    if version_accepted:
        status = "✅ ACCETTATO"
        print(f"🔄 Versione: {status}")
    elif rollback_performed:
        status = "🔄 ROLLBACK"
        print(f"🔄 Versione: {status}")
    else:
        status = "➡️ PRIMA VERSIONE"
        print(f"🔄 Versione: {status}")
    
    print(f"📁 Versioni totali: {total_versions}")
    
    # Qualità
    if overall_score >= 0.8:
        quality = "🏆 ECCLENTE"
    elif overall_score >= 0.6:
        quality = "👍 BUONA"
    elif overall_score >= 0.4:
        quality = "⚠️ DISCRETA"
    else:
        quality = "❌ SCARSA"
    
    print(f"🎯 Qualità: {quality}")
    
    # Aree di miglioramento
    improvement_areas = report.get("prompt_optimization", {}).get("improvement_areas", [])
    if improvement_areas:
        print(f"🔧 Aree miglioramento: {', '.join(improvement_areas)}")
    else:
        print("🔧 Aree miglioramento: Nessuna")
    
    print("=" * 50)
    print(f"⏰ Completato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return report


def run_versioning_test() -> Dict[str, Any]:
    """
    Simula due cicli con punteggi diversi e verifica rollback funzioni.
    
    Returns:
        Dict[str, Any]: Risultati del test
    """
    print("🧪 Genesi Lab - Versioning Test")
    print(f"📅 Data test: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # Inizializza versioning
    versioning = PromptVersioning()
    
    # Test 1: Primo ciclo (deve essere accettato)
    print("\n📝 TEST 1: Primo ciclo (nessun precedente)")
    report1 = run_lab_cycle(n_conversations=10)  # Ciclo piccolo per velocità
    
    score1 = report1["versioning_results"]["new_score"]
    accepted1 = report1["versioning_results"]["version_accepted"]
    versions1 = report1["versioning_results"]["total_versions"]
    
    print(f"   Score: {score1:.3f}")
    print(f"   Accettato: {'✅' if accepted1 else '❌'}")
    print(f"   Versioni: {versions1}")
    
    # Test 2: Secondo ciclo con score inferiore (dovrebbe fare rollback)
    print("\n📝 TEST 2: Secondo ciclo con score inferiore (simulato)")
    
    # Per simulare uno score inferiore, modifichiamo temporaneamente il sistema
    # In un caso reale, questo dipenderebbe dalle conversazioni simulate
    
    # Salviamo il prompt corrente prima di simulare
    current_prompt = versioning.get_latest_prompt_version()
    previous_score_for_test = score1
    
    # Simuliamo un nuovo score inferiore (sotto soglia)
    simulated_new_score = previous_score_for_test - 0.05  # Sotto soglia 2%
    
    print(f"   Score precedente: {previous_score_for_test:.3f}")
    print(f"   Score simulato: {simulated_new_score:.3f}")
    
    # Test della logica di accettazione
    should_accept = versioning.should_accept_new_prompt(simulated_new_score, previous_score_for_test)
    print(f"   Sarebbe accettato: {'✅' if should_accept else '❌'}")
    
    if not should_accept:
        print("   🔄 Rollback sarebbe eseguito")
        # Verifichiamo che rollback funzioni
        rollback_result = versioning.rollback_to_previous()
        rollback_success = rollback_result is not None
        print(f"   Rollback test: {'✅ SUCCESSO' if rollback_success else '❌ FALLITO'}")
    else:
        rollback_success = False
        print("   ➡️ Nessun rollback necessario")
    
    # Test 3: Verifica statistiche versioning
    print("\n📝 TEST 3: Statistiche versioning")
    stats = versioning.get_versioning_stats()
    
    print(f"   Total versions: {stats['total_versions']}")
    print(f"   Latest version: {stats['latest_version']}")
    print(f"   History dir exists: {stats['history_dir_exists']}")
    print(f"   Current prompt exists: {stats['current_prompt_exists']}")
    
    # Test 4: Verifica history
    print("\n📝 TEST 4: Version history")
    history = versioning.get_version_history()
    
    print(f"   Versioni in history: {len(history)}")
    if history:
        latest = history[0]
        print(f"   Latest: {latest['filename']} (score: {latest['overall_score']:.3f})")
    
    # Risultati finali
    test_results = {
        "test_timestamp": datetime.now().isoformat(),
        "test_1": {
            "score": score1,
            "accepted": accepted1,
            "versions": versions1,
            "passed": accepted1 and versions1 >= 1
        },
        "test_2": {
            "previous_score": previous_score_for_test,
            "simulated_score": simulated_new_score,
            "should_accept": should_accept,
            "rollback_test": rollback_success,
            "passed": not should_accept and rollback_success
        },
        "test_3": {
            "stats": stats,
            "passed": stats['total_versions'] >= 1 and stats['history_dir_exists']
        },
        "test_4": {
            "history_count": len(history),
            "passed": len(history) >= 1
        },
        "overall_passed": all([
            accepted1 and versions1 >= 1,
            not should_accept and rollback_success,
            stats['total_versions'] >= 1 and stats['history_dir_exists'],
            len(history) >= 1
        ])
    }
    
    print("\n" + "=" * 50)
    print("🧪 RISULTATI TEST VERSIONING")
    print("=" * 50)
    
    for test_name, result in [
        ("Test 1 - Primo ciclo", test_results["test_1"]["passed"]),
        ("Test 2 - Rollback logica", test_results["test_2"]["passed"]),
        ("Test 3 - Statistiche", test_results["test_3"]["passed"]),
        ("Test 4 - History", test_results["test_4"]["passed"])
    ]:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    overall_status = "✅ TUTTI I TEST PASSATI" if test_results["overall_passed"] else "❌ ALCUNI TEST FALLITI"
    print(f"\n🎯 {overall_status}")
    
    return test_results


if __name__ == "__main__":
    """
    Esecuzione come script: python -m lab.auto_runner
    """
    run_daily_cycle()
