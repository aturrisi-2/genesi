import ast
import sys

try:
    with open('core/llm_service.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Try to parse the file
    ast.parse(content)
    print('✅ File compiles correctly - no syntax errors')
    
except SyntaxError as e:
    print(f'❌ SyntaxError found: {e}')
    print(f'Line {e.lineno}: {e.text.strip() if e.text else "N/A"}')
    print(' ' * (e.offset - 1) + '^')
    
except Exception as e:
    print(f'❌ Other error: {e}')
