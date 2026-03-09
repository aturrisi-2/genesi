// ===============================
// CONVERSATION STATE
// ===============================
let currentConvId = null;

// ===============================
// APPLICATION MODE STATE
// ===============================
let currentMode = "chat"; // "chat" | "coding"
let currentConvFilter = "chat"; // mirrors currentMode for sidebar tab filter

// ===============================
// TTS TIMING STATE
// ===============================
window.lastTTSStart = 0;
window.lastTTSEnd = 0;
window.ttsPlaying = false;
window.ttsSessionActive = false;
window.ttsExpected = false;
window.responseProcessed = false;
window.isGenesiSpeaking = false;
let thinkingLabelTimer = null;
let thinkingStepIndex = 0;
let voiceStepIndex = 0;
const THINKING_STEPS = [
  'Analizzo richiesta e contesto...',
  'Controllo memoria e strumenti...',
  'Compongo la risposta finale...',
  'Organizzo i pensieri...',
];

// Fasi mostrate dopo che la risposta è pronta, in attesa che parta l'audio
const VOICE_STEPS = [
  'Preparo la voce...',
  'Elaboro il suono...',
  'Sto per parlare...',
  'Un momento...',
];
let restartAttempts = 0;
const MAX_RESTARTS = 5;

// ===============================
// AUDIO PRIMING
// ===============================
let _primedAudio = null;

// ===============================
// STATES
// ===============================
const STATES = { IDLE: 'idle', THINKING: 'thinking', RECORDING: 'recording' };
let recognitionActive = false; // Prevents concurrent SpeechRecognition starts

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

// Inline menu variables
const moreActionsBtn = document.getElementById('more-actions-btn');
const inlineActionsMenu = document.getElementById('inline-actions-menu');

if (moreActionsBtn && inlineActionsMenu) {
  moreActionsBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    inlineActionsMenu.classList.toggle('visible');
  });

  // Close menu if clicked outside
  document.addEventListener('click', (e) => {
    if (!inlineActionsMenu.contains(e.target) && e.target !== moreActionsBtn) {
      inlineActionsMenu.classList.remove('visible');
    }
  });
}

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
    // 1. Forza l'altezza sull'intera pagina così scompare ogni barra di scrolling di sistema
    const h = window.visualViewport.height;
    document.documentElement.style.setProperty('--app-height', h + 'px');
    document.body.style.height = h + 'px';
    const appWrapper = document.getElementById('genesi-app');
    if (appWrapper) appWrapper.style.height = h + 'px';

    // 2. Tira su la visual viewport (su iOS quando apri la tastiera la finestra può esser schiacciata giù)
    window.scrollTo({ top: 0, behavior: 'instant' });
  } else {
    document.documentElement.style.setProperty('--app-height', window.innerHeight + 'px');
  }
}

updateAppHeight();

