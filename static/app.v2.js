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

// Auth DOM
const authGate = document.getElementById('auth-gate');
const userBar = document.getElementById('user-bar');
const userGreeting = document.getElementById('user-greeting');
const adminLink = document.getElementById('admin-link');
const logoutBtn = document.getElementById('logout-btn');

// ===============================
// AUTH STATE
// ===============================
let _isLoggedIn = false;

function getAuthToken() {
  return localStorage.getItem('genesi_access_token');
}

function isLoggedIn() {
  const token = getAuthToken();
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      return false;
    }
    return true;
  } catch (e) {
    return false;
  }
}

function getTokenPayload() {
  const token = getAuthToken();
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch (e) {
    return null;
  }
}

function isAdmin() {
  const p = getTokenPayload();
  return p && p.admin === true;
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
    if (res.ok) {
      const data = await res.json();
      localStorage.setItem('genesi_access_token', data.access_token);
      localStorage.setItem('genesi_refresh_token', data.refresh_token);
      return true;
    }
  } catch (e) {}
  return false;
}

function doLogout() {
  localStorage.removeItem('genesi_access_token');
  localStorage.removeItem('genesi_refresh_token');
  localStorage.removeItem('genesi_is_admin');
  applyAuthState();
}

function applyAuthState() {
  _isLoggedIn = isLoggedIn();

  if (_isLoggedIn) {
    // Logged in: hide gate, show chat + user bar
    authGate.style.display = 'none';
    userBar.style.display = 'flex';
    document.getElementById('presence').style.display = '';
    dialogue.style.display = '';
    document.getElementById('status').style.display = '';
    chatForm.style.display = '';

    // Greeting
    const payload = getTokenPayload();
    const uid = payload ? payload.sub : '';
    userGreeting.textContent = 'Ciao';

    // Admin link
    if (isAdmin()) {
      adminLink.style.display = 'inline-block';
    } else {
      adminLink.style.display = 'none';
    }
  } else {
    // Not logged in: show gate, hide chat
    authGate.style.display = 'flex';
    userBar.style.display = 'none';
    document.getElementById('presence').style.display = 'none';
    dialogue.style.display = 'none';
    document.getElementById('status').style.display = 'none';
    chatForm.style.display = 'none';
  }
}

