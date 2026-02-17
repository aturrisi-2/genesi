import re

with open('core/llm_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find single-quoted strings with apostrophes
pattern = r"'[^']*'[^']*'"
matches = re.findall(pattern, content)

print('Single-quoted strings with apostrophes:')
for match in matches:
    print(f'  {match}')

# Also check for lines with single quotes that might have issues
lines = content.split('\n')
for i, line in enumerate(lines, 1):
    if "'" in line and '"""' not in line and "'''" not in line:
        # Check if it's a single-quoted string
        if line.strip().startswith("'") or "'" in line and not line.strip().startswith('#'):
            print(f'Line {i}: {line.strip()}')
