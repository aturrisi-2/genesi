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
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const axios = require("axios");
const pino = require("pino");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
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
async function askGenesi(text, senderName, senderId, groupId) {
    try {
        const token = await getToken();

        // Usa l'endpoint /api/chat/group — gestisce tutta la logica memoria/contesto
        // come il gruppo Telegram (build_group_context, append_raw_message, ecc.)
        const res = await axios.post(`${GENESI_URL}/api/chat/group`, {
            text,
            sender_name: senderName,
            sender_id:   senderId,
            group_id:    groupId,
        }, {
            headers: { Authorization: `Bearer ${token}` },
            timeout: 35000,
        });

        return res.data.response || null;
    } catch (e) {
        if (e.response?.status === 401) {
            authToken = null;
        }
        console.error("[Genesi] API error:", e.message, e.response?.data);
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
        printQRInTerminal: false,
        browser: ["Genesi", "Chrome", "1.0.0"],
        generateHighQualityLinkPreview: false,
        getMessage: async () => undefined,
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
        if (qr) {
            console.log("\n========== QR CODE WHATSAPP ==========");
            qrcode.generate(qr, { small: true });
            // Salva anche su file per recupero remoto
            fs.writeFileSync("./qr-latest.txt", qr);
            console.log("=======================================\n");
            console.log("[Baileys] Apri WhatsApp → Impostazioni → Dispositivi collegati → Collega un dispositivo");
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

                // Salva nel buffer grezzo locale (fallback se backend non disponibile)
                addToBuffer(groupId, senderName, text);
                console.log(`[${senderName}@${groupId.slice(0,10)}] ${text.slice(0, 60)}`);

                // Filtra: risponde solo se invocata/saluto/buona notizia
                if (!shouldRespond(text)) continue;

                console.log(`[Baileys] Intervengo per: "${text.slice(0, 50)}"`);

                // Typing indicator
                await sock.sendPresenceUpdate("composing", groupId);

                const reply = await askGenesi(text, senderName, senderJid, groupId);

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
