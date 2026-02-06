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
  const h = window.visualViewport
    ? window.visualViewport.height
    : window.innerHeight;
  document.documentElement.style.setProperty('--app-height', h + 'px');
}

updateAppHeight();

if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', () => {
    updateAppHeight();
    // After keyboard open/close, scroll to bottom if user was near bottom
    if (isNearBottom()) {
      requestAnimationFrame(() => scrollToBottom());
    }
  });
  window.visualViewport.addEventListener('scroll', updateAppHeight);
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
// TTS AUDIO
// ===============================
let currentAudio = null;
let ttsEnabled = true;

function stopAudio() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
}

async function playTTS(text) {
  if (!ttsEnabled || !text) return;

  stopAudio();

  try {
    const res = await fetch('/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });

    if (!res.ok) return;

    const blob = await res.blob();
    if (blob.size < 100) return;

    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;

    audio.onended = () => {
      URL.revokeObjectURL(url);
      currentAudio = null;
    };

    audio.onerror = () => {
      URL.revokeObjectURL(url);
      currentAudio = null;
    };

    await audio.play();
  } catch (e) {
    console.warn('TTS playback failed:', e);
    currentAudio = null;
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
  const text = textInput.value.trim();
  if (!text || currentState !== STATES.IDLE) return;

  textInput.value = '';

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
// MICROPHONE
// ===============================
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let currentStream = null;

function getSupportedMimeType() {
  for (const t of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/wav']) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return '';
}

function resetMicrophoneState() {
  mediaRecorder = null;
  audioChunks = [];
  isRecording = false;
  currentStream = null;
  micButton.classList.remove('recording');
}

async function startRecording() {
  if (currentState !== STATES.IDLE || isRecording) return;

  // Stop any playing TTS
  stopAudio();

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });

    currentStream = stream;
    const mimeType = getSupportedMimeType();
    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      setTimeout(async () => {
        if (currentStream) currentStream.getTracks().forEach(t => t.stop());

        const blobType = mimeType || 'audio/webm';
        const blob = new Blob(audioChunks, { type: blobType });
        resetMicrophoneState();

        if (blob.size < 500) {
          setState(STATES.IDLE);
          return;
        }
        await transcribeAudio(blob);
      }, 200);
    };

    mediaRecorder.start(1000);
    isRecording = true;
    setState(STATES.RECORDING);
    micButton.classList.add('recording');

  } catch (e) {
    console.error('Mic denied:', e);
    setState(STATES.IDLE);
  }
}

function stopRecording() {
  if (!isRecording || !mediaRecorder) return;
  mediaRecorder.stop();
}

async function transcribeAudio(blob) {
  setState(STATES.THINKING);
  try {
    const fd = new FormData();
    fd.append('audio', blob, `rec${blob.type.includes('wav') ? '.wav' : '.webm'}`);
    const res = await fetch('/stt', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`STT ${res.status}`);
    const result = await res.json();
    const text = result.text?.trim() || '';
    if (text) {
      textInput.value = text;
      setState(STATES.IDLE);
      sendMessage();
    } else {
      setState(STATES.IDLE);
    }
  } catch (e) {
    console.error('STT error:', e);
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
  // Wait for keyboard animation to complete, then scroll
  setTimeout(() => {
    updateAppHeight();
    scrollToBottom();
  }, 300);
});

// ===============================
// INIT
// ===============================
(async () => {
  await bootstrapUser();
  scrollToBottom();
})();