if (window.visualViewport) {
  const _onViewport = () => {
    updateAppHeight();
    // 3. Spinge la chat al bottom senza esitazioni o easing che si impallano mentre la tastiera sale
    requestAnimationFrame(() => {
      window.scrollTo(0, 0);
      scrollToBottom();
    });
    setTimeout(scrollToBottom, 50);
    setTimeout(scrollToBottom, 200);
  };
  window.visualViewport.addEventListener('resize', _onViewport);
  window.visualViewport.addEventListener('scroll', _onViewport);

  // 4. Se la casella acquista il Focus, forziamo il tracking viewport aggiuntivo (salvagente per delay iOS)
  const tgInput = document.getElementById('text-input');
  if (tgInput) {
    tgInput.addEventListener('focus', () => { setTimeout(_onViewport, 300); });
  }
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

// Typewriter animation state — syncs text display with TTS audio
let _twBubble   = null;  // bubble element to animate
let _twShown    = '';    // text already typed (previous chunks)
let _twTimeout  = null;  // active setTimeout handle
let _twFullText = '';    // complete response text (for final render / fallback)
let _twImages   = '';    // rendered images HTML (appended on final render)

// Starts character-by-character typewriter for one TTS chunk, timed to audio duration
function _startTypewriterChunk(text, durationMs) {
  if (!_twBubble || !text) return;
  hideThinking(); // L'audio sta partendo — nascondi qualsiasi status residuo
  clearTimeout(_twTimeout);

  const chars = text.split('');
  const getWeight = (ch) => {
    if ('.!?'.includes(ch)) return 5;
    if (',;:'.includes(ch)) return 2.5;
    if (ch === '\n') return 4;
    if (ch === ' ') return 1.2;
    return 1;
  };
  const totalWeight = chars.reduce((sum, ch) => sum + getWeight(ch), 0);
  const msPerWeight = totalWeight > 0 ? durationMs / totalWeight : 30;

  let i = 0;
  let typed = '';
  const typeNext = () => {
    if (i >= chars.length) { _twShown += text; return; }
    const ch = chars[i++];
    typed += ch;
    const _twPrev = typed.slice(0, -1);
    const _twLast = typed.slice(-1);
    _twBubble.innerHTML = _twShown + _twPrev +
      '<span class="char-appear">' + _twLast + '</span>' +
      '<span class="stream-cursor"></span>';
    _twTimeout = setTimeout(typeNext, Math.max(1, getWeight(ch) * msPerWeight));
  };
  typeNext();
}

// Shows fully-rendered markdown in bubble — called after TTS ends or on barge-in
function _twFinalRender() {
  hideThinking(); // safety: se TTS non parte mai, nascondi comunque il thinking
  if (!_twBubble) return;
  clearTimeout(_twTimeout);
  _twBubble.classList.remove('streaming');
  _twBubble.innerHTML = (_twFullText || '') + (_twImages || '');
  _twBubble = null;
  _twShown = '';
  _twFullText = '';
  _twImages = '';
  scrollToBottom();
}

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
function stopAllTTS(isNewSession = false) {
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
  window.ttsPlaying = false;

  // SE STIAMO INIZIANDO UNA NUOVA SESSIONE, NON resettiamo sessionActive/expected
  if (!isNewSession) {
    window.ttsSessionActive = false;
    window.ttsExpected = false;
    _twFinalRender(); // barge-in: show full text immediately
  }

  console.log('[TTS_INTERRUPTED_BY_USER]');
}

function _interruptTTS(reason) {
  if (_ttsSource || _isPlayingChunk || activeTTSSources.length > 0) {
    console.log('[BARGE-IN] interrupt reason=' + reason);
    stopAllTTS(false); // standard barge-in
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
  const maxChunkSize = tts_mode === 'psychological' ? 200 : 300;

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
    try {
      await Promise.race([
        ttsCtx.resume(),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1000))
      ]);
      console.log('[TTS] AudioContext resumed (blob) - state=' + ttsCtx.state);
    } catch (e) {
      console.warn('[TTS] Timeout/Errore nel resume() (blob)', e);
    }
  }

  try {
    console.log('[TTS_FLOW] step=7 calling_playTTSAudio');

    // Set current TTS chunk text for typewriter sync
    window._twCurrentText = text;

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
    try {
      await Promise.race([
        ttsCtx.resume(),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1000))
      ]);
      console.log('[TTS] AudioContext resumed - state=' + ttsCtx.state);
    } catch (e) {
      console.warn('[TTS] Timeout/Errore nel resume()', e);
    }
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

    // Set current TTS chunk text for typewriter sync
    window._twCurrentText = text;

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
      window.ttsSessionActive = true;
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
        window.ttsSessionActive = false;
        resolve();

      } catch (error) {
        console.error('[TTS] Error in playTTS:', error);
        window.ttsSessionActive = false;
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

          const reminderText = maskSensitiveText(notif.text || 'Promemoria');

          // Inserisci in chat come messaggio assistente
          addMessage(`🔔 Promemoria: ${reminderText}`, 'genesi');
          playUISound('notification');

          // Notifica desktop opzionale
          if (getSystemSetting('desktopNotifications') && 'Notification' in window && Notification.permission === 'granted') {
            try {
              new Notification('Genesi · Promemoria', {
                body: reminderText,
                icon: '/static/icon.png',
                tag: `genesi-reminder-${notif.id}`,
              });
            } catch (e) {
              console.warn('DESKTOP_NOTIFICATION_FAILED', e);
            }
          }

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

      // Handle Sync Popups
      if (data.sync_status) {
        handleSyncPopups(data.sync_status);
      }
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

function handleSyncPopups(status) {
  // 1. Google Sync (Mandatory)
  if (!status.google_synced) {
    showSyncPopup({
      type: 'google',
      title: 'Configura Google',
      text: 'Per iniziare a gestire i tuoi impegni, Genesi ha bisogno di accedere al tuo Google Calendar. È un passaggio consigliato per attivare le funzioni avanzate.',
      primaryBtn: 'Collega Google Calendar',
      secondaryBtn: 'Lo farò più tardi',
      onPrimary: () => {
        window.location.href = `/api/calendar/google/login?token=${getAuthToken()}`;
      },
      onSecondary: () => {
        closeSyncPopup();
      },
      mandatory: false
    });
    return;
  }

  // 2. iCloud Sync (Optional)
  if (!status.icloud_synced && !status.icloud_dismissed) {
    showSyncPopup({
      type: 'icloud',
      title: 'Sincronizza iCloud',
      text: 'Vuoi sincronizzare anche i tuoi promemoria Apple? Puoi farlo ora o decidere di saltare questo passaggio per sempre.',
      primaryBtn: 'Configura iCloud',
      secondaryBtn: 'Forse più tardi',
      onPrimary: () => {
        // Avvia il wizard iCloud direttamente in chat
        closeSyncPopup();
        const textInput = document.getElementById('text-input');
        if (textInput) {
          textInput.value = 'collega iCloud';
          sendMessage();
        }
      },
      onSecondary: async () => {
        await dismissICloudSync();
        closeSyncPopup();
      }
    });
  }
}

async function dismissICloudSync() {
  try {
    await fetch('/api/user/icloud/dismiss', {
      method: 'POST',
      headers: authHeaders()
    });
  } catch (e) { console.error("Dismiss fail", e); }
}

function showSyncPopup(config) {
  // Remove existing if any
  const existing = document.querySelector('.sync-modal-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.className = 'sync-modal-overlay';
  overlay.id = 'sync-modal-overlay';

  const iconSvg = config.type === 'google'
    ? `<svg viewBox="0 0 24 24"><path d="M21 12.2c0-.7-.1-1.4-.2-2H12v3.9h5c-.2 1-.8 2-1.7 2.6v2.1h2.7c1.6-1.5 2.5-3.8 2.5-6.6z" fill="#4285F4"/><path d="M12 21c2.4 0 4.5-.8 6-2.1l-2.7-2.1c-.8.5-1.8.8-3.3.8-2.5 0-4.6-1.7-5.4-4H3.9v2.1C5.4 18.7 8.5 21 12 21z" fill="#34A853"/><path d="M6.6 13.6c-.2-.5-.3-1-.3-1.6s.1-1.1.3-1.6V8.3H3.9c-.6 1.2-.9 2.5-.9 3.7s.3 2.5.9 3.7l2.7-2.1z" fill="#FBBC05"/><path d="M12 6.4c1.3 0 2.5.5 3.4 1.3l2.6-2.6C16.5 3.7 14.4 3 12 3 8.5 3 5.3 5.1 3.9 8.3l2.7 2.1c.8-2.4 2.9-4 5.4-4z" fill="#EA4335"/></svg>`
    : `<svg viewBox="0 0 24 24"><path d="M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" stroke="currentColor"/><path d="M12 6v6l4 2" stroke="currentColor" stroke-linecap="round"/></svg>`;

  overlay.innerHTML = `
    <div class="sync-modal">
      ${!config.mandatory ? `
        <button class="sync-close-btn" id="sync-close-x">
          <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </button>
      ` : ''}
      <div class="sync-icon">${iconSvg}</div>
      <h2 class="sync-title">${config.title}</h2>
      <p class="sync-text">${config.text}</p>
      <div class="sync-buttons">
        <button class="sync-btn sync-btn-primary" id="sync-primary">${config.primaryBtn}</button>
        ${config.secondaryBtn ? `<button class="sync-btn sync-btn-secondary" id="sync-secondary">${config.secondaryBtn}</button>` : ''}
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // Trigger animation
  setTimeout(() => overlay.classList.add('visible'), 50);

  document.getElementById('sync-primary').onclick = config.onPrimary;
  const sec = document.getElementById('sync-secondary');
  if (sec) sec.onclick = config.onSecondary;

  const closeX = document.getElementById('sync-close-x');
  if (closeX) closeX.onclick = closeSyncPopup;

  // Click on overlay to close (iCloud only)
  if (!config.mandatory) {
    overlay.onclick = (e) => {
      if (e.target === overlay) closeSyncPopup();
    };
  }
}

function closeSyncPopup() {
  const overlay = document.querySelector('.sync-modal-overlay');
  if (overlay) {
    overlay.classList.remove('visible');
    setTimeout(() => overlay.remove(), 400);
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
// SETTINGS MODAL
// ===============================
const settingsModal = document.getElementById('settings-modal');
const settingsBtn = document.getElementById('settings-btn');
const closeSettingsBtn = document.getElementById('close-settings-btn');
const resetMicBtn = document.getElementById('reset-mic-btn');
const settingsTabs = Array.from(document.querySelectorAll('.settings-tab'));
const settingsPanels = Array.from(document.querySelectorAll('.settings-panel'));
const resetPreferencesBtn = document.getElementById('reset-preferences-btn');

const SETTINGS_DEFAULTS = {
  desktopNotifications: false,
  uiSounds: false,
  sendOnEnter: true,
  confirmCritical: true,
  maskSensitive: true,
  newsTickerSource: 'italy',
};

const SETTINGS_INPUTS = {
  desktopNotifications: document.getElementById('setting-desktop-notifications'),
  uiSounds: document.getElementById('setting-ui-sounds'),
  sendOnEnter: document.getElementById('setting-send-on-enter'),
  confirmCritical: document.getElementById('setting-confirm-critical'),
  maskSensitive: document.getElementById('setting-mask-sensitive'),
  newsTickerSource: document.getElementById('setting-news-ticker-source'),
};

let currentSystemSettings = { ...SETTINGS_DEFAULTS };

function getStoredSystemSettings() {
  try {
    const parsed = JSON.parse(localStorage.getItem('genesi-system-settings') || '{}') || {};
    if (!['italy', 'world', 'technology'].includes(parsed.newsTickerSource)) {
      parsed.newsTickerSource = SETTINGS_DEFAULTS.newsTickerSource;
    }
    return { ...SETTINGS_DEFAULTS, ...parsed };
  } catch (e) {
    return { ...SETTINGS_DEFAULTS };
  }
}

function applySystemSettingsRuntime(settings) {
  currentSystemSettings = { ...SETTINGS_DEFAULTS, ...(settings || {}) };
  document.body.classList.toggle('privacy-mask-sensitive', !!currentSystemSettings.maskSensitive);
}

function getSystemSetting(key) {
  return !!getSystemSettingValue(key);
}

function getSystemSettingValue(key, fallback = null) {
  if (Object.prototype.hasOwnProperty.call(currentSystemSettings, key)) {
    return currentSystemSettings[key];
  }
  return fallback;
}

function shouldConfirmCritical() {
  return getSystemSetting('confirmCritical');
}

function askCriticalConfirm(message) {
  if (!shouldConfirmCritical()) return true;
  return confirm(message);
}

function maskSensitiveText(text) {
  const raw = String(text || '');
  if (!getSystemSetting('maskSensitive')) return raw;
  return raw
    .replace(/([\w.+-]{2})[\w.+-]*@([\w-]+\.[\w.-]+)/g, '$1***@$2')
    .replace(/\b(\d{2})\d{4,}(\d{2})\b/g, '$1••••$2')
    .replace(/\b([A-Za-z0-9_\-]{3})[A-Za-z0-9_\-]{6,}\b/g, '$1••••');
}

async function ensureDesktopNotificationPermission() {
  if (!('Notification' in window)) return false;
  if (Notification.permission === 'granted') return true;
  if (Notification.permission === 'denied') return false;
  try {
    const permission = await Notification.requestPermission();
    return permission === 'granted';
  } catch (e) {
    return false;
  }
}

function playUISound(kind = 'tap') {
  if (!getSystemSetting('uiSounds')) return;
  const ctx = window.audioContext;
  if (!ctx) return;
  const baseFreq = kind === 'notification' ? 880 : kind === 'receive' ? 720 : 560;
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = baseFreq;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.04, ctx.currentTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.11);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.12);
  } catch (e) {
    console.warn('[UI_SOUND] playback failed', e);
  }
}

function loadSystemSettings() {
  const finalSettings = getStoredSystemSettings();
  Object.entries(SETTINGS_INPUTS).forEach(([key, el]) => {
    if (!el) return;
    if (el.type === 'checkbox') {
      el.checked = !!finalSettings[key];
      return;
    }
    el.value = finalSettings[key];
  });
  applySystemSettingsRuntime(finalSettings);
}

async function saveSystemSettings() {
  const payload = { ...SETTINGS_DEFAULTS };
  Object.entries(SETTINGS_INPUTS).forEach(([key, el]) => {
    if (!el) return;
    if (el.type === 'checkbox') {
      payload[key] = !!el.checked;
      return;
    }
    payload[key] = String(el.value || SETTINGS_DEFAULTS[key]);
  });
  if (!['italy', 'world', 'technology'].includes(payload.newsTickerSource)) {
    payload.newsTickerSource = SETTINGS_DEFAULTS.newsTickerSource;
  }
  localStorage.setItem('genesi-system-settings', JSON.stringify(payload));
  const previousTickerSource = currentSystemSettings.newsTickerSource;
  applySystemSettingsRuntime(payload);

  if (payload.desktopNotifications) {
    await ensureDesktopNotificationPermission();
  }

  if (payload.newsTickerSource !== previousTickerSource && typeof initializeNewsTicker === 'function') {
    initializeNewsTicker();
  }
}

function activateSettingsTab(tabName) {
  settingsTabs.forEach((tab) => {
    const active = tab.dataset.settingsTab === tabName;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
  });

  settingsPanels.forEach((panel) => {
    const active = panel.dataset.settingsPanel === tabName;
    panel.classList.toggle('hidden', !active);
  });

  if (tabName === 'sync') {
    loadIntegrationsStatus();
  }
}

if (settingsBtn) {
  settingsBtn.onclick = () => {
    settingsModal.classList.remove('hidden');
    loadSystemSettings();
    activateSettingsTab('system');
  };
}

if (closeSettingsBtn) {
  closeSettingsBtn.onclick = () => settingsModal.classList.add('hidden');
}

if (resetMicBtn) {
  resetMicBtn.onclick = () => {
    if (typeof stopVoiceMode === 'function') stopVoiceMode();
    setTimeout(() => {
      if (typeof startVoiceMode === 'function') startVoiceMode();
      console.log('🧪 MANUAL MIC RESTART TRIGGERED');
      settingsModal.classList.add('hidden');
    }, 300);
  };
}

if (resetPreferencesBtn) {
  resetPreferencesBtn.onclick = () => {
    Object.entries(SETTINGS_INPUTS).forEach(([key, el]) => {
      if (!el) return;
      if (el.type === 'checkbox') {
        el.checked = !!SETTINGS_DEFAULTS[key];
        return;
      }
      el.value = SETTINGS_DEFAULTS[key];
    });
    saveSystemSettings();
  };
}

settingsTabs.forEach((tab) => {
  tab.addEventListener('click', () => activateSettingsTab(tab.dataset.settingsTab));
});

Object.values(SETTINGS_INPUTS).forEach((inputEl) => {
  if (inputEl) {
    inputEl.addEventListener('change', saveSystemSettings);
  }
});

loadSystemSettings();

// Combined background click for modals
window.addEventListener('click', (e) => {
  if (e.target === settingsModal) {
    settingsModal.classList.add('hidden');
  }
  const icloudModal = document.getElementById('icloud-modal');
  if (e.target === icloudModal) {
    icloudModal.classList.add('hidden');
  }
});

// ===============================
// INTEGRATIONS PANEL
// ===============================

async function loadIntegrationsStatus() {
  const list = document.getElementById('integrations-list');
  if (!list) return;
  list.innerHTML = '<div class="intg-loading">Caricamento...</div>';

  try {
    const res = await fetch('/api/integrations/status', {
      headers: { 'Authorization': 'Bearer ' + getAuthToken() },
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    renderIntegrationsList(data.integrations || []);
  } catch (e) {
    list.innerHTML = '<div class="intg-loading">Errore caricamento integrazioni.</div>';
  }
}

function renderIntegrationsList(integrations) {
  const list = document.getElementById('integrations-list');
  if (!list) return;

  if (!integrations.length) {
    list.innerHTML = '<div class="intg-loading">Nessuna integrazione disponibile.</div>';
    return;
  }

  list.innerHTML = integrations.map(intg => {
    const isAutomation = intg.type === 'automation';
    const isConnected = !isAutomation && intg.connected && (intg.linked !== false);

    let statusLabel, statusClass, btnHtml;

    if (isAutomation) {
      statusLabel = '◈ Via OpenClaw';
      statusClass = 'automation';
      btnHtml = `<span class="intg-badge-auto">PC automation</span>`;
    } else if (isConnected) {
      statusLabel = '● Connesso';
      statusClass = 'connected';
      btnHtml = `<button class="intg-btn disconnect" onclick="disconnectIntegration('${intg.platform}')">Disconnetti</button>`;
    } else {
      statusLabel = '○ Non collegato';
      statusClass = 'disconnected';
      btnHtml = `<button class="intg-btn connect" onclick="connectIntegration('${intg.platform}')">Collega</button>`;
    }

    return `
      <div class="intg-item" id="intg-item-${intg.platform}">
        <span class="intg-icon">${intg.icon || '🔗'}</span>
        <div class="intg-info">
          <span class="intg-name">${intg.display_name}</span>
          <span class="intg-status ${statusClass}">${statusLabel}</span>
        </div>
        ${btnHtml}
      </div>`;
  }).join('');
}

function _startWizardInChat(platform) {
  if (settingsModal) settingsModal.classList.add('hidden');
  const textInput = document.getElementById('text-input');
  if (textInput && typeof sendMessage === 'function') {
    textInput.value = `configura ${platform}`;
    setTimeout(() => {
      sendMessage();
    }, 100);
  }
}

const WIZARD_PLATFORMS = new Set(['facebook', 'instagram', 'tiktok', 'telegram', 'gmail', 'google_calendar', 'icloud']);

async function connectIntegration(platform) {
  const token = getAuthToken();

  if (platform === 'whatsapp') {
    if (settingsModal) settingsModal.classList.add('hidden');
    const textInput = document.getElementById('text-input');
    if (textInput && typeof sendMessage === 'function') {
      textInput.value = 'manda un messaggio su WhatsApp';
      setTimeout(() => {
        sendMessage();
      }, 100);
    }
    return;
  }

  // Piattaforme gestite da OpenClaw via chat
  if (WIZARD_PLATFORMS.has(platform)) {
    _startWizardInChat(platform);
    return;
  }

  // OAuth platforms: open popup
  const connectUrl = `/api/integrations/${platform}/connect?token=${encodeURIComponent(token)}`;
  const popup = window.open(
    connectUrl,
    'genesi_connect_' + platform,
    'width=560,height=660,scrollbars=yes,resizable=yes'
  );

  // Poll for popup close to refresh status
  const checkClosed = setInterval(() => {
    if (!popup || popup.closed) {
      clearInterval(checkClosed);
      setTimeout(() => loadIntegrationsStatus(), 1000);
    }
  }, 800);
}

async function disconnectIntegration(platform) {
  if (!askCriticalConfirm(`Vuoi davvero disconnettere ${platform}?`)) return;

  try {
    await fetch(`/api/integrations/${platform}/disconnect`, {
      method: 'DELETE',
      headers: { 'Authorization': 'Bearer ' + getAuthToken() },
    });
    await loadIntegrationsStatus();
  } catch (e) {
    alert('Errore durante la disconnessione.');
  }
}

let imageLightbox = null;

function ensureImageLightbox() {
  if (imageLightbox) return imageLightbox;

  imageLightbox = document.createElement('div');
  imageLightbox.id = 'image-lightbox';
  imageLightbox.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.88);z-index:9999;align-items:center;justify-content:center;padding:20px;';
  imageLightbox.style.display = 'none';
  imageLightbox.innerHTML = `
    <button type="button" aria-label="Chiudi anteprima" data-lightbox-close="1" style="position:absolute;top:14px;right:14px;border:0;background:rgba(255,255,255,0.12);color:#fff;font-size:28px;line-height:1;cursor:pointer;border-radius:10px;width:42px;height:42px;">×</button>
    <img alt="Anteprima immagine" style="max-width:min(95vw,1400px);max-height:90vh;width:auto;height:auto;object-fit:contain;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,0.45);">
  `;

  imageLightbox.addEventListener('click', (e) => {
    if (e.target === imageLightbox || e.target.closest('[data-lightbox-close]')) {
      closeImageLightbox();
    }
  });

  document.body.appendChild(imageLightbox);
  return imageLightbox;
}

function openImageLightbox(url, title) {
  if (!url) return;
  const lb = ensureImageLightbox();
  const img = lb.querySelector('img');
  img.src = url;
  img.alt = title || 'Anteprima immagine';
  lb.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closeImageLightbox() {
  if (!imageLightbox) return;
  const img = imageLightbox.querySelector('img');
  if (img) img.removeAttribute('src');
  imageLightbox.style.display = 'none';
  document.body.style.overflow = '';
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && imageLightbox && imageLightbox.style.display !== 'none') {
    closeImageLightbox();
  }
});

dialogue.addEventListener('click', (e) => {
  const image = e.target.closest('.chat-image-preview');
  if (!image) return;
  e.preventDefault();
  const fullUrl = image.dataset.fullUrl;
  const title = image.dataset.title;
  openImageLightbox(fullUrl, title);
});

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

  const escapeAttr = (value) => String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  let html = '<div class="image-grid" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">';
  images.forEach(img => {
    const thumb = img.thumbnail || img.url;
    const fullUrl = img.url || thumb;
    const title = img.title || 'Immagine generata';
    const source = img.source || '';
    html += `
            <div style="width:240px;max-width:100%;text-align:center;">
                <img src="${thumb}" 
                     alt="${escapeAttr(title)}"
                     data-full-url="${escapeAttr(fullUrl)}"
                     data-title="${escapeAttr(title)}"
                     class="chat-image-preview"
                     loading="lazy"
                     onerror="this.parentElement.style.display='none'"
                     style="width:100%;height:170px;object-fit:cover;border-radius:10px;cursor:pointer;border:1px solid rgba(255,255,255,0.15);">
                <div style="font-size:11px;color:#888;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeAttr(source)}</div>
            </div>`;
  });
  html += '</div>';
  return html;
}

function renderMessageContent(text) {
  if (!text) return "";

  // 1. Placeholder replacement (e.g., token for auth links)
  const token = getAuthToken() || "";
  let html = text.replace(/{{token}}/g, token);
  html = html.replace(/%7B%7Btoken%7D%7D/g, token); // URL-encoded version

  // Escape HTML helper
  const escape = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // 2. Code blocks (```lang ... ```)
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre class="code-block"><code class="${lang ? 'lang-' + lang : ''}">${escape(code.trim())}</code></pre>`;
  });

  // 3. Markdown Links [Label](URL)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
    const resolvedUrl = url.replace(/\{\{token\}\}|%7B%7Btoken%7D%7D/gi, token);
    // Links that start with /api/integrations/.../connect get a button style
    const isConnectLink = /\/api\/integrations\/[^/]+\/connect/.test(resolvedUrl)
      || /\/api\/integrations\/telegram\/link-token/.test(resolvedUrl);
    const cls = isConnectLink ? 'chat-connect-btn' : 'chat-link';
    return `<a href="${resolvedUrl}" target="_blank" class="${cls}">${escape(label)}</a>`;
  });

  // 4. Bold and Italic
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // 5. Inline code (`code`)
  html = html.replace(/`([^`]+)`/g, (_, code) => `<code class="inline-code">${escape(code)}</code>`);

  // 6. Lists
  // Simplified: lines starting with "- " or "* " become list items
  html = html.split('\n').map(line => {
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      return `<li style="margin-left: 20px; margin-bottom: 4px; list-style-type: none;">✦ ${line.trim().substring(2)}</li>`;
    }
    return line;
  }).join('\n');

  // 7. Newline -> <br> (only outside pre and li blocks)
  html = html.replace(/(?<!<\/pre>|<\/li>)\n(?!<pre|<li)/g, '<br>');

  return html;
}


function addMessage(text, sender) {
  const el = document.createElement('div');
  el.className = `message ${sender}`;

  // Parse response per gestire immagini
  const parsed = parseResponse(text);

  // Usa renderMessageContent per formattazione code blocks + escape HTML
  const renderedContent = renderMessageContent(parsed.text);

  if (sender === 'user' && parsed.text.length > 500 && parsed.text.includes('\n')) {
    const snippetHtml = `
      <div class="long-text-snippet">
        <div class="snippet-header">
          <span class="snippet-title">📄 Documento di testo (${parsed.text.length} caratteri)</span>
          <div class="snippet-controls">
            <button class="expand-btn">Espandi</button>
            <button class="download-btn">Scarica</button>
          </div>
        </div>
        <div class="snippet-content" style="display:none;">
          ${renderedContent}
        </div>
      </div>
    `;
    el.innerHTML = snippetHtml + renderImages(parsed.images);

    // Gestione eventi per espandere/collassare e scaricare
    const expandBtn = el.querySelector('.expand-btn');
    const contentDiv = el.querySelector('.snippet-content');
    expandBtn.addEventListener('click', (e) => {
      e.preventDefault();
      if (contentDiv.style.display === 'none') {
        contentDiv.style.display = 'block';
        expandBtn.textContent = 'Riduci';
      } else {
        contentDiv.style.display = 'none';
        expandBtn.textContent = 'Espandi';
      }
      setTimeout(scrollToBottom, 50);
    });

    const dlBtn = el.querySelector('.download-btn');
    dlBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const blob = new Blob([parsed.text], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = "allegato.txt";
      a.click();
      URL.revokeObjectURL(url);
    });
  } else {
    el.innerHTML = renderedContent + renderImages(parsed.images);
  }

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

function updateAgentStatus(statusData) {
  if (!statusData) {
    hideThinking();
    return;
  }

  // Handle both string and object { text, screenshot }
  const text = typeof statusData === 'string' ? statusData : statusData.text;
  showThinking(text || 'Sto lavorando in background...');
  scrollToBottom();
}

// ===============================
// CHAT API — STREAMING (SSE)
// ===============================
/**
 * Streaming version of sendChatMessage.
 * Returns { response, tts_text } when done, or throws on error.
 * Calls onChunk(text) for each incremental chunk, onFirstChunk() when streaming starts.
 */
async function sendChatMessageStream(message, { onChunk, onFirstChunk } = {}) {
  if (currentMode === 'coding') throw new Error('streaming not supported in coding mode');

  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { ...authHeaders(), 'Accept': 'text/event-stream' },
    body: JSON.stringify({
      message,
      conversation_id: typeof currentConvId !== 'undefined' ? currentConvId : null
    })
  });

  if (res.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed) return sendChatMessageStream(message, { onChunk, onFirstChunk });
    doLogout();
    throw new Error('Session expired');
  }
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';
  let ttsText = '';
  let firstChunkFired = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete line

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      let evt;
      try { evt = JSON.parse(line.slice(6)); } catch { continue; }

      if (evt.chunk) {
        // Non nascondere il thinking — la risposta è pronta ma l'audio non ha ancora iniziato
        fullText += evt.chunk;
        if (!firstChunkFired) {
          firstChunkFired = true;
          if (onFirstChunk) onFirstChunk();
        }
        if (onChunk) onChunk(fullText);
      } else if (evt.status) {
        updateAgentStatus(evt.status);
      } else if (evt.synthesis_pending) {
        updateAgentStatus('Sintetizzando risposta finale...');
        fullText = '';
        if (onChunk) onChunk(''); // empty → bubble shows just cursor mentre synthesis gira
      } else if (evt.done) {
        showThinking(null, 'voice');
        ttsText = evt.done_tts || evt.tts_text || fullText;
        // Se il backend fornisce 'response' (es: payload JSON per le immagini), usa quello!
        const finalResponse = typeof evt.response !== 'undefined' ? evt.response : (ttsText || fullText);

        // Prioritize ttsText (synthesis) so tool results are displayed correctly.
        // Fall back to fullText for pure-streaming routes where ttsText is empty.
        return { response: finalResponse, tts_text: ttsText };
      } else if (evt.error) {
        throw new Error(evt.error);
      }
    }
  }
  // Stream ended without explicit done event
  return { response: fullText, tts_text: fullText };
}

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
      body: JSON.stringify({
        message,
        conversation_id: typeof currentConvId !== 'undefined' ? currentConvId : null
      })
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

  // Barge-in: stop EVERYTHING and lock mic
  ttsGenerationId++;
  stopAllTTS(false); // Barge-in clear
  window.isGenesiSpeaking = true;
  if (voiceRecognition && recognitionActive) {
    try { voiceRecognition.stop(); } catch (e) { }
  }

  // Warm AudioContext NOW (sync, during user gesture) — iOS requires this
  _warmTTSCtx();

  const text = textToUse;
  console.log('SEND_MSG_STATE state=' + currentState + ' text_len=' + text.length);
  if (!text || currentState !== STATES.IDLE) {
    window.isGenesiSpeaking = false; // RELEASE LOCK if msg skipped
    return;
  }

  textInput.value = '';
  textInput.style.height = '44px';
  autoResizeInput(textInput);

  // Decide if we keep focus on the input box based on device
  const isMobile = window.innerWidth <= 768 || ('ontouchstart' in window) || navigator.maxTouchPoints > 0;
  if (isMobile) {
    textInput.blur(); // Chiude la tastiera su mobile
  } else {
    setTimeout(() => textInput.focus(), 10); // Mantiene fissa la tastiera pronta per scrivere su pc
  }

  // Pulse shockwave on send
  const ic = document.getElementById('input-container');
  ic.classList.remove('pulse');
  void ic.offsetWidth;
  ic.classList.add('pulse');

  addUserMessage(text);
  playUISound('tap');

  // Salva messaggio utente nella conversazione corrente
  saveMessageToConversation('user', text);

  // PARTE 1: Mostra animazione thinking come messaggio reale
  setState(STATES.THINKING);
  window.ttsExpected = false; // Reset per ogni nuovo messaggio
  window.responseProcessed = false;

  // Determina se è una query per l'archivio della memoria
  const memoryTriggers = [
    "prima", "abbiamo parlato", "ricordi", "ricordarmi",
    "l'altra volta", "ieri", "di cosa", "come mi chiamo",
    "ti ricordi", "cosa abbiamo detto", "cosa dicevamo",
    "sai cosa", "ricordi cosa", "mi ricordi", "ci siamo detti",
    "avevamo parlato", "discusso", "avevamo detto",
    "questa chat", "vecchia chat", "archivio"
  ];
  const isMemoryQuery = memoryTriggers.some(t => text.toLowerCase().includes(t));

  if (isMemoryQuery && window.currentConvId) {
    showThinking("Sto rileggendo l'archivio di questa chat...");
  } else {
    showThinking();
  }

  console.log('FRONTEND_THINKING_START');

  try {
    let data;
    let alreadyRendered = false;

    // ── STREAMING PATH (non in coding mode) ─────────────────────────────────
    if (currentMode !== 'coding') {
      let streamBubble = null;
      try {
        data = await sendChatMessageStream(text, {
          onFirstChunk: () => {
            // Non nascondere thinking qui — lo farà _startTypewriterChunk quando l'audio parte
            streamBubble = document.createElement('div');
            streamBubble.className = 'message genesi streaming';
            const hue = _neonHues[_neonIdx % _neonHues.length];
            streamBubble.style.setProperty('--neon-hue', hue + 'deg');
            _neonIdx++;
            dialogue.appendChild(streamBubble);
            // Init typewriter state
            _twBubble = streamBubble;
            _twShown = '';
            _twFullText = '';
            _twImages = '';
            clearTimeout(_twTimeout);
            scrollToBottom();
          },
          onChunk: (fullText) => {
            if (streamBubble) {
              // Show only cursor while TTS will drive the typewriter
              streamBubble.innerHTML = '<span class="stream-cursor"></span>';
              scrollToBottom();
            }
          }
        });

        if (data && data.response && streamBubble) {
          const parsed = handleChatResponse(data.response);
          streamBubble.classList.remove('streaming');
          // Save for _twFinalRender — TTS will drive typewriter, render markdown at end
          _twFullText = renderMessageContent(parsed.text);
          _twImages = renderImages(parsed.images);
          streamBubble.innerHTML = '<span class="stream-cursor"></span>';
          saveMessageToConversation('assistant', parsed.text);
          playUISound('receive');
          scrollToBottom();
          alreadyRendered = true;
        } else if (!data?.response) {
          if (streamBubble) { streamBubble.remove(); streamBubble = null; }
          return;
        }
      } catch (streamErr) {
        console.warn('[STREAM_FALLBACK] errore streaming, uso endpoint normale:', streamErr.message);
        if (streamBubble) { streamBubble.remove(); streamBubble = null; }
        data = await sendChatMessage(text);
      }
    } else {
      // Coding mode: endpoint normale
      data = await sendChatMessage(text);
    }

    console.log('[FRONTEND] response received');

    // ── RENDER NORMALE (fallback o coding mode) ──────────────────────────────
    if (!alreadyRendered) {
      const botMessage = data.response;
      if (!botMessage || botMessage.trim().length === 0) return;
      console.log(`LLM_RESPONSE_LENGTH: ${botMessage.length} chars`);
      hideThinking();
      const parsed = handleChatResponse(botMessage);
      if (parsed.images && parsed.images.length > 0) {
        addMessage(parsed.text, 'genesi');
        saveMessageToConversation('assistant', parsed.text);
        playUISound('receive');
        const lastMsg = document.querySelector('.message.genesi:last-child');
        if (lastMsg) lastMsg.insertAdjacentHTML('beforeend', renderImages(parsed.images));
      } else {
        addMessage(parsed.text, 'genesi');
        saveMessageToConversation('assistant', parsed.text);
        playUISound('receive');
      }
    }
    console.log('[TEXT_RENDERED] text_len=' + (data?.response?.length || 0));

    // TTS ASINCRONO — completamente scollegato dal render
    const rawTtsText = (typeof data.tts_text !== 'undefined') ? data.tts_text : data.response;
    function stripCodeForTTS(text) {
      if (!text) return "";
      return text
        .replace(/```[\s\S]*?```/g, '. ')
        .replace(/`[^`]+`/g, '')
        .trim();
    }
    const ttsText = (currentMode === 'coding') ? stripCodeForTTS(rawTtsText) : rawTtsText;

    // RELEASE IF NO TTS EXPECTED
    if (!ttsText || ttsText.trim().length === 0) {
      console.log('[TTS_ASYNC] Skipped: empty tts text');
      window.ttsExpected = false;
      window.isGenesiSpeaking = false;
      _twFinalRender();
      return;
    }


    // Se la risposta contiene mic_control, forziamo lo stato (Surgical Fix)
    if (data.mic_control && data.mic_control.type === 'TTS_START') {
      window.isGenesiSpeaking = true;
      if (voiceRecognition && recognitionActive) {
        try { voiceRecognition.stop(); } catch (e) { }
      }

      // FAILSAFE: Proactive reset after 60s to prevent stuck mic on long errors
      setTimeout(() => {
        if (window.isGenesiSpeaking) {
          window.isGenesiSpeaking = false;
          console.log('⏰ TTS_FAILSAFE: Force releasing mic after 60s');
          if (voiceModeActive && !recognitionActive) {
            try { voiceRecognition?.start(); } catch (e) { }
          }
        }
      }, 60000);
    }

    // Se ttsText è vuoto o solo spazi dopo il filtro, non chiamare TTS affatto
    if (!ttsText || ttsText.trim().length === 0) {
      console.log('[TTS_ASYNC] Skipped: empty after code filtering or no text');
      window.ttsExpected = false;
      _twFinalRender();
      return;
    }

    console.log('[TTS_ASYNC_START] tts_text_len=' + ttsText.length);
    window.ttsExpected = true;
    window.responseProcessed = true; // ATOMIC: Only now the poller can proceed
    playTTSAsync(ttsText, data.tts_mode);

  } catch (e) {
    console.error('Chat error:', e);
    window.isGenesiSpeaking = false; // RELEASE LOCK on error
    window.responseProcessed = true;
    window.ttsExpected = false;
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
  // Ferma qualsiasi TTS attualmente in corso per evitare sovrapposizioni
  // Segnala che stiamo per iniziare una nuova sessione
  stopAllTTS(true);
  window.ttsExpected = true;
  window.isGenesiSpeaking = true; // MIC KILLER START
  if (voiceRecognition && recognitionActive) {
    try { voiceRecognition.stop(); } catch (e) { }
  }

  // Reset abort flag + create fresh AbortController for this generation
  _ttsAborted = false;
  window.ttsSessionActive = true; // Impedisce riavvio mic mentre IIFE si avvia
  currentTTSAbortController = new AbortController();
  const myGenId = ttsGenerationId;

  // Fire-and-forget: TTS non blocca MAI il render del testo
  (async () => {
    try {
      console.log('[TTS_ASYNC] Starting TTS genId=' + myGenId + ' len=' + text.length + ' mode=' + mode);
      await playTTS(text, mode);
      console.log('[TTS_ASYNC] TTS completed genId=' + myGenId);
      _twFinalRender();
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
function showThinking(labelText = null, mode = 'thinking') {
  let thinking = document.getElementById("genesi-thinking");
  const isAnimated = !labelText;

  if (!thinking) {
    thinking = document.createElement("div");
    thinking.className = "thinking-row";
    thinking.id = "genesi-thinking";
    thinking.innerHTML = `
      <div class="thinking-label"></div>
      <div class="thinking-dots">
        <span></span>
        <span></span>
        <span></span>
      </div>
    `;

    dialogue.appendChild(thinking);
  }

  const labelEl = thinking.querySelector('.thinking-label');
  if (!labelEl) return;

  if (thinkingLabelTimer) {
    clearInterval(thinkingLabelTimer);
    thinkingLabelTimer = null;
  }

  if (isAnimated) {
    thinking.dataset.animated = 'true';
    thinking.dataset.mode = mode;
    if (mode === 'voice') {
      voiceStepIndex = 0;
      labelEl.textContent = VOICE_STEPS[voiceStepIndex];
      thinkingLabelTimer = setInterval(() => {
        const node = document.getElementById('genesi-thinking');
        if (!node || node.dataset.animated !== 'true') return;
        voiceStepIndex = (voiceStepIndex + 1) % VOICE_STEPS.length;
        const lbl = node.querySelector('.thinking-label');
        if (lbl) lbl.textContent = VOICE_STEPS[voiceStepIndex];
      }, 1200);
    } else {
      labelEl.textContent = THINKING_STEPS[thinkingStepIndex % THINKING_STEPS.length];
      thinkingLabelTimer = setInterval(() => {
        const node = document.getElementById('genesi-thinking');
        if (!node || node.dataset.animated !== 'true') return;
        thinkingStepIndex = (thinkingStepIndex + 1) % THINKING_STEPS.length;
        const lbl = node.querySelector('.thinking-label');
        if (lbl) lbl.textContent = THINKING_STEPS[thinkingStepIndex];
      }, 1400);
    }
  } else {
    thinking.dataset.animated = 'false';
    labelEl.textContent = labelText;
  }

  dialogue.scrollTop = dialogue.scrollHeight;
}

function hideThinking() {
  if (thinkingLabelTimer) {
    clearInterval(thinkingLabelTimer);
    thinkingLabelTimer = null;
  }
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
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
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
      if (result.response) playTTSAsync(result.response, result.tts_mode || 'normal');

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
    if (data.response) playTTSAsync(data.response, data.tts_mode || 'normal');

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
  if (e.key === 'Enter' && !e.shiftKey && getSystemSetting('sendOnEnter')) {
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

    return new Promise((resolve) => {
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);

      console.log('[TTS] AudioBufferSource creato genId=' + myGenId);

      // Track in activeTTSSources
      activeTTSSources.push(source);

      let forceCleanupTimeout = null;

      // Cleanup helper
      const cleanup = () => {
        if (forceCleanupTimeout) {
          clearTimeout(forceCleanupTimeout);
          forceCleanupTimeout = null;
        }
        const idx = activeTTSSources.indexOf(source);
        if (idx > -1) activeTTSSources.splice(idx, 1);
        if (_ttsSource === source) _ttsSource = null;
        _isPlayingChunk = false;
        window.ttsPlaying = false;
        window.lastTTSEnd = Date.now();
        resolve(); // Sblocca l'attesa
      };

      // Configura eventi
      source.onended = () => {
        console.log('[TTS] Playback completato genId=' + myGenId);
        cleanup();
      };

      // Imposta timestamp TTS PRIMA del playback
      window.lastTTSStart = Date.now();

      // Set variables before start
      window.ttsPlaying = true;
      _wasPlayingChunk = true;
      _isPlayingChunk = true;

      // Avvia typewriter sincronizzato con l'audio
      _startTypewriterChunk(window._twCurrentText || '', audioBuffer.duration * 1000);

      // Avvia playback
      console.log('[TTS] Avvio playback genId=' + myGenId);
      source.start(0);

      // Timeout di sicurezza per evitare blocchi infiniti su iOS
      // Safari (se la Context è rimasta suspendata l'onended non scatta mai)
      const durationMs = (audioBuffer.duration || 0) * 1000;
      const safetyDelay = durationMs > 0 ? durationMs + 2000 : 5000; // Margine di 2 secondi (o 5s se duration sconosciuta)

      forceCleanupTimeout = setTimeout(() => {
        console.warn(`[TTS] Safety timeout (${safetyDelay}ms) triggerato per genId=${myGenId}. Forziamo il cleanup!`);
        try { source.stop(); } catch (e) { }
        cleanup();
      }, safetyDelay);
    });

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

// ── CONV TAB FILTER ──
window.switchConvTab = function (filter) {
  currentConvFilter = filter;
  document.querySelectorAll('.conv-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === filter);
  });
  loadConversations();
};

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

  // Filter by active mode tab
  const filtered = convs.filter(c => (c.conv_type || 'chat') === currentConvFilter);

  // Sort conversations: pinned first, then by the original backend date sorting
  filtered.sort((a, b) => {
    if (a.pinned === b.pinned) return 0;
    return a.pinned ? -1 : 1;
  });

  filtered.forEach(c => {
      const safeTitle = maskSensitiveText(c.title || 'Conversazione');
    const item = document.createElement('div');
    item.className = 'conv-item' + (c.id === currentConvId ? ' active' : '') + (c.pinned ? ' pinned' : '');
    item.dataset.id = c.id;
    item.innerHTML = `
        <span class="conv-title" title="${safeTitle}">${c.pinned ? '📌 ' : ''}${safeTitle}</span>
            <div class="conv-actions">
                <button class="conv-btn" onclick="togglePinConv('${c.id}', ${!c.pinned})" title="${c.pinned ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}">${c.pinned ? '★' : '☆'}</button>
                <button class="conv-btn" onclick="renameConv('${c.id}')" title="Rinomina">✎</button>
                <button class="conv-btn" onclick="deleteConv('${c.id}')" title="Elimina">✕</button>
            </div>`;
    item.addEventListener('click', (e) => {
      if (e.target.closest('.conv-btn')) return;
      openConversation(c.id);

      // Nascondi sidebar su mobile (larghezza <= 768px di solito, ma chiudiamo la sidebar)
      if (window.innerWidth <= 768) {
        document.getElementById('sidebar').classList.add('sidebar-collapsed');
        if (document.getElementById('sidebar-toggle-clean')) {
          document.getElementById('sidebar-toggle-clean').style.setProperty('display', 'flex', 'important');
        }
      }
    });
    list.appendChild(item);
  });
}

window.togglePinConv = async function (convId, pinValue) {
  await fetch(`/api/conversations/${convId}/pin`, {
    method: 'PATCH',
    headers: { 'Authorization': `Bearer ${getAuthToken()}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ pinned: pinValue })
  });
  await loadConversations();
};

window.clearAllConvs = async function () {
  if (!confirm('Stai per svuotare TUTTE le chat. Questa azione è irreversibile. Vuoi procedere?')) return;
  await fetch('/api/conversations', {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${getAuthToken()}` }
  });
  currentConvId = null;
  clearChat();
  await loadConversations();
};

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
  if (!askCriticalConfirm('Eliminare questa conversazione?')) return;
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
}

function toggleCodingMode() {
  const codingBtn = document.getElementById('coding-mode-btn');

  // Toggle mode
  if (currentMode === "chat") {
    currentMode = "coding";
    currentConvFilter = "coding";
    codingBtn.classList.add('active');
    codingBtn.style.backgroundColor = '#00ff88';
    codingBtn.style.color = '#000';
    document.body.classList.add('coding-active');
    startMatrixAnimation();
    console.log('CODING_MODE_ACTIVATED');
  } else {
    currentMode = "chat";
    currentConvFilter = "chat";
    codingBtn.classList.remove('active');
    codingBtn.style.backgroundColor = '';
    codingBtn.style.color = '';
    document.body.classList.remove('coding-active');
    stopMatrixAnimation();
    console.log('CODING_MODE_DEACTIVATED');
  }

  // Update tab UI active state
  document.querySelectorAll('.conv-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === currentConvFilter);
  });

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
        await fetch(`/ api / conversations / ${c.id}`, {
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
      (c.title === 'Nuova chat' || !c.title) &&
      (c.conv_type || 'chat') === currentMode
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
        headers: { 'Authorization': `Bearer ${getAuthToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ conv_type: currentMode })
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

const NEWS_TICKER_SOURCES = {
  italy: {
    label: 'News Italia',
    rssUrls: [
      'https://news.google.com/rss?hl=it&gl=IT&ceid=IT:it',
    ],
  },
  world: {
    label: 'News Mondo',
    rssUrls: [
      'https://news.google.com/rss/headlines/section/topic/WORLD?hl=it&gl=IT&ceid=IT:it',
      'https://news.google.com/rss?hl=it&gl=IT&ceid=IT:it',
    ],
  },
  technology: {
    label: 'Tecnologia',
    rssUrls: [
      'https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=it&gl=IT&ceid=IT:it',
    ],
  },
};

let newsTickerState = {
  animation: null,
  source: SETTINGS_DEFAULTS.newsTickerSource,
  mobilePaused: false,
};

function normalizeTickerSource(source) {
  return Object.prototype.hasOwnProperty.call(NEWS_TICKER_SOURCES, source) ? source : SETTINGS_DEFAULTS.newsTickerSource;
}

function escapeHtml(raw) {
  return String(raw || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

async function fetchTickerFeed(rssUrl) {
  const endpoint = `https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(rssUrl)}`;
  const response = await fetch(endpoint);
  if (!response.ok) {
    throw new Error(`Ticker feed unavailable (${response.status})`);
  }
  const payload = await response.json();
  if (payload.status !== 'ok' || !Array.isArray(payload.items)) {
    throw new Error('Ticker feed payload invalid');
  }
  return payload.items;
}

async function fetchTickerItemsFromBackend(source) {
  const endpoint = `/api/news/ticker?source=${encodeURIComponent(source)}`;
  const response = await fetch(endpoint, {
    headers: {
      'Authorization': `Bearer ${getAuthToken()}`,
    },
  });
  if (!response.ok) {
    throw new Error(`Ticker backend unavailable (${response.status})`);
  }
  const payload = await response.json();
  if (!payload || !Array.isArray(payload.items)) {
    throw new Error('Ticker backend payload invalid');
  }
  return payload.items
    .map((item) => ({
      link: String(item.link || '').trim(),
      title: String(item.title || '').trim(),
    }))
    .filter((item) => item.link && item.title);
}

async function loadTickerItems(source) {
  try {
    const backendItems = await fetchTickerItemsFromBackend(source);
    if (backendItems.length) {
      return backendItems;
    }
  } catch (err) {
    console.warn('[TICKER] backend source error', source, err);
  }

  const selected = NEWS_TICKER_SOURCES[source] || NEWS_TICKER_SOURCES[SETTINGS_DEFAULTS.newsTickerSource];
  const allItems = [];

  for (const feedUrl of selected.rssUrls) {
    try {
      const items = await fetchTickerFeed(feedUrl);
      allItems.push(...items);
    } catch (err) {
      console.warn('[TICKER] feed error', feedUrl, err);
    }
  }

  const deduped = [];
  const seenLinks = new Set();
  for (const item of allItems) {
    const link = String(item.link || '').trim();
    const title = String(item.title || '').trim();
    if (!link || !title || seenLinks.has(link)) continue;
    seenLinks.add(link);
    deduped.push({ link, title });
    if (deduped.length >= 14) break;
  }

  return deduped;
}

function stopNewsTickerAnimation() {
  if (newsTickerState.animation) {
    newsTickerState.animation.cancel();
    newsTickerState.animation = null;
  }
}

function renderTickerItems(trackEl, items) {
  const sourceLabel = NEWS_TICKER_SOURCES[newsTickerState.source]?.label || 'News';
  if (!items.length) {
    trackEl.innerHTML = `<span class="presence-item">${sourceLabel}: nessuna notizia disponibile al momento.</span>`;
    return;
  }

  const rowMarkup = items
    .map((item) => `<a class="presence-link" href="${escapeHtml(item.link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a>`)
    .join('<span class="presence-separator" aria-hidden="true">|</span>');

  trackEl.innerHTML = `${rowMarkup}<span class="presence-separator" aria-hidden="true">|</span>${rowMarkup}`;
}

function startNewsTickerAnimation(containerEl, trackEl) {
  stopNewsTickerAnimation();
  newsTickerState.mobilePaused = false;

  // Se il container è dentro un elemento hidden (ww-data), offsetWidth=0.
  // Attende che diventi visibile tramite ResizeObserver prima di animare.
  if (!containerEl.offsetWidth) {
    const obs = new ResizeObserver(() => {
      if (containerEl.offsetWidth > 0) {
        obs.disconnect();
        startNewsTickerAnimation(containerEl, trackEl);
      }
    });
    obs.observe(containerEl);
    return;
  }

  const loopWidth = Math.max(trackEl.scrollWidth / 2, containerEl.offsetWidth);
  const startX = containerEl.offsetWidth;
  const endX = -loopWidth;
  const pixelsPerSecond = 56;
  const duration = Math.max(18000, Math.round(((startX + loopWidth) / pixelsPerSecond) * 1000));

  newsTickerState.animation = trackEl.animate(
    [
      { transform: `translateX(${startX}px)` },
      { transform: `translateX(${endX}px)` },
    ],
    {
      duration,
      iterations: Infinity,
      easing: 'linear',
    },
  );
}

function bindNewsTickerInteractions(containerEl) {
  if (!containerEl || containerEl.dataset.tickerBound === '1') return;
  containerEl.dataset.tickerBound = '1';

  containerEl.addEventListener('mouseenter', () => {
    if (newsTickerState.animation) {
      newsTickerState.animation.pause();
    }
  });

  containerEl.addEventListener('mouseleave', () => {
    if (newsTickerState.animation && !newsTickerState.mobilePaused) {
      newsTickerState.animation.play();
    }
  });

  containerEl.addEventListener('click', (event) => {
    const isLink = !!event.target.closest('.presence-link');
    if (isLink) return;
    const isTouchLike = window.matchMedia('(hover: none)').matches || navigator.maxTouchPoints > 0;
    if (!isTouchLike || !newsTickerState.animation) return;
    newsTickerState.mobilePaused = !newsTickerState.mobilePaused;
    if (newsTickerState.mobilePaused) {
      newsTickerState.animation.pause();
      containerEl.classList.add('is-paused');
    } else {
      newsTickerState.animation.play();
      containerEl.classList.remove('is-paused');
    }
  });
}

async function initializeNewsTicker() {
  const containerEl = document.getElementById('presence');
  const trackEl = document.getElementById('presence-track');
  if (!containerEl || !trackEl) return;

  bindNewsTickerInteractions(containerEl);
  const selectedSource = normalizeTickerSource(getSystemSettingValue('newsTickerSource', SETTINGS_DEFAULTS.newsTickerSource));
  newsTickerState.source = selectedSource;

  stopNewsTickerAnimation();
  containerEl.classList.remove('is-paused');
  trackEl.innerHTML = `<span class="presence-item">Caricamento ${escapeHtml(NEWS_TICKER_SOURCES[selectedSource].label)}...</span>`;

  try {
    const items = await loadTickerItems(selectedSource);
    renderTickerItems(trackEl, items);
    requestAnimationFrame(() => startNewsTickerAnimation(containerEl, trackEl));
  } catch (e) {
    console.warn('[TICKER] initialization failed', e);
    trackEl.innerHTML = '<span class="presence-item">Errore nel caricamento notizie.</span>';
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
  document.getElementById('sidebar-toggle-clean')?.addEventListener('click', toggleSidebar);

  // Chiudi sidebar cliccando fuori (su main-chat)
  document.getElementById('main-chat')?.addEventListener('click', (e) => {
    const sidebar = document.getElementById('sidebar');
    if (sidebar && !sidebar.classList.contains('sidebar-collapsed')) {
      // Se il click NON è sull'handle neon o il nuovo bottone clean
      if (!e.target.closest('.sidebar-toggle-clean')) {
        sidebar.classList.add('sidebar-collapsed');
      }
    }
  });

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

  initializeNewsTicker();
})();

// Esponi activeTTSSources globalmente per Voice Mode
window.activeTTSSources = activeTTSSources;

// ════════════════════════════════════════════════════════════
// MATRIX ANIMATION — coding mode background
// ════════════════════════════════════════════════════════════
let _matrixAnimFrame = null;
let _matrixCanvas = null;
let _matrixCtx = null;
const _MATRIX_CHARS = '01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホ';

function startMatrixAnimation() {
  if (_matrixCanvas) return; // already running
  const canvas = document.createElement('canvas');
  canvas.id = 'matrix-canvas';
  document.body.appendChild(canvas);
  _matrixCanvas = canvas;
  _matrixCtx = canvas.getContext('2d');

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  canvas._matrixResize = resize;
  window.addEventListener('resize', resize);

  const fontSize = 14;
  let cols = Math.floor(canvas.width / fontSize);
  let drops = new Array(cols).fill(1);

  function draw() {
    // Recalculate cols in case of resize
    cols = Math.floor(canvas.width / fontSize);
    if (drops.length !== cols) {
      drops = new Array(cols).fill(1);
    }
    _matrixCtx.fillStyle = 'rgba(0, 0, 0, 0.05)';
    _matrixCtx.fillRect(0, 0, canvas.width, canvas.height);
    _matrixCtx.fillStyle = '#00ff41';
    _matrixCtx.font = fontSize + 'px monospace';
    for (let i = 0; i < drops.length; i++) {
      const c = _MATRIX_CHARS[Math.floor(Math.random() * _MATRIX_CHARS.length)];
      _matrixCtx.fillText(c, i * fontSize, drops[i] * fontSize);
      if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
        drops[i] = 0;
      }
      drops[i]++;
    }
    _matrixAnimFrame = requestAnimationFrame(draw);
  }
  draw();
}

function stopMatrixAnimation() {
  if (_matrixAnimFrame) {
    cancelAnimationFrame(_matrixAnimFrame);
    _matrixAnimFrame = null;
  }
  if (_matrixCanvas) {
    window.removeEventListener('resize', _matrixCanvas._matrixResize);
    _matrixCanvas.remove();
    _matrixCanvas = null;
    _matrixCtx = null;
  }
}

// ════════════════════════════════════════════════════════════
// VOICE MODE — Conversazione continua
// ════════════════════════════════════════════════════════════
let voiceModeActive = false;
let voiceRecognition = null;
let voiceSilenceTimer = null;
let voiceBlockedUntil = 0;
const VOICE_SILENCE_MS = 1000;

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
  rec.continuous = true;
  rec.interimResults = true;
  let finalTranscript = '';

  rec.onstart = () => {
    recognitionActive = true;
    restartAttempts = 0;
    console.log('VOICE_REC_STARTED');
  };

  rec.onresult = (event) => {
    if (Date.now() < voiceBlockedUntil || window.isGenesiSpeaking) {
      console.log('VOICE_BLOCKED transcript ignored (speaking=' + window.isGenesiSpeaking + ')');
      return;
    }
    if (!voiceModeActive) return;
    finalTranscript = '';
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
      } else {
        interim += event.results[i][0].transcript;
      }
    }

    // Check for "Stop" command or similar
    const currentInpValue = finalTranscript || interim;
    const inp = document.getElementById('message-input');
    if (inp) inp.value = currentInpValue;

    clearTimeout(voiceSilenceTimer);
    if (finalTranscript.trim().length > 0) {
      voiceSilenceTimer = setTimeout(() => {
        if (voiceModeActive && Date.now() >= voiceBlockedUntil) {
          sendVoiceMessage(finalTranscript.trim());
        }
      }, VOICE_SILENCE_MS);
    }
  };

  rec.onend = () => {
    recognitionActive = false;
    console.log('VOICE_REC_ENDED');
    if (!voiceModeActive || window.isGenesiSpeaking) {
      console.log('VOICE_RESTART_ABORTED active=' + voiceModeActive + ' speaking=' + window.isGenesiSpeaking);
      return;
    }

    if (restartAttempts >= MAX_RESTARTS) {
      console.warn('VOICE_MAX_RESTARTS_REACHED');
      // Reset attempts after 15s to allow future restarts
      setTimeout(() => { restartAttempts = 0; }, 15000);
      return;
    }

    restartAttempts++;
    const delay = 250 * restartAttempts;
    console.log(`🔄 VOICE_RESTART_ATTEMPT #${restartAttempts} in ${delay}ms`);

    setTimeout(() => {
      if (!voiceModeActive || recognitionActive || window.isGenesiSpeaking) return;
      try {
        voiceRecognition?.start();
      } catch (e) { }
    }, delay);
  };

  rec.onerror = (e) => {
    recognitionActive = false;
    console.warn('VOICE_REC_ERROR', e.error);
    if (!voiceModeActive || e.error === 'aborted' || e.error === 'not-allowed') return;

    setTimeout(() => {
      if (voiceModeActive && !recognitionActive && Date.now() >= voiceBlockedUntil) {
        try { voiceRecognition.start(); }
        catch (err) { }
      }
    }, 1000);
  };

  return rec;
}

