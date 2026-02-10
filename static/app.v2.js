// ===============================
// AUDIO PRIMING
// ===============================
let _primedAudio = null;

// ===============================
// STATES
// ===============================
const STATES = { IDLE: 'idle', THINKING: 'thinking', RECORDING: 'recording' };

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

// User bar DOM (auth disabilitato)
const userBar = document.getElementById('user-bar');
const userGreeting = document.getElementById('user-greeting');
const adminLink = document.getElementById('admin-link');
const logoutBtn = document.getElementById('logout-btn');

// ===============================
// AUTH STATE - DISABILITATO
// ===============================
let _isLoggedIn = true; // SEMPRE loggato

function getAuthToken() {
  return null; // Nessun token
}

function isLoggedIn() {
  return true; // SEMPRE loggato
}

function getTokenPayload() {
  return null; // Nessun payload
}

function isAdmin() {
  return false; // Mai admin
}

async function tryRefreshToken() {
  return false; // Nessun refresh
}

function doLogout() {
  // Nessun logout - disabilitato
}

function applyAuthState() {
  // SEMPRE loggato - mostra chat, nascondi auth
  userBar.style.display = 'flex';
  document.getElementById('presence').style.display = '';
  dialogue.style.display = '';
  document.getElementById('status').style.display = '';
  chatForm.style.display = '';

  // Greeting fisso
  userGreeting.textContent = 'Ciao';

  // Admin link sempre nascosto
  adminLink.style.display = 'none';
  logoutBtn.style.display = 'none';
}

