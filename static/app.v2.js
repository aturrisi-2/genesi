// ===============================
// CONVERSATION STATE
// ===============================
let currentConvId = null;

// ===============================
// APPLICATION MODE STATE
// ===============================
let currentMode = "chat"; // "chat" | "coding"

// ===============================
// TTS TIMING STATE
// ===============================
window.lastTTSStart = 0;

// ===============================
// AUDIO PRIMING
// ===============================
let _primedAudio = null;

// ===============================
// STATES
// ===============================
const STATES = { IDLE: 'idle', THINKING: 'thinking', RECORDING: 'recording' };

// ===============================
// DEV_MODE for local development
// ===============================
const DEV_MODE =
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1";

// ===============================
// DOM
// ===============================
const app = document.getElementById('genesi-app');
const dialogue = document.getElementById('dialogue');
const textInput = document.getElementById('text-input');
const sendButton = document.getElementById('send-button');
const micButton = document.getElementById('mic-button');
const plusButton = document.getElementById('plus-button');
const chatForm = document.getElementById('chat-form');

// Camera state
let cameraStream = null;
let cameraVideo = null;

// User bar DOM (auth enabled)
const userBar = document.getElementById('user-bar');
const userGreeting = document.getElementById('user-greeting');
const adminLink = document.getElementById('admin-link');
const logoutBtn = document.getElementById('logout-btn');

// ===============================
// AUTH STATE — JWT-based
// ===============================
function getAuthToken() {
  return localStorage.getItem('genesi_access_token');
}

function isLoggedIn() {
  const token = getAuthToken();
  if (!token) return false;
  const payload = getTokenPayload();
  if (!payload) return false;
  // Check expiry
  if (payload.exp && payload.exp * 1000 < Date.now()) return false;
  return true;
}

function getTokenPayload() {
  const token = getAuthToken();
  if (!token) return null;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    return JSON.parse(atob(parts[1]));
  } catch (e) {
    return null;
  }
}

function isAdmin() {
  return localStorage.getItem('genesi_is_admin') === 'true';
}

async function tryRefreshToken() {
  const refresh = localStorage.getItem('genesi_refresh_token');
  if (!refresh) return false;
  try {
    const res = await fetch('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    localStorage.setItem('genesi_access_token', data.access_token);
    return true;
  } catch (e) {
    return false;
  }
}

function doLogout() {
  const token = getAuthToken();
  if (token) {
    fetch('/auth/logout', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token },
    }).catch(() => { });
  }
  localStorage.removeItem('genesi_access_token');
  localStorage.removeItem('genesi_refresh_token');
  localStorage.removeItem('genesi_user_id');
  localStorage.removeItem('genesi_is_admin');
  window.location.href = '/login';
}

function authHeaders() {
  const token = getAuthToken();
  const h = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = 'Bearer ' + token;
  return h;
}

function authHeadersRaw() {
  const token = getAuthToken();
  const h = {};
  if (token) h['Authorization'] = 'Bearer ' + token;
  return h;
}

function applyAuthState() {
  if (!isLoggedIn() && !DEV_MODE) {
    // Not logged in — redirect to login (unless in DEV_MODE)
    window.location.href = '/login';
    return;
  }

  userBar.style.display = 'flex';
  document.getElementById('presence').style.display = '';
  dialogue.style.display = '';
  document.getElementById('status').style.display = '';
  chatForm.style.display = '';

  // Greeting from token payload
  const payload = getTokenPayload();


  // Admin link
  adminLink.style.display = isAdmin() ? '' : 'none';
  logoutBtn.style.display = '';
}

// Logout handler
if (logoutBtn) {
  logoutBtn.addEventListener('click', (e) => {
    e.preventDefault();
    doLogout();
  });
}

// ===============================
// VIEWPORT HEIGHT — iOS KEYBOARD FIX
// ===============================
// iOS Safari: 100vh doesn't shrink when keyboard opens.
// We track visualViewport.height and set --app-height.
// The CSS flex layout then naturally shrinks #dialogue.

function updateAppHeight() {
  if (window.visualViewport) {
    const h = window.visualViewport.height;
    document.documentElement.style.setProperty('--app-height', h + 'px');
    document.getElementById('genesi-app').style.transform = '';
  } else {
    document.documentElement.style.setProperty('--app-height', window.innerHeight + 'px');
  }
}

updateAppHeight();

if (window.visualViewport) {
  const _onViewport = () => {
    updateAppHeight();
    window.scrollTo(0, 0);
    requestAnimationFrame(() => scrollToBottom());
  };
  window.visualViewport.addEventListener('resize', _onViewport);
  window.visualViewport.addEventListener('scroll', _onViewport);
} else {
  window.addEventListener('resize', updateAppHeight);
}

// ===============================
// SMART AUTOSCROLL
// ===============================
// Only auto-scroll if user is near the bottom.
// If user scrolled up to read history, don't force them down.

function isNearBottom(threshold = 80) {
  const gap = dialogue.scrollHeight - dialogue.scrollTop - dialogue.clientHeight;
  return gap < threshold;
}

function scrollToBottom() {
  dialogue.scrollTop = dialogue.scrollHeight;
}

function scrollToBottomSmooth() {
  // Use instant scroll — smooth causes delays on keyboard open
  dialogue.scrollTop = dialogue.scrollHeight;
  // Fallback for iOS rendering delay
  requestAnimationFrame(() => {
    dialogue.scrollTop = dialogue.scrollHeight;
  });
}

// ===============================
// TTS STATE
// ===============================
let _ttsCtx = null;
let _ttsSource = null;
let _isPlayingChunk = false;
let _wasPlayingChunk = false;
let ttsEnabled = true;
let _ttsAborted = false;
let activeTTSSources = [];           // ALL active Audio elements
let currentTTSAbortController = null; // AbortController for in-flight fetches
let ttsGenerationId = 0;              // Monotonic ID — stale async skips playback

// ===============================
// TTS TEXT NORMALIZATION
// ===============================
function normalizeTextForTTS(text) {
  if (!text || typeof text !== 'string') return text;

  const original = text;

  // Converta "..." e "...." in "."
  text = text.replace(/\.{3,4}/g, '.');

  // Garantisce uno spazio dopo il punto se manca e c'è un carattere
  text = text.replace(/\.([a-zA-ZàèéìòùÀÈÉÌÒÙ])/g, '. $1');

  // Rimuove chunk contenenti solo punteggiatura
  text = text.replace(/^[.,;:!?]+$/, '');

  // Rimuove spazi multipli
  text = text.replace(/\s+/g, ' ').trim();

  // Log debug solo se necessario
  if (original !== text) {
    console.log('[TTS_NORMALIZE] before:', JSON.stringify(original));
    console.log('[TTS_NORMALIZE] after:', JSON.stringify(text));
  }

  return text;
}

function _getTTSCtx() {
  // USA ESCLUSIVAMENTE il AudioContext globale creato alla prima gesture
  if (!window.audioContext) {
    console.error('[TTS] Global AudioContext not available - audio not unlocked');
    return null;
  }

  console.log('[TTS] Using global AudioContext, state=' + window.audioContext.state);
  return window.audioContext;
}

// iOS Safari: AudioContext must be created+resumed during a synchronous
// user gesture (tap/click). Call this at the START of any gesture handler,
// BEFORE any await, so the gesture is still "active" for iOS.
function _warmTTSCtx() {
  const ctx = _getTTSCtx();
  if (!ctx) {
    console.warn('[TTS] Cannot warm - no global AudioContext');
    return;
  }

  console.log('[TTS] WarmTTSCtx - state=' + ctx.state);

  // Resume per qualsiasi stato non-running
  if (ctx.state === 'suspended' || ctx.state === 'interrupted') {
    ctx.resume().then(() => {
      console.log('[TTS] ctx resumed successfully, state=' + ctx.state);
    }).catch(err => {
      console.error('[TTS] ctx resume failed:', err);
    });
  } else if (ctx.state === 'running') {
    console.log('[TTS] ctx already running');
  }
}

function primeAudio() {
  if (!_primedAudio) {
    _primedAudio = new Audio();
    _primedAudio.muted = true;
    _primedAudio.play().catch(() => { });
    console.log('[AUDIO] primed');
  }
}

function stopAudio() {
  if (_ttsSource) {
    try { _ttsSource.stop(); } catch (e) { }
    _ttsSource = null;
  }
}

// ===============================
// BARGE-IN — immediate TTS interruption on user input
// ===============================
function stopAllTTS() {
  console.log('[TTS_FORCE_STOP] sources=' + activeTTSSources.length + ' playing=' + _isPlayingChunk);

  // 1. Abort all in-flight TTS fetch requests
  if (currentTTSAbortController) {
    try { currentTTSAbortController.abort(); } catch (e) { }
    currentTTSAbortController = null;
  }

  // 2. Stop ALL tracked audio sources
  activeTTSSources.forEach(src => {
    try {
      if (typeof src.stop === 'function') src.stop();
      if (typeof src.pause === 'function') src.pause();
      src.currentTime = 0;
      src.src = '';
    } catch (e) { }
  });
  activeTTSSources = [];

  // 3. Stop legacy _ttsSource if somehow not in array
  if (_ttsSource) {
    try {
      _ttsSource.pause();
      _ttsSource.currentTime = 0;
      _ttsSource.src = '';
    } catch (e) { }
    _ttsSource = null;
  }

  // 4. Abort chunk queue + reset flags
  _ttsAborted = true;
  _isPlayingChunk = false;
  _wasPlayingChunk = false;

  console.log('[TTS_INTERRUPTED_BY_USER]');
}

function _interruptTTS(reason) {
  if (_ttsSource || _isPlayingChunk || activeTTSSources.length > 0) {
    console.log('[BARGE-IN] interrupt reason=' + reason);
    stopAllTTS();
  }
}

// ===============================
// SEGMENTAZIONE INTELLIGENTE TTS
// ===============================
function _splitTextForTTS(text, tts_mode = 'normal') {
  // Dividi il testo in chunk di 1-2 frasi per punteggiatura forte
  const sentences = text.split(/([.!?]+)\s*/);
  const chunks = [];
  let currentChunk = '';

  // Per psychological: max 1 frase per chunk, più brevi
  const maxChunkSize = tts_mode === 'psychological' ? 150 : 200;

  for (let i = 0; i < sentences.length; i += 2) {
    const sentence = sentences[i] + (sentences[i + 1] || '');
    if (!sentence.trim()) continue;

    // Per psychological: forza 1 frase per chunk
    if (tts_mode === 'psychological') {
      if (currentChunk.trim()) {
        chunks.push(currentChunk.trim());
      }
      currentChunk = sentence;
    } else {
      // Per normal/informative: 1-2 frasi per chunk
      if (currentChunk.length + sentence.length < maxChunkSize) {
        currentChunk += sentence;
      } else {
        if (currentChunk.trim()) {
          chunks.push(currentChunk.trim());
        }
        currentChunk = sentence;
      }
    }
  }

  // Aggiungi l'ultimo chunk
  if (currentChunk.trim()) {
    chunks.push(currentChunk.trim());
  }

  return chunks;
}

