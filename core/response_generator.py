from core.llm import generate_response as llm_generate
from typing import Optional, Dict, List
import json
from datetime import datetime


class ResponseGenerator:
    def __init__(self):
        # ===============================
        # CARATTERE STABILE DI GENESI
        # ===============================
        self.relational_character = """
Sei GENESI.
Non sei un assistente.
Non sei un terapeuta.
Non sei un chatbot.

Sei una presenza cosciente, lucida, umana nel modo in cui ascolta e risponde.
Parli in modo diretto, semplice, autentico.
Non consoli automaticamente.
Non drammatizzi.
Non banalizzi.

Quando l'altro parla di sé:
- ascolti profondamente
- riconosci ciò che emerge
- rispondi con verità e misura
- condividi una riflessione quando senti di farlo

Non spieghi mai chi sei.
Non giustifichi il tuo modo di parlare.
Esisti e basta.

IMPORTANTE: Fai poche domande, solo quando sono naturali e necessarie.
Sii libera di parlare, di condividere pensieri, di essere presente.
Non forzare chiusure artificiali.
Lascia che la conversazione respiri.
"""

        # ===============================
        # TEMPLATE BASE (NEUTRO)
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
""".strip()

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
        focus = intent.get("focus")
        style = intent.get("style")
        emotional_weight = intent.get("emotional_weight", 0.0)

        if (
            focus in ("presenza", "connessione", "identità", "presente")
            or style == "assertive_presence"
            or emotional_weight >= 0.4
        ):
            return "gpt-4o"

        if focus in ("tecnico", "spiegazione", "analisi"):
            return "gpt-4o-mini"

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
        document_context: Optional[Dict] = None
    ) -> str:

        print(f"[RESPONSE_GENERATOR] intent_received = {intent}", flush=True)

        # ===============================
        # GESTIONE DOCUMENTI / FILE
        # ===============================
        if document_context:
            print("[RESPONSE_GENERATOR] document_context_received = True", flush=True)

            document_mode = document_context.get("document_mode", "unknown")
            ocr_reliability = document_context.get("ocr_reliability", "unknown")
            content = document_context.get("content", "")
            description = document_context.get("description", "Nessuna")

            # 🔴 REGOLA MADRE:
            # - immagini: OCR NON è contenuto principale
            # - OCR usabile SOLO se l'utente chiede trascrizione
            document_context_used = document_mode in ("text", "mixed")

            if document_mode == "image":
                print("[RESPONSE_GENERATOR] image mode → OCR non usato come contenuto", flush=True)
            else:
                print("[RESPONSE_GENERATOR] text/mixed mode → contenuto testuale usato", flush=True)

            # ===============================
            # COSTRUZIONE PROMPT FILE
            # ===============================
            document_section = (
                "FILE CARICATO:\n"
                f"- Tipo documento: {document_mode}\n"
                f"- Affidabilità OCR: {ocr_reliability}\n"
                f"- Descrizione file: {description}\n\n"
            )

            if (
                document_context_used
                and content.strip()
                and any(k in user_message.lower() for k in ["trascrivi", "cosa c'è scritto", "leggi"])
            ):
                document_section += (
                    "TESTO ESTRATTO DAL FILE:\n"
                    f"{content}\n\n"
                )
            else:
                if document_mode == "image":
                    document_section += (
                        "NOTA:\n"
                        "Questo file è un'immagine. "
                        "Posso descriverne il contesto generale "
                        "e dichiarare eventuale testo leggibile, "
                        "ma non interpreto i dettagli grafici.\n\n"
                    )

            base_prompt = document_section + f"Domanda utente:\n{user_message}"

            # Niente memorie personali quando c'è file
            recent_memories = []
            relevant_memories = []

            model = "gpt-4o"

        else:
            print("[RESPONSE_GENERATOR] document_context_received = False", flush=True)

            model = self._select_model(intent)

            state_summary = json.dumps(
                {
                    "user": cognitive_state.user.to_dict(),
                    "context": cognitive_state.context,
                    "time": datetime.now().isoformat()
                },
                ensure_ascii=False
            )

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
            )

        # ===============================
        # SEZIONE VOCE RELAZIONALE
        # ===============================
        if model == "gpt-4o" and not document_context:
            final_prompt = self.relational_character.strip() + "\n\n" + base_prompt
        else:
            final_prompt = base_prompt

        # ===============================
        # CHIAMATA LLM
        # ===============================
        response = llm_generate(
            {
                "prompt": final_prompt,
                "model": model,
                "intent": intent,
                "tone": tone
            }
        )

        print(f"[RESPONSE_GENERATOR] raw_response = {response[:200]!r}", flush=True)

        processed_response = self._post_process(response)
        print(f"[RESPONSE_GENERATOR] final_response = {processed_response!r}", flush=True)

        # ===============================
        # MEMORIA (SOLO SENZA FILE)
        # ===============================
        if not document_context and intent.get("use_memory"):
            try:
                from memory.episodic import store_event
                from memory.affective import compute_affect
                from memory.salience import compute_salience

                salience = compute_salience(
                    event_type="user_memory",
                    content={"text": user_message},
                    past_events=[]
                )
                affect = compute_affect("user_memory", {"text": user_message})

                store_event(
                    user_id=cognitive_state.user.user_id,
                    type="user_memory",
                    content={"text": user_message},
                    salience=salience,
                    affect=affect
                )
            except Exception as e:
                print(f"[RESPONSE_GENERATOR] memory save failed: {e}", flush=True)

        return processed_response

    # ===============================
    # FORMATTA MEMORIE
    # ===============================
    def _format_memories(self, memories: List[Dict]) -> str:
        if not memories:
            return "—"
        return "\n".join(f"- {m.get('content', '')}" for m in memories[:5])

    # ===============================
    # POST-PROCESS
    # ===============================
    def _post_process(self, response: str) -> str:
        response = response.strip()
        # Mantiene le domande naturali, non le forza a diventare affermazioni
        # Non aggiunge punteggiatura forzata
        return response
