param(
    [string]$BranchName = "feature/hardening-intent-tts"
)

Write-Host "🔄 Switching to $BranchName ..." -ForegroundColor Cyan

# Assicura che non ci siano file sporchi
git status

# Cambia branch
git checkout $BranchName

# Allinea con remoto
git pull origin $BranchName

Write-Host "✅ Ora sei su $BranchName" -ForegroundColor Green
git branch
