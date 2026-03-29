/**
 * Genesi WhatsApp Group Bridge — Baileys
 *
 * Collega Genesi ai gruppi WhatsApp come membro normale.
 * Non tocca nulla dell'integrazione Cloud API esistente (messaggi 1:1).
 * Chiama solo http://localhost:8000/api/chat con platform="whatsapp_group".
 */

const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion,
    makeCacheableSignalKeyStore,
    makeInMemoryStore,
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const axios = require("axios");
const pino = require("pino");
require("dotenv").config();

const GENESI_URL       = process.env.GENESI_URL || "http://localhost:8000";
const GROUP_EMAIL      = process.env.GENESI_GROUP_EMAIL || "whatsapp_group@genesi.group";
const GROUP_PASSWORD   = process.env.GENESI_GROUP_PASSWORD || "changeme";
const ALLOWED_GROUPS   = (process.env.ALLOWED_GROUPS || "").split(",").map(s => s.trim()).filter(Boolean);
const AUTH_DIR         = "./baileys-auth";

const logger = pino({ level: "silent" }); // silenzia i log interni di Baileys

// ── Buffer messaggi grezzi per gruppo ────────────────────────────────────────
// { groupId: [{name, text, ts}] }
const rawBuffers = {};
const MAX_RAW = 25;

function addToBuffer(groupId, name, text) {
    if (!rawBuffers[groupId]) rawBuffers[groupId] = [];
    rawBuffers[groupId].push({ name, text: text.slice(0, 200), ts: Date.now() });
    rawBuffers[groupId] = rawBuffers[groupId].slice(-MAX_RAW);
}

function getRecentMessages(groupId, limit = 15) {
    return (rawBuffers[groupId] || []).slice(-limit);
}

// ── Filtro: quando Genesi interviene ─────────────────────────────────────────
const GREETINGS_RE    = /\b(ciao a tutti|buongiorno|buonasera|buonanotte|salve|hey a tutti)\b/i;
const GENESI_RE       = /\bgenesi\b/i;
const CELEBRATION_EMO = ["🎉","🎊","🥳","🎈","🥂","🍾","🎂","🏆","🎁"];
const GOOD_NEWS_KW    = ["ce l'ho fatta","ho preso","ho comprato","ho vinto","abbiamo vinto",
                         "promozione","promosso","promossa","laurea","diploma","compleanno","auguri","finalmente"];

function shouldRespond(text) {
    if (GENESI_RE.test(text)) return true;
    if (GREETINGS_RE.test(text)) return true;
    if (CELEBRATION_EMO.some(e => text.includes(e))) return true;
    const lower = text.toLowerCase();
    if (GOOD_NEWS_KW.some(kw => lower.includes(kw))) return true;
    return false;
}

// ── Auth Genesi API ───────────────────────────────────────────────────────────
let authToken = null;

async function getToken() {
    if (authToken) return authToken;
    const res = await axios.post(`${GENESI_URL}/auth/login`, {
        email: GROUP_EMAIL,
        password: GROUP_PASSWORD,
    }, { timeout: 10000 });
    authToken = res.data.access_token;
    console.log("[Genesi] Token ottenuto");
    return authToken;
}

// ── Chiamata a Genesi ─────────────────────────────────────────────────────────
async function askGenesi(text, senderName, groupId) {
    try {
        const token = await getToken();

        // Costruisce il contesto discussione (come fa Telegram)
        const recentMsgs = getRecentMessages(groupId);
        let discussion = "";
        if (recentMsgs.length) {
            discussion = "[DISCUSSIONE IN CORSO — messaggi recenti del gruppo:]\n"
                + recentMsgs.map(m => `  ${m.name}: ${m.text}`).join("\n")
                + "\n[FINE DISCUSSIONE]\n";
        }

        const enriched = `${text}\n\n[GRUPPO FAMILIARE: scrive ${senderName}. `
            + `Sei un membro della famiglia. Usa il nome ${senderName}.]\n`
            + discussion
            + `[CONTESTO FAMIGLIA: ${senderName} è un membro della famiglia di Alfio.]`;

        const res = await axios.post(`${GENESI_URL}/api/chat`, {
            message: enriched,
            platform: "whatsapp_group",
        }, {
            headers: { Authorization: `Bearer ${token}` },
            timeout: 35000,
        });

        return res.data.response || null;
    } catch (e) {
        if (e.response?.status === 401) {
            authToken = null; // forza re-login al prossimo messaggio
        }
        console.error("[Genesi] API error:", e.message);
        return null;
    }
}

