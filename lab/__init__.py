"""
Genesi Lab v1 - Main Module
Funzione principale per esecuzione del ciclo di laboratorio
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime

from .simulator import ConversationSimulator
from .supervisor import SupervisorEngine
from .adaptive_prompt import AdaptivePromptBuilder
from .metrics_schema import ConversationMetrics
from .prompt_versioning import PromptVersioning


def run_lab_cycle(n_conversations: int = 50) -> Dict[str, Any]:
    """
    Esegue un ciclo completo di laboratorio Genesi con versioning.
    
    Processo:
    1) Simula n conversazioni realistiche
    2) Valuta ogni conversazione con il supervisor
    3) Costruisce prompt adattivo basato su metriche
    4) Confronta punteggi e gestisce versioning
    5) Eventuale rollback automatico
    6) Salva risultati e genera report
    
    Args:
        n_conversations: Numero di conversazioni da simulare (default: 50)
        
    Returns:
        Dict[str, Any]: Report completo del ciclo di laboratorio
    """
    print(f"🧪 Iniziando Genesi Lab v1 - Ciclo con {n_conversations} conversazioni")
    print(f"⏰ Orario di inizio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Inizializza sistema versioning
    versioning = PromptVersioning()
    
    # Ottiene score precedente per confronto
    previous_score = versioning._get_previous_score()
    if previous_score is not None:
        print(f"📊 Score precedente rilevato: {previous_score:.3f}")
    else:
        print(f"📊 Nessun score precedente - primo ciclo")
    
    # FASE 1: Simulazione conversazioni
    print("\n📝 FASE 1: Simulazione conversazioni...")
    simulator = ConversationSimulator()
    conversations = simulator.run_simulation(n_conversations)
    
    # Statistiche della simulazione
    sim_stats = simulator.get_simulation_stats(conversations)
    print(f"✅ Simulate {len(conversations)} conversazioni")
    print(f"   - Lunghezza media messaggio utente: {sim_stats.get('avg_user_message_length', 0):.1f} caratteri")
    print(f"   - Lunghezza media risposta: {sim_stats.get('avg_response_length', 0):.1f} caratteri")
    print(f"   - Ratio domande: {sim_stats.get('questions_ratio', 0):.2f}")
    
    # FASE 2: Valutazione con supervisor
    print("\n🔍 FASE 2: Valutazione qualità con supervisor...")
    supervisor = SupervisorEngine()
    all_metrics = []
    
    for i, (user_msg, assistant_msg) in enumerate(conversations):
        if i % 10 == 0:
            print(f"   Valutazione conversazione {i+1}/{len(conversations)}...")
        
        metrics = supervisor.evaluate(user_msg, assistant_msg)
        all_metrics.append(metrics)
    
    print(f"✅ Valutate {len(all_metrics)} conversazioni")
    
    # Statistiche aggregate delle metriche
    avg_clarity = sum(m.clarity_score for m in all_metrics) / len(all_metrics)
    avg_coherence = sum(m.coherence_score for m in all_metrics) / len(all_metrics)
    avg_memory = sum(m.contextual_memory_score for m in all_metrics) / len(all_metrics)
    avg_human = sum(m.human_likeness_score for m in all_metrics) / len(all_metrics)
    avg_redundancy = sum(m.redundancy_score for m in all_metrics) / len(all_metrics)
    avg_hallucination = sum(m.hallucination_risk for m in all_metrics) / len(all_metrics)
    avg_overall = sum(m.overall_score for m in all_metrics) / len(all_metrics)
    
    print(f"   - Score medio chiarezza: {avg_clarity:.3f}")
    print(f"   - Score medio coerenza: {avg_coherence:.3f}")
    print(f"   - Score medio memoria: {avg_memory:.3f}")
    print(f"   - Score medio umanità: {avg_human:.3f}")
    print(f"   - Score medio ridondanza: {avg_redundancy:.3f}")
    print(f"   - Score medio rischio hallucination: {avg_hallucination:.3f}")
    print(f"   - Score complessivo: {avg_overall:.3f}")
    
    # FASE 3: Costruzione prompt adattivo
    print("\n🔧 FASE 3: Costruzione prompt adattivo...")
    prompt_builder = AdaptivePromptBuilder()
    prompt_result = prompt_builder.build_adaptive_prompt(all_metrics)
    
    print(f"✅ Prompt adattivo generato")
    print(f"   - Aree di miglioramento identificate: {len(prompt_result['improvement_areas'])}")
    print(f"   - Istruzioni aggiuntive: {len(prompt_result['additional_instructions'])}")
    print(f"   - Lunghezza prompt finale: {len(prompt_result['system_prompt'])} caratteri")
    
    # FASE 4: Versioning e confronto punteggi
    print("\n📋 FASE 4: Versioning e confronto punteggi...")
    
    new_score = avg_overall
    version_accepted = True
    rollback_performed = False
    
    if previous_score is not None:
        # Confronta punteggi e decide se accettare
        version_accepted = versioning.should_accept_new_prompt(new_score, previous_score)
        
        if version_accepted:
            # Salva nuova versione
            saved_path = versioning.save_new_prompt_version(prompt_result)
            print(f"✅ Nuova versione accettata e salvata")
        else:
            # Rollback automatico
            print(f"⚠️ Nuovo prompt non soddisfa soglia minima - eseguo rollback...")
            rollback_path = versioning.rollback_to_previous()
            if rollback_path:
                rollback_performed = True
                print(f"🔄 Rollback completato con successo")
            else:
                print(f"❌ Rollback fallito")
    else:
        # Primo ciclo - salva direttamente
        saved_path = versioning.save_new_prompt_version(prompt_result)
        print(f"✅ Prima versione salvata")
    
    # FASE 5: Report finale
    print("\n📊 FASE 5: Generazione report finale...")
    
    # Analisi distribuzione qualità
    quality_distribution = {}
    for metrics in all_metrics:
        level = metrics.get_quality_level()
        quality_distribution[level] = quality_distribution.get(level, 0) + 1
    
    # Aree di miglioramento più comuni
    improvement_areas_count = {}
    for metrics in all_metrics:
        for area in metrics.get_improvement_areas():
            improvement_areas_count[area] = improvement_areas_count.get(area, 0) + 1
    
    # Statistiche versioning
    versioning_stats = versioning.get_versioning_stats()
    
    # Report completo
    report = {
        "cycle_info": {
            "timestamp": datetime.now().isoformat(),
            "conversations_simulated": n_conversations,
            "conversations_evaluated": len(all_metrics),
            "lab_version": "v1.1",  # Aggiornato con versioning
            "versioning_enabled": True
        },
        "simulation_stats": sim_stats,
        "quality_metrics": {
            "average_scores": {
                "clarity": avg_clarity,
                "coherence": avg_coherence,
                "memory_usage": avg_memory,
                "human_likeness": avg_human,
                "redundancy": avg_redundancy,
                "hallucination_risk": avg_hallucination,
                "overall": avg_overall
            },
            "quality_distribution": quality_distribution,
            "improvement_areas_frequency": improvement_areas_count
        },
        "versioning_results": {
            "previous_score": previous_score,
            "new_score": new_score,
            "version_accepted": version_accepted,
            "rollback_performed": rollback_performed,
            "total_versions": versioning_stats["total_versions"],
            "latest_version": versioning_stats["latest_version"]
        },
        "prompt_optimization": {
            "improvement_areas": prompt_result['improvement_areas'],
            "additional_instructions_count": len(prompt_result['additional_instructions']),
            "prompt_length": len(prompt_result['system_prompt']),
            "prompt_expansion_ratio": len(prompt_result['system_prompt']) / len(prompt_result['base_prompt'])
        },
        "files_generated": {
            "supervisor_logs": "lab/supervisor_logs.json",
            "adaptive_prompt": "lab/global_prompt.json",
            "version_history": "lab/prompt_history/"
        }
    }
    
    # Salva report
    report_file = f"lab/lab_cycle_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    import json
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"📄 Report salvato in: {report_file}")
    except Exception as e:
        print(f"⚠️ Warning: Impossibile salvare report: {e}")
    
    # Riepilogo finale
    print(f"\n🎉 CICLO LAB COMPLETATO CON SUCCESSO!")
    print(f"⏰ Orario di completamento: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📈 Score complessivo medio: {avg_overall:.3f}")
    
    if previous_score is not None:
        score_change = new_score - previous_score
        change_symbol = "📈" if score_change > 0 else "📉" if score_change < 0 else "➡️"
        print(f"{change_symbol} Variazione score: {score_change:+.3f}")
    
    if avg_overall >= 0.8:
        print("🏆 Qualità: ECCLENTE")
    elif avg_overall >= 0.6:
        print("👍 Qualità: BUONA")
    elif avg_overall >= 0.4:
        print("⚠️ Qualità: DISCRETA")
    else:
        print("❌ Qualità: SCARSA")
    
    # Status versioning
    if version_accepted:
        print("✅ Versioning: NUOVA VERSIONE ACCETTATA")
    elif rollback_performed:
        print("🔄 Versioning: ROLLBACK ESEGUITO")
    else:
        print("➡️ Versioning: PRIMA VERSIONE")
    
    print(f"🔧 Prompt attivo: lab/global_prompt.json")
    print(f"📋 Log valutazioni: lab/supervisor_logs.json")
    print(f"📁 Version history: lab/prompt_history/")
    
    return report


def get_lab_summary() -> Dict[str, Any]:
    """
    Fornisce un riepilogo dello stato attuale del laboratorio.
    
    Returns:
        Dict[str, Any]: Riepilogo del laboratorio
    """
    from pathlib import Path
    import json
    
    lab_dir = Path("lab")
    if not lab_dir.exists():
        return {"status": "Lab directory not found"}
    
    # Controlla file esistenti
    supervisor_logs = lab_dir / "supervisor_logs.json"
    prompt_file = lab_dir / "global_prompt.json"
    
    summary = {
        "lab_directory": str(lab_dir),
        "files": {
            "supervisor_logs": {
                "exists": supervisor_logs.exists(),
                "size_mb": supervisor_logs.stat().st_size / (1024*1024) if supervisor_logs.exists() else 0
            },
            "global_prompt": {
                "exists": prompt_file.exists(),
                "size_mb": prompt_file.stat().st_size / (1024*1024) if prompt_file.exists() else 0
            }
        }
    }
    
    # Se esistono, estrai informazioni aggiuntive
    if prompt_file.exists():
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_data = json.load(f)
            summary["latest_prompt"] = {
                "date": prompt_data.get("date"),
                "overall_score": prompt_data.get("metrics_average", {}).get("overall_score"),
                "improvement_areas": len(prompt_data.get("improvement_areas", []))
            }
        except Exception:
            pass
    
    if supervisor_logs.exists():
        try:
            with open(supervisor_logs, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            summary["supervisor_stats"] = {
                "total_evaluations": len(lines),
                "last_evaluation": lines[-1].strip() if lines else None
            }
        except Exception:
            pass
    
    return summary


# Funzione di utilità per testing rapido
def run_quick_test() -> Dict[str, Any]:
    """
    Esegue un test rapido con 10 conversazioni per verifica funzionamento.
    
    Returns:
        Dict[str, Any]: Risultati del test rapido
    """
    print("🚀 Eseguendo test rapido Genesi Lab (10 conversazioni)...")
    return run_lab_cycle(n_conversations=10)


def run_versioning_test() -> Dict[str, Any]:
    """
    Simula due cicli con punteggi diversi e verifica rollback funzioni.
    
    Returns:
        Dict[str, Any]: Risultati del test versioning
    """
    from .auto_runner import run_versioning_test as _run_versioning_test
    return _run_versioning_test()
