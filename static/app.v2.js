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

// ===============================
// Auto-scroll Utility
// ===============================
function scrollToBottom() {
  requestAnimationFrame(() => {
    window.scrollTo({
      top: document.body.scrollHeight,
      behavior: "auto"
    });
  });
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

  // 🔒 Salviamo identity lato client
  userIdentity = data.identity || {};
}

// ===============================
// UI State Management
// ===============================
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
  scrollToBottom(); // Auto-scroll after adding message
  return messageEl;
}

function addUserMessage(text) {
  const msg = addMessage(text, 'user');
  scrollToBottom(); // Ensure scroll after message is added
  return msg;
}

function addGenesiMessage(text) {
  const msg = addMessage(text, 'genesi');
  scrollToBottom(); // Ensure scroll after message is added
  return msg;
}

// ===============================
// API Communication
// ===============================
async function sendChatMessage(message) {
  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_id: getUserId(),
        message: message
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data.response || "Non ho capito.";

  } catch (error) {
    console.error('Error sending message:', error);
    return "C'è stato un errore di connessione.";
  }
}

// ===============================
// Message Sending
// ===============================
async function sendMessage() {
  const text = textInput.value.trim();
  if (!text || currentState !== STATES.IDLE) return;

  // Add user message and clear input
  addUserMessage(text);
  textInput.value = '';
  setState(STATES.THINKING);

  try {
    const reply = await sendChatMessage(text);
    addGenesiMessage(reply);
  } catch (err) {
    console.error(err);
    addGenesiMessage("C'è stato un errore. Riprova.");
  } finally {
    setState(STATES.IDLE);
  }
}

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

  // Simulate voice input
  setTimeout(() => {
    const transcript = "Questo è un messaggio dettato di esempio.";
    textInput.value = transcript;
    setState(STATES.IDLE);
    sendMessage();
  }, 600);
}

// ===============================
// Event Listeners
// ===============================
textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendButton.addEventListener('click', sendMessage);
micButton.addEventListener('mousedown', startRecording);
micButton.addEventListener('touchstart', startRecording);
document.addEventListener('mouseup', stopRecording);
document.addEventListener('touchend', stopRecording);

// Initialize
let currentState = STATES.IDLE;
setState(STATES.IDLE);

// ===============================
// App Init
// ===============================
(async () => {
  await bootstrapUser();
})();
// ===============================
// 📱 iOS KEYBOARD FIX (CRITICO)
// ===============================
const input = document.getElementById("text-input");
const inputContainer = document.getElementById("input-container");

if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", () => {
        const vh = window.visualViewport.height;
        document.documentElement.style.setProperty(
            "--vh",
            `${vh}px`
        );

        // forza scroll all'ultimo messaggio
        setTimeout(() => {
            dialogue.scrollTop = dialogue.scrollHeight;
        }, 50);
    });
}

// quando clicchi l’input → resta visibile
input.addEventListener("focus", () => {
    setTimeout(() => {
        dialogue.scrollTop = dialogue.scrollHeight;
    }, 100);
});

// quando chiudi tastiera → reset naturale
input.addEventListener("blur", () => {
    setTimeout(() => {
        dialogue.scrollTop = dialogue.scrollHeight;
    }, 100);
});

// Initial scroll to bottom
scrollToBottom();