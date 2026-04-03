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
// Account per messaggi diretti (1:1) — di default usa l'account principale di Alfio
const DIRECT_EMAIL     = process.env.GENESI_DIRECT_EMAIL || "alfio.turrisi@gmail.com";
const DIRECT_PASSWORD  = process.env.GENESI_DIRECT_PASSWORD || "ZOEennio0810";
const ALLOWED_GROUPS   = (process.env.ALLOWED_GROUPS || "").split(",").map(s => s.trim()).filter(Boolean);
const AUTH_DIR         = "./baileys-auth";

const logger = pino({ level: "silent" }); // silenzia i log interni di Baileys

// ── Buffer messaggi grezzi per gruppo ────────────────────────────────────────
// { groupId: [{name, text, ts}] }
const rawBuffers = {};
const MAX_RAW = 25;

// ── Ultima risposta di Genesi per gruppo (per CONTINUAZIONE) ──────────────────
// { groupId: { text, ts } }
const lastGenesiReply = {};
const GENESI_REPLY_TTL = 5 * 60 * 1000; // 5 minuti

function addToBuffer(groupId, name, text) {
    if (!rawBuffers[groupId]) rawBuffers[groupId] = [];
    rawBuffers[groupId].push({ name, text: text.slice(0, 200), ts: Date.now() });
    rawBuffers[groupId] = rawBuffers[groupId].slice(-MAX_RAW);
}

function getRecentMessages(groupId, limit = 15) {
    const msgs = (rawBuffers[groupId] || []).slice(-limit);
    // Inserisce l'ultima risposta di Genesi se recente (< 5 min) —
    // così shouldRespond sa che Genesi ha già parlato e può riconoscere follow-up
    const last = lastGenesiReply[groupId];
    if (last && Date.now() - last.ts < GENESI_REPLY_TTL) {
        return [...msgs, { name: "Genesi", text: last.text.slice(0, 200) }];
    }
    return msgs;
}

// ── Filtro: quando Genesi interviene ─────────────────────────────────────────
// Fast-path locale solo per menzione diretta — tutto il resto decide l'LLM
const GENESI_RE = /\bgenesi\b/i;

async function shouldRespond(text, recentMessages, token) {
    // Fast-path: menzione diretta → sempre sì senza chiamare LLM
    if (GENESI_RE.test(text)) return true;

    // LLM decide per tutto il resto (saluti, buone notizie, ecc.)
    try {
        const res = await axios.post(`${GENESI_URL}/api/chat/group/should_respond`, {
            text,
            recent_messages: recentMessages,
        }, {
            headers: { Authorization: `Bearer ${token}` },
            timeout: 8000,
        });
        return res.data.intervieni === true;
    } catch (e) {
        // In caso di errore, non intervenire
        return false;
    }
}

// ── Auth Genesi API ───────────────────────────────────────────────────────────
const tokens = { group: null, direct: null };

async function getToken(type = "group") {
    if (tokens[type]) return tokens[type];
    const email    = type === "direct" ? DIRECT_EMAIL    : GROUP_EMAIL;
    const password = type === "direct" ? DIRECT_PASSWORD : GROUP_PASSWORD;
    const res = await axios.post(`${GENESI_URL}/auth/login`, { email, password }, { timeout: 10000 });
    tokens[type] = res.data.access_token;
    console.log(`[Genesi] Token ${type} ottenuto`);
    return tokens[type];
}

// ── Chiamata a Genesi — gruppo ────────────────────────────────────────────────
async function askGenesiGroup(text, senderName, senderId, groupId, token = null) {
    try {
        if (!token) token = await getToken("group");
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
        if (e.response?.status === 401) tokens.group = null;
        console.error("[Genesi] Group API error:", e.message, e.response?.data);
        return null;
    }
}

