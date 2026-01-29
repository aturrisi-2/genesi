def decide_response_strategy(file_analysis: dict, context: dict = None) -> dict:
    kind = file_analysis.get("kind", "binary")
    subtype = file_analysis.get("subtype", "unknown")
    size = file_analysis.get("size", "medium")
    processable = file_analysis.get("processable", False)
    
    if kind == "text":
        if subtype in ["py", "js", "html", "css"]:
            return {
                "strategy": "code_analysis",
                "model": "gpt-4o",
                "tools": ["reasoning", "code_interpreter"],
                "response_mode": "direct"
            }
        else:
            return {
                "strategy": "text_analysis",
                "model": "gpt-4o",
                "tools": ["reasoning"],
                "response_mode": "direct"
            }
    
    elif kind == "image":
        return {
            "strategy": "image_analysis",
            "model": "gpt-4o",
            "tools": ["vision", "reasoning"],
            "response_mode": "direct"
        }
    
    elif kind == "document":
        if subtype == "pdf":
            return {
                "strategy": "document_analysis",
                "model": "gpt-4o",
                "tools": ["pdf_reader", "reasoning"],
                "response_mode": "direct"
            }
        else:
            return {
                "strategy": "document_analysis",
                "model": "gpt-4o",
                "tools": ["reasoning"],
                "response_mode": "direct"
            }
    
    elif kind == "audio":
        return {
            "strategy": "audio_transcription",
            "model": "whisper",
            "tools": ["transcription"],
            "response_mode": "direct"
        }
    
    elif kind == "video":
        return {
            "strategy": "video_analysis",
            "model": "gpt-4o",
            "tools": ["video_frame_analysis", "reasoning"],
            "response_mode": "direct"
        }
    
    else:
        return {
            "strategy": "binary_info",
            "model": "gpt-4o",
            "tools": ["file_info"],
            "response_mode": "direct"
        }
