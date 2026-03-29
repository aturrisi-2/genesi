/**
 * Registrazione una-tantum del numero WhatsApp via SMS.
 * Eseguire una sola volta: node register.js +393313650671
 *
 * Dopo la registrazione, avviare il servizio normale: node index.js
 */

const {
    default: makeWASocket,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    makeCacheableSignalKeyStore,
    DisconnectReason,
} = require("@whiskeysockets/baileys");
const pino   = require("pino");
const readline = require("readline");
require("dotenv").config();

const AUTH_DIR = "./baileys-auth";

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const ask = (q) => new Promise(resolve => rl.question(q, resolve));

async function main() {
    const phoneNumber = process.argv[2] || process.env.WA_PHONE_NUMBER_FULL;
    if (!phoneNumber) {
        console.error("Uso: node register.js +393313650671");
        process.exit(1);
    }

    const clean = phoneNumber.replace(/[^0-9]/g, "");
    console.log(`\n=== Registrazione WhatsApp per +${clean} ===\n`);

    const { version } = await fetchLatestBaileysVersion();
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const logger = pino({ level: "silent" });

    const sock = makeWASocket({
        version,
        logger,
        auth: {
            creds: state.creds,
            keys: makeCacheableSignalKeyStore(state.keys, logger),
        },
        printQRInTerminal: false,
        browser: ["Genesi", "Chrome", "1.0.0"],
        getMessage: async () => undefined,
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async ({ connection, lastDisconnect }) => {
        if (connection === "open") {
            console.log("\n✅ Registrazione completata! WhatsApp connesso.");
            console.log("Ora puoi avviare il servizio: node index.js\n");
            rl.close();
            process.exit(0);
        }
        if (connection === "close") {
            const code = lastDisconnect?.error?.output?.statusCode;
            if (code === DisconnectReason.loggedOut) {
                console.log("Sessione non valida. Cancella la cartella baileys-auth/ e riprova.");
                process.exit(1);
            }
        }
    });

    // Se già registrato, non serve fare nulla
    if (state.creds.registered) {
        console.log("Numero già registrato. Avvia direttamente: node index.js");
        rl.close();
        process.exit(0);
    }

    // Richiedi pairing code (viene inviato come SMS o notifica WhatsApp)
    try {
        console.log("Richiedo il codice di abbinamento a WhatsApp...");
        const pairingCode = await sock.requestPairingCode(clean);
        console.log("\n╔══════════════════════════════════════╗");
        console.log(`║  CODICE PAIRING:  ${pairingCode}  ║`);
        console.log("╚══════════════════════════════════════╝\n");
        console.log("Apri WhatsApp sul tuo telefono:");
        console.log("  Impostazioni → Dispositivi collegati → Collega dispositivo");
        console.log("  Scegli 'Collega con numero di telefono'");
        console.log("  Inserisci il codice sopra\n");
        console.log("In attesa che tu inserisca il codice...\n");
    } catch (e) {
        console.error("Errore richiesta pairing code:", e.message);

        // Fallback: registrazione via SMS
        console.log("\nTento registrazione via SMS...");
        try {
            await sock.register(clean, "sms");
            const code = await ask("Inserisci il codice SMS ricevuto su +"+clean+": ");
            await sock.register(clean, undefined, code.trim());
        } catch (e2) {
            console.error("Errore SMS:", e2.message);
            process.exit(1);
        }
    }
}

main().catch(e => { console.error(e); process.exit(1); });