// Logout handler (disabilitato)
if (logoutBtn) {
  logoutBtn.addEventListener('click', () => {
    console.log('Logout disabilitato');
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
    const top = window.visualViewport.offsetTop;
    document.documentElement.style.setProperty('--app-height', h + 'px');
    // iOS Safari: when keyboard opens, viewport scrolls up — compensate
    document.getElementById('genesi-app').style.transform =
      top > 0 ? 'translateY(' + top + 'px)' : '';
  } else {
    document.documentElement.style.setProperty('--app-height', window.innerHeight + 'px');
  }
}

updateAppHeight();

if (window.visualViewport) {
  const _onViewport = () => {
    updateAppHeight();
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
    _primedAudio.play().catch(() => {});
    console.log('[AUDIO] primed');
  }
}

function stopAudio() {
  if (_ttsSource) {
    try { _ttsSource.stop(); } catch (e) {}
    _ttsSource = null;
  }
}

// ===============================
// BARGE-IN — immediate TTS interruption on user input
// ===============================
function _interruptTTS(reason) {
  if (_ttsSource) {
    console.log('[BARGE-IN] interrupt reason=' + reason);
    try { _ttsSource.stop(); } catch (e) {}
    _ttsSource = null;
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
  
  if (!text || text.trim().length === 0) {
    console.log('[TTS_ABORT] reason=segmented_empty_text text_len=' + (text ? text.length : 0));
    console.log('[TTS_FLOW] step=2 segmented_skip_empty_text');
    return;
  }
  
  const chunks = _splitTextForTTS(text, tts_mode);
  console.log('[TTS_FLOW] step=3 segmented_chunks_created count=' + chunks.length);
  console.log('[TTS] CHUNKING: total_len=' + text.length + ' mode=' + tts_mode);
  console.log('[TTS] CHUNKS:', chunks.map((c, i) => `${i + 1}: "${c.substring(0, 50)}..." (${c.length}char)`));
  
  // Array per i blob pre-caricati
  const chunkBlobs = new Array(chunks.length);
  
  // Funzione per fetch di un chunk
  const fetchChunk = async (index) => {
    const chunk = chunks[index];
    const normalizedChunk = normalizeTextForTTS(chunk);
    console.log('[TTS_PREFETCH] index=' + (index + 1) + '/total=' + chunks.length + ' len=' + chunk.length);
    
    try {
      const response = await fetch('/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: normalizedChunk })
      });
      
      if (!response.ok) {
        throw new Error('TTS fetch failed: ' + response.status);
      }
      
      const blob = await response.blob();
      chunkBlobs[index] = blob;
      console.log('[TTS_PREFETCH_DONE] index=' + (index + 1) + ' size=' + blob.size);
    } catch (e) {
      console.error('[TTS_PREFETCH_ERROR] index=' + (index + 1), e);
      chunkBlobs[index] = null;
    }
  };
  
  // Pre-fetch del primo chunk
  await fetchChunk(0);
  
  // Ciclo principale con prefetch
  for (let i = 0; i < chunks.length; i++) {
    console.log('[TTS_FLOW] step=4.' + (i + 1) + ' processing_chunk_' + (i + 1) + '/' + chunks.length);
    
    // VERIFICA INPUT UTENTE PRIMA DI OGNI CHUNK (escluso primo chunk)
    // Interruzione utente solo se _ttsSource=null e non siamo in un ciclo naturale
    if (i > 0 && _ttsSource === null && !_isPlayingChunk && !_wasPlayingChunk) {
      console.log('[TTS_FLOW] step=5.' + (i + 1) + ' interrupted_before_chunk_' + (i + 1));
      break;
    }
    
    // Avvia prefetch del chunk successivo mentre questo suona
    if (i < chunks.length - 1) {
      fetchChunk(i + 1); // Non await per fetch in background
    }
    
    const chunk = chunks[i];
    console.log('[TTS_CHUNK] index=' + (i + 1) + '/total=' + chunks.length + ' len=' + chunk.length);
    console.log('[TTS] PLAYING chunk', i + 1, '/', chunks.length, 'len=' + chunk.length);
    console.log('[TTS] CHUNK TEXT:', chunk);
    
    try {
      console.log('[TTS_FLOW] step=6.' + (i + 1) + ' calling_playTTSChunk');
      
      // Misura tempo tra chunk
      const chunkStartTime = performance.now();
      
      await _playTTSChunkWithBlob(chunk, chunkBlobs[i], i);
      
      const chunkEndTime = performance.now();
      const chunkDuration = chunkEndTime - chunkStartTime;
      
      console.log('[TTS_FLOW] step=7.' + (i + 1) + ' playTTSChunk_completed duration=' + chunkDuration.toFixed(2) + 'ms');
      
      // PAUSA LUNGA per psychological tra chunk
      if (tts_mode === 'psychological' && i < chunks.length - 1) {
        console.log('[TTS_FLOW] step=8.' + (i + 1) + ' psychological_pause');
        await new Promise(resolve => setTimeout(resolve, 800)); // 800ms pause
        console.log('[TTS_FLOW] step=9.' + (i + 1) + ' psychological_pause_completed');
      }
    } catch (e) {
      console.error('[TTS_FLOW] step=ERROR.' + (i + 1) + ' chunk_error:', e);
      break;
    }
    
    // VERIFICA INPUT UTENTE DOPO OGNI CHUNK
    // NOTA: _ttsSource=null dopo chunk completato è normale (audio finito)
    // L'interruzione utente viene gestita prima del prossimo chunk
  }
  
  console.log('[TTS_FLOW] step=11 segmented_finished');
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
    console.log('[TTS_ABORT] reason=empty_prefetched_blob');
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
    const response = await fetch('/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: normalizedText })
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
      console.log('[TTS_ABORT] reason=empty_blob');
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
  
  if (!text || text.trim().length === 0) {
    console.log('[TTS_ABORT] reason=empty_text text_len=' + (text ? text.length : 0));
    console.log('[TTS_FLOW] step=2 playTTS_skip_empty_text');
    return;
  }
  
  console.log('[TTS_FLOW] step=3 playTTS_checking_segmentation');
  
  // FORZA segmentazione per testi informativi, psychological o lunghi
  console.log('[TTS_FLOW] step=3.5 checking_conditions tts_mode=' + tts_mode + ' len=' + text.length);
  
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
}

// ===============================
// USER IDENTITY
// ===============================
function getUserId() {
  // Prefer auth user_id from JWT, fallback to localStorage
  const payload = getTokenPayload();
  if (payload && payload.sub) {
    localStorage.setItem('genesi_user_id', payload.sub);
    return payload.sub;
  }
  let id = localStorage.getItem('genesi_user_id');
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem('genesi_user_id', id);
  }
  return id;
}

let userIdentity = {};

async function bootstrapUser() {
  try {
    const res = await fetch('/user/bootstrap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: getUserId() })
    });
    if (res.ok) {
      const data = await res.json();
      userIdentity = data.identity || {};
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

function addMessage(text, sender) {
  const el = document.createElement('div');
  el.className = `message ${sender}`;
  
  // Usa innerHTML con escape per proteggere da XSS ma permettere formattazione
  // Previene sovrascritture future garantendo che il contenuto sia locked
  const escapedText = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
  
  el.innerHTML = escapedText;
  
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
function addGenesiMessage(text) { return addMessage(text, 'genesi'); }

// ===============================
// CHAT API
// ===============================
async function sendChatMessage(message) {
  // Nessun controllo auth - accesso diretto
  const res = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: getUserId(), message })
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data;
}

// ===============================
// SEND MESSAGE
// ===============================
async function sendMessage() {
  // Audio Priming: previeni NotAllowedError su Safari/iOS
  primeAudio();
  
  // Barge-in: interrompi TTS su input utente
  _interruptTTS('user_input');

  // Warm AudioContext NOW (sync, during user gesture) — iOS requires this
  _warmTTSCtx();

  const text = textInput.value.trim();
  if (!text || currentState !== STATES.IDLE) return;

  textInput.value = '';

  // Pulse shockwave on send
  const ic = document.getElementById('input-container');
  ic.classList.remove('pulse');
  void ic.offsetWidth;
  ic.classList.add('pulse');

  addUserMessage(text);
  setState(STATES.THINKING);

  try {
    const data = await sendChatMessage(text);
    console.log('[FRONTEND] response received - data=', data);
    
    // USA SEMPRE response - CONTRATTO API BACKEND
    const botMessage = data.response;
    
    if (!botMessage || botMessage.trim().length === 0) return;
    
    // RENDERING GARANTITO: aggiungi messaggio e verifica sia visibile
    console.log('[FRONTEND] CHAT RESPONSE RENDERED:', data.response);
    const messageElement = addGenesiMessage(botMessage);
    
    // VERIFICA: assicura che il messaggio sia nel DOM
    if (!messageElement || !document.contains(messageElement)) {
      console.error('[RENDER_ERROR] Message element not found in DOM after insertion');
      return;
    }
    
    // TTS SOLO DOPO rendering confermato
    if (data && data.response && data.response.trim().length > 0) {
      console.log('[TTS_MANDATORY] response valida, forcing TTS');
      console.log('[TTS_CALL] response_len=' + data.response.length + ' tts_mode=' + (data.tts_mode || 'none'));
      console.log('[TTS_CALL] response_preview=' + data.response.substring(0, 100) + '...');
      
      // USA tts_text per il TTS, display_text per la UI
      const ttsText = data.tts_text || data.response; // Fallback a response se tts_text non disponibile
      console.log('[TTS_CALL] tts_text_len=' + ttsText.length + ' tts_text_preview=' + ttsText.substring(0, 100) + '...');
      
      // TTS asincrono non bloccante - non interferisce con il rendering
      setTimeout(() => {
        try {
          console.log('[TTS_CALL] about_to_call_playTTS');
          playTTS(ttsText, data.tts_mode);
          console.log('[TTS_CALL] playTTS_returned_successfully');
        } catch (e) {
          console.error('[TTS_ABORT] reason=exception_in_playTTS error=', e);
          console.error('[TTS_ABORT] error_stack=', e.stack);
        }
      }, 50); // piccolo delay per garantire rendering completo
    } else if (data) {
      console.log('[TTS_SKIP] response vuota o non valida, skipping TTS');
    }
  } catch (e) {
    console.error('Chat error:', e);
    addGenesiMessage("Qualcosa non ha funzionato. Riprova tra poco.");
  } finally {
    setState(STATES.IDLE);
  }
}

chatForm.addEventListener('submit', (e) => {
  e.preventDefault();
  sendMessage();
});

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

const _useWebAudio = _isIOS || (_isSafari && !window.MediaRecorder);

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

// --- MediaRecorder path (Chrome, Android, Firefox) ---
let mediaRecorder = null;
let audioChunks = [];

function getSupportedMimeType() {
  if (typeof MediaRecorder === 'undefined') return '';
  for (const t of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']) {
    if (MediaRecorder.isTypeSupported(t)) return t;
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
    try { _audioCtx.close(); } catch(e) {}
  }
  _audioCtx = null;
  if (_gainContext && _gainContext.state !== 'closed') {
    try { _gainContext.close(); } catch(e) {}
  }
  _gainContext = null;
  isRecording = false;
  currentStream = null;
  micButton.classList.remove('recording');
}

async function startRecording() {
  // Barge-in: interrompi TTS quando utente preme mic
  _interruptTTS('mic_press');

  // Warm TTS AudioContext during mic tap gesture (iOS needs this for post-mic TTS)
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
    
    // SAFARI DESKTOP: constraints specifiche
    if (_isSafari && !_isIOS) {
      console.log('[MIC][DESKTOP] using Safari-specific constraints');
      // Safari desktop a volte richiede constraints più semplici
      constraints.audio = true;
    }
    
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    
    if (_isSafari && !_isIOS) {
      console.log('[MIC][DESKTOP] permission granted, Safari desktop stream ready');
    }
    
    console.log('[MIC] permission granted, tracks=' + stream.getAudioTracks().length);
    currentStream = stream;

    if (_useWebAudio) {
      // --- iOS Safari: AudioContext + ScriptProcessorNode → PCM WAV ---
      console.log('[iOS STT] setting up AudioContext recording');
      
      try {
        _audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: _SAMPLE_RATE });
        
        // iOS requires resume after user gesture
        if (_audioCtx.state === 'suspended') {
          await _audioCtx.resume();
          console.log('[iOS STT] AudioContext resumed');
        }
        
        console.log('[iOS STT] AudioContext rate=' + _audioCtx.sampleRate + ' state=' + _audioCtx.state);

        const source = _audioCtx.createMediaStreamSource(stream);
        
        // Aggiungi GainNode per ridurre volume a 0.3 (evita clipping)
        const gainNode = _audioCtx.createGain();
        gainNode.gain.value = 0.3;
        console.log('[iOS STT] GainNode created with gain=0.3');
        
        _scriptNode = _audioCtx.createScriptProcessor(4096, 1, 1);
        _pcmBuffers = [];
        _pcmLength = 0;
        let frameCount = 0;
        let audioDetected = false;
        let clippingCount = 0;

        _scriptNode.onaudioprocess = (e) => {
          const data = e.inputBuffer.getChannelData(0);
          
          // DEBUG iOS: verifica dati audio e calcola RMS/clipping
          let hasNonZero = false;
          let maxValue = 0;
          let sumSquares = 0;
          
          for (let i = 0; i < data.length; i++) {
            const absValue = Math.abs(data[i]);
            if (absValue > 0.00001) { // Soglia più bassa
              hasNonZero = true;
              maxValue = Math.max(maxValue, absValue);
            }
            
            // Clipping detection
            if (absValue > 0.95) {
              clippingCount++;
            }
            
            // RMS calculation
            sumSquares += data[i] * data[i];
          }
          
          const rms = Math.sqrt(sumSquares / data.length);
          
          // iOS: raccoglie TUTTI i dati audio senza soglia
          const copy = new Float32Array(data.length);
          copy.set(data);
          _pcmBuffers.push(copy);
          _pcmLength += copy.length;
          frameCount++;
          
          // Primo rilevamento audio
          if (hasNonZero && !audioDetected) {
            audioDetected = true;
            console.log('[iOS STT] AUDIO DETECTED! maxValue=' + maxValue.toFixed(6) + ' rms=' + rms.toFixed(6) + ' clipping=' + clippingCount);
          }
          
          // Log dettagliato per debug iOS
          if (frameCount === 1) {
            console.log('[iOS STT] FIRST FRAME: length=' + data.length + ' hasNonZero=' + hasNonZero + ' maxValue=' + maxValue.toFixed(6) + ' rms=' + rms.toFixed(6));
          }
          
          if (frameCount % 100 === 0) {
            console.log('[iOS STT] frame ' + frameCount + ': samples=' + _pcmLength + ' hasNonZero=' + hasNonZero + ' maxValue=' + maxValue.toFixed(6) + ' rms=' + rms.toFixed(6) + ' clipping=' + clippingCount);
          }
        };

        source.connect(gainNode);
        gainNode.connect(_scriptNode);
        // CONNETTI a destination per iOS (importante!)
        _scriptNode.connect(_audioCtx.destination);
        
        console.log('[iOS STT] ScriptProcessor connected to destination');

        isRecording = true;
        setState(STATES.RECORDING);
        micButton.classList.add('recording');
        console.log('[iOS STT] recording started with audio output');
        
        // Log finale statisthe alla fine della registrazione
        const originalStop = stopRecording;
        stopRecording = function() {
          console.log('[iOS STT] RECORDING STOPPED - FINAL STATS:');
          console.log('[iOS STT] Total frames: ' + frameCount);
          console.log('[iOS STT] Total samples: ' + _pcmLength);
          console.log('[iOS STT] Clipping events: ' + clippingCount);
          console.log('[iOS STT] Audio detected: ' + audioDetected);
          console.log('[iOS STT] Estimated duration: ' + (_pcmLength / 16000).toFixed(2) + 's');
          console.log('[iOS STT] Target amplitude: 8000-15000 (avoid >20000)');
          return originalStop.call(this);
        };
        
      } catch (error) {
        console.error('[iOS STT] AudioContext setup failed:', error);
        // Fallback: prova MediaRecorder se AudioContext fallisce
        console.log('[iOS STT] falling back to MediaRecorder');
        _useWebAudio = false;
        // Continua con il percorso MediaRecorder sotto
      }
    }
    
    if (!_useWebAudio) {
      // --- Standard: MediaRecorder con gain ---
      const mimeType = getSupportedMimeType();
      console.log('[MIC] MediaRecorder mimeType=' + mimeType);
      
      // Crea AudioContext per applicare gain anche a MediaRecorder
      const gainCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = gainCtx.createMediaStreamSource(stream);
      const gainNode = gainCtx.createGain();
      gainNode.gain.value = 0.3;
      
      // Crea destination per lo stream post-gain
      const destination = gainCtx.createMediaStreamDestination();
      source.connect(gainNode);
      gainNode.connect(destination);
      
      console.log('[MIC] GainNode created for MediaRecorder: gain=0.3');
      
      // MediaRecorder USA lo stream post-gain
      console.log('[MIC] Recording from POST-GAIN stream');
      mediaRecorder = new MediaRecorder(destination.stream, mimeType ? { mimeType } : {});
      audioChunks = [];
      
      // Salva contesto per cleanup
      _gainContext = gainCtx;

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const blobType = mimeType || 'audio/webm';
        const blob = new Blob(audioChunks, { type: blobType });
        console.log('[MIC] MediaRecorder blob size=' + blob.size);
        const stream = currentStream;
        resetMicrophoneState();
        if (stream) stream.getTracks().forEach(t => t.stop());
        await transcribeAudio(blob);
      };

      mediaRecorder.start(1000);
      console.log('[MIC] MediaRecorder started');
      
      if (_isSafari && !_isIOS) {
        console.log('[MIC][DESKTOP] Safari desktop recording started');
      }
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
      try { _audioCtx.close(); } catch(e) {}
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
    const ext = blob.type.includes('wav') ? '.wav' : '.webm';
    const fd = new FormData();
    fd.append('audio', blob, 'rec' + ext);
    
    console.log('[STT] sending POST /stt...');
    const res = await fetch('/stt', { method: 'POST', body: fd });
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

    loadingMsg = addGenesiMessage("Sto analizzando il file...");
    setState(STATES.THINKING);

    const fd = new FormData();
    fd.append('file', file);
    fd.append('user_id', getUserId());

    try {
      const res = await fetch('/upload', { method: 'POST', body: fd });
      if (!res.ok) throw new Error(`Upload ${res.status}`);
      const result = await res.json();
      if (loadingMsg) loadingMsg.remove();

      // Update bubble — short status only, full analysis goes to chat
      try {
        _updateBubbleStatus('Analisi completata');
        if (result.preview_url) _setBubblePreview(result.preview_url, file);
      } catch (_) { /* cosmetic */ }

      // Full analysis in chat message (not in bubble)
      addGenesiMessage(result.response || "File ricevuto.");

      // Auto-dismiss bubble after 6s
      setTimeout(() => { try { _dismissFileBubble(); } catch(_){} }, 6000);
    } catch (e) {
      console.error('Upload error:', e);
      if (loadingMsg) loadingMsg.remove();
      try { _updateBubbleStatus('Errore'); } catch(_){}
      addGenesiMessage("Errore nel caricamento. Riprova.");
      setTimeout(() => { try { _dismissFileBubble(); } catch(_){} }, 3000);
    } finally {
      setState(STATES.IDLE);
    }
  };
  input.click();
}