// ── Chiamata a Genesi — diretto 1:1 ──────────────────────────────────────────
async function askGenesiDirect(text) {
    try {
        const token = await getToken("direct");
        const res = await axios.post(`${GENESI_URL}/api/chat`, {
            message:  text,
            platform: "whatsapp",
        }, {
            headers: { Authorization: `Bearer ${token}` },
            timeout: 35000,
        });
        return res.data.response || null;
    } catch (e) {
        if (e.response?.status === 401) tokens.direct = null;
        console.error("[Genesi] Direct API error:", e.message, e.response?.data);
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

    _activeSock = sock;  // aggiorna subito il riferimento
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
            const loggedOut  = code === DisconnectReason.loggedOut;
            const replaced   = code === 440; // sessione sostituita da altro client
            console.log(`[Baileys] Connessione chiusa (code=${code}). Reconnect: ${!loggedOut && !replaced}`);
            if (loggedOut || replaced) {
                console.log("[Baileys] Sessione non valida (logout o sostituita). Uscita — systemd riavvierà.");
                process.exit(1);
            } else {
                setTimeout(startBaileys, 5000);
            }
        } else if (connection === "open") {
            console.log("[Baileys] ✅ Connesso a WhatsApp. In ascolto su gruppi e messaggi diretti...");
        }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
        if (type !== "notify") return;

        for (const msg of messages) {
            try {
                if (msg.key.fromMe) continue;

                const remoteJid = msg.key.remoteJid;
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

                const senderJid = msg.key.participant || groupId;
                let senderName = (msg.pushName || senderJid).split(" ")[0];
                try {
                    const meta = await sock.groupMetadata(groupId);
                    const p = meta?.participants?.find(x => x.id === senderJid);
                    if (p?.name) senderName = p.name.split(" ")[0];
                } catch (_) {}

                // Salva nel buffer grezzo locale
                addToBuffer(groupId, senderName, text);
                console.log(`[${senderName}@${groupId.slice(0,10)}] ${text.slice(0, 60)}`);

                // Filtra: LLM decide se intervenire
                const token = await getToken("group");

                // Fast-path: reply diretta a un messaggio di Genesi → sempre sì
                const contextInfo = msg.message?.extendedTextMessage?.contextInfo || {};
                const quotedParticipant = contextInfo.participant || contextInfo.remoteJid || "";
                const myJid = sock.user?.id?.replace(/:.*@/, "@") || "";
                const isReplyToGenesi = myJid && quotedParticipant && quotedParticipant.replace(/:.*@/, "@") === myJid;
                if (isReplyToGenesi) {
                    console.log(`[Baileys] Reply diretta a Genesi da ${senderName} → intervengo`);
                } else {
                    const recentMsgs = getRecentMessages(groupId);
                    if (!await shouldRespond(text, recentMsgs, token)) continue;
                }

                console.log(`[Baileys] Intervengo per: "${text.slice(0, 50)}"`);

                await sock.sendPresenceUpdate("composing", groupId);
                const reply = await askGenesiGroup(text, senderName, senderJid, groupId, token);
                await sock.sendPresenceUpdate("paused", groupId);

                if (reply) {
                    await sock.sendMessage(groupId, { text: reply });
                    lastGenesiReply[groupId] = { text: reply, ts: Date.now() };
                    console.log(`[Genesi → ${senderName}] ${reply.slice(0, 80)}`);
                }
            } catch (e) {
                console.error("[Baileys] Errore messaggio:", e.message);
            }
        }
    });
}

// ── HTTP server per invio proattivo (compleanni, reminder, ecc.) ──────────────
// Python chiama: POST http://localhost:3001/send  { "groupId": "...", "text": "..." }
const http = require("http");
const SEND_PORT = parseInt(process.env.BAILEYS_SEND_PORT || "3001", 10);
const SEND_SECRET = process.env.BAILEYS_SEND_SECRET || "";

let _activeSock = null;  // riferimento al socket Baileys attivo

function startHttpServer() {
    const server = http.createServer(async (req, res) => {
        if (req.method !== "POST" || req.url !== "/send") {
            res.writeHead(404); res.end("not found"); return;
        }
        let body = "";
        req.on("data", d => body += d);
        req.on("end", async () => {
            try {
                const { groupId, text, secret } = JSON.parse(body);
                if (SEND_SECRET && secret !== SEND_SECRET) {
                    res.writeHead(403); res.end("forbidden"); return;
                }
                if (!groupId || !text) {
                    res.writeHead(400); res.end("missing groupId or text"); return;
                }
                if (!_activeSock) {
                    res.writeHead(503); res.end("socket not ready"); return;
                }
                await _activeSock.sendMessage(groupId, { text });
                console.log(`[Baileys/HTTP] Sent to ${groupId}: ${text.slice(0, 60)}`);
                res.writeHead(200, {"Content-Type": "application/json"});
                res.end(JSON.stringify({ ok: true }));
            } catch (e) {
                console.error("[Baileys/HTTP] Send error:", e.message);
                res.writeHead(500); res.end(e.message);
            }
        });
    });
    server.listen(SEND_PORT, "127.0.0.1", () => {
        console.log(`[Baileys/HTTP] Send server on 127.0.0.1:${SEND_PORT}`);
    });
}

// ── Avvio ─────────────────────────────────────────────────────────────────────
console.log("[Genesi Baileys] Avvio servizio WhatsApp gruppi...");
startHttpServer();
startBaileys().catch(e => {
    console.error("[Baileys] Errore fatale:", e);
    process.exit(1);
});