// ── Main Baileys ──────────────────────────────────────────────────────────────
async function startBaileys() {
    const { version } = await fetchLatestBaileysVersion();
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

    const sock = makeWASocket({
        version,
        logger,
        auth: {
            creds: state.creds,
            keys: makeCacheableSignalKeyStore(state.keys, logger),
        },
        printQRInTerminal: true,
        browser: ["Genesi", "Chrome", "1.0.0"],
        generateHighQualityLinkPreview: false,
        getMessage: async () => undefined,
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
        if (qr) {
            console.log("\n[Baileys] Scansiona il QR code con WhatsApp:\n");
        }
        if (connection === "close") {
            const code = lastDisconnect?.error?.output?.statusCode;
            const loggedOut = code === DisconnectReason.loggedOut;
            console.log(`[Baileys] Connessione chiusa (code=${code}). Reconnect: ${!loggedOut}`);
            if (!loggedOut) {
                setTimeout(startBaileys, 5000);
            } else {
                console.log("[Baileys] Logout — cancella baileys-auth/ e riscansiona il QR.");
            }
        } else if (connection === "open") {
            console.log("[Baileys] ✅ Connesso a WhatsApp. In ascolto sui gruppi...");
        }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
        if (type !== "notify") return;

        for (const msg of messages) {
            try {
                if (msg.key.fromMe) continue;

                const groupId = msg.key.remoteJid;
                if (!groupId?.endsWith("@g.us")) continue; // solo gruppi

                // Filtro per gruppi specifici (se configurato)
                if (ALLOWED_GROUPS.length && !ALLOWED_GROUPS.includes(groupId)) continue;

                const text = (
                    msg.message?.conversation
                    || msg.message?.extendedTextMessage?.text
                    || msg.message?.imageMessage?.caption
                    || msg.message?.videoMessage?.caption
                    || ""
                ).trim();

                if (!text) continue;

                // Nome mittente
                const senderJid = msg.key.participant || groupId;
                let senderName = senderJid.replace("@s.whatsapp.net", "").replace("@g.us", "");
                try {
                    const meta = await sock.groupMetadata(groupId);
                    const p = meta?.participants?.find(x => x.id === senderJid);
                    if (p?.name) senderName = p.name.split(" ")[0];
                    else if (msg.pushName) senderName = msg.pushName.split(" ")[0];
                } catch (_) {
                    if (msg.pushName) senderName = msg.pushName.split(" ")[0];
                }

                // Salva nel buffer grezzo (sempre, anche se Genesi non risponde)
                addToBuffer(groupId, senderName, text);
                console.log(`[${senderName}@${groupId.slice(0,10)}] ${text.slice(0, 60)}`);

                // Filtra: risponde solo se invocata/saluto/buona notizia
                if (!shouldRespond(text)) continue;

                console.log(`[Baileys] Intervengo per: "${text.slice(0, 50)}"`);

                // Typing indicator
                await sock.sendPresenceUpdate("composing", groupId);

                const reply = await askGenesi(text, senderName, groupId);

                await sock.sendPresenceUpdate("paused", groupId);

                if (reply) {
                    await sock.sendMessage(groupId, { text: reply });
                    console.log(`[Genesi → ${senderName}] ${reply.slice(0, 80)}`);
                }
            } catch (e) {
                console.error("[Baileys] Errore messaggio:", e.message);
            }
        }
    });
}

// ── Avvio ─────────────────────────────────────────────────────────────────────
console.log("[Genesi Baileys] Avvio servizio WhatsApp gruppi...");
startBaileys().catch(e => {
    console.error("[Baileys] Errore fatale:", e);
    process.exit(1);
});
