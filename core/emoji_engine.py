"""
Emoji Engine - Global emoji enrichment system
Non-intrusive styling layer for Genesi responses
"""

import re
from typing import Dict, Optional

# Intent to emoji mapping
INTENT_EMOJI_MAP: Dict[str, str] = {
    "greeting": "👋😊",
    "reminder_create": "📅⏰", 
    "reminder_list": "📋✨",
    "confirmation": "✅",
    "error": "⚠️",
    "question": "🤔",
    "positive": "✨😊",
    "neutral": "💬",
    "relational": "🤝",
    "admin": "🛠️",
    "weather": "☀️",
}

# Context-specific emoji mapping for certain patterns
CONTEXT_EMOJI_MAP: Dict[str, str] = {
    "chiamare": "📞",
    "medico": "🏥",
    "riunione": "👥",
    "cantiere": "🏗️",
    "appuntamento": "📅",
    "promemoria": "📝",
    "task": "📋",
    "lavoro": "💼",
    "casa": "🏠",
    "sole": "☀️",
    "piove": "🌧️",
    "nuvoloso": "☁️",
    "tempo": "🌤️",
}

def enrich_with_emojis(text: str, intent: Optional[str] = None) -> str:
    """
    Enrich text with appropriate emojis based on intent and context.
    
    Args:
        text: Input text to enrich
        intent: Optional intent classification for targeted emoji selection
        
    Returns:
        Text enriched with appropriate emojis
    """
    if not text or not isinstance(text, str):
        return text
    
    # Skip if text already contains emojis (to avoid duplication)
    if _has_emoji(text):
        return text
    
    # Skip if text looks like structured data (JSON, IDs, etc.)
    if _is_structured_data(text):
        return text
    
    enriched_text = text
    
    # Add intent-specific emoji at the beginning or end
    if intent and intent in INTENT_EMOJI_MAP:
        emoji = INTENT_EMOJI_MAP[intent]
        enriched_text = _add_intent_emoji(enriched_text, intent, emoji)
    
    # Add context-specific emojis for certain keywords
    enriched_text = _add_context_emojis(enriched_text)
    
    return enriched_text

def apply(text: str, intent: Optional[str] = None) -> str:
    """
    Apply emoji enrichment to text - main entry point.
    
    Args:
        text: Input text to enrich
        intent: Optional intent classification for targeted emoji selection
        
    Returns:
        Text enriched with appropriate emojis
    """
    return enrich_with_emojis(text, intent)

def _has_emoji(text: str) -> bool:
    """Check if text already contains emoji characters."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return bool(emoji_pattern.search(text))

def _is_structured_data(text: str) -> bool:
    """Check if text looks like structured data that shouldn't be modified."""
    # Skip JSON-like strings
    if text.strip().startswith(('{', '[', '"')) and text.strip().endswith(('}', ']', '"')):
        return True
    
    # Skip UUID-like strings
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    if uuid_pattern.match(text.strip()):
        return True
    
    # Skip pure numeric strings
    if text.strip().isdigit():
        return True
    
    # Skip file paths
    if '/' in text or '\\' in text or text.endswith(('.json', '.py', '.js', '.html')):
        return True
    
    return False

def _add_intent_emoji(text: str, intent: str, emoji: str) -> str:
    """Add intent-specific emoji to text."""
    lines = text.split('\n')
    
    if intent == "greeting":
        # Add greeting emoji at the beginning
        lines[0] = lines[0] + " " + emoji
    elif intent == "reminder_create":
        # Add confirmation emoji at start, reminder emoji at end
        # For reminder_create, use both emojis: confirmation at start, reminder at end
        confirmation_emoji = "✅"
        reminder_emoji = "📅⏰"
        lines[0] = lines[0].replace("Perfetto", "Perfetto " + confirmation_emoji)
        if len(lines) > 1:
            lines[-1] = lines[-1] + " " + reminder_emoji
        else:
            lines[0] = lines[0] + " " + reminder_emoji
    elif intent == "reminder_list":
        # Add list emoji to the header line
        if lines and "promemoria" in lines[0].lower():
            lines[0] = lines[0] + " " + emoji
    elif intent == "weather":
        # Add weather emoji at the end
        lines[-1] = lines[-1] + " " + emoji
    elif intent in ["confirmation", "positive"]:
        # Add emoji at the beginning
        lines[0] = emoji + " " + lines[0]
    elif intent == "error":
        # Add emoji at the beginning
        lines[0] = emoji + " " + lines[0]
    elif intent == "question":
        # Add emoji at the end
        lines[-1] = lines[-1] + " " + emoji
    elif intent in ["neutral", "relational", "admin"]:
        # Add emoji at the beginning
        lines[0] = emoji + " " + lines[0]
    
    return '\n'.join(lines)

def _add_context_emojis(text: str) -> str:
    """Add context-specific emojis for certain keywords."""
    lines = text.split('\n')
    enriched_lines = []
    
    for line in lines:
        enriched_line = line
        
        # Add context emojis for numbered list items (but not the number itself)
        if re.match(r'^\d+[\.\)]\s+', line.strip()):
            # This is a numbered list item, add emoji at the end
            for keyword, emoji in CONTEXT_EMOJI_MAP.items():
                if keyword.lower() in line.lower():
                    enriched_line = line.rstrip() + " " + emoji
                    break
        
        enriched_lines.append(enriched_line)
    
    return '\n'.join(enriched_lines)
