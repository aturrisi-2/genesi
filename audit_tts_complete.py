#!/usr/bin/env python3
"""
AUDIT ARCHITETTURALE COMPLETO - Punti di accesso TTS
Scansiona TUTTO il codice per identificare OGNI punto di accesso al TTS
"""

import os
import re
from pathlib import Path

def audit_tts_access_points():
    """Scansiona tutto il progetto per trovare punti di accesso TTS"""
    print("AUDIT ARCHITETTURALE COMPLETO - Punti di accesso TTS")
    print("=" * 60)
    
    project_root = Path(__file__).parent
    tts_patterns = [
        r'tts',
        r'TTS',
        r'text_to_speech',
        r'synthesize',
        r'playTTS',
        r'/tts',
        r'final_text',
        r'response.*text',
        r'tts_text',
        r'display_text',
        r'sanitize.*tts',
        r'edge.*tts',
        r'coqui.*tts'
    ]
    
    file_extensions = ['.py', '.js']
    exclude_dirs = ['.git', '__pycache__', 'node_modules', '.pytest_cache']
    
    findings = []
    
    for file_path in project_root.rglob('*'):
        # Skip directories and excluded
        if file_path.is_dir() or any(exclude in file_path.parts for exclude in exclude_dirs):
            continue
            
        # Only check relevant file types
        if file_path.suffix not in file_extensions:
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                
                for line_num, line in enumerate(lines, 1):
                    for pattern in tts_patterns:
                        matches = re.finditer(pattern, line, re.IGNORECASE)
                        for match in matches:
                            # Get context around the match
                            start_line = max(0, line_num - 2)
                            end_line = min(len(lines), line_num + 2)
                            context = '\n'.join(lines[start_line:end_line])
                            
                            findings.append({
                                'file': str(file_path.relative_to(project_root)),
                                'line': line_num,
                                'pattern': pattern,
                                'match': match.group(),
                                'line_content': line.strip(),
                                'context': context
                            })
                            
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
    
    # Group findings by file
    by_file = {}
    for finding in findings:
        file_path = finding['file']
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(finding)
    
    # Print detailed report
    print(f"\nTROVATI {len(findings)} PUNTI DI ACCESSO TTS")
    print("=" * 60)
    
    for file_path, file_findings in sorted(by_file.items()):
        print(f"\n📁 FILE: {file_path}")
        print("-" * 40)
        
        for finding in file_findings:
            print(f"  📍 Linea {finding['line']}: {finding['match']}")
            print(f"     Pattern: {finding['pattern']}")
            print(f"     Contenuto: {finding['line_content']}")
            print(f"     Contesto:\n     {finding['context']}")
            print()
    
    # Summary by pattern
    print("\nRIEPILOGO PER PATTERN")
    print("=" * 60)
    pattern_summary = {}
    for finding in findings:
        pattern = finding['pattern']
        if pattern not in pattern_summary:
            pattern_summary[pattern] = []
        pattern_summary[pattern].append(finding)
    
    for pattern, pattern_findings in sorted(pattern_summary.items()):
        print(f"\n🔍 PATTERN: {pattern} ({len(pattern_findings)} occorrenze)")
        for finding in pattern_findings:
            print(f"    {finding['file']}:{finding['line']}")
    
    # Critical findings - direct TTS calls
    print("\n🚨 PUNTI CRITICI - Chiamate dirette TTS")
    print("=" * 60)
    critical_patterns = [r'/tts', r'playTTS', r'text_to_speech', r'synthesize']
    
    critical_findings = [f for f in findings if any(re.search(cp, f['match'], re.IGNORECASE) for cp in critical_patterns)]
    
    if critical_findings:
        for finding in critical_findings:
            print(f"  🚨 {finding['file']}:{finding['line']} - {finding['match']}")
            print(f"     {finding['line_content']}")
    else:
        print("  ✅ Nessuna chiamata diretta TTS trovata")
    
    return findings

if __name__ == "__main__":
    findings = audit_tts_access_points()
    print(f"\nAudit completato: {len(findings)} punti di accesso TTS identificati")
