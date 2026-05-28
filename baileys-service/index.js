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
    downloadMediaMessage,
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const axios = require("axios");
const pino = require("pino");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");
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
async function askGenesiGroup(text, senderName, senderId, groupId, groupName = "WhatsApp Group", participants = null, token = null) {
    try {
        if (!token) token = await getToken("group");
        const res = await axios.post(`${GENESI_URL}/api/chat/group`, {
            text,
            sender_name: senderName,
            sender_id:   senderId,
            group_id:    groupId,
            group_name:  groupName,
            participants: participants,
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
        browser: ["Ubuntu", "Chrome", "20.0.04"],
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
                if (!remoteJid) continue;

                // 1. GESTIONE MESSAGGI DIRETTI (1:1)
                if (!remoteJid.endsWith("@g.us")) {
                    const mType = Object.keys(msg.message || {})[0];
                    if (!mType) continue;

                    let text = "";
                    let caption = "";
                    let filename = "";
                    let mime = "";
                    let finalMsgType = "text";

                    if (mType === "conversation") {
                        text = msg.message.conversation;
                        finalMsgType = "text";
                    } else if (mType === "extendedTextMessage") {
                        text = msg.message.extendedTextMessage.text;
                        finalMsgType = "text";
                    } else if (mType === "imageMessage") {
                        caption = msg.message.imageMessage.caption || "";
                        mime = msg.message.imageMessage.mimetype || "image/jpeg";
                        finalMsgType = "image";
                    } else if (mType === "audioMessage") {
                        mime = msg.message.audioMessage.mimetype || "audio/ogg";
                        finalMsgType = "audio";
                    } else if (mType === "documentMessage") {
                        caption = msg.message.documentMessage.caption || "";
                        filename = msg.message.documentMessage.fileName || "document";
                        mime = msg.message.documentMessage.mimetype || "application/octet-stream";
                        finalMsgType = "document";
                    } else {
                        continue;
                    }

                    // Se ha un media, scaricalo localmente
                    if (["imageMessage", "audioMessage", "documentMessage"].includes(mType)) {
                        try {
                            const buffer = await downloadMediaMessage(
                                msg,
                                "buffer",
                                {},
                                { logger }
                            );
                            const mediaId = msg.key.id;
                            const cacheDir = "/opt/genesi-baileys/media-cache";
                            if (!fs.existsSync(cacheDir)) {
                                fs.mkdirSync(cacheDir, { recursive: true });
                            }
                            const filePath = path.join(cacheDir, mediaId);
                            fs.writeFileSync(filePath, buffer);
                            fs.writeFileSync(filePath + ".mime", mime);
                            console.log(`[Baileys] Media 1:1 salvato in cache: ${filePath} (${mime})`);
                        } catch (err) {
                            console.error("[Baileys] Errore salvataggio media 1:1:", err.message);
                        }
                    }

                    // Prepara payload simulato Meta Cloud API (preservando il JID completo con dominio)
                    const senderPhone = remoteJid;

                    const payload = {
                        object: "whatsapp_business_account",
                        entry: [{
                            id: "baileys",
                            changes: [{
                                value: {
                                    messaging_product: "whatsapp",
                                    metadata: {
                                        display_phone_number: "393313650671",
                                        phone_number_id: "1094888310365993"
                                    },
                                    contacts: [{
                                        profile: {
                                            name: msg.pushName || "Utente"
                                        },
                                        wa_id: senderPhone
                                    }],
                                    messages: [{
                                        from: senderPhone,
                                        id: msg.key.id,
                                        timestamp: Math.floor(Date.now() / 1000).toString(),
                                        type: finalMsgType === "audio" ? "audio" : finalMsgType
                                    }]
                                },
                                field: "messages"
                            }]
                        }]
                    };

                    const messageObj = payload.entry[0].changes[0].value.messages[0];
                    if (finalMsgType === "text") {
                        messageObj.text = { body: text.trim() };
                    } else if (finalMsgType === "image") {
                        messageObj.image = { id: msg.key.id, caption: caption.trim(), mime_type: mime };
                    } else if (finalMsgType === "audio") {
                        messageObj.audio = { id: msg.key.id, mime_type: mime };
                        messageObj.voice = { id: msg.key.id, mime_type: mime };
                    } else if (finalMsgType === "document") {
                        messageObj.document = { id: msg.key.id, filename: filename, caption: caption.trim(), mime_type: mime };
                    }

                    // Invia a Python FastAPI locale
                    try {
                        console.log(`[Baileys] Inoltro messaggio 1:1 da ${senderPhone} a Python...`);
                        await axios.post(`${GENESI_URL}/api/whatsapp/webhook`, payload, { timeout: 15000 });
                    } catch (err) {
                        console.error("[Baileys] Errore inoltro messaggio 1:1 a Python:", err.message);
                    }
                    continue;
                }

                // 2. GESTIONE MESSAGGI DI GRUPPO
                const groupId = remoteJid;

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
                let groupName = "WhatsApp Group";
                let participants = null;
                try {
                    const meta = await sock.groupMetadata(groupId);
                    if (meta?.subject) groupName = meta.subject;
                    const p = meta?.participants?.find(x => x.id === senderJid);
                    if (p?.name) senderName = p.name.split(" ")[0];
                    
                    if (meta?.participants) {
                        const myJid = sock.user?.id?.replace(/:.*@/, "@") || "";
                        participants = meta.participants.map(part => {
                            const cleanId = part.id.replace(/:.*@/, "@");
                            let pName = part.name || part.verifiedName || part.notify || null;
                            if (pName) {
                                pName = pName.trim();
                            }
                            return {
                                id: cleanId,
                                name: pName,
                                is_me: cleanId === myJid
                            };
                        });
                    }
                } catch (_) {}

                // Salva nel buffer grezzo locale
                addToBuffer(groupId, senderName, text);
                console.log(`[${senderName}@${groupName}] ${text.slice(0, 60)}`);

                // Filtra: LLM decide se intervenire
                const token = await getToken("group");

                // Fast-path: reply diretta a un messaggio di Genesi → sempre sì
                const contextInfo = msg.message?.extendedTextMessage?.contextInfo || {};
                const quotedParticipant = contextInfo.participant || contextInfo.remoteJid || "";
                const myJid = sock.user?.id?.replace(/:.*@/, "@") || "";
                const isReplyToGenesi = myJid && quotedParticipant && quotedParticipant.replace(/:.*@/, "@") === myJid;

                // Estrai il testo quotato per iniettarlo nel contesto
                let quotedText = "";
                if (isReplyToGenesi) {
                    const qm = contextInfo.quotedMessage;
                    quotedText = (
                        qm?.conversation
                        || qm?.extendedTextMessage?.text
                        || ""
                    ).trim().slice(0, 300);
                    console.log(`[Baileys] Reply diretta a Genesi da ${senderName} in ${groupName} → intervengo`);
                } else {
                    const recentMsgs = getRecentMessages(groupId);
                    if (!await shouldRespond(text, recentMsgs, token)) continue;
                }

                // Se c'è un messaggio quotato di Genesi, anteponi al testo per dare contesto
                const textToSend = (isReplyToGenesi && quotedText)
                    ? `[Stai rispondendo a questo tuo messaggio precedente: "${quotedText}"]\n${text}`
                    : text;

                console.log(`[Baileys] Intervengo in ${groupName} per: "${textToSend.slice(0, 50)}"`);

                await sock.sendPresenceUpdate("composing", groupId);
                const reply = await askGenesiGroup(textToSend, senderName, senderJid, groupId, groupName, participants, token);
                await sock.sendPresenceUpdate("paused", groupId);

                if (reply) {
                    await sock.sendMessage(groupId, { text: reply });
                    lastGenesiReply[groupId] = { text: reply, ts: Date.now() };
                    console.log(`[Genesi → ${senderName} in ${groupName}] ${reply.slice(0, 80)}`);
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
                const { groupId, text, imageUrl, caption, presence, secret } = JSON.parse(body);
                if (SEND_SECRET && secret !== SEND_SECRET) {
                    res.writeHead(403); res.end("forbidden"); return;
                }
                if (!groupId) {
                    res.writeHead(400); res.end("missing groupId"); return;
                }
                if (!_activeSock) {
                    res.writeHead(503); res.end("socket not ready"); return;
                }

                if (presence) {
                    await _activeSock.sendPresenceUpdate(presence, groupId);
                    console.log(`[Baileys/HTTP] Presence updated for ${groupId}: ${presence}`);
                } else if (imageUrl) {
                    await _activeSock.sendMessage(groupId, { image: { url: imageUrl }, caption: caption || text || "" });
                    console.log(`[Baileys/HTTP] Sent image to ${groupId}: ${imageUrl}`);
                } else if (text) {
                    await _activeSock.sendMessage(groupId, { text });
                    console.log(`[Baileys/HTTP] Sent text to ${groupId}: ${text.slice(0, 60)}`);
                } else {
                    res.writeHead(400); res.end("missing text, imageUrl, or presence"); return;
                }

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
