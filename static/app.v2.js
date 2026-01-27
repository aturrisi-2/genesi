// ===============================
// Stati dell'applicazione
// ===============================
const STATES = {
  IDLE: 'idle',
  THINKING: 'thinking',
  RECORDING: 'recording'
};

// ===============================
// DOM Elements
// ===============================
const app = document.getElementById('genesi-app');
const dialogue = document.getElementById('dialogue'); // chat container reale
const textInput = document.getElementById('text-input');
const sendButton = document.getElementById('send-button');
const micButton = document.getElementById('mic-button');
const inputContainer = document.getElementById('input-container');
const chatForm = document.getElementById('chat-form'); // ⚠️ DEVE ESISTERE IN HTML

// ===============================
// Auto-scroll Utility (ROBUSTO iOS)
// ===============================
function scrollToBottom(force = false) {
  requestAnimationFrame(() => {
    dialogue.scrollTop = dialogue.scrollHeight;
  });

  if (force) {
    setTimeout(() => {
      dialogue.scrollTop = dialogue.scrollHeight;
    }, 120);
  }
}

// ===============================
// User Identity
// ===============================
function getUserId() {
  let id = localStorage.getItem('genesi_user_id');
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem('genesi_user_id', id);
  }
  return id;
}

// ===============================
// User Bootstrap
// ===============================
let userIdentity = {};

async function bootstrapUser() {
  const userId = getUserId();

  const res = await fetch("/user/bootstrap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId })
  });

  if (!res.ok) {
    console.error("Bootstrap failed");
    return;
  }

  const data = await res.json();
  userIdentity = data.identity || {};
}

// ===============================
// UI State Management
// ===============================
let currentState = STATES.IDLE;

function setState(newState) {
  currentState = newState;
  app.dataset.state = currentState;
  sendButton.disabled = currentState !== STATES.IDLE;
}

// ===============================
// Message Handling
// ===============================
function addMessage(text, sender) {
  const messageEl = document.createElement('div');
  messageEl.className = `message ${sender}`;
  messageEl.textContent = text;
  dialogue.appendChild(messageEl);
  scrollToBottom(true);
  return messageEl;
}

function addUserMessage(text) {
  return addMessage(text, 'user');
}

function addGenesiMessage(text) {
  return addMessage(text, 'genesi');
}

// ===============================
// API Communication
// ===============================
async function sendChatMessage(message) {
  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: getUserId(),
        message
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.response || "Non ho capito.";

  } catch (error) {
    console.error(error);
    return "C'è stato un errore di connessione.";
  }
}

// ===============================
// Message Sending (UNICO PUNTO)
// ===============================
async function sendMessage() {
  const text = textInput.value.trim();
  if (!text || currentState !== STATES.IDLE) return;

  // 🔥 svuota SUBITO (fix iOS)
  textInput.value = "";

  addUserMessage(text);
  setState(STATES.THINKING);

  try {
    const reply = await sendChatMessage(text);
    addGenesiMessage(reply);
  } catch {
    addGenesiMessage("C'è stato un errore. Riprova.");
  } finally {
    setState(STATES.IDLE);
    scrollToBottom(true);
  }
}

// ===============================
// FORM SUBMIT (FIX DEFINITIVO iOS)
// ===============================
chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage();
});

// ===============================
// Microphone (UI Only)
// ===============================
function startRecording() {
  if (currentState !== STATES.IDLE) return;
  setState(STATES.RECORDING);
  micButton.classList.add('recording');
}

function stopRecording() {
  if (currentState !== STATES.RECORDING) return;

  micButton.classList.remove('recording');
  setState(STATES.THINKING);

  setTimeout(() => {
    textInput.value = "Questo è un messaggio dettato di esempio.";
    setState(STATES.IDLE);
    sendMessage();
  }, 600);
}

// ===============================
// Event Listeners
// ===============================
sendButton.addEventListener('click', sendMessage);
micButton.addEventListener('mousedown', startRecording);
micButton.addEventListener('touchstart', startRecording);
document.addEventListener('mouseup', stopRecording);
document.addEventListener('touchend', stopRecording);

// ===============================
// 📱 iOS KEYBOARD FIX
// ===============================
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", () => {
    document.documentElement.style.setProperty(
      "--vh",
      `${window.visualViewport.height}px`
    );
    scrollToBottom(true);
  });
}

textInput.addEventListener("focus", () => {
  setTimeout(() => scrollToBottom(true), 150);
});

textInput.addEventListener("blur", () => {
  setTimeout(() => scrollToBottom(true), 150);
});

// ===============================
// App Init
// ===============================
(async () => {
  await bootstrapUser();
  scrollToBottom(true);
})();
