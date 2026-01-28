import os
from pathlib import Path

def analyze_file(file_path: str, filename: str, content_type: str) -> dict:
    ext = Path(filename).suffix.lower()
    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    
    # Size categories
    if size < 1024 * 100:  # < 100KB
        size_cat = "small"
    elif size < 1024 * 1024 * 5:  # < 5MB
        size_cat = "medium"
    else:
        size_cat = "large"
    
    # File kind detection
    text_exts = {'.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.csv'}
    image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'}
    audio_exts = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'}
    video_exts = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm'}
    document_exts = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
    
    if ext in text_exts:
        kind = "text"
        subtype = ext[1:] if ext else "unknown"
    elif ext in image_exts:
        kind = "image"
        subtype = ext[1:] if ext else "unknown"
    elif ext in audio_exts:
        kind = "audio"
        subtype = ext[1:] if ext else "unknown"
    elif ext in video_exts:
        kind = "video"
        subtype = ext[1:] if ext else "unknown"
    elif ext in document_exts:
        kind = "document"
        subtype = ext[1:] if ext else "unknown"
    else:
        kind = "binary"
        subtype = ext[1:] if ext else "unknown"
    
    # Processability check
    processable = kind in ["text", "image", "document"] and size_cat != "large"
    
    return {
        "kind": kind,
        "subtype": subtype,
        "size": size_cat,
        "processable": processable
    }
