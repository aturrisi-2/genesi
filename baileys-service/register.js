/**
 * Collegamento Baileys a WhatsApp via pairing code.
 *
 * PREREQUISITO: WhatsApp installato sul telefono con il numero target.
 *
 * Passi:
 *   1. node register.js +393313650671
 *   2. Apri WhatsApp sul telefono → Impostazioni → Dispositivi collegati
 *      → Collega dispositivo → Collega con numero di telefono
 *   3. Inserisci il codice mostrato qui
 *   4. Dopo il collegamento puoi avviare: node index.js
 */

const {
    default: makeWASocket,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    makeCacheableSignalKeyStore,
    DisconnectReason,
} = require("@whiskeysockets/baileys");
const pino = require("pino");
require("dotenv").config();

const AUTH_DIR = "./baileys-auth";

async function main() {
    const phoneNumber = process.argv[2] || process.env.WA_PHONE_NUMBER_FULL;
    if (!phoneNumber) {
        console.error("Uso: node register.js +393313650671");
        process.exit(1);
    }

    const clean = phoneNumber.replace(/[^0-9]/g, "");
    console.log(`\n=== Collegamento WhatsApp Baileys per +${clean} ===`);
    console.log("Assicurati che WhatsApp sia installato sul telefono con questo numero.\n");

    const { version } = await fetchLatestBaileysVersion();
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const logger = pino({ level: "silent" });

    // Se già collegato, esci
    if (state.creds.me) {
        console.log("✅ Già collegato come:", state.creds.me.id);
        console.log("Avvia il servizio: node index.js");
        process.exit(0);
    }

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

    sock.ev.on("connection.update", async ({ connection, lastDisconnect, qr }) => {
        if (qr) {
            // QR code come fallback (non dovrebbe apparire con pairing code)
            console.log("\n[QR CODE disponibile ma usa il pairing code sopra]");
        }
        if (connection === "open") {
            console.log("\n✅ Collegamento completato! WhatsApp connesso.");
            console.log("Puoi avviare il servizio: node index.js\n");
            process.exit(0);
        }
        if (connection === "close") {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            console.log("Connessione chiusa, codice:", statusCode);
            if (statusCode === DisconnectReason.loggedOut) {
                console.log("Sessione non valida. Cancella baileys-auth/ e riprova.");
                process.exit(1);
            }
            if (statusCode === DisconnectReason.timedOut) {
                console.log("Timeout — riprova tra qualche secondo.");
                process.exit(1);
            }
        }
    });

    // Aspetta che la connessione sia aperta prima di richiedere il pairing code
    await new Promise(resolve => setTimeout(resolve, 3000));

    console.log("Richiedo il codice di abbinamento...");
    try {
        const pairingCode = await sock.requestPairingCode(clean);
        const formatted = pairingCode.match(/.{1,4}/g)?.join("-") || pairingCode;
        console.log("\n┌─────────────────────────────────┐");
        console.log(`│   CODICE PAIRING:  ${formatted.padEnd(13)}│`);
        console.log("└─────────────────────────────────┘\n");
        console.log("Sul telefono con WhatsApp:");
        console.log("  → Impostazioni → Dispositivi collegati");
        console.log("  → Collega dispositivo → Collega con numero di telefono");
        console.log(`  → Inserisci: ${formatted}\n`);
        console.log("In attesa conferma... (max 5 minuti)\n");
    } catch (e) {
        console.error("\nErrore pairing code:", e.message);
        console.log("\nSoluzione: assicurati che WhatsApp sia aperto e connesso");
        console.log("sul telefono con il numero +"+clean);
        process.exit(1);
    }

    // Timeout 5 minuti
    setTimeout(() => {
        console.log("\nTimeout — il codice è scaduto. Riavvia lo script.");
        process.exit(1);
    }, 5 * 60 * 1000);
}

main().catch(e => { console.error(e); process.exit(1); });
