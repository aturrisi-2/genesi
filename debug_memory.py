#!/usr/bin/env python3
# Debug memoria
from memory.episodic import get_recent_events

user_id = 'test-memory-2'
events = get_recent_events(user_id, limit=5)

print(f'Eventi trovati: {len(events)}')
for i, event in enumerate(events):
    print(f'Evento {i}:')
    print(f'  type={getattr(event, "type", "N/A")}')
    print(f'  content={getattr(event, "content", "N/A")}')
    if hasattr(event, 'content'):
        content = event.content
        print(f'  Content type: {type(content)}')
        if isinstance(content, dict):
            print(f'  Content keys: {list(content.keys())}')
            for key, value in content.items():
                print(f'    {key}: {value}')