// Logout handler
if (logoutBtn) {
  logoutBtn.addEventListener('click', doLogout);
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
// TTS AUDIO — decoded via AudioContext (Safari-safe)
// ===============================
let _ttsCtx = null;
let _ttsSource = null;
let ttsEnabled = true;

function _getTTSCtx() {
  if (!_ttsCtx || _ttsCtx.state === 'closed') {
    _ttsCtx = new (window.AudioContext || window.webkitAudioContext)();
    console.log('[TTS] AudioContext created, rate=' + _ttsCtx.sampleRate);
  }
  return _ttsCtx;
}

// iOS Safari: AudioContext must be created+resumed during a synchronous
// user gesture (tap/click). Call this at the START of any gesture handler,
// BEFORE any await, so the gesture is still "active" for iOS.
function _warmTTSCtx() {
  const ctx = _getTTSCtx();
  if (ctx.state === 'suspended') {
    ctx.resume();
    console.log('[TTS] ctx warmed (resume called during gesture)');
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
  if (!ttsEnabled || !text) return;
  
  const chunks = _splitTextForTTS(text, tts_mode);
  console.log('[TTS] CHUNKING: total_len=' + text.length + ' mode=' + tts_mode);
  console.log('[TTS] CHUNKS:', chunks.map((c, i) => `${i + 1}: "${c.substring(0, 50)}..." (${c.length}char)`));
  
  for (let i = 0; i < chunks.length; i++) {
    // VERIFICA INPUT UTENTE PRIMA DI OGNI CHUNK
    if (_ttsSource === null) {
      console.log('[TTS] interrupted before chunk', i + 1);
      break;
    }
    
    const chunk = chunks[i];
    console.log('[TTS] PLAYING chunk', i + 1, '/', chunks.length, 'len=' + chunk.length);
    console.log('[TTS] CHUNK TEXT:', chunk);
    
    try {
      await _playTTSChunk(chunk);
      
      // PAUSA LUNGA per psychological tra chunk
      if (tts_mode === 'psychological' && i < chunks.length - 1) {
        console.log('[TTS] psychological pause between chunks');
        await new Promise(resolve => setTimeout(resolve, 800)); // 800ms pause
      }
    } catch (e) {
      console.error('[TTS] chunk error:', e);
      break;
    }
    
    // VERIFICA INPUT UTENTE DOPO OGNI CHUNK
    if (_ttsSource === null) {
      console.log('[TTS] interrupted after chunk', i + 1);
      break;
    }
  }
}

async function _playTTSChunk(text) {
  if (!ttsEnabled || !text) return;
  
  console.log('[TTS] _playTTSChunk len=' + text.length);
  console.log('[TTS] TEXT:', text);
  
  try {
    console.log('[TTS] FETCH: calling /tts...');
    const response = await fetch('/tts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({'text': text})
    });
    
    console.log('[TTS] RESPONSE: status=' + response.status + ' headers=' + JSON.stringify(Object.fromEntries(response.headers.entries())));
    
    if (!response.ok) {
      console.error('[TTS] HTTP error:', response.status, response.statusText);
      const errorText = await response.text();
      console.error('[TTS] ERROR BODY:', errorText);
      return;
    }
    
    const audioBlob = await response.blob();
    console.log('[TTS] BLOB: size=' + audioBlob.size + ' type=' + audioBlob.type);
    
    // ASSERT FINALE: blob size > 0
    if (audioBlob.size === 0) {
      console.error('[TTS] ERROR: Audio blob size 0!');
      return;
    }
    
    if (audioBlob.size < 100) {
      console.warn('[TTS] WARNING: Audio blob very small (' + audioBlob.size + ' bytes)');
    }
    
    const audioUrl = URL.createObjectURL(audioBlob);
    console.log('[TTS] AUDIO URL created');
    
    const audio = new Audio(audioUrl);
    _ttsSource = audio;
    
    audio.onended = () => {
      console.log('[TTS] CHUNK ENDED: duration=' + audio.duration + 's');
      _ttsSource = null;
      URL.revokeObjectURL(audioUrl);
    };
    
    audio.oncanplay = () => {
      console.log('[TTS] AUDIO CAN PLAY: duration=' + audio.duration + 's');
    };
    
    console.log('[TTS] CALLING audio.play()...');
    await audio.play();
    console.log('[TTS] AUDIO PLAYING: duration=' + audio.duration + 's');
    
  } catch (e) {
    console.error('[TTS] _playTTSChunk error:', e);
    _ttsSource = null;
  }
}

async function playTTS(text, tts_mode = 'normal') {
  if (!ttsEnabled || !text) return;
  console.log('[TTS] playTTS len=' + text.length + ' mode=' + tts_mode);
  
  // FORZA segmentazione per testi informativi, psychological o lunghi
  if (tts_mode === 'informative' || tts_mode === 'psychological' || text.length > 500) {
    await playTTSSegmented(text, tts_mode);
  } else {
    // Testi brevi normali: playback normale
    await _playTTSChunk(text);
  }
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
  el.textContent = text;

  // Assign rotating neon hue
  const hue = _neonHues[_neonIdx % _neonHues.length];
  el.style.setProperty('--neon-hue', hue + 'deg');
  _neonIdx++;

  dialogue.appendChild(el);

  // Always scroll on new message (user just sent or received)
  requestAnimationFrame(() => scrollToBottom());
  return el;
}

function addUserMessage(text) { return addMessage(text, 'user'); }
function addGenesiMessage(text) { return addMessage(text, 'genesi'); }

// ===============================
// CHAT API
// ===============================
async function sendChatMessage(message) {
  if (!_isLoggedIn) {
    return 'Devi accedere per usare Genesi.';
  }
  const res = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: getUserId(), message })
  });
  if (res.status === 401 || res.status === 403) {
    // Try refresh
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return await sendChatMessage(message);
    }
    doLogout();
    return 'La sessione è scaduta. Effettua di nuovo l\'accesso.';
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data;
}