async function playTTSSegmented(text, tts_mode = 'normal') {
  console.log('[TTS_FLOW] step=1 segmented_start len=' + text.length + ' mode=' + tts_mode);

  // Reset abort flag at start of new segmented playback
  _ttsAborted = false;

  if (!text || text.trim().length === 0) {
    console.log('[TTS_ABORT] reason=segmented_empty_text text_len=' + (text ? text.length : 0));
    console.log('[TTS_FLOW] step=2 segmented_skip_empty_text');
    return;
  }

  const chunks = _splitTextForTTS(text, tts_mode);
  console.log('[TTS_FLOW] step=3 segmented_chunks_created count=' + chunks.length);
  console.log('[TTS] CHUNKING: total_len=' + text.length + ' mode=' + tts_mode);
  console.log('[TTS] CHUNKS:', chunks.map((c, i) => `${i + 1}: "${c.substring(0, 50)}..." (${c.length}char)`));

  // Array per le promise dei blob pre-caricati
  const chunkFetchPromises = new Array(chunks.length);

  // Capture generationId at start of this segmented session
  const myGenId = ttsGenerationId;

  // Funzione per fetch di un chunk
  const fetchChunk = async (index) => {
    if (_ttsAborted || ttsGenerationId !== myGenId) return null;
    const chunk = chunks[index];
    const normalizedChunk = normalizeTextForTTS(chunk);
    console.log('[TTS_PREFETCH] index=' + (index + 1) + '/total=' + chunks.length + ' len=' + chunk.length + ' genId=' + myGenId);

    try {
      const headers = authHeaders();
      console.log('[TTS_PREFETCH] AUTH HEADERS: ' + JSON.stringify(headers));
      const response = await fetch('/api/tts/', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ text: normalizedChunk }),
        signal: currentTTSAbortController ? currentTTSAbortController.signal : undefined
      });

      if (!response.ok) {
        throw new Error('TTS fetch failed: ' + response.status);
      }

      const blob = await response.blob();
      console.log('[TTS_PREFETCH_DONE] index=' + (index + 1) + ' size=' + blob.size);
      return blob;
    } catch (e) {
      if (e.name === 'AbortError') {
        console.log('[TTS_PREFETCH_ABORTED] index=' + (index + 1));
      } else {
        console.error('[TTS_PREFETCH_ERROR] index=' + (index + 1), e);
      }
      return null;
    }
  };

  // Pre-fetch del primo chunk
  chunkFetchPromises[0] = fetchChunk(0);

  // Ciclo principale con prefetch
  for (let i = 0; i < chunks.length; i++) {
    // CHECK ABORT FLAG + GENERATION ID before every chunk
    if (_ttsAborted || ttsGenerationId !== myGenId) {
      console.log('[TTS_FLOW] step=ABORTED chunk_' + (i + 1) + '/' + chunks.length + ' aborted=' + _ttsAborted + ' genStale=' + (ttsGenerationId !== myGenId));
      break;
    }

    console.log('[TTS_FLOW] step=4.' + (i + 1) + ' processing_chunk_' + (i + 1) + '/' + chunks.length);

    // Avvia prefetch del chunk successivo mentre questo suona
    if (i < chunks.length - 1 && !chunkFetchPromises[i + 1]) {
      chunkFetchPromises[i + 1] = fetchChunk(i + 1);
    }

    const chunk = chunks[i];
    console.log('[TTS_CHUNK] index=' + (i + 1) + '/total=' + chunks.length + ' len=' + chunk.length);
    console.log('[TTS] PLAYING chunk', i + 1, '/', chunks.length, 'len=' + chunk.length);
    console.log('[TTS] CHUNK TEXT:', chunk);

    try {
      console.log('[TTS_FLOW] step=6.' + (i + 1) + ' calling_playTTSChunk');

      // Misura tempo tra chunk
      const chunkStartTime = performance.now();

      // ATTENDI esplicitamente che il fetch del chunk corrente sia completato prima del playback
      const blob = await chunkFetchPromises[i];

      await _playTTSChunkWithBlob(chunk, blob, i);

      const chunkEndTime = performance.now();
      const chunkDuration = chunkEndTime - chunkStartTime;

      console.log('[TTS_FLOW] step=7.' + (i + 1) + ' playTTSChunk_completed duration=' + chunkDuration.toFixed(2) + 'ms');

      // PAUSA LUNGA per psychological tra chunk — but check abort
      if (tts_mode === 'psychological' && i < chunks.length - 1 && !_ttsAborted && ttsGenerationId === myGenId) {
        console.log('[TTS_FLOW] step=8.' + (i + 1) + ' psychological_pause');
        await new Promise(resolve => setTimeout(resolve, 800)); // 800ms pause
        console.log('[TTS_FLOW] step=9.' + (i + 1) + ' psychological_pause_completed');
      }
    } catch (e) {
      console.log('[TTS_FLOW] step=ERROR.' + (i + 1) + ' chunk_error:', e);
      break;
    }
  }

  console.log('[TTS_FLOW] step=11 segmented_finished aborted=' + _ttsAborted);
  console.log('[TTS_DONE] total_chunks=' + chunks.length);
  // Resetta stato solo alla fine di tutti i chunk
  _wasPlayingChunk = false;
}

async function _playTTSChunkWithBlob(text, blob, chunkIndex) {
  console.log('[TTS_FLOW] step=1 chunk_start len=' + text.length);

  if (!text || text.trim().length === 0) {
    console.log('[TTS_ABORT] reason=chunk_empty_text text_len=' + (text ? text.length : 0));
    console.log('[TTS_FLOW] step=2 chunk_skip_empty_text');
    return;
  }

  if (!blob || blob.size === 0) {
    console.log('[TTS_EMPTY_BLOB] prefetched blob is empty or null');
    console.log('[TTS_FLOW] step=3 empty_prefetched_blob');
    return;
  }

  console.log('[TTS] _playTTSChunkWithBlob len=' + text.length + ' blob_size=' + blob.size);
  console.log('[TTS] TEXT:', text);

  // VERIFICA AUDIO UNLOCK PRIMA DI PROCEDERE
  if (!window.audioUnlocked) {
    console.warn('[TTS] Audio not unlocked - skipping TTS playback (blob)');
    console.log('[TTS_ABORT] reason=audio_not_unlocked_blob');
    return;
  }

  // VERIFICA E RIPRISTINA AudioContext PRIMA della riproduzione
  const ttsCtx = _getTTSCtx();
  if (!ttsCtx) {
    console.warn('[TTS] No AudioContext available - skipping TTS (blob)');
    console.log('[TTS_ABORT] reason=no_audiocontext_blob');
    return;
  }

  console.log('[TTS] AudioContext check (blob) - state=' + ttsCtx.state);

  if (ttsCtx.state === 'suspended' || ttsCtx.state === 'interrupted') {
    console.log('[TTS] Resuming AudioContext before blob playback');
    await ttsCtx.resume();
    console.log('[TTS] AudioContext resumed (blob) - state=' + ttsCtx.state);
  }

  try {
    console.log('[TTS_FLOW] step=7 calling_playTTSAudio');

    // USA NUOVA FUNZIONE playTTSAudio con decodeAudioData
    await playTTSAudio(blob);

    // ATTENDI CHE IL CHUNK FINISCA PRIMA DI PASSARE AL SUCCESSIVO
    console.log('[TTS_FLOW] step=8 waiting_for_chunk_end');
    await new Promise(resolve => {
      const checkEnded = () => {
        if (!_isPlayingChunk) {
          console.log('[TTS_FLOW] step=9 audio_ended');
          console.log('[TTS] CHUNK ENDED - AudioBufferSourceNode completato');
          resolve();
        } else {
          setTimeout(checkEnded, 100); // Controlla ogni 100ms
        }
      };
      checkEnded();
    });

  } catch (e) {
    console.log('[TTS_FLOW] step=ERROR chunk_exception');
    console.error('[TTS] _playTTSChunkWithBlob error:', e);
    _ttsSource = null;
  }
}

async function _playTTSChunk(text) {
  console.log('[TTS_FLOW] step=1 chunk_start len=' + text.length);

  if (!text || text.trim().length === 0) {
    console.log('[TTS_ABORT] reason=chunk_empty_text text_len=' + (text ? text.length : 0));
    console.log('[TTS_FLOW] step=2 chunk_skip_empty_text');
    return;
  }

  console.log('[TTS] _playTTSChunk len=' + text.length);
  console.log('[TTS] TEXT:', text);

  // VERIFICA AUDIO UNLOCK PRIMA DI PROCEDERE
  if (!window.audioUnlocked) {
    console.warn('[TTS] Audio not unlocked - skipping TTS playback');
    console.log('[TTS_ABORT] reason=audio_not_unlocked');
    return;
  }

  // VERIFICA E RIPRISTINA AudioContext PRIMA della riproduzione
  const ttsCtx = _getTTSCtx();
  if (!ttsCtx) {
    console.warn('[TTS] No AudioContext available - skipping TTS');
    console.log('[TTS_ABORT] reason=no_audiocontext');
    return;
  }

  console.log('[TTS] AudioContext check - state=' + ttsCtx.state);

  if (ttsCtx.state === 'suspended' || ttsCtx.state === 'interrupted') {
    console.log('[TTS] Resuming AudioContext before playback');
    await ttsCtx.resume();
    console.log('[TTS] AudioContext resumed - state=' + ttsCtx.state);
  }

  try {
    console.log('[TTS_FLOW] step=3 calling_fetch_tts');
    console.log('[TTS] FETCH: calling /tts...');
    console.log('[TTS] richiesta inviata - text_len=' + text.length);

    const normalizedText = normalizeTextForTTS(text);
    const headers = authHeaders();
    console.log('[TTS] AUTH HEADERS: ' + JSON.stringify(headers));
    const response = await fetch('/api/tts/', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ text: normalizedText }),
      signal: currentTTSAbortController ? currentTTSAbortController.signal : undefined
    });

    console.log('[TTS_FLOW] step=4 fetch_response_received');
    console.log('[TTS] RESPONSE: status=' + response.status + ' headers=' + JSON.stringify(Object.fromEntries(response.headers)));

    if (!response.ok) {
      console.log('[TTS_ABORT] reason=fetch_failed status=' + response.status);
      console.log('[TTS_FLOW] step=5 fetch_failed');
      return;
    }

    console.log('[TTS_FLOW] step=5 reading_blob');
    const blob = await response.blob();
    console.log('[TTS_FLOW] step=6 blob_received');
    console.log('[TTS] BLOB: size=' + blob.size + ' type=' + blob.type);
    console.log('[TTS] TTS blob ricevuto - size=' + blob.size + ' type=' + blob.type);

    if (!blob || blob.size === 0) {
      console.log('[TTS_EMPTY_BLOB] fetched blob is empty, size=' + (blob ? blob.size : 'null'));
      console.log('[TTS_FLOW] step=7 empty_blob');
      return;
    }

    console.log('[TTS_FLOW] step=7 calling_playTTSAudio');

    // USA NUOVA FUNZIONE playTTSAudio con decodeAudioData
    await playTTSAudio(blob);

    // ATTENDI CHE IL CHUNK FINISCA PRIMA DI PASSARE AL SUCCESSIVO
    console.log('[TTS_FLOW] step=8 waiting_for_chunk_end');
    await new Promise(resolve => {
      const checkEnded = () => {
        if (!_isPlayingChunk) {
          console.log('[TTS_FLOW] step=9 audio_ended');
          console.log('[TTS] CHUNK ENDED - AudioBufferSourceNode completato');
          resolve();
        } else {
          setTimeout(checkEnded, 100); // Controlla ogni 100ms
        }
      };
      checkEnded();
    });

  } catch (e) {
    console.log('[TTS_FLOW] step=ERROR chunk_exception');
    console.error('[TTS] _playTTSChunk error:', e);
    _ttsSource = null;
  }
}

