#!/bin/bash
# Script download Mistral 7B - Modello più capace per Genesi

echo "🚀 Download Mistral 7B Instruct per Genesi..."
echo "Questo modello è 10x più capace di Llama-2-7B"
echo "Dimensione: ~4.1GB"
echo ""

# Crea directory modelli se non esiste
mkdir -p /opt/models

# Download Mistral 7B Instruct
echo "📥 Download mistral-7b-instruct-v0.2.Q4_K_M.gguf..."
wget -c https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf \
     -O /opt/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf

echo ""
echo "✅ Download completato!"
echo "📁 File salvato in: /opt/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
echo ""
echo "🎯 PROSSIMO PASSO:"
echo "1. Riavvia llama.cpp con il nuovo modello:"
echo "   ./main -m /opt/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf --host 127.0.0.1 --port 8080"
echo ""
echo "2. Riavvia Genesi"
echo ""
echo "🚀 Goditi conversazioni molto più naturali!"
