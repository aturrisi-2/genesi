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
    
    # Pattern critici per TTS
    critical_patterns = [
        r'/tts',
        r'playTTS',
        r'text_to_speech',
        r'synthesize.*bytes',
        r'tts_text',
        r'display_text',
        r'final_text.*tts',
        r'response.*tts'
    ]
    
    # Pattern variabili testo
    text_patterns = [
        r'final_text',
        r'response.*text',
        r'tts_text',
        r'display_text'
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
                    # Check for critical TTS patterns
                    for pattern in critical_patterns:
                        matches = re.finditer(pattern, line, re.IGNORECASE)
                        for match in matches:
                            findings.append({
                                'file': str(file_path.relative_to(project_root)),
                                'line': line_num,
                                'type': 'CRITICAL',
                                'pattern': pattern,
                                'match': match.group(),
                                'line_content': line.strip()
                            })
                    
                    # Check for text variable patterns
                    for pattern in text_patterns:
                        matches = re.finditer(pattern, line, re.IGNORECASE)
                        for match in matches:
                            findings.append({
                                'file': str(file_path.relative_to(project_root)),
                                'line': line_num,
                                'type': 'TEXT_VAR',
                                'pattern': pattern,
                                'match': match.group(),
                                'line_content': line.strip()
                            })
                            
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
    
    # Group findings by type
    critical_findings = [f for f in findings if f['type'] == 'CRITICAL']
    text_var_findings = [f for f in findings if f['type'] == 'TEXT_VAR']
    
    # Print critical findings first
    print(f"\nPUNTI CRITICI TTS ({len(critical_findings)} trovati)")
    print("=" * 60)
    
    if critical_findings:
        for finding in sorted(critical_findings, key=lambda x: (x['file'], x['line'])):
            print(f"FILE: {finding['file']}")
            print(f"LINEA {finding['line']}: {finding['match']}")
            print(f"CONTENUTO: {finding['line_content']}")
            print(f"PATTERN: {finding['pattern']}")
            print("-" * 40)
    else:
        print("Nessun punto critico TTS trovato")
    
    # Print text variable findings
    print(f"\nVARIABILI TESTO ({len(text_var_findings)} trovate)")
    print("=" * 60)
    
    if text_var_findings:
        for finding in sorted(text_var_findings, key=lambda x: (x['file'], x['line'])):
            print(f"FILE: {finding['file']}")
            print(f"LINEA {finding['line']}: {finding['match']}")
            print(f"CONTENUTO: {finding['line_content']}")
            print(f"PATTERN: {finding['pattern']}")
            print("-" * 40)
    else:
        print("Nessuna variabile testo trovata")
    
    # Summary by file
    print(f"\nRIEPILOGO PER FILE")
    print("=" * 60)
    
    by_file = {}
    for finding in findings:
        file_path = finding['file']
        if file_path not in by_file:
            by_file[file_path] = {'critical': 0, 'text_var': 0}
        
        if finding['type'] == 'CRITICAL':
            by_file[file_path]['critical'] += 1
        else:
            by_file[file_path]['text_var'] += 1
    
    for file_path, counts in sorted(by_file.items()):
        if counts['critical'] > 0 or counts['text_var'] > 0:
            print(f"{file_path}: CRITICAL={counts['critical']}, TEXT_VAR={counts['text_var']}")
    
    return findings

if __name__ == "__main__":
    findings = audit_tts_access_points()
    print(f"\nAudit completato: {len(findings)} punti di accesso TTS identificati")
    
    # Save findings to file for reference
    with open('tts_audit_report.txt', 'w', encoding='utf-8') as f:
        f.write("TTS AUDIT REPORT\n")
        f.write("=" * 50 + "\n\n")
        for finding in findings:
            f.write(f"{finding['file']}:{finding['line']} - {finding['type']} - {finding['match']}\n")
            f.write(f"  {finding['line_content']}\n\n")