async function playTTS(text, tts_mode = 'normal') {
  console.log('[TTS_FLOW] step=1 playTTS_start len=' + text.length + ' mode=' + tts_mode);
  console.log("STEP_2_TTS_REQUESTED");

  if (_ttsAborted) {
    console.log('[TTS_ABORT] reason=aborted_before_start');
    return;
  }

  if (!text || text.trim().length === 0) {
    console.log('[TTS_ABORT] reason=empty_text text_len=' + (text ? text.length : 0));
    console.log('[TTS_FLOW] step=2 playTTS_skip_empty_text');
    return;
  }

  console.log('[TTS_FLOW] step=3 playTTS_checking_segmentation');

  // FORZA segmentazione per testi informativi, psychological o lunghi
  console.log('[TTS_FLOW] step=3.5 checking_conditions tts_mode=' + tts_mode + ' len=' + text.length);

  return new Promise((resolve, reject) => {
    const executeTTS = async () => {
      try {
        if (tts_mode === 'informative' || tts_mode === 'psychological' || text.length > 500) {
          console.log('[TTS_FLOW] step=4 playTTS_calling_segmented');
          console.log('[TTS_DEBUG] _ttsSource_before_segmented=' + _ttsSource);
          await playTTSSegmented(text, tts_mode);
          console.log('[TTS_FLOW] step=5 playTTS_segmented_completed');
        } else {
          console.log('[TTS_FLOW] step=4 playTTS_calling_single_chunk');
          // Testi brevi normali: playback normale
          await _playTTSChunk(text);
          console.log('[TTS_FLOW] step=5 playTTS_single_chunk_completed');
        }

        console.log('[TTS_FLOW] step=6 playTTS_finished');
        console.log("STEP_3_TTS_READY");
        resolve();

      } catch (error) {
        console.error('[TTS] Error in playTTS:', error);
        resolve(); // NON bloccare UI anche in caso di errore
      }
    };

    executeTTS();
  });
}

// ===============================
// USER IDENTITY — from JWT only
// ===============================
function getUserId() {
  // user_id from JWT payload — NEVER generated client-side
  const payload = getTokenPayload();
  return payload ? payload.sub : null;
}

let userIdentity = {};

// Polling notifiche reminder — avvia dopo login
function startNotificationPolling() {
  const authToken = getAuthToken();
  if (!authToken) {
    console.log("NOTIFICATION_POLLING_SKIPPED_NO_TOKEN");
    return;
  }

  const notificationInterval = setInterval(async () => {
    try {
      const response = await fetch('/api/notifications/pending', {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });

      if (response.status === 401) {
        console.warn("NOTIFICATION_POLLING_STOPPED_401");
        clearInterval(notificationInterval);
        return;
      }

      if (!response.ok) return;

      const data = await response.json();
      if (data.count > 0) {
        for (const notif of data.notifications) {
          // Mostra solo se non già mostrata
          const key = `notif_shown_${notif.id}`;
          if (sessionStorage.getItem(key)) continue;
          sessionStorage.setItem(key, '1');

          // Inserisci in chat come messaggio assistente
          addMessage(`🔔 Promemoria: ${notif.text}`, 'genesi');

          // Marca come letta chiamando endpoint ack
          await fetch(`/api/notifications/ack/${notif.id}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` }
          });
        }
      }
    } catch (err) {
      console.error("NOTIFICATION_POLLING_ERROR", err);
    }
  }, 30000);
}

async function bootstrapUser() {
  if (!isLoggedIn()) return;
  try {
    const res = await fetch('/api/user/bootstrap', {
      method: 'POST',
      headers: authHeaders(),
    });
    if (res.ok) {
      const data = await res.json();
      userIdentity = data.identity || {};
    } else if (res.status === 401) {
      // Token expired — try refresh
      const refreshed = await tryRefreshToken();
      if (refreshed) {
        return bootstrapUser();
      } else {
        doLogout();
      }
    }
  } catch (e) {
    console.error('Bootstrap error:', e);
  }
}

// ===============================
// UI STATE
// ===============================
let currentState = STATES.IDLE;

function setState(newState) {
  currentState = newState;
  app.dataset.state = currentState;
  sendButton.disabled = currentState !== STATES.IDLE;
}

// ===============================
// MESSAGES
// ===============================
// Neon hue palette — each message gets a different color
const _neonHues = [180, 300, 90, 210, 330, 45, 270, 150, 0, 60];
let _neonIdx = 0;

function parseResponse(rawResponse) {
  // Prova a parsare come JSON con immagini
  if (typeof rawResponse === 'string' && rawResponse.trim().startsWith('{')) {
    try {
      const parsed = JSON.parse(rawResponse);
      if (parsed.text && parsed.images) {
        return parsed;
      }
    } catch (e) { }
  }
  // Risposta normale come stringa
  return { text: rawResponse, images: [] };
}

function renderImages(images) {
  if (!images || images.length === 0) return '';

  let html = '<div class="image-grid" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">';
  images.forEach(img => {
    const thumb = img.thumbnail || img.url;
    html += `
            <div style="width:160px;text-align:center;">
                <img src="${thumb}" 
                     alt="${img.title}"
                     loading="lazy"
                     onerror="this.parentElement.style.display='none'"
                     onclick="window.open('${img.url}', '_blank')"
                     style="width:100%;height:110px;object-fit:cover;border-radius:8px;cursor:pointer;border:1px solid rgba(255,255,255,0.15);">
                <div style="font-size:10px;color:#888;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${img.source}</div>
            </div>`;
  });
  html += '</div>';
  return html;
}

function renderMessageContent(text) {
  // Escape HTML base
  const escape = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Sostituisci ```lang\n...\n``` con <pre><code>
  let html = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre class="code-block"><code class="${lang ? 'lang-' + lang : ''}">${escape(code.trim())}</code></pre>`;
  });

  // Sostituisci `inline code` con <code>
  html = html.replace(/`([^`]+)`/g, (_, code) => `<code class="inline-code">${escape(code)}</code>`);

  // Newline → <br> per testo normale (solo fuori dai pre)
  html = html.replace(/(?<!<\/pre>)\n(?!<pre)/g, '<br>');

  return html;
}

function addMessage(text, sender) {
  const el = document.createElement('div');
  el.className = `message ${sender}`;

  // Parse response per gestire immagini
  const parsed = parseResponse(text);

  // Usa renderMessageContent per formattazione code blocks + escape HTML
  const renderedContent = renderMessageContent(parsed.text);

  el.innerHTML = renderedContent + renderImages(parsed.images);

  // Assign rotating neon hue
  const hue = _neonHues[_neonIdx % _neonHues.length];
  el.style.setProperty('--neon-hue', hue + 'deg');
  _neonIdx++;

  dialogue.appendChild(el);

  // Always scroll on new message (user just sent or received)
  requestAnimationFrame(() => scrollToBottom());

  // Log per debugging del rendering
  console.log('[RENDER] Message added:', { sender, textLength: text.length, element: el });

  return el;
}

function addUserMessage(text) { return addMessage(text, 'user'); }

// ===============================
// CHAT API
// ===============================
async function sendChatMessage(message) {
  try {
    // Route to different endpoint based on current mode
    const endpoint = currentMode === "coding" ? "/coding/" : "/api/chat";

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ message })
    });
    if (res.status === 401) {
      const refreshed = await tryRefreshToken();
      if (refreshed) return sendChatMessage(message);
      doLogout();
      throw new Error('Session expired');
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data;
  } catch (e) {
    console.error('sendChatMessage error:', e);
    throw e;
  }
}

// ===============================
// AUTO-RESIZE INPUT
// ===============================
function autoResizeInput(el) {
  el.style.height = 'auto';
  const newHeight = Math.min(el.scrollHeight, 150);
  el.style.height = newHeight + 'px';

  // Aggiusta l'altezza del container chat per compensare
  const chatBox = document.querySelector('#dialogue');
  if (chatBox) {
    const inputArea = el.closest('#input-container') || el.parentElement;
    const inputHeight = inputArea ? inputArea.offsetHeight : newHeight;
    chatBox.style.paddingBottom = inputHeight + 'px';
  }
}

// ===============================
// CHAT RESPONSE HANDLER
// ===============================
function handleChatResponse(rawResponse) {
  // Controlla se è una risposta con immagini
  if (typeof rawResponse === 'string' && rawResponse.trim().startsWith('{"text"')) {
    try {
      const parsed = JSON.parse(rawResponse);
      if (parsed.text && parsed.images) {
        return { text: parsed.text, images: parsed.images };
      }
    } catch (e) { }
  }
  return { text: rawResponse, images: [] };
}

