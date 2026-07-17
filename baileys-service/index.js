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

// ── REPLY WHITELIST (fix: gruppi operativi silenziosi) ──────────────────────
// Default: SILENZIO. Env e Admin controls abilitano solo reply visibili, non la
// partecipazione generale.
const WHATSAPP_REPLY_ENABLED_GROUPS = (process.env.WHATSAPP_REPLY_ENABLED_GROUPS || "")
    .split(",").map(s => s.trim()).filter(Boolean);
const ADMIN_GROUP_CONTROLS_PATH = process.env.GENESI_GROUP_CONTROLS_PATH || "/opt/genesi/memory/admin/group_controls.json";
const _lastAdminReplyAllowedLog = {};

function maskJid(jid) {
    if (!jid) return "<none>";
    const at = jid.indexOf("@");
    const local = at >= 0 ? jid.slice(0, at) : jid;
    const dom = at >= 0 ? jid.slice(at) : "";
    if (local.length <= 6) return local.slice(0, 2) + "***" + dom;
    return local.slice(0, 3) + "***" + local.slice(-2) + dom;
}

function isWhatsAppGroupReplyEnabledByAdmin(groupId) {
    if (!groupId) return false;
    try {
        if (!fs.existsSync(ADMIN_GROUP_CONTROLS_PATH)) return false;
        const raw = fs.readFileSync(ADMIN_GROUP_CONTROLS_PATH, "utf8");
        const data = JSON.parse(raw || "{}");
        const info = data?.whatsapp_reply_enabled_groups?.[groupId];
        const enabled = info?.enabled === true;
        if (enabled) {
            const now = Date.now();
            if (!_lastAdminReplyAllowedLog[groupId] || now - _lastAdminReplyAllowedLog[groupId] > 60000) {
                console.log(`[Baileys/GroupControls] Reply visibili abilitate da Admin controls per ${maskJid(groupId)}`);
                _lastAdminReplyAllowedLog[groupId] = now;
            }
        }
        return enabled;
    } catch (err) {
        console.error("[Baileys/GroupControls] Errore lettura controlli Admin:", err.message);
        return false;
    }
}

function whatsappGroupReplyGate(groupId) {
    const env = !!groupId && WHATSAPP_REPLY_ENABLED_GROUPS.includes(groupId);
    const admin = !env && isWhatsAppGroupReplyEnabledByAdmin(groupId);
    return { allowed: env || admin, env, admin };
}

function isWhatsAppGroupReplyEnabled(groupId) {
    return whatsappGroupReplyGate(groupId).allowed;
}
const AUTH_DIR         = "./baileys-auth";

const logger = pino({ level: "silent" }); // silenzia i log interni di Baileys

// ── Buffer messaggi grezzi per gruppo ────────────────────────────────────────
// { groupId: [{name, text, ts}] }
const rawBuffers = {};
const MAX_RAW = 25;

// ── Ultima risposta di Genesi per gruppo (per CONTINUAZIONE) ──────────────────
// { groupId: { text, ts } }
const lastGenesiReply = {};
const GENESI_REPLY_TTL = 10 * 60 * 1000; // 10 minuti
// Finestra di "conversazione attiva": se Genesi ha appena risposto a una persona,
// continua a seguirla anche senza essere nominata di nuovo, per questo intervallo.
const ENGAGED_WINDOW = 150 * 1000; // 2,5 minuti

// ── Cache per i nomi dei contatti visti ───────────────────────────────────────
// { jid/lid: name }
const contactCache = {};

// ── Cache groupMetadata (riduce le chiamate di rete a ogni messaggio) ─────────
// Chiamare groupMetadata su ogni messaggio appesantisce l'event loop e può far
// scattare rate-limit (errori 503). Cache con TTL: una chiamata per gruppo ogni 5 min.
const _groupMetaCache = {};  // { groupId: { meta, ts } }
const GROUP_META_TTL = 5 * 60 * 1000;

async function getGroupMetaCached(sock, groupId) {
    const c = _groupMetaCache[groupId];
    if (c && Date.now() - c.ts < GROUP_META_TTL) return c.meta;
    const meta = await sock.groupMetadata(groupId);
    _groupMetaCache[groupId] = { meta, ts: Date.now() };
    return meta;
}

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

function hasLettersOrNumbers(text) {
    return /[\p{L}\p{N}]/u.test(text || "");
}

function isEmojiOnlyMessage(text) {
    const s = (text || "").trim();
    return !!s && !hasLettersOrNumbers(s);
}

function isClearlyDirectedFollowup(text) {
    const s = (text || "").trim();
    if (!s || isEmojiOnlyMessage(s)) return false;
    if (GENESI_RE.test(s)) return true;
    return (
        /\b(cosa ne pensi|che ne pensi|secondo te|che dici)\b/i.test(s)
        || /\b(puoi|potresti|riesci|continua|spiega|spiegami|dimmi|aiutami|mi aiuti|rispondi|fammi capire)\b/i.test(s)
        // A question/request from the same person immediately after Genesi's
        // reply is conversationally directed even when the name is omitted.
        || /^(chi|quale|quali|quanto|quanti|dove|quando|come|perch[eé]|cosa|che(?: cosa)?)\b/i.test(s)
        || /\b(fammi|mostrami|mandami|inviami|elencami|confronta|cerca)\b/i.test(s)
        || /\?\s*$/.test(s)
    );
}

