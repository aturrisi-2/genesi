# Baileys Runtime Runbook

This runbook documents the WhatsApp bridge runtime boundary. It is intentionally operational documentation only: do not use this file as permission to edit the live runtime.

## Runtime Layout

| Path | Role | Git tracked |
| --- | --- | --- |
| `/opt/genesi/baileys-service/index.js` | Source copy kept in the Genesi repository | yes |
| `/opt/genesi-baileys/index.js` | Live Node.js runtime used by systemd | no |
| `/opt/genesi-baileys/.env` | Runtime environment, auth and whitelist configuration | no |
| `/opt/genesi-baileys/baileys-auth*` | WhatsApp auth/session store | no |
| `/opt/genesi-baileys/media-cache` | Runtime media cache | no |
| `/opt/genesi-baileys/baileys.log` | Runtime log | no |
| `/opt/genesi-baileys/node_modules` | Runtime dependencies | no |

## Systemd Boundary

`genesi-baileys.service` runs the live runtime from `/opt/genesi-baileys`:

```text
WorkingDirectory=/opt/genesi-baileys
ExecStart=/usr/bin/node index.js
```

The backend repository can deploy normally without changing the live Baileys process. A backend push does not automatically synchronize `/opt/genesi/baileys-service/index.js` into `/opt/genesi-baileys/index.js`.

## What Not To Do

- Do not edit `/opt/genesi-baileys/index.js` directly during normal backend work.
- Do not touch `/opt/genesi-baileys/.env`.
- Do not touch `baileys-auth*`.
- Do not touch `media-cache`.
- Do not touch `baileys.log`.
- Do not touch `node_modules`.
- Do not restart `genesi-baileys.service` unless explicitly authorized.
- Do not copy files from the repository into the runtime without a dedicated sync procedure.

## Read-Only Checks

Use these only when an operator asks for a Baileys audit:

```bash
systemctl is-active genesi-baileys.service
node --check /opt/genesi/baileys-service/index.js
node --check /opt/genesi-baileys/index.js
diff -u /opt/genesi/baileys-service/index.js /opt/genesi-baileys/index.js | sed -n '1,240p'
```

Do not print `.env` contents. If a check needs configuration state, report booleans or presence only.

## Controlled Sync Procedure

Only run this with explicit authorization:

1. Create a timestamped backup of the live file:

   ```bash
   cp /opt/genesi-baileys/index.js /opt/genesi-baileys/index.js.backup-$(date +%Y%m%d-%H%M%S)
   ```

2. Copy only the tracked source:

   ```bash
   cp /opt/genesi/baileys-service/index.js /opt/genesi-baileys/index.js
   ```

3. Validate syntax:

   ```bash
   node --check /opt/genesi-baileys/index.js
   ```

4. If syntax fails, restore the backup and stop.

5. Restart only `genesi-baileys.service` if explicitly authorized.

6. Verify service health and logs without touching backend `genesi.service`.

## Desync Risk

The main risk is a mismatch between the repository source and the live runtime. This can cause:

- backend/admin group controls implemented in Python but not respected by live WhatsApp;
- old engaged-window behavior still live after a backend deploy;
- missing log markers when debugging;
- runtime behavior disappearing after manual file replacement.

For any Baileys-related change, record both states:

- repository commit containing `baileys-service/index.js`;
- live runtime backup path and restart time.

## Future Recommendation

Move Baileys runtime deployment into a tracked, repeatable release path:

- package the bridge as a separate tracked service or subproject;
- make sync/restart a single controlled script with preflight and rollback;
- keep auth/session/media/log files outside the deploy artifact;
- make the deploy report include source hash, runtime hash, backup path, syntax check and service PID.