// ===============================
// SEND MESSAGE
// ===============================
async function sendMessage(voiceText = null) {
  // Audio Priming: previeni NotAllowedError su Safari/iOS
  primeAudio();

  // Fix: when called as event listener, voiceText is an Event object
  const textToUse = (typeof voiceText === 'string') ? voiceText : textInput.value.trim();

  // Barge-in: increment generation + force-stop ALL TTS
  // MA NON durante voice mode conversazionale!
  ttsGenerationId++;
  if (!voiceModeActive) {
    stopAllTTS();
  }

  // Warm AudioContext NOW (sync, during user gesture) — iOS requires this
  _warmTTSCtx();

  const text = textToUse;
  console.log('SEND_MSG_STATE state=' + currentState + ' text_len=' + text.length);
  if (!text || currentState !== STATES.IDLE) return;

  textInput.value = '';
  textInput.style.height = '44px';
  autoResizeInput(textInput);
  textInput.blur(); // Chiude la tastiera su mobile per mostrare la risposta

  // Pulse shockwave on send
  const ic = document.getElementById('input-container');
  ic.classList.remove('pulse');
  void ic.offsetWidth;
  ic.classList.add('pulse');

  addUserMessage(text);

  // Salva messaggio utente nella conversazione corrente
  saveMessageToConversation('user', text);

  // PARTE 1: Mostra animazione thinking come messaggio reale
  setState(STATES.THINKING);
  showThinking();
  console.log('FRONTEND_THINKING_START');

  try {
    // PARTE 1: Chiama /api/chat
    const data = await sendChatMessage(text);
    console.log('[FRONTEND] response received');

    // USA SEMPRE response - CONTRATTO API BACKEND
    const botMessage = data.response;

    if (!botMessage || botMessage.trim().length === 0) return;

    console.log(`LLM_RESPONSE_LENGTH: ${botMessage.length} chars`);

    // RENDER IMMEDIATO — il testo appare SUBITO, senza attendere TTS
    hideThinking();
    const parsed = handleChatResponse(botMessage);
    if (parsed.images && parsed.images.length > 0) {
      // Aggiungi messaggio testo
      addMessage(parsed.text, 'genesi');
      // Salva risposta assistente nella conversazione corrente
      saveMessageToConversation('assistant', parsed.text);
      // Aggiungi griglia immagini
      const lastMsg = document.querySelector('.message.genesi:last-child');
      if (lastMsg) {
        let grid = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">';
        parsed.images.forEach(img => {
          grid += `<div style="width:150px;text-align:center;">
                    <img src="${img.thumbnail || img.url}" 
                         alt="${img.title}"
                         loading="lazy"
                         onerror="this.parentElement.style.display='none'"
                         onclick="window.open('${img.url}','_blank')"
                         style="width:100%;height:100px;object-fit:cover;border-radius:8px;cursor:pointer;">
                    <div style="font-size:10px;color:#888;margin-top:2px;">${img.source}</div>
                </div>`;
        });
        grid += '</div>';
        lastMsg.insertAdjacentHTML('beforeend', grid);
      }
    } else {
      addMessage(parsed.text, 'genesi');
      // Salva risposta assistente nella conversazione corrente
      saveMessageToConversation('assistant', parsed.text);
    }
    console.log('[TEXT_RENDERED] text_len=' + parsed.text.length);

    // TTS ASINCRONO — completamente scollegato dal render
    const rawTtsText = data.tts_text || data.response;
    function stripCodeForTTS(text) {
      return text
        .replace(/```[\s\S]*?```/g, '. ')
        .replace(/`[^`]+`/g, '')
        .trim();
    }
    const ttsText = (currentMode === 'coding') ? stripCodeForTTS(rawTtsText) : rawTtsText;

    // Se ttsText è vuoto o solo spazi dopo il filtro, non chiamare TTS affatto
    if (!ttsText || ttsText.trim().length === 0) {
      console.log('[TTS_ASYNC] Skipped: empty after code filtering in coding mode');
      return;
    }

    console.log('[TTS_ASYNC_START] tts_text_len=' + ttsText.length);
    playTTSAsync(ttsText, data.tts_mode);

  } catch (e) {
    console.error('Chat error:', e);
    // PARTE 4: Fallback in caso di errore
    hideThinking();
    addMessage("Qualcosa non ha funzionato. Riprova tra poco.", 'genesi');
    console.log('TTS_ERROR_FALLBACK');
  } finally {
    setState(STATES.IDLE);
  }
}

// ===============================
// TTS ASYNC — completamente scollegato dal render
// ===============================
function playTTSAsync(text, mode) {
  // Reset abort flag + create fresh AbortController for this generation
  _ttsAborted = false;
  currentTTSAbortController = new AbortController();
  const myGenId = ttsGenerationId;

  // Fire-and-forget: TTS non blocca MAI il render del testo
  (async () => {
    try {
      console.log('[TTS_ASYNC] Starting TTS genId=' + myGenId + ' len=' + text.length + ' mode=' + mode);
      await playTTS(text, mode);
      console.log('[TTS_ASYNC] TTS completed genId=' + myGenId);
    } catch (e) {
      if (e.name === 'AbortError') {
        console.log('[TTS_ASYNC] TTS aborted genId=' + myGenId);
      } else {
        console.warn('[TTS_ASYNC] TTS failed (non-blocking):', e.message);
        console.log('[TTS_PLAY_FAILED] error=' + e.message);
      }
    }
  })();
}

// ===============================
// THINKING DOTS - INDEPENDENT ROW
// ===============================
function showThinking() {
  const thinking = document.createElement("div");
  thinking.className = "thinking-row";
  thinking.id = "genesi-thinking";

  thinking.innerHTML = `
    <div class="thinking-dots">
      <span></span>
      <span></span>
      <span></span>
    </div>
  `;

  dialogue.appendChild(thinking);
  dialogue.scrollTop = dialogue.scrollHeight;
}

function hideThinking() {
  const thinking = document.getElementById("genesi-thinking");
  if (thinking) thinking.remove();
}

// ===============================
// MICROPHONE — DUAL PATH (iOS Safari + Others)
// ===============================
let isRecording = false;
let currentStream = null;

// Platform detection affidabile
const _isIOS = (() => {
  // iOS detection robusta
  return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
})();

const _isSafari = (() => {
  // Safari detection basata su feature, non solo userAgent
  const isSafariLike = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
  const hasSafariFeatures =
    typeof safari !== 'undefined' || // Safari extension object
    !window.chrome || // No Chrome
    (window.safari && window.safari.pushNotification); // Safari push notifications

  return isSafariLike || hasSafariFeatures;
})();

// Use WebAudio/ScriptProcessor ONLY if MediaRecorder is truly unavailable
// iOS Safari 14.5+ supports MediaRecorder with audio/mp4
let _useWebAudio = !window.MediaRecorder;

// Detection dettagliata per logging
function _getPlatformInfo() {
  return {
    isIOS: _isIOS,
    isSafari: _isSafari,
    hasMediaRecorder: !!window.MediaRecorder,
    hasGetUserMedia: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
    userAgent: navigator.userAgent,
    platform: navigator.platform
  };
}

// --- MediaRecorder path (all platforms including iOS Safari 14.5+) ---
let mediaRecorder = null;
let audioChunks = [];
let _gainContext = null;

function getSupportedMimeType() {
  if (typeof MediaRecorder === 'undefined') return '';
  // audio/mp4 is the ONLY format iOS Safari MediaRecorder supports
  const types = _isIOS
    ? ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
    : ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
  for (const t of types) {
    try { if (MediaRecorder.isTypeSupported(t)) return t; } catch (e) { }
  }
  return '';
}

// --- WebAudio/PCM path (iOS Safari) ---
let _audioCtx = null;
let _scriptNode = null;
let _pcmBuffers = [];
let _pcmLength = 0;
const _SAMPLE_RATE = 16000;

function _encodeWAV(samples) {
  const len = samples.length;
  const buf = new ArrayBuffer(44 + len * 2);
  const view = new DataView(buf);
  // RIFF header
  _writeStr(view, 0, 'RIFF');
  view.setUint32(4, 36 + len * 2, true);
  _writeStr(view, 8, 'WAVE');
  // fmt
  _writeStr(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);       // PCM
  view.setUint16(22, 1, true);       // mono
  view.setUint32(24, _SAMPLE_RATE, true);
  view.setUint32(28, _SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  // data
  _writeStr(view, 36, 'data');
  view.setUint32(40, len * 2, true);
  for (let i = 0; i < len; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

function _writeStr(view, offset, str) {
  for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
}

function _downsample(buffer, fromRate, toRate) {
  if (fromRate === toRate) return buffer;
  const ratio = fromRate / toRate;
  const len = Math.round(buffer.length / ratio);
  const result = new Float32Array(len);
  for (let i = 0; i < len; i++) {
    const idx = Math.round(i * ratio);
    result[i] = buffer[Math.min(idx, buffer.length - 1)];
  }
  return result;
}

function resetMicrophoneState() {
  mediaRecorder = null;
  audioChunks = [];
  _pcmBuffers = [];
  _pcmLength = 0;
  if (_scriptNode) { _scriptNode.disconnect(); _scriptNode = null; }
  if (_audioCtx && _audioCtx.state !== 'closed') {
    try { _audioCtx.close(); } catch (e) { }
  }
  _audioCtx = null;
  if (_gainContext && _gainContext.state !== 'closed') {
    try { _gainContext.close(); } catch (e) { }
  }
  _gainContext = null;
  isRecording = false;
  currentStream = null;
  micButton.classList.remove('recording');
}

async function startRecording() {
  // Barge-in: interrompi TTS quando utente preme mic
  _interruptTTS('mic_press');

  // Warm AudioContext NOW (sync, during user gesture) — iOS requires this
  _warmTTSCtx();

  const platform = _getPlatformInfo();
  console.log('[MIC] start', platform);
  if (currentState !== STATES.IDLE || isRecording) return;
  stopAudio();

  // CONTROLLO DEFENSIVO: verifica contesto sicuro (HTTPS richiesto)
  if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    console.error('[MIC] ERROR: insecure context, HTTPS required');
    alert('Microfono richiede connessione sicura (HTTPS).');
    return;
  }

  // SAFARI DESKTOP: controllo specifico
  if (_isSafari && !_isIOS) {
    console.log('[MIC][DESKTOP] Safari desktop detected');

    // Verifica che getUserMedia sia disponibile
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      console.error('[MIC][DESKTOP] getUserMedia not available in Safari');
      alert('Microfono non disponibile in Safari. Assicurati di aver concesso il permesso e di usare Safari 11+.');
      return;
    }

    console.log('[MIC][DESKTOP] getUserMedia available, requesting permission...');
  }

  // CONTROLLO DEFENSIVO: verifica supporto mediaDevices
  if (!navigator.mediaDevices) {
    console.error('[MIC] ERROR: navigator.mediaDevices not supported');
    alert('Microfono non supportato in questo browser. Usa Chrome o Safari.');
    return;
  }

  // CONTROLLO DEFENSIVO: verifica getUserMedia
  if (!navigator.mediaDevices.getUserMedia) {
    console.error('[MIC] ERROR: getUserMedia not supported');
    alert('Microfono non supportato in questo browser. Usa Chrome o Safari.');
    return;
  }

  try {
    console.log('[MIC] requesting permission...');
    const constraints = {
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false
      }
    };

    // SAFARI (desktop + iOS): use simple constraints — complex ones can fail
    if (_isSafari || _isIOS) {
      console.log('[MIC] Safari/iOS: using simple audio constraints');
      constraints.audio = true;
    }

    const stream = await navigator.mediaDevices.getUserMedia(constraints);

    if (_isSafari && !_isIOS) {
      console.log('[MIC][DESKTOP] permission granted, Safari desktop stream ready');
    }

    console.log('[MIC] permission granted, tracks=' + stream.getAudioTracks().length);
    currentStream = stream;

    if (_useWebAudio) {
      // --- FALLBACK: ScriptProcessor for ancient iOS without MediaRecorder ---
      console.log('[iOS STT] setting up AudioContext recording (no MediaRecorder)');

      try {
        // Do NOT force sampleRate — let iOS choose its native rate
        _audioCtx = new (window.AudioContext || window.webkitAudioContext)();

        // iOS requires resume after user gesture
        if (_audioCtx.state === 'suspended') {
          await _audioCtx.resume();
          console.log('[iOS STT] AudioContext resumed');
        }

        console.log('[iOS STT] AudioContext rate=' + _audioCtx.sampleRate + ' state=' + _audioCtx.state);

        const source = _audioCtx.createMediaStreamSource(stream);

        _scriptNode = _audioCtx.createScriptProcessor(4096, 1, 1);
        _pcmBuffers = [];
        _pcmLength = 0;

        _scriptNode.onaudioprocess = (e) => {
          const data = e.inputBuffer.getChannelData(0);
          const copy = new Float32Array(data.length);
          copy.set(data);
          _pcmBuffers.push(copy);
          _pcmLength += copy.length;
        };

        source.connect(_scriptNode);
        _scriptNode.connect(_audioCtx.destination);

        console.log('[iOS STT] ScriptProcessor connected');

        isRecording = true;
        setState(STATES.RECORDING);
        micButton.classList.add('recording');
        console.log('[iOS STT] recording started');

      } catch (error) {
        console.error('[iOS STT] AudioContext setup failed:', error);
        _useWebAudio = false;
      }
    }

    if (!_useWebAudio) {
      // --- MAIN PATH: MediaRecorder (Chrome, Android, Firefox, iOS 14.5+, Safari) ---
      const mimeType = getSupportedMimeType();
      console.log('[MIC] MediaRecorder mimeType=' + mimeType + ' isIOS=' + _isIOS);

      // iOS Safari: use raw stream (GainNode + createMediaStreamDestination can fail)
      // Other browsers: apply gain via AudioContext
      let recordStream = stream;

      if (!_isIOS) {
        try {
          const gainCtx = new (window.AudioContext || window.webkitAudioContext)();
          const source = gainCtx.createMediaStreamSource(stream);
          const gainNode = gainCtx.createGain();
          gainNode.gain.value = 0.3;
          const destination = gainCtx.createMediaStreamDestination();
          source.connect(gainNode);
          gainNode.connect(destination);
          recordStream = destination.stream;
          _gainContext = gainCtx;
          console.log('[MIC] GainNode applied: gain=0.3');
        } catch (gainErr) {
          console.warn('[MIC] GainNode failed, using raw stream:', gainErr);
          recordStream = stream;
        }
      } else {
        console.log('[MIC][iOS] using raw stream (no GainNode)');
      }

      const recOptions = mimeType ? { mimeType } : {};
      mediaRecorder = new MediaRecorder(recordStream, recOptions);
      audioChunks = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const blobType = mimeType || 'audio/webm';
        const blob = new Blob(audioChunks, { type: blobType });
        console.log('[MIC] blob size=' + blob.size + ' type=' + blobType);
        const savedStream = currentStream;
        resetMicrophoneState();
        if (savedStream) savedStream.getTracks().forEach(t => t.stop());
        await transcribeAudio(blob);
      };

      mediaRecorder.start(1000);
      console.log('[MIC] MediaRecorder started' + (_isIOS ? ' (iOS)' : ''));
    }

    isRecording = true;
    setState(STATES.RECORDING);
    micButton.classList.add('recording');

    if (_isSafari && !_isIOS) {
      console.log('[MIC][DESKTOP] Safari desktop recording active');
    } else {
      console.log('[MIC] recording started successfully');
    }

  } catch (e) {
    console.error('[MIC] denied:', e);
    setState(STATES.IDLE);
  }
}

function stopRecording() {
  console.log('[MIC] stop, isRecording=' + isRecording + ' webAudio=' + _useWebAudio);
  if (!isRecording) return;

  if (_useWebAudio) {
    // --- iOS: stop ScriptProcessor, build WAV, send ---
    if (_scriptNode) _scriptNode.disconnect();
    if (_audioCtx && _audioCtx.state !== 'closed') {
      try { _audioCtx.close(); } catch (e) { }
    }
    const nativeSR = _audioCtx ? _audioCtx.sampleRate : _SAMPLE_RATE;
    const stream = currentStream;

    // Merge PCM buffers
    console.log('[iOS STT] merging PCM buffers: ' + _pcmBuffers.length + ' buffers, total length: ' + _pcmLength);

    if (_pcmLength === 0) {
      console.error('[iOS STT] NO PCM DATA COLLECTED - microphone issue');
      resetMicrophoneState();
      if (stream) stream.getTracks().forEach(t => t.stop());
      setState(STATES.IDLE);
      return;
    }

    const merged = new Float32Array(_pcmLength);
    let offset = 0;
    for (const buf of _pcmBuffers) { merged.set(buf, offset); offset += buf.length; }

    const downsampled = _downsample(merged, nativeSR, _SAMPLE_RATE);
    const wavBlob = _encodeWAV(downsampled);
    console.log('[iOS STT] wav size: ' + wavBlob.size + ' bytes');

    resetMicrophoneState();
    if (stream) stream.getTracks().forEach(t => t.stop());

    transcribeAudio(wavBlob);

  } else {
    // --- Standard: stop MediaRecorder (onstop handler fires) ---
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
    }
  }
}

async function transcribeAudio(blob) {
  console.log('[STT] request sent size=' + blob.size + ' type=' + blob.type);

  setState(STATES.THINKING);

  // FASE 4: FINALLY GLOBALE PER GARANTIRE STOP MICROFONO
  try {
    const ext = blob.type.includes('wav') ? '.wav' : blob.type.includes('mp4') ? '.mp4' : '.webm';
    const fd = new FormData();
    fd.append('audio', blob, 'rec' + ext);

    console.log('[STT] sending POST /api/stt/ ...');
    const res = await fetch('/api/stt/', { method: 'POST', body: fd, headers: authHeadersRaw() });
    console.log('[STT] response status=' + res.status);

    if (!res.ok) {
      console.error('[STT] HTTP error: ' + res.status);
      throw new Error('STT ' + res.status);
    }

    const result = await res.json();
    const text = result.text?.trim() || '';
    const status = result.stt_status || result.status || '';
    console.log('[STT] transcription received: "' + text + '" stt_status=' + status);

    // GESTIONE STATI EMPTY/ERROR/NOISE
    if (status === 'empty' || status === 'error' || status === 'noise') {
      console.log('[STT] ' + status + ' transcription → showing feedback');
      setState(STATES.IDLE);

      // Feedback appropriato
      if (status === 'empty' && result.action === 'retry') {
        _showSTTRetryFeedback();
      } else if (status === 'noise') {
        _showSTTNoiseFeedback(result.quality_issues || result.transcription_issues);
      } else {
        _showSTTErrorFeedback();
      }
      return; // NON inviare nulla a /chat
    }

    // INVIA SOLO se trascrizione valida
    console.log('[STT] setting input and sending message...');
    textInput.value = text;
    setState(STATES.IDLE);
    sendMessage();

  } catch (e) {
    console.error('[STT] request failed:', e);
    setState(STATES.IDLE);
    _showSTTErrorFeedback();

  } finally {
    // FASE 4: GARANTISCI STOP MICROFONO SEMPRE
    if (isRecording) {
      console.log('[STT] FINALLY: forcing stop recording (guaranteed)');
      try {
        stopRecording();
      } catch (stopError) {
        console.error('[STT] Error stopping recording in finally:', stopError);
        // Forza reset stato UI anche se stopRecording fallisce
        isRecording = false;
        setState(STATES.IDLE);
        const micButton = document.getElementById('mic-button');
        if (micButton) {
          micButton.classList.remove('recording');
          micButton.textContent = '🎤';
        }
      }
    }

    console.log('[STT] FINALLY: microphone cleanup completed');
  }
}

function _showSTTNoiseFeedback(issues) {
  // Feedback non verbale per rumore/qualità audio
  const micButton = document.getElementById('mic-button');
  if (micButton) {
    // Animazione arancione per rumore
    micButton.style.backgroundColor = '#ff8800';
    setTimeout(() => {
      micButton.style.backgroundColor = '';
    }, 1000);
  }

  // Mostra tooltip con dettagli problemi
  const issueText = Array.isArray(issues) ? issues.join(', ') : 'rumore rilevato';
  const tooltip = document.createElement('div');
  tooltip.textContent = 'Audio di bassa qualità: ' + issueText;
  tooltip.style.cssText = `
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(255,136,0,0.9);
    color: white;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 14px;
    z-index: 1000;
    animation: fadeInOut 3s ease-in-out;
    max-width: 300px;
    text-align: center;
  `;

  document.body.appendChild(tooltip);
  setTimeout(() => {
    if (tooltip.parentNode) {
      tooltip.parentNode.removeChild(tooltip);
    }
  }, 3000);
}

function _showSTTErrorFeedback() {
  // Feedback non verbale per errore STT
  const micButton = document.getElementById('mic-button');
  if (micButton) {
    // Animazione rossa per errore
    micButton.style.backgroundColor = '#ff4444';
    setTimeout(() => {
      micButton.style.backgroundColor = '';
    }, 1000);
  }

  // Mostra tooltip errore
  const tooltip = document.createElement('div');
  tooltip.textContent = 'Errore microfono, riprova';
  tooltip.style.cssText = `
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(255,68,68,0.9);
    color: white;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 14px;
    z-index: 1000;
    animation: fadeInOut 2s ease-in-out;
  `;

  document.body.appendChild(tooltip);
  setTimeout(() => {
    if (tooltip.parentNode) {
      tooltip.parentNode.removeChild(tooltip);
    }
  }, 2000);
}

function _showSTTRetryFeedback() {
  // Feedback non verbale per retry STT
  const micButton = document.getElementById('mic-button');
  if (micButton) {
    // Animazione mic button per indicare retry
    micButton.style.animation = 'pulse 1s ease-in-out 2';
    setTimeout(() => {
      micButton.style.animation = '';
    }, 2000);
  }

  // Mostra tooltip temporaneo
  const tooltip = document.createElement('div');
  tooltip.textContent = 'Non ho sentito bene, riprova';
  tooltip.style.cssText = `
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0,0,0,0.8);
    color: white;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 14px;
    z-index: 1000;
    animation: fadeInOut 2s ease-in-out;
  `;

  document.body.appendChild(tooltip);
  setTimeout(() => {
    if (tooltip.parentNode) {
      tooltip.parentNode.removeChild(tooltip);
    }
  }, 2000);
}

// ===============================
// FILE BUBBLE — preview fumetto
// ===============================
let _activeBubble = null;
const _isMobile = () => window.innerWidth <= 600;
const _truncate = (s, max) => { if (!s) return ''; return s.length > max ? s.slice(0, max - 1) + '…' : s; };

function _fileIcon(type) {
  if (type.startsWith('image/')) return '🖼';
  if (type === 'application/pdf') return '📄';
  if (type.startsWith('audio/')) return '🎵';
  if (type.startsWith('video/')) return '🎬';
  if (type.startsWith('text/') || type.includes('json') || type.includes('xml')) return '📝';
  if (type.includes('zip') || type.includes('tar') || type.includes('rar')) return '📦';
  return '📎';
}

function _showFileBubble(file, status) {
  _dismissFileBubble(true);

  const type = file.type || '';
  const bubble = document.createElement('div');
  bubble.className = 'file-bubble';

  // Thumbnail or icon
  if (type.startsWith('image/')) {
    const thumb = document.createElement('img');
    thumb.className = 'file-bubble__thumb';
    thumb.alt = file.name;
    const reader = new FileReader();
    reader.onload = (ev) => { thumb.src = ev.target.result; };
    reader.readAsDataURL(file);
    bubble.appendChild(thumb);
  } else {
    const icon = document.createElement('div');
    icon.className = 'file-bubble__icon';
    icon.textContent = _fileIcon(type);
    bubble.appendChild(icon);
  }

  // Info
  const info = document.createElement('div');
  info.className = 'file-bubble__info';
  const nameEl = document.createElement('div');
  nameEl.className = 'file-bubble__name';
  nameEl.textContent = _truncate(file.name, _isMobile() ? 24 : 36);
  const statusEl = document.createElement('div');
  statusEl.className = 'file-bubble__status';
  statusEl.textContent = _truncate(status || 'Genesi sta guardando...', 120);
  info.appendChild(nameEl);
  info.appendChild(statusEl);
  bubble.appendChild(info);

  // Close
  const closeBtn = document.createElement('button');
  closeBtn.className = 'file-bubble__close';
  closeBtn.textContent = '✕';
  closeBtn.addEventListener('click', (ev) => {
    ev.stopPropagation();
    _dismissFileBubble();
  });
  bubble.appendChild(closeBtn);

  // Expanded preview container (hidden by default)
  const previewWrap = document.createElement('div');
  previewWrap.className = 'file-bubble__preview';
  bubble.appendChild(previewWrap);

  // Tap to expand/collapse
  bubble.addEventListener('click', () => {
    bubble.classList.toggle('expanded');
  });

  // Insert between #presence and #dialogue
  const presence = document.getElementById('presence');
  if (presence && presence.nextSibling) {
    presence.parentNode.insertBefore(bubble, presence.nextSibling);
  } else {
    app.prepend(bubble);
  }

  _activeBubble = bubble;
  return bubble;
}

function _updateBubbleStatus(text) {
  if (!_activeBubble) return;
  const s = _activeBubble.querySelector('.file-bubble__status');
  if (s) s.textContent = _truncate(text, 120);
}

function _setBubblePreview(previewUrl, file) {
  if (!_activeBubble) return;
  const wrap = _activeBubble.querySelector('.file-bubble__preview');
  if (!wrap) return;
  const type = file.type || '';

  if (type.startsWith('image/')) {
    const img = document.createElement('img');
    img.src = previewUrl;
    img.alt = _truncate(file.name, 30);
    img.onerror = () => img.remove();
    wrap.appendChild(img);
  } else if (type === 'application/pdf') {
    // Mobile: link only (object embed is too heavy)
    // Desktop: object embed with link fallback
    if (_isMobile()) {
      const link = document.createElement('a');
      link.href = previewUrl;
      link.target = '_blank';
      link.textContent = 'Apri PDF ↗';
      link.className = 'preview-pdf-link';
      wrap.appendChild(link);
    } else {
      const obj = document.createElement('object');
      obj.data = previewUrl;
      obj.type = 'application/pdf';
      const link = document.createElement('a');
      link.href = previewUrl;
      link.target = '_blank';
      link.textContent = 'Apri PDF';
      link.className = 'preview-pdf-link';
      obj.appendChild(link);
      wrap.appendChild(obj);
    }
  }
}

function _dismissFileBubble(instant) {
  if (!_activeBubble) return;
  const el = _activeBubble;
  _activeBubble = null;
  if (instant) {
    el.remove();
    return;
  }
  el.style.animation = 'bubbleOut 0.25s ease forwards';
  el.addEventListener('animationend', () => el.remove(), { once: true });
}

// ===============================
// FILE UPLOAD
// ===============================
function handleFileUpload() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '*/*';

  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    let loadingMsg = null;
    try {
      // Show bubble immediately with local preview
      _showFileBubble(file, 'Genesi sta guardando...');
    } catch (_) { /* bubble is cosmetic, never block upload */ }

    loadingMsg = addMessage("Sto analizzando il file...", 'genesi');
    setState(STATES.THINKING);

    const fd = new FormData();
    fd.append('file', file);

    try {
      const res = await fetch('/api/upload/', { method: 'POST', body: fd, headers: authHeadersRaw() });
      if (!res.ok) throw new Error(`Upload ${res.status}`);
      const result = await res.json();
      if (loadingMsg) loadingMsg.remove();

      // Update bubble — short status only, full analysis goes to chat
      try {
        _updateBubbleStatus('Analisi completata');
        if (result.preview_url) _setBubblePreview(result.preview_url, file);
      } catch (_) { /* cosmetic */ }

      // Full analysis in chat message (not in bubble)
      addMessage(result.response || "File ricevuto.", 'genesi');

      // Auto-dismiss bubble after 6s
      setTimeout(() => { try { _dismissFileBubble(); } catch (_) { } }, 6000);
    } catch (e) {
      console.error('Upload error:', e);
      if (loadingMsg) loadingMsg.remove();
      try { _updateBubbleStatus('Errore'); } catch (_) { }
      addMessage("Errore nel caricamento. Riprova.", 'genesi');
      setTimeout(() => { try { _dismissFileBubble(); } catch (_) { } }, 3000);
    } finally {
      setState(STATES.IDLE);
    }
  };
  input.click();
}

// ===============================
// CAMERA — getUserMedia pipeline (iOS Safari + Android)
// ===============================
async function startCamera() {
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false
    });

    cameraVideo = document.createElement("video");
    cameraVideo.srcObject = cameraStream;
    cameraVideo.setAttribute("playsinline", "");
    cameraVideo.playsInline = true;
    cameraVideo.muted = true;

    await cameraVideo.play();

    showCameraOverlay(cameraVideo);

    console.log("[CAMERA] started");
  } catch (err) {
    console.error("[CAMERA] error:", err);
    addMessage("Non riesco ad accedere alla fotocamera.", 'genesi');
  }
}

function showCameraOverlay(video) {
  const overlay = document.createElement("div");
  overlay.id = "cameraOverlay";

  overlay.innerHTML = `
    <div class="camera-container"></div>
    <div class="camera-controls">
      <button id="snapBtn" type="button">Scatta</button>
      <button id="closeCamera" type="button">Chiudi</button>
    </div>
  `;

  document.body.appendChild(overlay);

  overlay.querySelector(".camera-container").appendChild(video);

  document.getElementById("snapBtn").onclick = captureFrame;
  document.getElementById("closeCamera").onclick = stopCamera;
}

async function captureFrame() {
  if (!cameraVideo) return;

  const canvas = document.createElement("canvas");
  const MAX_WIDTH = 1280;
  const vw = cameraVideo.videoWidth || 640;
  const vh = cameraVideo.videoHeight || 480;
  const ratio = vw / vh;

  canvas.width = Math.min(vw, MAX_WIDTH);
  canvas.height = canvas.width / ratio;

  const ctx = canvas.getContext("2d");
  ctx.drawImage(cameraVideo, 0, 0, canvas.width, canvas.height);

  const blob = await new Promise(resolve =>
    canvas.toBlob(resolve, "image/jpeg", 0.8)
  );

  console.log("[CAMERA] photo captured size=", blob.size);

  stopCamera();
  await uploadCapturedImage(blob);
}

async function uploadCapturedImage(blob) {
  const loadingMsg = addMessage("Sto analizzando la foto...", 'genesi');
  setState(STATES.THINKING);

  const formData = new FormData();
  formData.append("file", blob, "camera_" + Date.now() + ".jpg");

  try {
    const res = await fetch("/api/upload/", {
      method: "POST",
      body: formData,
      headers: authHeadersRaw()
    });

    if (!res.ok) throw new Error("Upload " + res.status);

    const data = await res.json();
    if (loadingMsg) loadingMsg.remove();

    addMessage(data.response || "Foto caricata.", 'genesi');

    console.log("[CAMERA_UPLOAD] success doc_id=", data.doc_id);
  } catch (err) {
    console.error("[CAMERA_UPLOAD] error:", err);
    if (loadingMsg) loadingMsg.remove();
    addMessage("Errore nel caricamento della foto.", 'genesi');
  } finally {
    setState(STATES.IDLE);
  }
}

function stopCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(track => track.stop());
    cameraStream = null;
  }
  cameraVideo = null;

  const overlay = document.getElementById("cameraOverlay");
  if (overlay) overlay.remove();

  console.log("[CAMERA] stopped");
}

// ===============================
// EVENT LISTENERS
// ===============================
sendButton.addEventListener('click', sendMessage);
plusButton.addEventListener('click', handleFileUpload);

// Intercept form submit to prevent page reload
chatForm.addEventListener('submit', async (e) => {
  e.preventDefault(); // BLOCCA reload pagina
  await sendMessage();
});

const handleMicToggle = (e) => {
  // Audio Priming: previeni NotAllowedError su Safari/iOS
  primeAudio();

  if (e.type === 'touchstart') e.preventDefault();
  isRecording ? stopRecording() : startRecording();
};

const isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);

if (isTouchDevice) {
  micButton.addEventListener('touchstart', handleMicToggle, { passive: false });
} else {
  micButton.addEventListener('click', handleMicToggle);
}

if (isTouchDevice) {
  document.addEventListener('touchend', (e) => {
    if (e.target !== micButton && isRecording) stopRecording();
  });
}

// ===============================
// INPUT FOCUS — KEYBOARD HANDLING + BARGE-IN
// ===============================
textInput.addEventListener('focus', () => {
  // Barge-in: interrompi TTS quando utente inizia a scrivere
  _interruptTTS('text_focus');
  // iOS keyboard animation can take ~400ms on first open
  setTimeout(() => { updateAppHeight(); scrollToBottom(); }, 100);
  setTimeout(() => { updateAppHeight(); scrollToBottom(); }, 400);
});

// Barge-in su ogni digitazione (solo se TTS sta suonando)
textInput.addEventListener('input', () => {
  autoResizeInput(textInput);
  if (_ttsSource || activeTTSSources.length > 0) {
    _interruptTTS('text_typing');
  }
});

// Enter invia, Shift+Enter va a capo
textInput.addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
  // Shift+Enter: comportamento default (va a capo)
});
// ===============================
// CONVERSATION PERSISTENCE
// ===============================
async function saveMessageToConversation(role, content) {
  if (!currentConvId) {
    console.warn('SAVE_SKIPPED no currentConvId');
    return;
  }
  const convId = currentConvId; // snapshot locale per evitare race condition
  try {
    await fetch(`/api/conversations/${convId}/messages`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ role, content })
    });
  } catch (e) { console.warn('saveMessage error', e); }
}

function unlockAudio() {
  if (window.audioUnlocked) {
    console.log('[AUDIO] Already unlocked');
    return;
  }

  console.log('[AUDIO] Unlocking audio on first user gesture');

  try {
    // Crea AudioContext globale
    window.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    console.log('[AUDIO] Global AudioContext created, state=' + window.audioContext.state);

    // Resume immediato
    window.audioContext.resume().then(() => {
      console.log('[AUDIO] Global AudioContext resumed successfully');
      window.audioUnlocked = true;
      console.log('[AUDIO] Audio unlocked successfully');
    }).catch(err => {
      console.error('[AUDIO] Global AudioContext resume failed:', err);
      window.audioUnlocked = true; // Anche se fallisce, consideriamo unlocked
    });

  } catch (error) {
    console.error('[AUDIO] Failed to create global AudioContext:', error);
    window.audioUnlocked = true; // Fallback
  }
}

// Funzione per verificare stato audio unlock
function isAudioUnlocked() {
  return window.audioUnlocked === true && window.audioContext && window.audioContext.state === 'running';
}

// ===============================
// TTS AUDIO PLAYBACK - SIMPLE HTMLAudioElement
// ===============================
async function playTTSAudio(blob) {
  console.log('[TTS] TTS blob ricevuto - size=' + blob.size + ' type=' + blob.type);

  try {
    // SIMPLE PLAYBACK: Usa HTMLAudioElement diretto
    await playSimpleAudio(blob);

  } catch (error) {
    console.error('[TTS] Errore durante playback TTS:', error);
    console.error('[TTS] Errore details:', error.message);
    _ttsSource = null;
    _isPlayingChunk = false;
  }
}

async function playSimpleAudio(blob) {
  console.log('[TTS] Avvio playback con Web Audio API (decodeAudioData)');

  // Guard: skip if generation changed during async
  const myGenId = ttsGenerationId;
  if (_ttsAborted) {
    console.log('[TTS] playSimpleAudio skipped — aborted');
    return;
  }

  const ctx = _getTTSCtx();
  if (!ctx) {
    console.error('[TTS] AudioContext non disponibile per playSimpleAudio.');
    return;
  }

  try {
    const arrayBuffer = await blob.arrayBuffer();
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

    // Final generation check before play
    if (ttsGenerationId !== myGenId || _ttsAborted) {
      console.log('[TTS] playSimpleAudio skipped — stale genId=' + myGenId + ' current=' + ttsGenerationId);
      return;
    }

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    console.log('[TTS] AudioBufferSource creato genId=' + myGenId);

    // Track in activeTTSSources
    activeTTSSources.push(source);

    // Cleanup helper
    const cleanup = () => {
      const idx = activeTTSSources.indexOf(source);
      if (idx > -1) activeTTSSources.splice(idx, 1);
      if (_ttsSource === source) _ttsSource = null;
      _isPlayingChunk = false;
    };

    // Configura eventi
    source.onended = () => {
      window.ttsPlaying = false;
      console.log('[TTS] Playback completato genId=' + myGenId);
      cleanup();
    };

    // Imposta timestamp TTS PRIMA del playback
    window.lastTTSStart = Date.now();

    // Set variables before start
    window.ttsPlaying = true;
    _wasPlayingChunk = true;

    // Avvia playback
    console.log('[TTS] Avvio playback genId=' + myGenId);
    source.start(0);
    console.log('[TTS] Audio avviato genId=' + myGenId + ' activeSources=' + activeTTSSources.length);

  } catch (error) {
    console.error('[TTS] Errore decodifica o playback genId=' + myGenId, error);
    _isPlayingChunk = false;
    window.ttsPlaying = false;
  }
}

// iOS: pre-unlock AudioContext on very first user interaction
document.addEventListener('touchstart', function _firstTouch() {
  console.log('[AUDIO] First touch detected - unlocking audio');
  unlockAudio();

  // Audio Priming: previeni NotAllowedError su Safari/iOS
  primeAudio();
  _warmTTSCtx();

  document.removeEventListener('touchstart', _firstTouch);
}, { once: true });

// Prima gesture su desktop (click)
document.addEventListener('click', function _firstClick(e) {
  // Solo se non è già stato unlockato da touch
  if (!window.audioUnlocked) {
    console.log('[AUDIO] First click detected - unlocking audio');
    unlockAudio();
  }

  document.removeEventListener('click', _firstClick);
}, { once: true });

// ===============================
// GLOBAL SIDEBAR FUNCTIONS
// ===============================
function clearChat() {
  const dialogue = document.getElementById('dialogue');
  if (dialogue) {
    dialogue.innerHTML = '';
  }
}

async function loadConversations() {
  try {
    const res = await fetch('/api/conversations', {
      headers: { 'Authorization': `Bearer ${getAuthToken()}` }
    });
    const data = await res.json();
    renderConvList(data.conversations || []);
  } catch (e) { console.warn('loadConversations error', e); }
}

function renderConvList(convs) {
  const list = document.getElementById('conv-list');
  if (!list) return;
  list.innerHTML = '';
  convs.forEach(c => {
    const item = document.createElement('div');
    item.className = 'conv-item' + (c.id === currentConvId ? ' active' : '');
    item.dataset.id = c.id;
    item.innerHTML = `
            <span class="conv-title" title="${c.title}">${c.title}</span>
            <div class="conv-actions">
                <button class="conv-btn" onclick="renameConv('${c.id}')" title="Rinomina">✎</button>
                <button class="conv-btn" onclick="deleteConv('${c.id}')" title="Elimina">✕</button>
            </div>`;
    item.addEventListener('click', (e) => {
      if (e.target.classList.contains('conv-btn')) return;
      openConversation(c.id);
    });
    list.appendChild(item);
  });
}

async function createNewConversation() {
  const res = await fetch('/api/conversations', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${getAuthToken()}` }
  });
  const conv = await res.json();
  currentConvId = conv.id;
  clearChat(); // funzione esistente o equivalente per pulire la UI
  await loadConversations();
}