function startVoiceMode() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) { alert('Browser non supporta il riconoscimento vocale.'); return; }
  voiceModeActive = true;
  voiceBlockedUntil = 0;
  playVoiceModePing('start');
  document.getElementById('voice-mode-btn')?.classList.add('active');
  document.getElementById('voice-mode-overlay')?.classList.replace('hidden', 'visible');
  document.querySelector('.input-wrapper')?.classList.add('nebula-listening');
  setVoiceOrbState('listening');
  setVoiceStatusText('In ascolto...');

  // Crea la recognition UNA SOLA VOLTA
  if (!voiceRecognition) {
    voiceRecognition = buildVoiceRecognition();
  }
  if (!recognitionActive) {
    try {
      voiceRecognition?.start();
    } catch (e) { console.warn("VOICE_START_FAIL", e); }
  }
  console.log('VOICE_MODE_STARTED');
}

let voiceMessageInProgress = false;
async function sendVoiceMessage(text) {
  console.log('SEND_VOICE_MSG text="' + text + '" len=' + (text?.length || 0));
  if (!text?.trim() || !voiceModeActive || voiceMessageInProgress) return;
  voiceMessageInProgress = true;

  try {
    clearTimeout(voiceSilenceTimer);
    voiceSilenceTimer = null;

    // Blocco mic preventivo lungo per coprire generazione LLM (60s fallback)
    voiceBlockedUntil = Date.now() + 60000;
    window.isGenesiSpeaking = true;
    console.log('VOICE_BLOCKED_START (sendVoiceMessage) timestamp=' + Date.now());

    // PAUSA MIC DURANTE TTS - Fermiamo il riconoscimento per sicurezza
    if (voiceRecognition && recognitionActive) {
      try {
        voiceRecognition.stop();
        console.log('🎤 Mic PAUSED - Genesi sta per rispondere');
      } catch (e) { }
    }

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
      voiceBlockedUntil = Date.now() + 800; // Delay anti-echo 0.8s
      window.isGenesiSpeaking = false;
      console.log('VOICE_UNBLOCKED_AND_LOCK_RELEASED');
      setVoiceOrbState('listening');
      setVoiceStatusText('In ascolto...');
      setTimeout(() => {
        if (!voiceModeActive || recognitionActive) return;
        try {
          console.log('VOICE_RESTART_AFTER_TTS');
          playVoiceModePing('start'); // Feedack audio quando apre il mic
          voiceRecognition?.start();
        } catch (e) { }
      }, 1000); // 1s delay
    });

    voiceMessageInProgress = false;
  } catch (e) {
    voiceMessageInProgress = false;
    console.error("VOICE_MSG_FAIL", e);
  }
}

