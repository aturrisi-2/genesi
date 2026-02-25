from datetime import datetime
import pytz

def get_time_context():
    """Restituisce il contesto temporale (Mattina/Pomeriggio/Sera/Notte) per Roma."""
    try:
        roma_tz = pytz.timezone('Europe/Rome')
        now = datetime.now(roma_tz)
        hour = now.hour
        
        if 6 <= hour < 12:
            return "mattina ☀️"
        elif 12 <= hour < 18:
            return "pomeriggio 🌅"
        elif 18 <= hour < 23:
            return "sera 🌙"
        else:
            return "notte 🛌"
    except Exception:
        # Fallback se pytz fallisce
        hour = datetime.now().hour
        if 6 <= hour < 12: return "mattina ☀️"
        elif 12 <= hour < 18: return "pomeriggio 🌅"
        elif 18 <= hour < 23: return "sera 🌙"
        else: return "notte 🛌"

def get_formatted_time():
    """Restituisce l'ora corrente formattata in HH:MM."""
    try:
        roma_tz = pytz.timezone('Europe/Rome')
        return datetime.now(roma_tz).strftime('%H:%M')
    except Exception:
        return datetime.now().strftime('%H:%M')
