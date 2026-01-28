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
const dialogue = document.getElementById('dialogue');
const textInput = document.getElementById('text-input');
const sendButton = document.getElementById('send-button');
const micButton = document.getElementById('mic-button');
const inputContainer = document.getElementById('input-container');
const chatForm = document.getElementById('chat-form');

// ===============================
// 📱 iOS Safari Auto-scroll ROBUSTO
// ===============================
function scrollToBottom(force = false) {
  const scroll = () => {
    dialogue.scrollTop = dialogue.scrollHeight;
  };
  
  requestAnimationFrame(scroll);
  
  if (force) {
    setTimeout(scroll, 100);
    setTimeout(scroll, 300);
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
// 📱 iOS Message Sending (FIX DEFINITIVO)
// ===============================
async function sendMessage() {
  const text = textInput.value.trim();
  if (!text || currentState !== STATES.IDLE) return;

  textInput.value = "";
  textInput.blur();

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
// 📱 iOS Form Submit (ENTER FIX)
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
// 📱 iOS Safari Keyboard & Viewport FIX
// ===============================
let viewportHeight = window.innerHeight;

if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", () => {
    const newHeight = window.visualViewport.height;
    document.documentElement.style.setProperty("--vh", `${newHeight}px`);
    
    if (Math.abs(newHeight - viewportHeight) > 100) {
      setTimeout(() => scrollToBottom(true), 150);
    }
    viewportHeight = newHeight;
  });
} else {
  window.addEventListener("resize", () => {
    document.documentElement.style.setProperty("--vh", `${window.innerHeight}px`);
    setTimeout(() => scrollToBottom(true), 150);
  });
}

textInput.addEventListener("focus", () => {
  setTimeout(() => scrollToBottom(true), 200);
});

textInput.addEventListener("blur", () => {
  setTimeout(() => scrollToBottom(true), 200);
});

// ===============================
// App Init
// ===============================
(async () => {
  await bootstrapUser();
  scrollToBottom(true);
})();