/** 
 * Segnale acustico sottile per indicare stato microfono
 */
function playVoiceModePing(type = 'start') {
  try {
    const ctx = window.audioContext || (window.AudioContext && new window.AudioContext());
    if (!ctx) return;
    if (ctx.state === 'suspended') ctx.resume();

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === 'start') {
      // "Ding" verso l'alto
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1100, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(0.04, ctx.currentTime + 0.02);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.2);
      osc.start();
      osc.stop(ctx.currentTime + 0.2);
    } else {
      // "Dong" verso il basso
      osc.type = 'sine';
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(330, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(0.04, ctx.currentTime + 0.02);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.2);
      osc.start();
      osc.stop(ctx.currentTime + 0.2);
    }
  } catch (e) { console.warn("PING_SFX_FAIL", e); }
}

function waitForTTSEnd(callback) {
  if (voiceTTSPollInterval) clearInterval(voiceTTSPollInterval);
  if (voiceTTSPollTimeout) clearTimeout(voiceTTSPollTimeout);

  const startTime = Date.now();
  let ttsWasDetected = false;

  const finish = () => {
    if (voiceTTSPollInterval) clearInterval(voiceTTSPollInterval);
    voiceTTSPollInterval = null;
    if (voiceTTSPollTimeout) clearTimeout(voiceTTSPollTimeout);
    voiceTTSPollTimeout = null;
    callback();
  };

  voiceTTSPollInterval = setInterval(() => {
    // 1. Aspetta che il backend risponda e decidiamo se c'è TTS
    if (!window.responseProcessed) return;

    // 2. Se sappiamo che non c'è TTS, finisci subito
    if (window.responseProcessed && !window.ttsExpected) {
      console.log('[VOICE_POLL] No TTS expected, bypassing wait');
      finish();
      return;
    }

    // 3. Monitora attività TTS
    const isPlaying = window.ttsSessionActive || window.ttsPlaying || (window._isPlayingChunk === true);
    if (isPlaying) {
      if (!ttsWasDetected) {
        console.log('[VOICE_POLL] TTS activity detected - locking mic');
      }
      ttsWasDetected = true;
      // Trascina il blocco voce in avanti mentre suona (buffer di sicurezza 1.5s)
      voiceBlockedUntil = Date.now() + 1500;
      return;
    }

    // 4. Se ha suonato (o abbiamo aspettato abbastanza) e ora è fermo
    const hasStarted = ttsWasDetected || (window.lastTTSStart > startTime);
    if (hasStarted && !isPlaying) {
      const currentGap = Date.now() - window.lastTTSEnd;
      // Guard di 2000ms per evitare gap tra chunk
      if (currentGap > 2000) {
        console.log('[VOICE_POLL] TTS finished detected, gap=' + currentGap);
        finish();
      }
    }
  }, 100);

  // Fallback: se dopo 60s non è successo nulla, sblocca (copre risposte molto lunghe)
  voiceTTSPollTimeout = setTimeout(() => {
    console.warn('[VOICE_POLL] Fallback timeout triggered (60s)');
    finish();
  }, 60000);
}