// ===============================
// EVENT LISTENERS
// ===============================
sendButton.addEventListener('click', sendMessage);
plusButton.addEventListener('click', handleFileUpload);

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
  if (_ttsSource) {
    _interruptTTS('text_typing');
  }
});

// ===============================
// INIT
// ===============================
// ===============================
// GLOBAL AUDIO UNLOCK - Prima gesture utente
// ===============================
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
// TTS AUDIO PLAYBACK - decodeAudioData + AudioBufferSourceNode
// ===============================
async function playTTSAudio(blob) {
  console.log('[TTS] TTS blob ricevuto - size=' + blob.size + ' type=' + blob.type);
  
  // Verifica AudioContext globale
  if (!window.audioContext) {
    console.error('[TTS] AudioContext non disponibile - audio non unlockato');
    return;
  }
  
  console.log('[AUDIO] context state: ' + window.audioContext.state);
  
  // Resume se suspended
  if (window.audioContext.state === 'suspended') {
    console.log('[TTS] Resume AudioContext...');
    await window.audioContext.resume();
    console.log('[TTS] AudioContext resumed - state: ' + window.audioContext.state);
  }
  
  try {
    // Converti blob in ArrayBuffer
    const arrayBuffer = await blob.arrayBuffer();
    console.log('[TTS] ArrayBuffer creato - size=' + arrayBuffer.byteLength);
    
    // Decodifica audio
    const audioBuffer = await window.audioContext.decodeAudioData(arrayBuffer);
    console.log('[TTS] AudioBuffer decodificato - duration=' + audioBuffer.duration + 's sampleRate=' + audioBuffer.sampleRate);
    
    // Crea AudioBufferSourceNode
    const source = window.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(window.audioContext.destination);
    
    // Log quando parte il playback
    source.onended = () => {
      console.log('[TTS] Playback completato');
      _ttsSource = null;
      _isPlayingChunk = false;
    };
    
    // Avvia playback
    console.log('[AUDIO] playback start');
    source.start(0);
    
    // Aggiorna stato TTS
    _ttsSource = source;
    _isPlayingChunk = true;
    _wasPlayingChunk = true;
    
    console.log('[TTS] AudioBufferSourceNode avviato con successo');
    
  } catch (error) {
    console.error('[TTS] Errore durante playback TTS:', error);
    console.error('[TTS] Errore details:', error.message);
    _ttsSource = null;
    _isPlayingChunk = false;
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

(async () => {
  // Apply auth state FIRST - sempre loggato
  applyAuthState();

  // Bootstrap utente SEMPRE
  await bootstrapUser();
  scrollToBottom();

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