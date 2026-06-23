# Workflow Claude Code → GitHub → VPS per Genesi

Questo documento descrive il flusso operativo consigliato per lavorare su **Genesi** usando Claude Code/Claude da smartphone o cloud, con GitHub come sorgente centrale e autodeploy sul VPS.

## Repository

- GitHub: https://github.com/aturrisi-2/genesi
- Branch stabile indicato dal link: `gold-faro-stable`
- Branch citato nei messaggi: `gold_faro_stable`

> Nota importante: `gold-faro-stable` e `gold_faro_stable` sono due branch diversi per Git. Prima di lavorare bisogna confermare quale dei due attiva realmente l'autodeploy.

## VPS

- Host SSH: `<user>@<vps-host>`
- Directory progetto sul VPS: `<vps-project-dir>` (es. `/opt/<app>`)
- Runtime: Python
- Autodeploy: già presente
- Restart automatico: già presente

## Flusso consigliato e sicuro

1. Claude Code lavora nel cloud o da smartphone sulla repo GitHub.
2. Le modifiche vengono fatte su un branch separato, non direttamente sul branch stabile.
3. Claude apre una Pull Request verso il branch stabile.
4. L'utente controlla diff e modifiche da GitHub, anche da smartphone.
5. Solo dopo approvazione si fa merge nel branch stabile.
6. Il merge attiva autodeploy e restart sul VPS.

Schema:

```text
Claude Code cloud/smartphone
        ↓
branch di lavoro: claude/nome-task
        ↓
Pull Request verso branch stabile
        ↓
review e approvazione utente
        ↓
merge su branch stabile
        ↓
autodeploy su VPS <vps-project-dir>
        ↓
restart app Python
```

## Regola di sicurezza

Evitare push diretti sul branch stabile, perché il branch stabile è collegato alla produzione.

Preferire sempre:

```text
branch separato → PR → review → merge → deploy
```

## Prompt operativo per Claude Code

Usare questo prompt quando si avvia un task da Claude Code cloud/app mobile:

```text
Lavora sulla repo aturrisi-2/genesi.
Usa come base il branch stabile del progetto, da confermare tra gold-faro-stable e gold_faro_stable.
Non pushare direttamente sul branch stabile.
Crea un branch separato con prefisso claude/ per le modifiche.
Esegui i controlli disponibili nel progetto.
Quando hai finito, fai push del branch e prepara/apri una Pull Request verso il branch stabile.
Ricorda che il merge sul branch stabile attiva autodeploy e restart sul VPS in <vps-project-dir>.
```

## Checklist prima del merge

- [ ] Branch stabile corretto confermato.
- [ ] Diff della PR controllato.
- [ ] Nessun segreto o credenziale inclusa nel codice.
- [ ] Test o controlli disponibili eseguiti.
- [ ] Logica di deploy/restart non modificata senza necessità.
- [ ] Merge approvato consapevolmente perché va in produzione.

## Note operative

- Il PC locale non deve restare acceso se si usa Claude Code cloud.
- Lo smartphone può essere usato per avviare task, seguire avanzamenti e approvare PR.
- Il VPS resta aggiornato tramite autodeploy già configurato.
