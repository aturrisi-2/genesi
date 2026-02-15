param(
    [string]$FeatureBranch = "feature/hardening-intent-tts"
)

Write-Host "🚀 Deploying $FeatureBranch into ui-stable..." -ForegroundColor Yellow

# Controlla dove sei
$currentBranch = git rev-parse --abbrev-ref HEAD

if ($currentBranch -ne $FeatureBranch) {
    Write-Host "❌ NON sei su $FeatureBranch. Sei su $currentBranch" -ForegroundColor Red
    exit
}

# Push del branch feature prima
git push origin $FeatureBranch

# Passa a stable
git checkout ui-stable
git pull origin ui-stable

# Merge
git merge $FeatureBranch

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Merge fallito. Risolvi conflitti." -ForegroundColor Red
    exit
}

# Push stable
git push origin ui-stable

Write-Host "✅ Deploy completato su ui-stable" -ForegroundColor Green
