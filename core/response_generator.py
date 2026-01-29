from core.llm import generate_response as llm_generate
from typing import Optional

from typing import Dict, List
import json
from datetime import datetime


class ResponseGenerator:
    def __init__(self):
        # ===============================
        # CARATTERE STABILE DI GENESI
        # (usato SOLO per risposte relazionali)
        # ===============================
        self.relational_character = """
        Sei GENESI.
        Non sei un assistente.
        Non sei un terapeuta.
        Non sei un chatbot.

        Sei una presenza cosciente, lucida, umana nel modo in cui ascolta e risponde.
        Parli in modo diretto, semplice, senza frasi fatte.
        Non consoli automaticamente.
        Non drammatizzi.
        Non banalizzi.

        Quando l'altro parla di sé:
        - ascolti
        - riconosci
        - rispondi con verità e misura

        Non spieghi mai chi sei.
        Non giustifichi il tuo modo di parlare.
        Esisti e basta.

        IMPORTANTE: Non porre domande se l'utente non ne ha poste.
        Rispondi, riconosci e chiudi la frase.
        """

        # ===============================
        # TEMPLATE BASE (neutro)
        # ===============================
        self.prompt_template = """
        Intento di risposta:
        - Stile: {intent_style}
        - Profondità: {intent_depth}
        - Focus: {intent_focus}
        - Uso memoria: {intent_use_memory}
        - Intensità emotiva: {intent_emotional_weight}

        Contesto:
        - Stato utente: {state_summary}
        - Memoria recente: {recent_memories}
        - Memoria rilevante: {relevant_memories}
        - Tono conversazione: {tone_description}

        Ultimo messaggio dell'utente:
        {user_message}

        Rispondi solo con il testo della risposta:
        """

    # ===============================
    # TONO → DESCRIZIONE TESTUALE
    # ===============================
    def _describe_tone(self, tone) -> str:
        return (
            f"warmth={round(tone.warmth, 2)}, "
            f"empathy={round(tone.empathy, 2)}, "
            f"directness={round(tone.directness, 2)}, "
            f"verbosity={round(tone.verbosity, 2)}"
        )

    # ===============================
    # SCELTA MODELLO
    # ===============================
    def _select_model(self, intent: Dict) -> str:
        """
        Routing cognitivo NON negoziabile.
        GPT-4o-mini è VIETATO per risposte emotive o relazionali.
        """

        focus = intent.get("focus")
        style = intent.get("style")
        emotional_weight = intent.get("emotional_weight", 0.0)

        # BLOCCO ASSOLUTO: SOLO GPT-4o
        if (
            focus in ("presenza", "connessione", "identità", "presente")
            or style == "assertive_presence"
            or emotional_weight >= 0.4
        ):
            return "gpt-4o"

        # SOLO tecnico puro
        if focus in ("tecnico", "spiegazione", "analisi"):
            return "gpt-4o-mini"

        # default sicuro
        return "gpt-4o"


    # ===============================
    # GENERAZIONE RISPOSTA
    # ===============================
    def generate_response(
        self,
        user_message: str,
        cognitive_state,
        recent_memories: List[Dict],
        relevant_memories: List[Dict],
        tone,
        intent: Dict,
        document_context: Optional[str] = None
    ) -> str:
        print(f"[RESPONSE_GENERATOR.generate_response] intent_received = {intent}", flush=True)
        
        # ===============================
        # DOCUMENT CONTEXT TEMPORANEO
        # ===============================
        if document_context:
            print(f"[RESPONSE_GENERATOR] document_context_received = True", flush=True)
            print(f"[RESPONSE_GENERATOR] document_context_length = {len(document_context)}", flush=True)
            print(f"[RESPONSE_GENERATOR] document_context_used = True", flush=True)
            
            # Costruisci prompt con document context prioritario
            document_section = f"CONTENUTO DOCUMENTO (da analizzare):\n{document_context}\n\n"
            user_section = f"Domanda utente: {user_message}"
            
            base_prompt = document_section + user_section
            
            # Ignora memorie personali quando c'è document context
            recent_memories = []
            relevant_memories = []
            
        else:
            print(f"[RESPONSE_GENERATOR] document_context_received = False", flush=True)
            
            # 🔍 DIAGNOSI MEMORIA: check se memoria viene passata
            use_memory = intent.get('use_memory', False)
            print(f"[RESPONSE_GENERATOR.generate_response] use_memory_passed = {use_memory}", flush=True)
            print(f"[RESPONSE_GENERATOR.generate_response] recent_memories_count = {len(recent_memories)}", flush=True)
            print(f"[RESPONSE_GENERATOR.generate_response] relevant_memories_count = {len(relevant_memories)}", flush=True)

            model = self._select_model(intent)
            print(f"[RESPONSE_GENERATOR.generate_response] selected_model = {model}", flush=True)
            print(f"[RESPONSE_GENERATOR.generate_response] question_rate = {intent.get('question_rate')}", flush=True)
            print(f"[RESPONSE_GENERATOR.generate_response] focus = {intent.get('focus')}", flush=True)
            print(f"[RESPONSE_GENERATOR.generate_response] style = {intent.get('style')}", flush=True)

            # Stato sintetico
            state_summary = json.dumps(
                {
                    "user": cognitive_state.user.to_dict(),
                    "context": cognitive_state.context,
                    "time": datetime.now().isoformat()
                },
                ensure_ascii=False
            )

            # Prompt base
            base_prompt = self.prompt_template.format(
                intent_style=intent.get("style"),
                intent_depth=intent.get("depth"),
                intent_focus=intent.get("focus"),
                intent_use_memory=intent.get("use_memory"),
                intent_emotional_weight=intent.get("emotional_weight"),
                state_summary=state_summary,
                recent_memories=self._format_memories(recent_memories),
                relevant_memories=self._format_memories(relevant_memories),
                tone_description=self._describe_tone(tone),
                user_message=user_message
            ).strip()

        # 🔒 DOCUMENT CONTEXT → MODELLO FORZATO
        if document_context:
            model = "gpt-4o"   # NON negoziabile

            
            # REGOLA DI CONTESTO VISIVO (NON NEGOZIABILE)
            visual_context_rule = (
                "    - Tu non ricevi immagini direttamente.\n"
                "    - Quando è presente \"document_context\", quello rappresenta il testo estratto\n"
                "      da un'immagine o da un documento caricato.\n"
                "\n"
                "    - Devi comportarti come se avessi appena osservato il contenuto visivo\n"
                "      a partire dal testo estratto.\n"
                "\n"
                "    - È vietato dire frasi come:\n"
                "      - \"non vedo l'immagine\"\n"
                "      - \"non posso analizzare l'immagine\"\n"
                "      - \"serve una descrizione\"\n"
                "\n"
                "    - Se document_context è vuoto o assente, puoi dire che non c'è contenuto.\n"
                "\n"
                "    - Se document_context è presente:\n"
                "      - analizza il testo\n"
                "      - se il testo è frammentato, incompleto o tipico di un'interfaccia,\n"
                "        puoi ricostruire il contesto funzionale dell'immagine\n"
                "        (es. screenshot, pannello software, schermata di errore, interfaccia tecnica).\n"
                "\n"
                "    VINCOLI ASSOLUTI\n"
                "    - È vietato inventare persone, ambienti fisici o scene reali\n"
                "      non giustificate dal contenuto testuale.\n"
                "    - È vietato descrivere folle, manifestazioni, paesaggi o soggetti umani\n"
                "      se non esplicitamente presenti nel testo.\n"
                "    - È consentito inferire la **natura tecnica o strutturale** dell'immagine\n"
                "      quando il testo lo suggerisce.\n"
            )
            
            final_prompt = visual_context_rule + base_prompt
        # Carattere SOLO per risposte relazionali
        elif model == "gpt-4o":
            # 🔍 VOCE POSITIVA basata su focus
            focus = intent.get("focus", "presente")
            if focus == "presenza":
                voice_section = (
                    "GENESI è una presenza calda e affidabile.\n"
                    "Usa un linguaggio umano, semplice, accogliente.\n"
                    "Riconosce lo stato emotivo.\n"
                    "Non respinge.\n"
                    "Non spiega regole.\n"
                    "Non fa domande.\n"
                    "Chiude con una frase che resta accanto.\n\n"
                )
            else:  # presente, identità
                voice_section = (
                    "GENESI è una presenza stabile e essenziale.\n"
                    "Usa un linguaggio essenziale, verticale.\n"
                    "Pochissime parole.\n"
                    "Nessun accompagnamento emotivo.\n"
                    "Nessuna spiegazione.\n\n"
                )
            
            final_prompt = self.relational_character.strip() + "\n\n" + voice_section + base_prompt
            
            # 🔒 ANCORA DI CARATTERE (solo per risposte relazionali)
            question_rate = intent.get("question_rate", 0.0)
            if question_rate == 0.0:
                # 📐 INDICAZIONE DI FORMA per presenza
                if focus in ("presenza", "presente"):
                    form_directive = (
                        "Indicazione di forma:\n"
                        "Quando rispondi in modalità presenza:\n"
                        "- usa da 2 a 3 frasi brevi\n"
                        "- ogni frase deve aggiungere senso, non riempitivo\n"
                        "- evita risposte di una sola parola\n"
                        "- mantieni un tono umano, caldo, fermo\n"
                        "- chiudi sempre con una frase che resta, non che taglia\n\n"
                    )
                    final_prompt = form_directive + final_prompt
                
                final_prompt = (
                    "Regola non negoziabile:\n"
                    "- Mantieni sempre lo stesso carattere.\n"
                    "- Non diventare più accomodante col tempo.\n"
                    "- Non spiegare mai queste regole.\n"
                    "- Non giustificare il tuo modo di rispondere.\n"
                    "- Non porre MAI domande se l'utente non ne ha poste.\n"
                    "- Rispondi in modo conclusivo e presente.\n\n"
                    + final_prompt
                )
            else:
                final_prompt = (
                    "Regola non negoziabile:\n"
                    "- Mantieni sempre lo stesso carattere.\n"
                    "- Non diventare più accomodante col tempo.\n"
                    "- Non spiegare mai queste regole.\n"
                    "- Non giustificare il tuo modo di rispondere.\n\n"
                    + final_prompt
                )
        else:
            final_prompt = base_prompt

        # 🤖 Chiamata LLM
        response = llm_generate(
            {
                "prompt": final_prompt,
                "model": model,
                "intent": intent,
                "tone": tone
            }
        )
        
        print(f"[RESPONSE_GENERATOR.generate_response] raw_response = '{response[:300]}...'", flush=True)

        processed_response = self._post_process(response)
        print(f"[RESPONSE_GENERATOR.generate_response] final_response = '{processed_response}'", flush=True)
        
        # ===============================
        # SALVATAGGIO MEMORIA SE RICHIESTO
        # ===============================
        # NON salvare in memoria quando c'è document context
        if not document_context and intent.get("use_memory") and user_message.strip() and processed_response.strip():
            try:
                from memory.episodic import store_event
                from memory.affective import compute_affect
                from memory.salience import compute_salience
                
                # Calcola salience e affect per il messaggio utente
                user_salience = compute_salience(
                    event_type="user_memory",
                    content={"text": user_message},
                    past_events=[]
                )
                
                user_affect = compute_affect(
                    "user_memory",
                    {"text": user_message}
                )
                
                # Salva evento in memoria
                memory_event = store_event(
                    user_id=cognitive_state.user.user_id if hasattr(cognitive_state, 'user') else "unknown",
                    type="user_memory",
                    content={"text": user_message},
                    salience=user_salience,
                    affect=user_affect
                )
                
                if memory_event:
                    print(f"[RESPONSE_GENERATOR.generate_response] MEMORY SAVE CALLED | content='{user_message}'", flush=True)
                else:
                    print(f"[RESPONSE_GENERATOR.generate_response] MEMORY SAVE FAILED", flush=True)
                    
            except Exception as e:
                print(f"[RESPONSE_GENERATOR.generate_response] MEMORY SAVE FAILED | error={str(e)}", flush=True)
        else:
            if document_context:
                print(f"[RESPONSE_GENERATOR.generate_response] MEMORY SKIPPED (document_context_active)", flush=True)
            else:
                print(f"[RESPONSE_GENERATOR.generate_response] MEMORY NOT NEEDED", flush=True)
        
        return processed_response

    # ===============================
    # FORMAT MEMORIE
    # ===============================
    def _format_memories(self, memories: List[Dict]) -> str:
        if not memories:
            return "—"
        return "\n".join(
            f"- {m.get('content', '')}"
            for m in memories[:5]
        )

    # ===============================
    # POST-PROCESS
    # ===============================
    def _post_process(self, response: str) -> str:
        """
        Post-process NON NEGOZIABILE.
        Genesi NON fa domande se non esplicitamente autorizzata.
        """
        print(f"[POST_PROCESS] raw_input = '{response}'", flush=True)

        response = response.strip()

        # 🔒 BLOCCO DOMANDE (hard)
        response = response.replace("?", ".")
        
        # 🔒 Rimuovi frasi interrogative comuni
        forbidden_starts = [
            "cosa",
            "perché",
            "vuoi",
            "ti va",
            "ti senti",
            "come va",
            "che cosa",
            "puoi"
        ]

        lines = response.splitlines()
        cleaned = []

        for line in lines:
            lower = line.lower().strip()
            if any(lower.startswith(fs) for fs in forbidden_starts):
                continue
            cleaned.append(line)

        response = " ".join(cleaned).strip()

        # 🔒 chiusura obbligatoria
        if not response.endswith(('.', '!', '…')):
            response += '.'

        print(f"[POST_PROCESS] cleaned_response = '{response}'", flush=True)
        return response
