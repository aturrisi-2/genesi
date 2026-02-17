"""
Genesi Lab v1 - Conversation Simulator
Sistema per simulare conversazioni realistiche per testing
"""

import random
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass


@dataclass
class UserProfile:
    """Profilo utente simulato per personalizzare le conversazioni"""
    name: str
    personality_type: str
    interests: List[str]
    communication_style: str


class ConversationSimulator:
    """
    Simulatore di conversazioni realistiche per testing del sistema.
    
    Genera input utente basati su diversi profili psicologici
    e stili di comunicazione senza chiamare API esterne.
    """
    
    def __init__(self):
        """Inizializza il simulatore con profili predefiniti"""
        self.user_profiles = self._create_user_profiles()
        self.conversation_templates = self._create_conversation_templates()
        
    def run_simulation(self, n: int = 100) -> List[Tuple[str, str]]:
        """
        Esegue simulazione di n conversazioni.
        
        Args:
            n: Numero di conversazioni da simulare
            
        Returns:
            List[Tuple[str, str]]: Lista di (user_message, simulated_response)
        """
        conversations = []
        
        for i in range(n):
            # Seleziona profilo utente casuale
            profile = random.choice(self.user_profiles)
            
            # Genera messaggio utente basato sul profilo
            user_message = self._generate_user_message(profile, i)
            
            # Genera risposta simulata basata sul contesto
            assistant_response = self._generate_simulated_response(user_message, profile)
            
            conversations.append((user_message, assistant_response))
        
        return conversations
    
    def _create_user_profiles(self) -> List[UserProfile]:
        """
        Crea profili utente diversificati per simulazione.
        
        Returns:
            List[UserProfile]: Lista di profili predefiniti
        """
        return [
            # Utente curioso
            UserProfile(
                name="Marco",
                personality_type="curious",
                interests=["tecnologia", "scienza", "spazio"],
                communication_style="dettagliato"
            ),
            
            # Utente distratto
            UserProfile(
                name="Giulia",
                personality_type="distracted", 
                interests=["musica", "film", "serie tv"],
                communication_style="breve"
            ),
            
            # Utente emotivo
            UserProfile(
                name="Alessandro",
                personality_type="emotional",
                interests=["psicologia", "relazioni", "arte"],
                communication_style="espressivo"
            ),
            
            # Utente tecnico
            UserProfile(
                name="Roberta",
                personality_type="technical",
                interests=["programmazione", "database", "algoritmi"],
                communication_style="preciso"
            ),
            
            # Utente provocatorio
            UserProfile(
                name="Paolo",
                personality_type="provocative",
                interests=["filosofia", "politica", "società"],
                communication_style="sfidante"
            )
        ]
    
    def _create_conversation_templates(self) -> Dict[str, List[str]]:
        """
        Crea template di conversazione per ogni tipo di personalità.
        
        Returns:
            Dict[str, List[str]]: Template per ogni personalità
        """
        return {
            "curious": [
                "Perché {topic} funziona in questo modo?",
                "Mi spiegheresti meglio come funziona {topic}?",
                "Sono curioso di sapere tutto su {topic}",
                "Quali sono i dettagli tecnici di {topic}?",
                "Come si collega {topic} con {other_topic}?"
            ],
            
            "distracted": [
                "Ah, {topic}... a proposito, hai visto {distractor}?",
                "{topic} ok, ma poi {random_thought}",
                "Scusa, stavo pensando a {topic}... cosa dicevi?",
                "{topic} sì, ma è importante davvero?",
                "Breve su {topic} per favore"
            ],
            
            "emotional": [
                "Mi sento {emotion} quando penso a {topic}",
                "{topic} mi fa {emotion}, è normale?",
                "Non riesco a smettere di pensare a {topic}",
                "{topic} mi ha cambiato la vita",
                "Come gestisco le emozioni legate a {topic}?"
            ],
            
            "technical": [
                "Qual è l'algoritmo ottimale per {topic}?",
                "Complexity analysis di {topic}?",
                "Implementazione pratica di {topic}",
                "Best practices per {topic}",
                "Architettura consigliata per {topic}"
            ],
            
            "provocative": [
                "Sei sicuro che {topic} sia la soluzione migliore?",
                "Perché tutti seguono {topic} senza pensare?",
                "{topic} è sopravvalutato, non trovi?",
                "Dimostrami che {topic} funziona davvero",
                "Quali sono gli svantaggi nascosti di {topic}?"
            ]
        }
    
    def _generate_user_message(self, profile: UserProfile, index: int) -> str:
        """
        Genera messaggio utente basato sul profilo.
        
        Args:
            profile: Profilo utente
            index: Indice della conversazione
            
        Returns:
            str: Messaggio utente generato
        """
        # Seleziona interesse casuale
        interest = random.choice(profile.interests)
        
        # Seleziona template per personalità
        templates = self.conversation_templates.get(profile.personality_type, [])
        if not templates:
            template = "Dimmi di più su {topic}"
        else:
            template = random.choice(templates)
        
        # Sostituisci placeholder
        message = template.format(
            topic=interest,
            other_topic=random.choice(profile.interests),
            emotion=random.choice(["felice", "triste", "ansioso", "eccitato"]),
            distractor=random.choice(["il tempo", "un film", "una canzone"]),
            random_thought=random.choice(["forse dovrei dormire", "ho fame", "che ore sono"])
        )
        
        # Aggiungi variazioni basate su communication style
        if profile.communication_style == "breve":
            message = message.split(',')[0] if ',' in message else message
            message = message.split('?')[0] + '?' if '?' in message else message
        elif profile.communication_style == "espressivo":
            message = message + "!!!" if random.random() > 0.5 else message
        elif profile.communication_style == "preciso":
            message = message.replace("Dimmi", "Specificare")
        
        # Aggiungi elementi casuali per realismo
        if random.random() > 0.8:
            prefixes = ["Scusa, ", "Ehi, ", "Senti, ", "Però "]
            message = random.choice(prefixes) + message.lower()
        
        return message
    
    def _generate_simulated_response(self, user_message: str, profile: UserProfile) -> str:
        """
        Genera risposta simulata basata sul messaggio utente e profilo.
        
        Args:
            user_message: Messaggio dell'utente
            profile: Profilo utente
            
        Returns:
            str: Risposta simulata
        """
        # Analizza tipo di domanda
        message_lower = user_message.lower()
        
        # Risposta base basata su contenuto
        if "perché" in message_lower:
            base_response = self._generate_why_response(user_message, profile)
        elif "come" in message_lower:
            base_response = self._generate_how_response(user_message, profile)
        elif "qual è" in message_lower or "cosa" in message_lower:
            base_response = self._generate_what_response(user_message, profile)
        elif "mi sento" in message_lower or "emozion" in message_lower:
            base_response = self._generate_emotional_response(user_message, profile)
        else:
            base_response = self._generate_general_response(user_message, profile)
        
        # Adatta risposta allo stile di comunicazione
        if profile.communication_style == "breve":
            base_response = base_response.split('.')[0] + '.'
        elif profile.communication_style == "espressivo":
            base_response = base_response.replace("è", "è davvero")
        elif profile.communication_style == "preciso":
            base_response = base_response.replace("generalmente", "tipicamente")
        
        return base_response
    
    def _generate_why_response(self, user_message: str, profile: UserProfile) -> str:
        """Genera risposta a domande 'perché'"""
        return f"Il funzionamento di questo sistema si basa su principi consolidati che garantiscono affidabilità e prestazioni ottimali. La struttura è progettata per essere modulare e scalabile."
    
    def _generate_how_response(self, user_message: str, profile: UserProfile) -> str:
        """Genera risposta a domande 'come'"""
        return "Il processo avviene attraverso diverse fasi coordinate: prima l'analisi dei requisiti, poi l'implementazione strutturata e infine la validazione dei risultati."
    
    def _generate_what_response(self, user_message: str, profile: UserProfile) -> str:
        """Genera risposta a domande 'cosa/qual è'"""
        return "Si tratta di un sistema avanzato che combina intelligenza artificiale e machine learning per fornire risposte accurate e contestualizzate."
    
    def _generate_emotional_response(self, user_message: str, profile: UserProfile) -> str:
        """Genera risposta a contenuti emotivi"""
        return "Capisco come ti senti. È normale provare queste emozioni di fronte a situazioni complesse. Il mio ruolo è aiutarti a elaborare questi pensieri in modo costruttivo."
    
    def _generate_general_response(self, user_message: str, profile: UserProfile) -> str:
        """Genera risposta generica"""
        return "Questa è un'ottima domanda. La risposta dipende da diversi fattori che consideriamo attentamente per fornirti l'informazione più rilevante."
    
    def get_simulation_stats(self, conversations: List[Tuple[str, str]]) -> Dict[str, Any]:
        """
        Calcola statistiche sulle conversazioni simulate.
        
        Args:
            conversations: Lista di conversazioni simulate
            
        Returns:
            Dict[str, Any]: Statistiche della simulazione
        """
        if not conversations:
            return {"error": "No conversations provided"}
        
        user_messages = [conv[0] for conv in conversations]
        assistant_responses = [conv[1] for conv in conversations]
        
        # Statistiche base
        stats = {
            "total_conversations": len(conversations),
            "avg_user_message_length": sum(len(msg) for msg in user_messages) / len(user_messages),
            "avg_response_length": sum(len(resp) for resp in assistant_responses) / len(assistant_responses),
            "unique_user_profiles": len(set(user_messages)),  # Approssimazione
        }
        
        # Analisi contenuto
        question_words = ["perché", "come", "cosa", "qual", "dove", "quando"]
        questions_count = sum(1 for msg in user_messages 
                             if any(word in msg.lower() for word in question_words))
        
        stats["questions_ratio"] = questions_count / len(user_messages)
        
        # Analisi risposte
        technical_terms = ["sistema", "algoritmo", "implementazione", "struttura", "processo"]
        technical_responses = sum(1 for resp in assistant_responses 
                                 if any(term in resp.lower() for term in technical_terms))
        
        stats["technical_responses_ratio"] = technical_responses / len(assistant_responses)
        
        return stats