// ===============================
// SEND MESSAGE
// ===============================
async function sendMessage() {
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
    if (data && data.response) {
      addGenesiMessage(data.response);
      
      // TTS OBBLIGATORIO QUANDO should_respond=True
      if (data.should_respond) {
        console.log('[TTS_MANDATORY] should_respond=True, forcing TTS');
        playTTS(data.response, data.tts_mode);
      } else {
        console.log('[TTS_MANDATORY] should_respond=False, skipping TTS');
      }
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

// iOS Safari detection
const _isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const _isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
const _useWebAudio = _isIOS || (_isSafari && !window.MediaRecorder);

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
  isRecording = false;
  currentStream = null;
  micButton.classList.remove('recording');
}

async function startRecording() {
  // Barge-in: interrompi TTS quando utente preme mic
  _interruptTTS('mic_press');

  // Warm TTS AudioContext during mic tap gesture (iOS needs this for post-mic TTS)
  _warmTTSCtx();

  console.log('[MIC] start, iOS=' + _isIOS + ' safari=' + _isSafari + ' webAudio=' + _useWebAudio);
  if (currentState !== STATES.IDLE || isRecording) return;
  stopAudio();

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });
    console.log('[MIC] getUserMedia OK, tracks=' + stream.getAudioTracks().length);
    currentStream = stream;

    if (_useWebAudio) {
      // --- iOS Safari: AudioContext + ScriptProcessorNode → PCM WAV ---
      _audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: _SAMPLE_RATE });
      // iOS requires resume after user gesture
      if (_audioCtx.state === 'suspended') await _audioCtx.resume();
      console.log('[MIC][iOS] AudioContext rate=' + _audioCtx.sampleRate + ' state=' + _audioCtx.state);

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
      console.log('[MIC][iOS] recording via ScriptProcessor');

    } else {
      // --- Standard: MediaRecorder ---
      const mimeType = getSupportedMimeType();
      console.log('[MIC] MediaRecorder mimeType=' + mimeType);
      mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      audioChunks = [];

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
        if (blob.size < 500) { setState(STATES.IDLE); return; }
        await transcribeAudio(blob);
      };

      mediaRecorder.start(1000);
    }

    isRecording = true;
    setState(STATES.RECORDING);
    micButton.classList.add('recording');

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
    const merged = new Float32Array(_pcmLength);
    let offset = 0;
    for (const buf of _pcmBuffers) { merged.set(buf, offset); offset += buf.length; }

    const downsampled = _downsample(merged, nativeSR, _SAMPLE_RATE);
    const wavBlob = _encodeWAV(downsampled);
    console.log('[MIC][iOS] WAV blob size=' + wavBlob.size + ' samples=' + downsampled.length);

    resetMicrophoneState();
    if (stream) stream.getTracks().forEach(t => t.stop());

    if (wavBlob.size < 500) { setState(STATES.IDLE); return; }
    transcribeAudio(wavBlob);

  } else {
    // --- Standard: stop MediaRecorder (onstop handler fires) ---
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
    }
  }
}

async function transcribeAudio(blob) {
  console.log('[STT] sending size=' + blob.size + ' type=' + blob.type);
  setState(STATES.THINKING);
  try {
    const ext = blob.type.includes('wav') ? '.wav' : '.webm';
    const fd = new FormData();
    fd.append('audio', blob, 'rec' + ext);
    const res = await fetch('/stt', { method: 'POST', body: fd });
    console.log('[STT] status=' + res.status);
    if (!res.ok) throw new Error('STT ' + res.status);
    const result = await res.json();
    const text = result.text?.trim() || '';
    console.log('[STT] text="' + text + '"');
    if (text) {
      textInput.value = text;
      setState(STATES.IDLE);
      sendMessage();
    } else {
      setState(STATES.IDLE);
    }
  } catch (e) {
    console.error('[STT] error:', e);
    setState(STATES.IDLE);
  }
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
// iOS: pre-unlock AudioContext on very first user interaction
document.addEventListener('touchstart', function _firstTouch() {
  _warmTTSCtx();
  document.removeEventListener('touchstart', _firstTouch);
}, { once: true });

(async () => {
  // Apply auth state FIRST — determines what the user sees
  applyAuthState();

  if (_isLoggedIn) {
    await bootstrapUser();
    scrollToBottom();
  }

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