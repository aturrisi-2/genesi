# Script PowerShell per download Mistral 7B
# Esegui: .\download_mistral.ps1

Write-Host "🚀 Download Mistral 7B Instruct per Genesi..." -ForegroundColor Green
Write-Host "Modello 10x più capace di Llama-2-7B" -ForegroundColor Yellow
Write-Host "Dimensione: ~4.1GB" -ForegroundColor Yellow
Write-Host ""

# Crea directory
New-Item -ItemType Directory -Force -Path "C:\opt\models"

# Download
Write-Host "📥 Download mistral-7b-instruct-v0.2.Q4_K_M.gguf..." -ForegroundColor Blue
$url = "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
$output = "C:\opt\models\mistral-7b-instruct-v0.2.Q4_K_M.gguf"

try {
    Invoke-WebRequest -Uri $url -OutFile $output -UseBasicParsing
    Write-Host "✅ Download completato!" -ForegroundColor Green
    Write-Host "📁 File salvato in: $output" -ForegroundColor Green
} catch {
    Write-Host "❌ Errore download: $_" -ForegroundColor Red
    Write-Host "🌐 Scarica manualmente da: $url" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🎯 PROSSIMO PASSO:" -ForegroundColor Cyan
Write-Host "1. Riavvia llama.cpp con:" -ForegroundColor White
Write-Host "   .\main.exe -m C:\opt\models\mistral-7b-instruct-v0.2.Q4_K_M.gguf --host 127.0.0.1 --port 8080" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Riavvia Genesi" -ForegroundColor White
Write-Host ""
Write-Host "🚀 Goditi conversazioni molto più naturali!" -ForegroundColor Green
