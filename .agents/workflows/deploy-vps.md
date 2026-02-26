---
description: Deploy Genesi to VPS (gold-faro-stable)
---

1. Commit and push changes to the remote repository.
```powershell
git add .
git commit -m "update"
git push origin gold-faro-stable
```

// turbo
2. SSH to VPS and update the code.
```powershell
ssh luca@87.106.30.193 "cd /opt/genesi && git fetch origin && git checkout gold-faro-stable && git pull origin gold-faro-stable && sudo systemctl restart genesi"
```

3. Optionally check logs.
```powershell
ssh luca@87.106.30.193 "sudo journalctl -u genesi -n 50 -o cat"
```
