from typing import Dict, Any


POSITIVE_SIGNALS = [
    "grazie", "bene", "ottimo", "fantastico", "bellissimo", "perfetto",
    "felice", "contento", "contenta", "soddisfatto", "soddisfatta",
    "mi piace", "adoro", "meraviglioso", "stupendo", "grande",
    "finalmente", "evvai", "dai!", "sì!", "wow", "top",
    "mi sento meglio", "sto meglio", "va meglio", "ce l'ho fatta"
]

NEGATIVE_SIGNALS = [
    "male", "odio", "problema", "schifo", "orribile", "terribile",
    "triste", "tristezza", "depresso", "depressa", "giù",
    "stanco", "stanca", "esausto", "esausta", "non ce la faccio",
    "ansia", "ansioso", "ansiosa", "paura", "panico",
    "arrabbiato", "arrabbiata", "incazzato", "incazzata", "furioso",
    "preoccupato", "preoccupata", "stress", "stressato", "stressata",
    "non ne posso più", "mi hanno rotto", "sono stufo", "sono stufa",
    "mi sento solo", "mi sento sola", "non ho voglia",
    "piango", "ho pianto", "voglio piangere", "sto male",
    "disperato", "disperata", "in crisi", "burnout", "crollo",
    "fa schifo", "non sto bene", "mi sento male"
]


def compute_affect(event_type: str, content: Dict[str, Any]) -> float:
    affect = 0.0
    text = content.get("text", "").lower()

    # Segnali positivi
    pos_count = sum(1 for w in POSITIVE_SIGNALS if w in text)
    affect += min(pos_count * 0.2, 0.6)

    # Segnali negativi
    neg_count = sum(1 for w in NEGATIVE_SIGNALS if w in text)
    affect -= min(neg_count * 0.25, 0.8)

    # Enfasi
    if "!" in text:
        affect += 0.1 if affect >= 0 else -0.1
    if text.isupper() and len(text) > 3:
        affect += 0.15 if affect >= 0 else -0.15

    # Tipo evento
    if event_type == "error":
        affect -= 0.5

    return max(-1.0, min(1.0, round(affect, 2)))