function stopVoiceMode() {
  voiceModeActive = false;
  voiceBlockedUntil = 0;
  window.isGenesiSpeaking = false;
  playVoiceModePing('stop');
  clearTimeout(voiceSilenceTimer);
  voiceSilenceTimer = null;
  try { voiceRecognition?.stop(); } catch (e) { }
  voiceRecognition = null;
  document.getElementById('voice-mode-btn')?.classList.remove('active');
  document.getElementById('voice-mode-overlay')?.classList.replace('visible', 'hidden');
  const iw = document.querySelector('.input-wrapper');
  iw?.classList.remove('nebula-listening', 'nebula-speaking');
  console.log('VOICE_MODE_STOPPED');
}

function setVoiceOrbState(state) {
  const orb = document.querySelector('.voice-orb');
  if (orb) {
    orb.classList.remove('listening', 'speaking', 'idle');
    orb.classList.add(state);
  }
  // Nebulosa input box: blu=ascolto, ambra=parla
  const iw = document.querySelector('.input-wrapper');
  if (iw && (iw.classList.contains('nebula-listening') || iw.classList.contains('nebula-speaking'))) {
    iw.classList.remove('nebula-listening', 'nebula-speaking');
    if (state === 'speaking') iw.classList.add('nebula-speaking');
    else if (state === 'listening') iw.classList.add('nebula-listening');
  }
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

  const els = {
    widget: document.getElementById('weather-widget'),
    loading: document.getElementById('ww-loading'),
    data: document.getElementById('ww-data'),
    error: document.getElementById('ww-error'),
    city: document.getElementById('ww-city'),
    temp: document.getElementById('ww-temp'),
    desc: document.getElementById('ww-desc'),
    meta: document.getElementById('ww-meta'),
    time: document.getElementById('ww-time'),
    sun: document.querySelector('#weather-widget .weather-widget__sun'),
    moon: document.querySelector('#weather-widget .weather-widget__moon'),
    stars: document.querySelectorAll('#weather-widget .weather-widget__star'),
  };

  if (!els.widget) {
    console.warn('[WEATHER_WIDGET] Elemento #weather-widget non trovato nel DOM.');
    return;
  }

  function showState(state) {
    els.loading.hidden = state !== 'loading';
    els.data.hidden = state !== 'data';
    els.error.hidden = state !== 'error';

    if (state !== 'data') {
      els.widget.dataset.weather = 'clear';
      els.widget.dataset.phase = 'day';
    }
  }

  function updateClock() {
    const now = new Date();
    const time = now.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
    if (els.time) els.time.textContent = time;
  }

  let weatherRefreshInFlight = false;

  function classifyCloudiness(cloudCover) {
    const cc = Number(cloudCover);
    if (!Number.isFinite(cc) || cc < 15) return 'low';
    if (cc < 45) return 'mid';
    if (cc < 80) return 'high';
    return 'overcast';
  }

  function applyDynamicSceneTuning(payload, scene) {
    const cloudCover = Number(payload.cloud_cover ?? (scene.weather === 'clear' ? 8 : 60));
    const wind = Number(payload.wind_speed ?? 10);
    const humidity = Number(payload.humidity ?? 60);
    const weatherId = Number(payload.weather_id ?? 800);

    const cloudiness = classifyCloudiness(cloudCover);
    els.widget.dataset.cloudiness = cloudiness;

    const heavyRain = scene.weather === 'rain' && (weatherId >= 502 || wind >= 28);
    const thickMist = scene.weather === 'mist' && (humidity >= 85 || cloudCover >= 70);

    const cloudOpacity = Math.min(0.9, Math.max(0.35, 0.35 + (cloudCover / 100) * 0.6));
    const ambientSpeed = heavyRain ? '6.5s' : (scene.weather === 'thunder' ? '6s' : cloudCover >= 70 ? '8.5s' : '11s');
    const cloudSpeedA = Math.max(9, 20 - Math.round(cloudCover / 9) - Math.round(wind / 10));
    const cloudSpeedB = Math.max(11, cloudSpeedA + 3);
    const rainSpeed = heavyRain ? '0.35s' : '0.55s';
    const rainTilt = Math.min(22, Math.max(9, Math.round((wind / 2) + 8)));
    const cinemaBoost = scene.weather === 'thunder' ? '1' : (scene.weather === 'rain' ? '0.85' : '0.65');
    const fogOpacity = thickMist ? '0.95' : '0.8';
    const starOpacity = cloudCover >= 70 ? '0.52' : cloudCover >= 40 ? '0.7' : '0.92';

    els.widget.style.setProperty('--ww-cloud-opacity', cloudOpacity.toFixed(2));
    els.widget.style.setProperty('--ww-ambient-speed', ambientSpeed);
    els.widget.style.setProperty('--ww-cloud-speed-a', `${cloudSpeedA}s`);
    els.widget.style.setProperty('--ww-cloud-speed-b', `${cloudSpeedB}s`);
    els.widget.style.setProperty('--ww-rain-speed', rainSpeed);
    els.widget.style.setProperty('--ww-rain-tilt', `${rainTilt}deg`);
    els.widget.style.setProperty('--ww-cinema-boost', cinemaBoost);
    els.widget.style.setProperty('--ww-fog-opacity', fogOpacity);
    els.widget.style.setProperty('--ww-star-opacity', starOpacity);

    // Tema cromatico condiviso: ticker + aura generale coerenti col meteo corrente.
    let accent = '#6ed8ff';
    let accentSoft = 'rgba(110, 216, 255, 0.35)';
    let auraTop = 'rgba(110, 216, 255, 0.28)';
    let auraBottom = 'rgba(68, 158, 214, 0.20)';

    if (scene.weather === 'thunder') {
      accent = '#c4d7ff';
      accentSoft = 'rgba(196, 215, 255, 0.42)';
      auraTop = 'rgba(160, 188, 255, 0.30)';
      auraBottom = 'rgba(95, 124, 214, 0.22)';
    } else if (scene.weather === 'rain') {
      accent = '#8ccfff';
      accentSoft = 'rgba(140, 207, 255, 0.38)';
      auraTop = 'rgba(120, 184, 236, 0.28)';
      auraBottom = 'rgba(70, 132, 186, 0.22)';
    } else if (scene.weather === 'snow') {
      accent = '#eaf7ff';
      accentSoft = 'rgba(214, 240, 255, 0.40)';
      auraTop = 'rgba(205, 234, 255, 0.30)';
      auraBottom = 'rgba(146, 188, 222, 0.22)';
    } else if (scene.weather === 'mist') {
      accent = '#bdd7e8';
      accentSoft = 'rgba(189, 215, 232, 0.34)';
      auraTop = 'rgba(166, 194, 212, 0.26)';
      auraBottom = 'rgba(108, 139, 158, 0.2)';
    } else if (scene.weather === 'clouds') {
      accent = scene.phase === 'day' ? '#a7d2ee' : '#9ab7d6';
      accentSoft = scene.phase === 'day' ? 'rgba(167, 210, 238, 0.34)' : 'rgba(154, 183, 214, 0.34)';
      auraTop = scene.phase === 'day' ? 'rgba(144, 192, 223, 0.26)' : 'rgba(126, 160, 194, 0.24)';
      auraBottom = scene.phase === 'day' ? 'rgba(90, 137, 172, 0.2)' : 'rgba(72, 105, 150, 0.2)';
    } else if (scene.phase === 'night') {
      accent = '#9fc2ff';
      accentSoft = 'rgba(159, 194, 255, 0.34)';
      auraTop = 'rgba(122, 155, 219, 0.24)';
      auraBottom = 'rgba(74, 102, 170, 0.2)';
    }

    if (cloudCover >= 75 && scene.weather === 'clear') {
      accent = '#9ec7e8';
      accentSoft = 'rgba(158, 199, 232, 0.34)';
      auraTop = 'rgba(136, 176, 206, 0.24)';
      auraBottom = 'rgba(84, 122, 154, 0.2)';
    }

    const rootStyle = document.documentElement.style;
    rootStyle.setProperty('--meteo-accent', accent);
    rootStyle.setProperty('--meteo-accent-soft', accentSoft);
    rootStyle.setProperty('--meteo-aura-top', auraTop);
    rootStyle.setProperty('--meteo-aura-bottom', auraBottom);
  }

  function getWeatherScene(condition, iconCode) {
    const cond = String(condition || '').toLowerCase();
    const icon = String(iconCode || '').toLowerCase();

    // OpenWeather icon suffix ('d'/'n') is authoritative for the location.
    // Client local hour is used only when icon is missing or ambiguous.
    const hour = new Date().getHours();
    const clientNight = hour < 6 || hour >= 21;
    const isNight = icon ? icon.endsWith('n') : clientNight;

    if (cond.includes('thunder')) return { weather: 'thunder', phase: isNight ? 'night' : 'day' };
    if (cond.includes('snow') || icon.startsWith('13')) return { weather: 'snow', phase: isNight ? 'night' : 'day' };

    const isMist = cond.includes('mist')
      || cond.includes('fog')
      || cond.includes('haze')
      || cond.includes('smoke')
      || cond.includes('dust')
      || cond.includes('sand')
      || cond.includes('ash')
      || cond.includes('squall')
      || cond.includes('tornado')
      || icon.startsWith('50');
    if (isMist) return { weather: 'mist', phase: isNight ? 'night' : 'day' };

    if (cond.includes('rain') || cond.includes('drizzle') || icon.startsWith('09') || icon.startsWith('10')) {
      return { weather: 'rain', phase: isNight ? 'night' : 'day' };
    }
    // Solo 03* (scattered) e 04* (broken/overcast) mostrano nuvole — "few clouds" (02*) = clear
    if (icon.startsWith('03') || icon.startsWith('04')) {
      return { weather: 'clouds', phase: isNight ? 'night' : 'day' };
    }
    return { weather: 'clear', phase: isNight ? 'night' : 'day' };
  }

  function renderWeather(payload) {
    // Usa i codici OpenWeather per mantenere la scena coerente con i dati meteo reali.
    const scene = getWeatherScene(payload.condition, payload.icon_code);

    els.widget.dataset.weather = scene.weather;
    els.widget.dataset.phase = scene.phase;
    applyDynamicSceneTuning(payload, scene);

    // Failsafe UI: forza visibilità astro anche se CSS stale lato client.
    if (els.sun) els.sun.hidden = scene.phase !== 'day';
    if (els.moon) els.moon.hidden = scene.phase !== 'night';
    if (els.stars && els.stars.length) {
      const showStars = scene.phase === 'night' && scene.weather !== 'thunder';
      els.stars.forEach((star) => {
        star.hidden = !showStars;
      });
    }

    els.city.textContent = payload.city;
    els.temp.textContent = `${payload.temp}°`;
    els.desc.textContent = payload.description;
    els.meta.textContent = `${payload.humidity} % umidità · ${payload.wind_speed} km / h`;
    updateClock();
    showState('data');
    console.log(
      `[WEATHER_WIDGET] OK city = ${payload.city} temp = ${payload.temp}° condition = ${payload.condition}`
    );
  }

  async function fetchWeather(lat, lon) {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    let url = `/api/weather-widget?tz=${encodeURIComponent(tz)}&_ts=${Date.now()}`;
    if (lat !== null && lon !== null) {
      url += `&lat=${lat}&lon=${lon}`;
    }

    const resp = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`
      },
      cache: 'no-store',
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  function loadWithCoords(lat, lon) {
    return fetchWeather(lat, lon)
      .then(renderWeather)
      .catch(err => {
        console.warn('[WEATHER_WIDGET] Fetch con coordinate fallita:', err);
        // Secondo tentativo: fallback IP
        return fetchWeather(null, null)
          .then(renderWeather)
          .catch(() => showState('error'));
      });
  }

  function refreshMeteoData() {
    if (weatherRefreshInFlight) return;
    weatherRefreshInFlight = true;

    const endRefresh = () => {
      weatherRefreshInFlight = false;
    };

    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        pos => {
          const { latitude, longitude, accuracy } = pos.coords;

          // Se il fix è troppo grossolano (tipico fallback IP), preferiamo
          // lasciare al backend la scelta profilo/IP per evitare posizione errata.
          if (Number.isFinite(accuracy) && accuracy > 20000) {
            console.warn('[WEATHER_WIDGET] GPS poco preciso, fallback backend. accuracy=', accuracy);
            fetchWeather(null, null)
              .then(renderWeather)
              .catch(() => showState('error'))
              .finally(endRefresh);
            return;
          }

          loadWithCoords(latitude, longitude).finally(endRefresh);
        },
        _err => {
          console.info('[WEATHER_WIDGET] Geolocation negata — fallback IP');
          fetchWeather(null, null)
            .then(renderWeather)
            .catch(() => showState('error'))
            .finally(endRefresh);
        },
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
      );
    } else {
      console.info('[WEATHER_WIDGET] Geolocation non disponibile — fallback IP');
      fetchWeather(null, null)
        .then(renderWeather)
        .catch(() => showState('error'))
        .finally(endRefresh);
    }
  }

  // ── Entry point ──────────────────────────────────────────────
  function initWS() {
    showState('loading');
    refreshMeteoData();
    // Aggiorna orologio ogni minuto
    setInterval(updateClock, 60_000);
    // Aggiorna i dati meteo ogni 15 minuti (900.000 ms)
    setInterval(refreshMeteoData, 900_000);

    // Riprende aggiornamento quando l'utente torna sulla tab o online.
    window.addEventListener('focus', refreshMeteoData);
    window.addEventListener('online', refreshMeteoData);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) refreshMeteoData();
    });
  }

  if (document.readyState === 'complete') {
    initWS();
  } else {
    window.addEventListener('load', initWS);
  }

})();

// ── PWA: registrazione Service Worker ───────────────────────
if ('serviceWorker' in navigator) {
  const SW_VERSION = 'v7';
  navigator.serviceWorker
    .register(`/sw.js?v=${SW_VERSION}`, { updateViaCache: 'none' })
    .then((reg) => {
      console.log('[PWA] Service Worker registrato:', reg.scope);
      // Forza check aggiornamenti ad ogni load per ridurre i casi di JS stale.
      reg.update().catch(() => {});
    })
    .catch((err) => {
      console.warn('[PWA] Service Worker non registrato:', err);
    });
}

// ===============================
// ICLOUD INTEGRATION SYSTEM
// ===============================
const icloudModal = document.getElementById('icloud-modal');
const icloudBtn = document.getElementById('icloud-sync-btn');
const icloudStatusArea = document.getElementById('icloud-status-area');
const icloudSetupForm = document.getElementById('icloud-setup-form');
const icloud2FAForm = document.getElementById('icloud-2fa-form');
const icloudActiveActions = document.getElementById('icloud-active-actions');

if (icloudBtn) {
  icloudBtn.addEventListener('click', () => {
    icloudModal.classList.remove('hidden');
    refreshICloudStatus();
  });
}

const closeModalBtn = icloudModal ? icloudModal.querySelector('.close-modal') : null;
if (closeModalBtn) {
  closeModalBtn.addEventListener('click', () => icloudModal.classList.add('hidden'));
}

async function refreshICloudStatus() {
  if (!icloudStatusArea) return;
  icloudStatusArea.innerHTML = '<p>Controllo stato...</p>';
  icloudSetupForm.classList.add('hidden');
  icloudActiveActions.classList.add('hidden');

  try {
    const res = await fetch('/api/proactor/icloud/status', { headers: authHeaders() });
    const data = await res.json();

    if (data.error) {
      icloudStatusArea.innerHTML = `<p class="warningText">⚠️ ${data.error}</p>`;
    }

    if (!data.configured) {
      if (!data.error) icloudStatusArea.innerHTML = '<p>Non ancora collegato a iCloud.</p>';
      icloudSetupForm.classList.remove('hidden');
    } else {
      icloudStatusArea.innerHTML = `<p>✅ iCloud attivo: <b>${data.email}</b></p>`;
      if (data.last_sync) {
        icloudStatusArea.innerHTML += `<p style="font-size:0.8rem; color:#888;">Ultima sincronizzazione: ${new Date(data.last_sync * 1000).toLocaleString()}</p>`;
      }
      icloudActiveActions.classList.remove('hidden');
    }
  } catch (e) {
    icloudStatusArea.innerHTML = '<p class="error">Errore nel caricamento dello stato.</p>';
  }
}

const saveICloudBtn = document.getElementById('save-icloud-btn');
if (saveICloudBtn) {
  saveICloudBtn.addEventListener('click', async () => {
    const email = document.getElementById('icloud-email').value;
    const password = document.getElementById('icloud-password').value;
    if (!email || !password) return alert("Inserisci email e password.");

    saveICloudBtn.disabled = true;
    saveICloudBtn.innerText = "Connessione...";

    try {
      const res = await fetch('/api/proactor/icloud/setup', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        alert(data.message || "Collegato!");
        refreshICloudStatus();
      } else {
        alert(data.message || "Errore durante il setup.");
      }
    } catch (e) {
      alert("Si è verificato un errore.");
    } finally {
      saveICloudBtn.disabled = false;
      saveICloudBtn.innerText = "Collega con CalDAV";
    }
  });
}

const disconnectICloudBtn = document.getElementById('disconnect-icloud-btn');
if (disconnectICloudBtn) {
  disconnectICloudBtn.addEventListener('click', async () => {
    if (!askCriticalConfirm("Vuoi davvero scollegare l'account iCloud?")) return;
    try {
      const res = await fetch('/api/proactor/icloud/status', { method: 'DELETE', headers: authHeaders() });
      alert("Account scollegato.");
      refreshICloudStatus();
    } catch (e) {
      alert("Errore durante la disconnessione.");
    }
  });
}

const manualSyncBtn = document.getElementById('manual-sync-btn');
if (manualSyncBtn) {
  manualSyncBtn.addEventListener('click', async () => {
    manualSyncBtn.disabled = true;
    manualSyncBtn.innerText = "Sincronizzazione...";
    try {
      const res = await fetch('/api/proactor/icloud/sync', { method: 'POST', headers: authHeaders() });
      const data = await res.json();
      alert(`Sincronizzazione completata! ${data.count} nuovi promemoria trovati.`);
      refreshICloudStatus();
    } catch (e) {
      alert("Errore durante la sincronizzazione.");
    } finally {
      manualSyncBtn.disabled = false;
      manualSyncBtn.innerText = "Sincronizza Ora";
    }
  });
}

// ── Push Notifications — richiesta permesso e subscription ──
; (function initPushNotifications() {
  'use strict';

  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    console.info('[PUSH] Non supportato su questo browser.');
    return;
  }

  console.log('[PUSH] Supportato, registro handlers...');

  async function getVapidKey() {
    const resp = await fetch('/api/push/vapid-public-key');
    if (!resp.ok) throw new Error('VAPID key non disponibile');
    const data = await resp.json();
    return data.public_key;
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
  }

  async function subscribeToPush() {
    try {
      const registration = await navigator.serviceWorker.ready;
      const vapidKey = await getVapidKey();

      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      });

      // Invia subscription al backend
      const resp = await fetch('/api/push/subscribe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('genesi_access_token') || ''}`,
        },
        body: JSON.stringify(subscription.toJSON()),
      });

      if (resp.ok) {
        console.log('[PUSH] Subscription salvata sul server.');
      } else {
        console.warn('[PUSH] Errore salvataggio subscription:', resp.status);
      }
    } catch (err) {
      console.warn('[PUSH] Errore subscription:', err);
    }
  }

  async function initPush() {
    if (!getSystemSetting('desktopNotifications')) {
      console.info('[PUSH] Desktop notifications disabled by settings — skip push init.');
      return;
    }

    // Aspetta che l'utente sia loggato (presenza del token)
    const token = localStorage.getItem('genesi_access_token');
    if (!token) {
      console.info('[PUSH] Utente non loggato — skip push init.');
      return;
    }

    console.log('[PUSH] Requesting permission...');
    const permission = await Notification.requestPermission();
    console.log('[PUSH] Permesso notifiche:', permission);

    if (permission === 'granted') {
      await subscribeToPush();
    }
  }

  // Avvia dopo che il SW è pronto o fallisce
  console.log('🔴🔴🔴 [PUSH] Eseguo blocco SW ready...');
  navigator.serviceWorker.ready.then((reg) => {
    console.log('🔴🔴🔴 [PUSH] SW ready risolto, reg:', reg.scope);
    // Piccolo delay per non sovraccaricare il primo caricamento
    setTimeout(() => {
      console.log('🔴🔴🔴 [PUSH] trigger initPush (da setTimeout)');
      initPush().catch(e => console.error('🔴🔴🔴 [PUSH] Errore in initPush:', e));
    }, 2000);
  }).catch(e => console.error('🔴🔴🔴 [PUSH] Errore in SW ready:', e));

})();

// SURGICAL MIC KILLER - Listen for emergency signals
window.addEventListener('message', (event) => {
  if (event.data.type === 'TTS_START') {
    window.isGenesiSpeaking = true;
    if (typeof voiceRecognition !== 'undefined' && voiceRecognition && typeof recognitionActive !== 'undefined' && recognitionActive) {
      try { voiceRecognition.stop(); } catch (e) { }
    }
    console.log('🔴 MIC HARD STOPPED - External signal');

    // FAILSAFE: Force reset after 10s
    setTimeout(() => {
      if (window.isGenesiSpeaking) {
        window.isGenesiSpeaking = false;
        console.log('⏰ TTS_FAILSAFE_EXT: Force releasing mic');
        if (typeof voiceModeActive !== 'undefined' && voiceModeActive && typeof recognitionActive !== 'undefined' && !recognitionActive) {
          try { voiceRecognition?.start(); } catch (e) { }
        }
      }
    }, 10000);
  }
  if (event.data.type === 'TTS_END') {
    window.isGenesiSpeaking = false;
    console.log('🟢 MIC HOT-RELEASE - External signal');
  }
});