async function openConversation(convId) {
  currentConvId = convId;
  const res = await fetch(`/api/conversations/${convId}`, {
    headers: { 'Authorization': `Bearer ${getAuthToken()}` }
  });
  const conv = await res.json();
  clearChat();
  (conv.messages || []).forEach(m => addMessage(m.content, m.role));
  await loadConversations(); // aggiorna active state
}

async function renameConv(convId) {
  const newTitle = prompt('Nuovo nome:');
  if (!newTitle) return;
  await fetch(`/api/conversations/${convId}`, {
    method: 'PATCH',
    headers: { 'Authorization': `Bearer ${getAuthToken()}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: newTitle })
  });
  await loadConversations();
}

async function deleteConv(convId) {
  if (!confirm('Eliminare questa conversazione?')) return;
  await fetch(`/api/conversations/${convId}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${getAuthToken()}` }
  });
  if (currentConvId === convId) {
    currentConvId = null;
    clearChat();
  }
  await loadConversations();
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const isCollapsed = sidebar.classList.contains('sidebar-collapsed');
  sidebar.classList.toggle('sidebar-collapsed', !isCollapsed);
  document.getElementById('sidebar-open-btn').style.display = isCollapsed ? 'none' : 'block';
}

function toggleCodingMode() {
  const codingBtn = document.getElementById('coding-mode-btn');

  // Toggle mode
  if (currentMode === "chat") {
    currentMode = "coding";
    codingBtn.classList.add('active');
    codingBtn.style.backgroundColor = '#00ff88';
    codingBtn.style.color = '#000';
    console.log('CODING_MODE_ACTIVATED');
  } else {
    currentMode = "chat";
    codingBtn.classList.remove('active');
    codingBtn.style.backgroundColor = '';
    codingBtn.style.color = '';
    console.log('CODING_MODE_DEACTIVATED');
  }

  // Clear chat when switching modes
  clearChat();
  startNewSession();
}

// Pulizia conversazioni vuote all'avvio
async function cleanEmptyConversations() {
  try {
    const res = await fetch('/api/conversations', {
      headers: { 'Authorization': `Bearer ${getAuthToken()}` }
    });
    const convs = await res.json();
    for (const c of convs) {
      // Se il titolo è "Nuova chat" e non ha messaggi
      const hasMessages = c.message_count > 0 ||
        (c.messages && c.messages.length > 0) ||
        (c.title && c.title !== 'Nuova chat');
      if (!hasMessages) {
        await fetch(`/api/conversations/${c.id}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${getAuthToken()}` }
        });
      }
    }
    console.log('CLEANED_EMPTY_CONVS completed');
  } catch (e) { console.warn('cleanEmptyConversations error', e); }
}

// Crea nuova conversazione all'avvio
async function startNewSession() {
  try {
    // 1. Cancella tutte le conv vuote sul backend
    await fetch('/api/conversations/empty', {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${getAuthToken()}` }
    });

    // 2. Controlla se esiste già UNA conv vuota (appena creata)
    const listRes = await fetch('/api/conversations', {
      headers: { 'Authorization': `Bearer ${getAuthToken()}` }
    });
    const convData = await listRes.json(); const convs = Array.isArray(convData) ? convData : (convData.conversations || convData.items || Object.values(convData) || []);

    // DEBUG — stampa la struttura raw delle conv
    console.log('CONVS_RAW:', JSON.stringify(convs.slice(0, 3)));

    const existingEmpty = convs.find(c =>
      (!c.messages || c.messages.length === 0) &&
      (c.title === 'Nuova chat' || !c.title)
    );

    console.log('EXISTING_EMPTY:', existingEmpty ? existingEmpty.id : 'none');

    if (existingEmpty) {
      // Riusa quella vuota invece di crearne una nuova
      currentConvId = existingEmpty.id;
      console.log('SESSION_REUSE conv_id=' + currentConvId);
    } else {
      // Crea nuova solo se non esiste una vuota
      const res = await fetch('/api/conversations', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getAuthToken()}` }
      });
      const conv = await res.json();
      console.log('CONV_CREATED_RAW:', JSON.stringify(conv));
      currentConvId = conv.id;
      console.log('SESSION_STARTED conv_id=' + currentConvId);
    }

    console.log('CURRENT_CONV_ID_AFTER_START:', currentConvId);
    await loadConversations();
  } catch (e) {
    console.error('startNewSession FATAL:', e);
  }
}

(async () => {
  // Apply auth state FIRST - sempre loggato
  applyAuthState();

  // Bootstrap utente SEMPRE
  await bootstrapUser();

  // Avvia polling notifiche se loggato
  if (isLoggedIn()) {
    startNotificationPolling();
  }

  scrollToBottom();

  console.log("SIDEBAR_INIT_START");

  // Init sidebar dopo login/bootstrap
  document.getElementById('new-chat-btn')?.addEventListener('click', startNewSession);
  document.getElementById('coding-mode-btn')?.addEventListener('click', toggleCodingMode);
  document.getElementById('sidebar-toggle')?.addEventListener('click', toggleSidebar);
  document.getElementById('sidebar-open-btn')?.addEventListener('click', toggleSidebar);

  // Init Voice Mode
  initVoiceMode();

  // FORZA RE-INIZIALIZZAZIONE DOPO LOGIN
  if (isLoggedIn()) {
    console.log("SIDEBAR_LOADING_CONVERSATIONS");
    await startNewSession();

    // Validazione DOM
    const sidebarEl = document.querySelector(".sidebar");
    if (!sidebarEl) {
      console.error("SIDEBAR_DOM_ERROR: .sidebar element not found");
    } else if (!sidebarEl.children.length) {
      console.warn("SIDEBAR_DOM_WARNING: .sidebar exists but is empty");
    } else {
      console.log("SIDEBAR_DOM_OK: sidebar rendered with", sidebarEl.children.length, "children");
    }
  }

  console.log("SIDEBAR_INIT_DONE");

  // Neon flicker — wrap each word of the presence text in a span
  const presenceP = document.querySelector('#presence p');
  if (presenceP) {
    const words = presenceP.textContent.split(' ');
    presenceP.innerHTML = words.map((w, i) => {
      const flicker = (i === 2 || i === 5) ? ' style="animation: neonFlicker 6s ' + (i * 0.7) + 's infinite"' : '';
      return '<span' + flicker + '>' + w + '</span>';
    }).join(' ');
  }
})();

// Esponi activeTTSSources globalmente per Voice Mode
window.activeTTSSources = activeTTSSources;

// ════════════════════════════════════════════════════════════
// VOICE MODE — Conversazione continua
// ════════════════════════════════════════════════════════════
let voiceModeActive = false;
let voiceRecognition = null;
let voiceSilenceTimer = null;
let voiceBlockedUntil = 0;
const VOICE_SILENCE_MS = 1500;

// Singleton per waitForTTSEnd - previene chiamate parallele
let voiceTTSPollInterval = null;
let voiceTTSPollTimeout = null;

function initVoiceMode() {
  const btn = document.getElementById('voice-mode-btn');
  const stopBtn = document.getElementById('voice-mode-stop-btn');
  if (!btn) return;
  btn.addEventListener('click', () => voiceModeActive ? stopVoiceMode() : startVoiceMode());
  stopBtn?.addEventListener('click', stopVoiceMode);
}

function buildVoiceRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return null;
  const rec = new SpeechRecognition();
  rec.lang = 'it-IT';
  rec.continuous = false;
  rec.interimResults = true;
  let finalTranscript = '';

  rec.onresult = (event) => {
    if (Date.now() < voiceBlockedUntil) {
      console.log('VOICE_BLOCKED transcript ignored remaining=' + (voiceBlockedUntil - Date.now()) + 'ms');
      return;
    }
    if (!voiceModeActive) return;
    finalTranscript = '';
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript;
      else interim += event.results[i][0].transcript;
    }
    const inp = document.getElementById('message-input');
    if (inp) inp.value = finalTranscript || interim;
    clearTimeout(voiceSilenceTimer);
    if (finalTranscript) {
      voiceSilenceTimer = setTimeout(() => {
        if (Date.now() >= voiceBlockedUntil) sendVoiceMessage(finalTranscript);
      }, VOICE_SILENCE_MS);
    }
  };

  rec.onend = () => {
    if (!voiceModeActive) return;
    const waitMs = Math.max(1500, voiceBlockedUntil - Date.now());
    setTimeout(() => {
      if (!voiceModeActive) return;
      if (Date.now() < voiceBlockedUntil) return;
      try {
        voiceRecognition.stop();
      } catch (e) { }
      setTimeout(() => {
        if (!voiceModeActive) return;
        try { voiceRecognition.start(); }
        catch (e) { console.warn('VOICE_RESTART_ERROR', e); }
      }, 300);
    }, waitMs);
  };

  rec.onerror = (e) => {
    console.warn('VOICE_REC_ERROR', e.error);
    if (!voiceModeActive || e.error === 'aborted') return;
    setTimeout(() => {
      if (voiceModeActive && Date.now() >= voiceBlockedUntil) {
        try { voiceRecognition = buildVoiceRecognition(); voiceRecognition?.start(); }
        catch (e2) { }
      }
    }, 600);
  };

  return rec;
}

function startVoiceMode() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) { alert('Browser non supporta il riconoscimento vocale.'); return; }
  voiceModeActive = true;
  voiceBlockedUntil = 0;
  document.getElementById('voice-mode-btn')?.classList.add('active');
  document.getElementById('voice-mode-overlay')?.classList.replace('hidden', 'visible');
  setVoiceOrbState('listening');
  setVoiceStatusText('In ascolto...');

  // Crea la recognition UNA SOLA VOLTA
  if (!voiceRecognition) {
    voiceRecognition = buildVoiceRecognition();
  }
  voiceRecognition?.start();
  console.log('VOICE_MODE_STARTED');
}

async function sendVoiceMessage(text) {
  console.log('SEND_VOICE_MSG text="' + text + '" len=' + (text?.length || 0));
  if (!text?.trim() || !voiceModeActive) return;
  clearTimeout(voiceSilenceTimer);
  voiceSilenceTimer = null;

  voiceBlockedUntil = Date.now() + 12000;
  console.log('VOICE_BLOCKED_START timestamp=' + Date.now() + ' will unblock after 12s');

  // NON fare voiceRecognition?.stop() e NON fare voiceRecognition = null
  // Lascia che sia onend a gestire il ciclo

  // Imposta il testo nel campo input corretto
  textInput.value = text;
  textInput.style.height = 'auto';

  // Forza stato IDLE prima di chiamare sendMessage() per evitare il blocco
  setState(STATES.IDLE);

  await sendMessage(text);

  setVoiceOrbState('speaking');
  setVoiceStatusText('Genesi risponde...');

  waitForTTSEnd(() => {
    if (!voiceModeActive) return;
    voiceBlockedUntil = Date.now() + 1500;
    console.log('VOICE_UNBLOCKED timestamp=' + Date.now() + ' riavvio ascolto fra 1.5s');
    setVoiceOrbState('listening');
    setVoiceStatusText('In ascolto...');
    setTimeout(() => {
      if (!voiceModeActive) return;
      // Riutilizza l'istanza esistente invece di ricrearla
      try { voiceRecognition?.start(); } catch (e) { }
    }, 1500);
  });
}

function waitForTTSEnd(callback) {
  // Cancella poll precedenti per evitare chiamate parallele
  if (voiceTTSPollInterval) {
    clearInterval(voiceTTSPollInterval);
    voiceTTSPollInterval = null;
  }
  if (voiceTTSPollTimeout) {
    clearTimeout(voiceTTSPollTimeout);
    voiceTTSPollTimeout = null;
  }

  const startTime = Date.now();
  voiceTTSPollInterval = setInterval(() => {
    const ttsStarted = window.lastTTSStart > startTime;
    const ttsEnded = ttsStarted && window.ttsPlaying !== true;
    const safeDelay = (Date.now() - window.lastTTSStart) > 500;
    if (ttsEnded && safeDelay) {
      clearInterval(voiceTTSPollInterval);
      voiceTTSPollInterval = null;
      clearTimeout(voiceTTSPollTimeout);
      voiceTTSPollTimeout = null;
      setTimeout(callback, 800);
    }
  }, 150);

  // Fallback: se TTS non parte entro 10s, sblocca subito
  voiceTTSPollTimeout = setTimeout(() => {
    clearInterval(voiceTTSPollInterval);
    voiceTTSPollInterval = null;
    clearTimeout(voiceTTSPollTimeout);
    voiceTTSPollTimeout = null;
    const ttsStarted = window.lastTTSStart > startTime;
    if (!ttsStarted) {
      console.log('TTS_NOT_DETECTED timestamp=' + Date.now() + ' dopo 10s senza TTS');
    }
    if (voiceModeActive) callback();
  }, 10000);
}

function stopVoiceMode() {
  voiceModeActive = false;
  voiceBlockedUntil = 0;
  clearTimeout(voiceSilenceTimer);
  voiceSilenceTimer = null;
  try { voiceRecognition?.stop(); } catch (e) { }
  voiceRecognition = null;
  document.getElementById('voice-mode-btn')?.classList.remove('active');
  document.getElementById('voice-mode-overlay')?.classList.replace('visible', 'hidden');
  console.log('VOICE_MODE_STOPPED');
}

function setVoiceOrbState(state) {
  const orb = document.querySelector('.voice-orb');
  if (!orb) return;
  orb.classList.remove('listening', 'speaking', 'idle');
  orb.classList.add(state);
}

function setVoiceStatusText(text) {
  const el = document.querySelector('.voice-status-text');
  if (el) el.textContent = text;
}

// ═══════════════════════════════════════════════════════════════
// WEATHER WIDGET
// Chiamato al caricamento della pagina, non blocca nulla.
// Non usa Bearer token — endpoint pubblico della homepage.
// ═══════════════════════════════════════════════════════════════

(function initWeatherWidget() {
  'use strict';

  // Mappa icon_code OpenWeather → emoji
  const WEATHER_ICONS_MAP = {
    '01d': '☀️', '01n': '🌙',
    '02d': '⛅', '02n': '🌤️',
    '03d': '☁️', '03n': '☁️',
    '04d': '☁️', '04n': '☁️',
    '09d': '🌧️', '09n': '🌧️',
    '10d': '🌦️', '10n': '🌧️',
    '11d': '⛈️', '11n': '⛈️',
    '13d': '❄️', '13n': '❄️',
    '50d': '🌫️', '50n': '🌫️'
  };

  const els = {
    widget: document.getElementById('weather-widget'),
    loading: document.getElementById('ww-loading'),
    data: document.getElementById('ww-data'),
    error: document.getElementById('ww-error'),
    icon: document.getElementById('ww-icon'),
    city: document.getElementById('ww-city'),
    temp: document.getElementById('ww-temp'),
    desc: document.getElementById('ww-desc'),
    meta: document.getElementById('ww-meta'),
    time: document.getElementById('ww-time'),
  };

  if (!els.widget) {
    console.warn('[WEATHER_WIDGET] Elemento #weather-widget non trovato nel DOM.');
    return;
  }

  function showState(state) {
    els.loading.hidden = state !== 'loading';
    els.data.hidden = state !== 'data';
    els.error.hidden = state !== 'error';
  }

  function updateClock() {
    const now = new Date();
    const time = now.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
    if (els.time) els.time.textContent = time;
  }

  function renderWeather(payload) {
    // Usa l'icon_code di OpenWeatherMap per discriminare giorno/notte
    const icon = WEATHER_ICONS_MAP[payload.icon_code] || '🌡️';
    els.icon.textContent = icon;
    els.city.textContent = payload.city;
    els.temp.textContent = `${payload.temp}°`;
    els.desc.textContent = payload.description;
    els.meta.textContent = `${payload.humidity}% umidità · ${payload.wind_speed} km/h`;
    updateClock();
    showState('data');
    console.log(
      `[WEATHER_WIDGET] OK city=${payload.city} temp=${payload.temp}° condition=${payload.condition}`
    );
  }

  async function fetchWeather(lat, lon) {
    const url = lat !== null && lon !== null
      ? `/api/weather-widget?lat=${lat}&lon=${lon}`
      : `/api/weather-widget`;

    const resp = await fetch(url, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  function loadWithCoords(lat, lon) {
    fetchWeather(lat, lon)
      .then(renderWeather)
      .catch(err => {
        console.warn('[WEATHER_WIDGET] Fetch con coordinate fallita:', err);
        // Secondo tentativo: fallback IP
        fetchWeather(null, null)
          .then(renderWeather)
          .catch(() => showState('error'));
      });
  }

  function refreshMeteoData() {
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        pos => loadWithCoords(pos.coords.latitude, pos.coords.longitude),
        _err => {
          console.info('[WEATHER_WIDGET] Geolocation negata — fallback IP');
          fetchWeather(null, null)
            .then(renderWeather)
            .catch(() => showState('error'));
        },
        { timeout: 6000, maximumAge: 300_000 }
      );
    } else {
      console.info('[WEATHER_WIDGET] Geolocation non disponibile — fallback IP');
      fetchWeather(null, null)
        .then(renderWeather)
        .catch(() => showState('error'));
    }
  }

  // ── Entry point ──────────────────────────────────────────────
  showState('loading');
  refreshMeteoData();

  // Aggiorna orologio ogni minuto
  setInterval(updateClock, 60_000);
  // Aggiorna i dati meteo ogni 15 minuti (900.000 ms)
  setInterval(refreshMeteoData, 900_000);

})();