function isWeatherCityPrompt(text) {
    return /(?:di|per) quale citt[aà].*(?:meteo|previsioni)|(?:meteo|previsioni).*quale citt[aà]/i.test(text || "");
}

function isShortCityAnswer(text) {
    const s = (text || "").trim().replace(/^a\s+/i, "");
    if (!s || s.length > 60) return false;
    if (!/^[\p{L}][\p{L}'’ .-]*$/u.test(s)) return false;
    if (/^(non lo so|boh|nessuna|qui|da me)$/i.test(s)) return false;
    return s.split(/\s+/).length <= 5;
}

function weatherCityFollowupQuery(cityAnswer, previousReply) {
    const city = (cityAnswer || "").trim().replace(/^a\s+/i, "");
    const previous = (previousReply || "").toLowerCase();
    const period = previous.includes("dopodomani") ? "dopodomani"
        : previous.includes("domani") ? "domani"
        : previous.includes("stasera") ? "stasera"
        : previous.includes("oggi") ? "oggi"
        : "";
    return `meteo ${period ? `${period} ` : ""}a ${city}`;
}

function isWeatherResultReply(text) {
    return /^Per (?:oggi|domani|dopodomani|stasera) a .+?, le previsioni indicano|^(?:Si può valutare|Direi che il meteo|Io eviterei).*\ba\b/i.test(text || "");
}

function weatherContextFollowupQuery(followup, previousReply) {
    const previous = (previousReply || "").trim();
    const match = previous.match(/^Per (oggi|domani|dopodomani|stasera) a (.+?), le previsioni indicano/i);
    if (!match) return followup;
    return `meteo ${match[1]} a ${match[2]}. ${followup}`;
}

function isDelicateSupportCandidate(text) {
    const s = (text || "").toLowerCase();
    return /\b(lutto|perdita|morto|morta|mancare|venut[oa] a mancare|malattia|malato|malata|ospedale|dolore|triste|gi[uù]|a pezzi|supporto|ti siamo vicini|vi siamo vicini|condoglianze)\b/i.test(s);
}

async function shouldRespondDecision(text, recentMessages, token, groupId = "", senderName = "", operationalProbe = false) {
    // Fast-path: menzione diretta → sempre sì senza chiamare LLM
    if (!operationalProbe && GENESI_RE.test(text)) return { intervieni: true, motivo: "direct_mention" };

    // LLM decide per tutto il resto (saluti, buone notizie, ecc.)
    try {
        const res = await axios.post(`${GENESI_URL}/api/chat/group/should_respond`, {
            text,
            recent_messages: recentMessages,
            group_id: groupId,
            sender_name: senderName,
            operational_probe: operationalProbe,
        }, {
            headers: { Authorization: `Bearer ${token}` },
            timeout: 8000,
        });
        return {
            intervieni: res.data.intervieni === true,
            motivo: res.data.motivo || "backend_filter",
        };
    } catch (e) {
        // In caso di errore, non intervenire
        return { intervieni: false, motivo: "should_respond_error" };
    }
}

async function shouldRespond(text, recentMessages, token, groupId = "", senderName = "") {
    const decision = await shouldRespondDecision(text, recentMessages, token, groupId, senderName);
    return decision.intervieni === true;
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
async function askGenesiGroup(text, senderName, senderId, groupId, groupName = "WhatsApp Group", participants = null, token = null, mediaId = null, mediaType = null, mediaMime = null, recentMessages = null, replyToId = null, directedFollowup = false, messageId = null, messageTimestamp = null, mediaFilename = null) {
    const maxAttempts = 2;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        if (!token) token = await getToken("group");
        const res = await axios.post(`${GENESI_URL}/api/chat/group`, {
            text,
            sender_name: senderName,
            sender_id:   senderId,
            group_id:    groupId,
            group_name:  groupName,
            participants: participants,
            message_id:   messageId,
            message_timestamp: messageTimestamp,
            media_id:    mediaId,
            media_type:  mediaType,
            media_mime:  mediaMime,
            media_filename: mediaFilename,
            recent_messages: recentMessages,
            reply_to_id: replyToId,   // operational binding (T-A3.3); null se non e' una reply
            directed_followup: directedFollowup,
        }, {
            headers: { Authorization: `Bearer ${token}` },
            timeout: mediaId ? 120000 : 35000,
        });
        if (res.data.status === "operational_error") {
            throw new Error("operational_error");
        }
        return {
            reply: res.data.response || null,
            replyAllowed: res.data.reply_allowed !== false,
            status: res.data.status || "",
            media: Array.isArray(res.data.media) ? res.data.media : [],
        };
      } catch (e) {
        if (e.response?.status === 401) {
            tokens.group = null;
            token = null;
        }
        console.error(`[Genesi] Group API error attempt=${attempt}/${maxAttempts}:`, e.message, e.response?.data);
        if (attempt < maxAttempts) continue;
        return { reply: null, replyAllowed: false, status: "error" };
      }
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
    // Teardown del socket precedente: evita "socket zombie" che continuano a
    // riconnettersi in parallelo e martellano WhatsApp (cause di 428/503/440).
    if (_activeSock) {
        try { _activeSock.ev.removeAllListeners(); } catch (_) {}
        try { _activeSock.end(undefined); } catch (_) {}
        _activeSock = null;
    }
    // Una nuova connessione è in corso: sblocca la guardia così che, se questa
    // fallisce ad aprirsi, un'ulteriore chiusura possa rischedulare il reconnect.
    _reconnecting = false;

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
        keepAliveIntervalMs: 25000,  // ping attivo per non farsi chiudere la connessione idle
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
            if (loggedOut || replaced) {
                console.log(`[Baileys] Sessione non valida (code=${code}: logout o sostituita). Uscita — systemd riavvierà.`);
                process.exit(1);
            } else if (_reconnecting) {
                // Reconnect già pianificato: ignora le chiusure a raffica (anti-accavallamento)
                console.log(`[Baileys] Chiusura (code=${code}) ignorata: reconnect già in corso`);
            } else {
                _reconnecting = true;
                _connectAttempts = Math.min(_connectAttempts + 1, 6);
                const delay = Math.min(5000 * _connectAttempts, 30000);  // backoff 5s→30s
                console.log(`[Baileys] Connessione chiusa (code=${code}). Riconnetto tra ${delay / 1000}s (tentativo ${_connectAttempts})`);
                setTimeout(() => startBaileys().catch(e => console.error("[Baileys] Reconnect error:", e.message)), delay);
            }
        } else if (connection === "open") {
            _connectAttempts = 0;
            _reconnecting = false;
            _lastInbound = Date.now();
            console.log("[Baileys] ✅ Connesso a WhatsApp. In ascolto su gruppi e messaggi diretti...");
        }
    });

    // ── Genesi aggiunta a un gruppo: trigger di presentazione (logica nell'app) ──
    // L'evento di join è la scorciatoia "istantanea"; la GARANZIA robusta è il
    // fallback sul primo messaggio (lato app). Entrambi passano da /api/group/present
    // ed entrambi sono deduplicati sul registry: niente doppie presentazioni.
    sock.ev.on("group-participants.update", async (update) => {
        try {
            _lastInbound = Date.now();  // segnale di vita per il watchdog
            // La membership è cambiata: invalida la cache metadata del gruppo
            delete _groupMetaCache[update.id];

            const myJid = sock.user?.id?.replace(/:.*@/, "@") || "";
            const myLid = sock.user?.lid?.replace(/:.*@/, "@") || "";
            const BOT_IDS = ["393313650671@s.whatsapp.net", "69123891531797@lid"];
            // Baileys 7.x: update.participants può contenere stringhe JID OPPURE
            // oggetti {id, jid, lid}. Estrai sempre l'identificativo corretto.
            const involved = (update.participants || []).map(p => {
                const raw = (typeof p === "string") ? p : (p?.id || p?.jid || p?.lid || "");
                return String(raw).replace(/:.*@/, "@");
            });
            const meInvolved = involved.some(p => p && (p === myJid || (myLid && p === myLid) || BOT_IDS.includes(p)));

            // Genesi RIMOSSA da un gruppo → lo dimentica (così una futura riaggiunta ripresenta)
            if ((update.action === "remove") && meInvolved) {
                try {
                    const token = await getToken("group");
                    await axios.post(`${GENESI_URL}/api/chat/group/forget`, { group_id: update.id },
                        { headers: { Authorization: `Bearer ${token}` }, timeout: 15000 });
                    console.log(`[Baileys] Genesi rimossa dal gruppo ${update.id} — dimenticato`);
                } catch (fe) {
                    if (fe.response?.status === 401) tokens.group = null;
                    console.error("[Baileys] Errore forget gruppo:", fe.message);
                }
                return;
            }

            if (update.action !== "add" || !meInvolved) return;

            console.log(`[Baileys] Genesi aggiunta al gruppo ${update.id} — mi presento`);
            let subject = "questo gruppo";
            let participants = null;
            let adderName = "";
            try {
                const meta = await sock.groupMetadata(update.id);
                subject = meta?.subject || subject;
                participants = (meta?.participants || []).map(p => {
                    const pid = String(p.id || "").replace(/:.*@/, "@");
                    const isMe = pid === myJid || (myLid && pid === myLid) || BOT_IDS.includes(pid);
                    return { id: pid, name: contactCache[pid] || p.name || null, is_me: isMe };
                });
                const adderId = String(update.author || "").replace(/:.*@/, "@");
                adderName = contactCache[adderId] || "";
            } catch (metaErr) {
                console.error("[Baileys] Metadata gruppo non disponibile:", metaErr.message);
            }

            const token = await getToken("group");
            const res = await axios.post(`${GENESI_URL}/api/chat/group/present`, {
                group_id:    update.id,
                group_name:  subject,
                participants: participants,
                adder_name:  adderName,
            }, { headers: { Authorization: `Bearer ${token}` }, timeout: 35000 });

            if (res.data?.presented && res.data?.response) {
                await sock.sendMessage(update.id, { text: res.data.response });
                console.log(`[Baileys] Presentazione inviata in ${subject}`);
            } else {
                console.log(`[Baileys] Gruppo ${subject} già noto — nessuna ri-presentazione`);
            }
        } catch (e) {
            if (e.response?.status === 401) tokens.group = null;
            console.error("[Baileys] Errore presentazione gruppo:", e.message);
        }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
        _lastInbound = Date.now();  // segnale di vita per il watchdog
        if (type !== "notify") return;

        for (const msg of messages) {
            try {
                if (msg.key.fromMe) continue;

                const remoteJid = msg.key.remoteJid;
                if (!remoteJid) continue;

                // Cache del pushName del mittente se disponibile
                const senderJid = msg.key.participant || remoteJid;
                if (msg.pushName && senderJid) {
                    const cleanSender = senderJid.replace(/:.*@/, "@");
                    contactCache[cleanSender] = msg.pushName;
                }

                // 1. GESTIONE MESSAGGI DIRETTI (1:1)
                if (!remoteJid.endsWith("@g.us")) {
                    const mType = Object.keys(msg.message || {})[0];
                    if (!mType) continue;

                    // 1a. Intercetta le risposte alla campagna compleanni (testo, vocale o foto)
                    if (await handleBirthdayReply(msg, remoteJid, msg.pushName || "")) {
                        continue;  // gestito dalla campagna, non inoltrare al flusso normale
                    }

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
                    } else if (mType === "videoMessage") {
                        caption = msg.message.videoMessage.caption || "";
                        mime = msg.message.videoMessage.mimetype || "video/mp4";
                        finalMsgType = "video";
                    } else {
                        continue;
                    }

                    // Se ha un media, scaricalo localmente
                    if (["imageMessage", "audioMessage", "documentMessage", "videoMessage"].includes(mType)) {
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
                    } else if (finalMsgType === "video") {
                        messageObj.video = { id: msg.key.id, caption: caption.trim(), mime_type: mime };
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

                let text = (
                    msg.message?.conversation
                    || msg.message?.extendedTextMessage?.text
                    || msg.message?.imageMessage?.caption
                    || msg.message?.documentMessage?.caption
                    || msg.message?.videoMessage?.caption
                    || ""
                ).trim();
                const originalText = text;
                const messageId = msg.key.id || null;
                const messageTimestamp = msg.messageTimestamp
                    ? new Date(Number(msg.messageTimestamp) * 1000).toISOString()
                    : null;

                const mType = Object.keys(msg.message || {})[0];
                let mediaId = null;
                let mediaMime = null;
                let mediaType = null;
                let mediaFilename = null;

                if (mType === "imageMessage") {
                    mediaId = msg.key.id;
                    mediaMime = msg.message.imageMessage.mimetype || "image/jpeg";
                    mediaType = "image";
                } else if (mType === "documentMessage") {
                    mediaId = msg.key.id;
                    mediaMime = msg.message.documentMessage.mimetype || "application/octet-stream";
                    mediaType = "document";
                    mediaFilename = msg.message.documentMessage.fileName || null;
                } else if (mType === "audioMessage") {
                    mediaId = msg.key.id;
                    mediaMime = msg.message.audioMessage.mimetype || "audio/ogg";
                    mediaType = "audio";
                } else if (mType === "videoMessage") {
                    mediaId = msg.key.id;
                    mediaMime = msg.message.videoMessage.mimetype || "video/mp4";
                    mediaType = "video";
                }

                // Se non c'è testo e non c'è nemmeno media, salta il messaggio
                if (!text && !mediaType) continue;

                // Se c'è media ma non c'è didascalia, imposta testi descrittivi di fallback
                if (!text && mediaType === "image") {
                    text = "Analizza questa immagine.";
                } else if (!text && mediaType === "document") {
                    text = "Analizza questo documento.";
                } else if (!text && mediaType === "audio") {
                    text = "Ascolta questo audio.";
                } else if (!text && mediaType === "video") {
                    text = "Guarda questo video.";
                }

                // Se c'è un file multimediale scaricalo localmente
                if (mediaType && ["image", "document", "audio", "video"].includes(mediaType)) {
                    try {
                        const buffer = await downloadMediaMessage(
                            msg,
                            "buffer",
                            {},
                            { logger }
                        );
                        const cacheDir = "/opt/genesi-baileys/media-cache";
                        if (!fs.existsSync(cacheDir)) {
                            fs.mkdirSync(cacheDir, { recursive: true });
                        }
                        const filePath = path.join(cacheDir, mediaId);
                        fs.writeFileSync(filePath, buffer);
                        fs.writeFileSync(filePath + ".mime", mediaMime);
                        console.log(`[Baileys/Group] Media salvato in cache: ${filePath} (${mediaMime})`);
                    } catch (err) {
                        console.error("[Baileys/Group] Errore salvataggio media gruppo:", err.message);
                    }
                }

                let senderName = (msg.pushName || senderJid).split(" ")[0];
                let groupName = "WhatsApp Group";
                let participants = null;
                try {
                    const meta = await getGroupMetaCached(sock, groupId);
                    if (meta?.subject) groupName = meta.subject;
                    // Diagnostica (solo nome+jid+participant, niente testo/token): aiuta a
                    // mappare un gruppo reale al project_id senza indovinare il JID.
                    console.log(`[Baileys/GroupJID] name="${groupName}" jid=${groupId} participant=${senderJid || "unknown"}`);
                    const cleanSender = senderJid.replace(/:.*@/, "@");
                    const p = meta?.participants?.find(x => x.id === senderJid);
                    let resolvedSenderName = p?.name || contactCache[cleanSender] || msg.pushName;
                    if (resolvedSenderName) senderName = resolvedSenderName.split(" ")[0];
                    
                    if (meta?.participants) {
                        const myJid = sock.user?.id?.replace(/:.*@/, "@") || "";
                        const myLid = sock.user?.lid?.replace(/:.*@/, "@") || "";
                        const BOT_IDS = ["393313650671@s.whatsapp.net", "69123891531797@lid"];
                        participants = meta.participants.map(part => {
                            const cleanId = part.id.replace(/:.*@/, "@");
                            let pName = part.name || part.verifiedName || part.notify || contactCache[cleanId] || null;
                            if (pName) {
                                pName = pName.trim();
                            }
                            return {
                                id: cleanId,
                                name: pName,
                                is_me: cleanId === myJid || (myLid && cleanId === myLid) || BOT_IDS.includes(cleanId)
                            };
                        });
                    }
                } catch (err) {
                    console.error("[Baileys] Error fetching group metadata:", err.message || err);
                }

                // Salva nel buffer grezzo locale
                addToBuffer(groupId, senderName, text);
                console.log(`[${senderName}@${groupName}] ${text.slice(0, 60)}`);

                // ── REPLY GATE: whitelist, default SILENZIO ──────────────────
                // NON blocca la POST/ingest backend: la chiamata a /api/chat/group
                // resta (silent ingest/claim operational). La soppressione avviene
                // SOLO al momento del send (vedi piu' sotto). Gruppi non whitelistati:
                // backend chiamato per ingest, ma nessuna reply visibile, nessun
                // engaged, nessun log "Genesi →". Whitelist => comportamento attuale.
                const replyGate = whatsappGroupReplyGate(groupId);
                const replyAllowed = replyGate.allowed;

                // Filtra: LLM decide se intervenire
                const token = await getToken("group");

                // Fast-path: reply diretta a un messaggio di Genesi → sempre sì.
                // contextInfo robusto: il quoted/reply puo' arrivare da qualsiasi tipo
                // di messaggio (testo o media), non solo extendedTextMessage.
                const _m = msg.message || {};
                const contextInfo = _m.extendedTextMessage?.contextInfo
                    || _m.imageMessage?.contextInfo
                    || _m.audioMessage?.contextInfo
                    || _m.documentMessage?.contextInfo
                    || _m.videoMessage?.contextInfo
                    || {};
                // Operational binding (T-A3.3): id del messaggio quotato/replied →
                // backend Python lo usa come reply_to_id. Assente → null (no-op).
                const replyToId = contextInfo.stanzaId || null;
                const replyToParticipant = contextInfo.participant || null;
                const quotedParticipant = contextInfo.participant || contextInfo.remoteJid || "";
                const myJid = sock.user?.id?.replace(/:.*@/, "@") || "";
                const isReplyToGenesi = myJid && quotedParticipant && quotedParticipant.replace(/:.*@/, "@") === myJid;

                // Estrai il testo quotato per iniettarlo nel contesto
                let quotedText = "";
                const genericMediaWithoutCaption = !!mediaType && !originalText.trim();

                // Continuità: engaged e' solo un segnale debole. Non deve trasformare
                // ogni messaggio successivo in una richiesta a Genesi.
                const _last = lastGenesiReply[groupId];
                const _engaged = replyAllowed && _last && _last.to === senderName
                    && (Date.now() - _last.ts < ENGAGED_WINDOW);
                const _weatherCityAnswer = _engaged && isWeatherCityPrompt(_last.text)
                    && isShortCityAnswer(text);

                let shouldIntervene = false;
                let interventionReason = "";

                if (isReplyToGenesi) {
                    const qm = contextInfo.quotedMessage;
                    quotedText = (
                        qm?.conversation
                        || qm?.extendedTextMessage?.text
                        || ""
                    ).trim().slice(0, 300);
                    console.log(`[Baileys] Reply diretta a Genesi da ${senderName} in ${groupName} → intervengo`);
                    shouldIntervene = true;
                    interventionReason = isWeatherCityPrompt(quotedText) && isShortCityAnswer(text)
                        ? "engaged_weather_city"
                        : "reply_to_genesi";
                } else if (isEmojiOnlyMessage(originalText || text)) {
                    console.log(`WHATSAPP_GROUP_SILENT group=${maskJid(groupId)} name="${groupName}" reason=emoji_only`);
                    continue;
                } else if (genericMediaWithoutCaption) {
                    // Ordinary groups keep the existing silent behaviour. Mapped
                    // operational groups are different: the backend returns the
                    // deterministic "operational_ingest" override so the media
                    // reaches /group for silent ingest even without a caption.
                    const decision = await shouldRespondDecision(
                        text, getRecentMessages(groupId), token, groupId, senderName, true
                    );
                    if (!decision.intervieni || decision.motivo !== "operational_ingest") {
                        console.log(`WHATSAPP_GROUP_SILENT group=${maskJid(groupId)} name="${groupName}" reason=generic_media_without_caption media=${mediaType}`);
                        continue;
                    }
                    shouldIntervene = true;
                    interventionReason = decision.motivo;
                    console.log(`OPERATIONAL_MEDIA_INGEST_FORWARD group=${maskJid(groupId)} media=${mediaType}`);
                } else if (_weatherCityAnswer) {
                    console.log(`ENGAGED_WEATHER_CITY_ALLOWED group=${maskJid(groupId)} name="${groupName}" sender="${senderName}"`);
                    shouldIntervene = true;
                    interventionReason = "engaged_weather_city";
                } else if (_engaged && !isDelicateSupportCandidate(text) && isClearlyDirectedFollowup(text)) {
                    console.log(`ENGAGED_FOLLOWUP_ALLOWED group=${maskJid(groupId)} name="${groupName}" sender="${senderName}"`);
                    shouldIntervene = true;
                    interventionReason = "engaged_direct_followup";
                } else {
                    if (_engaged) {
                        console.log(`ENGAGED_IGNORED_NOT_DIRECTED group=${maskJid(groupId)} name="${groupName}" sender="${senderName}"`);
                    }
                    const recentMsgs = getRecentMessages(groupId);
                    const decision = await shouldRespondDecision(text, recentMsgs, token, groupId, senderName);
                    if (!decision.intervieni) continue;
                    shouldIntervene = true;
                    interventionReason = decision.motivo;
                }

                if (!shouldIntervene) continue;

                // Se c'è un messaggio quotato di Genesi, anteponi al testo per dare contesto
                const routedText = interventionReason === "engaged_weather_city"
                    ? weatherCityFollowupQuery(
                        text,
                        isWeatherCityPrompt(quotedText) ? quotedText : (_last?.text || "")
                    )
                    : (_engaged && isWeatherResultReply(_last?.text) && isClearlyDirectedFollowup(text))
                        ? weatherContextFollowupQuery(text, _last.text)
                    : text;
                const textToSend = (isReplyToGenesi && quotedText)
                    ? `[Stai rispondendo a questo tuo messaggio precedente: "${quotedText}"]\n${routedText}`
                    : routedText;

                console.log(`[Baileys] Intervengo in ${groupName} motivo=${interventionReason} per: "${textToSend.slice(0, 50)}"`);

                // The operational override exists only to carry data to the
                // backend. It must not emit typing presence or a visible reply.
                const operationalIngestOnly = interventionReason === "operational_ingest";
                const directedFollowup = interventionReason === "engaged_direct_followup"
                    || interventionReason === "engaged_weather_city"
                    || interventionReason === "reply_to_genesi";
                const backendResult = await askGenesiGroup(
                    textToSend, senderName, senderJid, groupId, groupName,
                    participants, token, mediaId, mediaType, mediaMime,
                    getRecentMessages(groupId), replyToId, directedFollowup,
                    messageId, messageTimestamp, mediaFilename
                );
                const reply = backendResult.reply;
                const backendReplyAllowed = backendResult.replyAllowed === true;

                if (reply && replyAllowed && backendReplyAllowed && !operationalIngestOnly) {
                    // Presence is emitted only after every reply gate has passed.
                    // Read-only/ingest-only groups never see a typing indicator.
                    await sock.sendPresenceUpdate("composing", groupId);
                    await sock.sendMessage(groupId, { text: reply });
                    // Foto operative allegate alla risposta (es. "fammi vedere le
                    // foto dei problemi"): inviate come immagini reali con
                    // didascalia, lette dalla media-cache locale. Stessi gate
                    // della reply testuale; l'URL resta il fallback.
                    const mediaItems = Array.isArray(backendResult.media) ? backendResult.media.slice(0, 5) : [];
                    for (const m of mediaItems) {
                        const caption = String(m.caption || "").slice(0, 900);
                        const fallback = `${caption}${m.url ? `\n${m.url}` : ""}`.trim();
                        try {
                            const safeId = String(m.media_id || "").replace(/[^A-Za-z0-9._-]/g, "");
                            const mediaPath = safeId ? `./media-cache/${safeId}` : "";
                            if (mediaPath && fs.existsSync(mediaPath)) {
                                await sock.sendMessage(groupId, { image: fs.readFileSync(mediaPath), caption });
                                continue;
                            }
                            if (fallback) {
                                await sock.sendMessage(groupId, { text: fallback });
                            }
                        } catch (mediaErr) {
                            console.error(`[Baileys] Invio foto fallito (${m.media_id}):`, mediaErr.message);
                            if (fallback) {
                                try { await sock.sendMessage(groupId, { text: fallback }); } catch (_) {}
                            }
                        }
                    }
                    await sock.sendPresenceUpdate("paused", groupId);
                    lastGenesiReply[groupId] = { text: reply, ts: Date.now(), to: senderName };
                    console.log(`[Genesi → ${senderName} in ${groupName}] ${reply.slice(0, 80)}${mediaItems.length ? ` (+${mediaItems.length} foto)` : ""}`);
                } else if (reply && (!backendReplyAllowed || operationalIngestOnly)) {
                    // Defence in depth: even an unexpected backend body cannot
                    // escape from an ingest-only request.
                    const suppressReason = operationalIngestOnly ? "operational_ingest_only" : "backend_reply_denied";
                    console.log(`GROUP_REPLY_SUPPRESSED group=${maskJid(groupId)} name="${groupName}" reason=${suppressReason}`);
                } else if (reply && !replyAllowed) {
                    // Gruppo non whitelistato: ingest gia' avvenuto via askGenesiGroup,
                    // la reply backend viene SCARTATA. Nessun sendMessage, nessun
                    // "Genesi →", nessun lastGenesiReply (engaged resta off).
                    console.log(`GROUP_REPLY_SUPPRESSED group=${maskJid(groupId)} name="${groupName}" reason=not_reply_enabled env=${replyGate.env} admin=${replyGate.admin}`);
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
let _reconnecting = false;   // guardia: un reconnect è già pianificato
let _connectAttempts = 0;    // contatore per il backoff esponenziale
let _lastInbound = Date.now();  // timestamp dell'ultimo evento ricevuto (watchdog anti-zombie)

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

// ── Watchdog anti-zombie ──────────────────────────────────────────────────────
// La connessione WhatsApp può "morire in silenzio" (TCP aperto ma stream eventi
// morto, senza evento di close → il reconnect normale non scatta). Questo watchdog
// rileva la situazione e forza la riconnessione: sonda attiva se non arrivano
// eventi da un po', e reconnect se la sonda fallisce o il silenzio è troppo lungo.
const WATCHDOG_IDLE_PROBE = 3 * 60 * 1000;   // 3 min senza eventi → sonda
const WATCHDOG_IDLE_FORCE = 10 * 60 * 1000;  // 10 min senza eventi → reconnect comunque
setInterval(async () => {
    const sock = _activeSock;
    if (!sock || _reconnecting) return;
    const idle = Date.now() - _lastInbound;
    if (idle < WATCHDOG_IDLE_PROBE) return;

    let alive = false;
    try {
        await Promise.race([
            sock.sendPresenceUpdate("available"),
            new Promise((_, rej) => setTimeout(() => rej(new Error("probe timeout")), 10000)),
        ]);
        alive = true;
    } catch (_) { alive = false; }

    if (!alive || idle > WATCHDOG_IDLE_FORCE) {
        if (_reconnecting) return;
        console.log(`[Baileys] Watchdog: connessione stale (idle=${Math.round(idle / 1000)}s, probe=${alive}) → forzo reconnect`);
        _reconnecting = true;  // blocca l'eventuale 'close' dal pianificare un secondo reconnect
        try { sock.end(new Error("watchdog reconnect")); } catch (_) {}
        // Riconnessione garantita anche se 'close' non viene emesso
        setTimeout(() => startBaileys().catch(e => console.error("[Baileys] Watchdog reconnect error:", e.message)), 2000);
    }
}, 60000);

// ── Campagna raccolta compleanni (DM diluiti, anti-ban) ──────────────────────
// Manda un messaggio privato a ogni membro del gruppo bersaglio chiedendo la data
// di nascita, con ampie pause casuali tra un invio e l'altro. Le risposte (in
// qualsiasi formato) vengono interpretate e salvate dall'app. Stato persistente:
// la campagna riprende dopo i riavvii e contatta ogni persona UNA sola volta.
const BIRTHDAY_CAMPAIGN_GROUP = process.env.BIRTHDAY_CAMPAIGN_GROUP || "393298879304-1482062977@g.us";
const BIRTHDAY_CAMPAIGN_FILE  = "/opt/genesi-baileys/birthday-campaign.json";
const BIRTHDAY_BOT_PHONE      = "393313650671";  // numero di Genesi: non auto-contattarsi
const _BDAY_MIN_DELAY = 10 * 60 * 1000;  // 10 min
const _BDAY_MAX_DELAY = 20 * 60 * 1000;  // 20 min

function _bdayLoad() {
    try { return JSON.parse(fs.readFileSync(BIRTHDAY_CAMPAIGN_FILE, "utf8")); }
    catch (_) { return { group: BIRTHDAY_CAMPAIGN_GROUP, contacted: {}, pending: {}, done: {} }; }
}
function _bdaySave(c) {
    try { fs.writeFileSync(BIRTHDAY_CAMPAIGN_FILE, JSON.stringify(c)); }
    catch (e) { console.error("[Bday] errore salvataggio stato:", e.message); }
}
function _phone(jid) { return String(jid || "").replace(/:.*@/, "@"); }

async function sendOneBirthdayDM() {
    if (!BIRTHDAY_CAMPAIGN_GROUP) return;
    const sock = _activeSock;
    if (!sock || _reconnecting) return;
    let meta;
    try { meta = await sock.groupMetadata(BIRTHDAY_CAMPAIGN_GROUP); }
    catch (e) { console.error("[Bday] metadata non disponibile:", e.message); return; }

    const c = _bdayLoad();
    const candidates = (meta.participants || [])
        .map(p => ({
            phone: _phone(p.phoneNumber || ""),
            lid: _phone(p.id || ""),
            name: contactCache[_phone(p.id)] || p.name || "",
        }))
        .filter(x => x.phone.endsWith("@s.whatsapp.net")
            && !x.phone.startsWith(BIRTHDAY_BOT_PHONE)
            && !c.contacted[x.phone]);

    if (!candidates.length) return;  // campagna completata
    const target = candidates[0];
    const nm = target.name ? " " + target.name.split(" ")[0] : "";
    const subject = meta.subject || "famiglia";
    const isRe = c.recontact && c.recontact[target.phone];
    const dm = isRe
        ? (`Ciao${nm}! Scusami davvero 🙏 Poco fa ti avevo scritto per chiederti la tua data ` +
           `di nascita, ma per un mio problema tecnico la tua risposta è andata persa e ti ho ` +
           `risposto a sproposito, senza senso. Ora ho sistemato tutto. Mi riscrivi per favore ` +
           `la tua data di nascita? Va benissimo in qualsiasi forma (es. "12 marzo" oppure ` +
           `"12 marzo 1985"). Grazie e scusa per il disguido! 🎂`)
        : (`Ciao${nm}! Sono Genesi, l'assistente della famiglia nel gruppo "${subject}" 😊\n` +
           `Mi piacerebbe ricordare il compleanno di tutti per fare gli auguri il giorno giusto. ` +
           `Mi scrivi la tua data di nascita? Va benissimo in qualsiasi forma, anche solo giorno e ` +
           `mese (es. "12 marzo" oppure "12 marzo 1985"). Se preferisci non dirmela, ignora pure ` +
           `questo messaggio. Grazie! 🎂`);
    try {
        await sock.sendMessage(target.phone, { text: dm });
        c.contacted[target.phone] = Date.now();
        c.pending[target.phone] = { name: target.name, asks: 1, ts: Date.now() };
        if (isRe && c.recontact) delete c.recontact[target.phone];  // scuse inviate una volta sola
        // Mappa LID→numero: le risposte 1:1 arrivano con remoteJid in formato @lid
        c.lidmap = c.lidmap || {};
        if (target.lid && target.lid.endsWith("@lid")) c.lidmap[target.lid] = target.phone;
        _bdaySave(c);
        console.log(`[Bday] DM ${isRe ? "(scuse) " : ""}inviato a ${target.name || target.phone} (rimasti ${candidates.length - 1})`);
    } catch (e) {
        console.error(`[Bday] invio fallito a ${target.phone}:`, e.message);
        c.contacted[target.phone] = Date.now();  // non ritentare all'infinito
        _bdaySave(c);
    }
}

async function handleBirthdayReply(msg, senderJid, name) {
    const raw = _phone(senderJid);
    const c = _bdayLoad();
    // Le risposte 1:1 arrivano con JID @lid: risolvi al numero tramite la mappa
    let phone = raw;
    if (!c.pending[phone] && c.lidmap && c.lidmap[raw]) phone = c.lidmap[raw];
    // Fallback: se è un @lid sconosciuto, risolvi il numero dai metadati del gruppo
    if (!c.pending[phone] && raw.endsWith("@lid") && _activeSock && BIRTHDAY_CAMPAIGN_GROUP) {
        try {
            const meta = await _activeSock.groupMetadata(BIRTHDAY_CAMPAIGN_GROUP);
            const part = (meta.participants || []).find(p => _phone(p.id) === raw);
            const ph = part && _phone(part.phoneNumber || "");
            if (ph && c.pending[ph]) {
                c.lidmap = c.lidmap || {}; c.lidmap[raw] = ph; _bdaySave(c);
                phone = ph;
            }
        } catch (_) {}
    }
    if (!c.pending[phone]) return false;  // non è una risposta attesa

    const mType = Object.keys(msg.message || {})[0];
    let text = (msg.message?.conversation || msg.message?.extendedTextMessage?.text || "").trim();
    let mediaId = null, mediaType = null, mediaMime = null;
    // Se rispondono con un VOCALE o una FOTO, scarica il media e fallo
    // trascrivere/OCR dall'app per estrarne la data.
    if (!text && (mType === "audioMessage" || mType === "imageMessage")) {
        try {
            const buffer = await downloadMediaMessage(msg, "buffer", {}, { logger });
            mediaId = msg.key.id;
            const cacheDir = "/opt/genesi-baileys/media-cache";
            if (!fs.existsSync(cacheDir)) fs.mkdirSync(cacheDir, { recursive: true });
            mediaType = (mType === "audioMessage") ? "audio" : "image";
            mediaMime = (mType === "audioMessage")
                ? (msg.message.audioMessage.mimetype || "audio/ogg")
                : (msg.message.imageMessage.mimetype || "image/jpeg");
            fs.writeFileSync(path.join(cacheDir, mediaId), buffer);
            fs.writeFileSync(path.join(cacheDir, mediaId) + ".mime", mediaMime);
        } catch (e) {
            console.error("[Bday] download media risposta fallito:", e.message);
            return false;
        }
    }
    if (!text && !mediaId) return false;  // niente da interpretare

    try {
        const token = await getToken("group");
        const res = await axios.post(`${GENESI_URL}/api/chat/group/birthday-dm`,
            { wa_id: phone, name: name || c.pending[phone].name || "", text,
              media_id: mediaId, media_type: mediaType, media_mime: mediaMime },
            { headers: { Authorization: `Bearer ${token}` }, timeout: 35000 });
        const reply = res.data?.reply || "";
        if (res.data?.found) {
            if (reply) await _activeSock.sendMessage(senderJid, { text: reply });
            delete c.pending[phone]; c.done[phone] = Date.now(); _bdaySave(c);
            console.log(`[Bday] compleanno salvato per ${name || phone}: ${res.data.date}`);
            return true;
        }
        // Data non capita: insisti gentilmente al massimo 2 volte, poi lascia perdere
        c.pending[phone].asks = (c.pending[phone].asks || 1) + 1;
        if (c.pending[phone].asks > 2) {
            delete c.pending[phone]; c.done[phone] = Date.now(); _bdaySave(c);
            return false;  // basta insistere: passa al flusso normale
        }
        _bdaySave(c);
        if (reply) await _activeSock.sendMessage(senderJid, { text: reply });
        return true;
    } catch (e) {
        if (e.response?.status === 401) tokens.group = null;
        console.error("[Bday] errore parse risposta:", e.message);
        return false;
    }
}

function scheduleBirthdayCampaign() {
    if (!BIRTHDAY_CAMPAIGN_GROUP) return;
    const delay = _BDAY_MIN_DELAY + Math.random() * (_BDAY_MAX_DELAY - _BDAY_MIN_DELAY);
    setTimeout(async () => {
        try { await sendOneBirthdayDM(); } catch (e) { console.error("[Bday] loop err:", e.message); }
        scheduleBirthdayCampaign();
    }, delay);
}

// ── Avvio ─────────────────────────────────────────────────────────────────────
console.log("[Genesi Baileys] Avvio servizio WhatsApp gruppi...");
startHttpServer();
// Primo DM dopo ~90s (verifica rapida), poi diluito 10-20 min tra un invio e l'altro
if (BIRTHDAY_CAMPAIGN_GROUP) {
    setTimeout(() => { sendOneBirthdayDM().catch(e => console.error("[Bday] first err:", e.message)); }, 90000);
    scheduleBirthdayCampaign();
}
startBaileys().catch(e => {
    console.error("[Baileys] Errore fatale:", e);
    process.exit(1);
});
