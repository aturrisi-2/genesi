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

async function playTTS(text) {
  if (!ttsEnabled || !text) return;
  console.log('[TTS] playTTS len=' + text.length);

  stopAudio();

  try {
    const res = await fetch('/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    console.log('[TTS] fetch status=' + res.status);
    if (!res.ok) { console.warn('[TTS] not ok'); return; }

    const arrayBuf = await res.arrayBuffer();
    console.log('[TTS] arrayBuffer bytes=' + arrayBuf.byteLength);
    if (arrayBuf.byteLength < 100) { console.warn('[TTS] too small'); return; }

    const ctx = _getTTSCtx();
    if (ctx.state === 'suspended') await ctx.resume();
    console.log('[TTS] ctx.state=' + ctx.state);

    const audioBuffer = await ctx.decodeAudioData(arrayBuf);
    console.log('[TTS] decoded, duration=' + audioBuffer.duration.toFixed(2) + 's');

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    source.onended = () => {
      console.log('[TTS] ended');
      _ttsSource = null;
    };

    _ttsSource = source;
    source.start(0);
    console.log('[TTS] playing');
  } catch (e) {
    console.error('[TTS] failed:', e);
    _ttsSource = null;
  }
}

// ===============================
// USER IDENTITY
// ===============================
function getUserId() {
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
function addMessage(text, sender) {
  const el = document.createElement('div');
  el.className = `message ${sender}`;
  el.textContent = text;
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
  const res = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: getUserId(), message })
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.response || '';
}

// ===============================
// SEND MESSAGE
// ===============================
async function sendMessage() {
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
    const reply = await sendChatMessage(text);
    if (reply) {
      addGenesiMessage(reply);
      playTTS(reply);
    }
  } catch (e) {
    console.error('Chat error:', e);
    addGenesiMessage("Errore di connessione. Riprova.");
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
// FILE UPLOAD
// ===============================
function handleFileUpload() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '*/*';

  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const loadingMsg = addGenesiMessage("Sto analizzando il file...");
    setState(STATES.THINKING);

    const fd = new FormData();
    fd.append('file', file);
    fd.append('user_id', getUserId());

    try {
      const res = await fetch('/upload', { method: 'POST', body: fd });
      if (!res.ok) throw new Error(`Upload ${res.status}`);
      const result = await res.json();
      loadingMsg.remove();
      addGenesiMessage(result.response || "File ricevuto.");
    } catch (e) {
      console.error('Upload error:', e);
      loadingMsg.remove();
      addGenesiMessage("Errore nel caricamento. Riprova.");
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
// INPUT FOCUS — KEYBOARD HANDLING
// ===============================
textInput.addEventListener('focus', () => {
  // iOS keyboard animation can take ~400ms on first open
  setTimeout(() => { updateAppHeight(); scrollToBottom(); }, 100);
  setTimeout(() => { updateAppHeight(); scrollToBottom(); }, 400);
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