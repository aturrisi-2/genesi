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
// Stato globale
// ===============================
let currentState = STATES.IDLE;

// ===============================
// UI State Management
// ===============================
function setState(newState) {
  currentState = newState;
  app.dataset.state = currentState;

  // input sempre attivo, blocchiamo solo il send
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
  dialogue.scrollTop = dialogue.scrollHeight;
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
  const response = await fetch('/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ text: message })
  });

  if (!response.ok) {
    throw new Error(`Chat error ${response.status}`);
  }

  const data = await response.json();
  return data.reply || data.response || "Non ho capito.";
}

// ===============================
// Message Sending
// ===============================
async function sendMessage() {
  const text = textInput.value.trim();
  if (!text || currentState !== STATES.IDLE) return;

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
// Event Listeners
// ===============================
textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendButton.addEventListener('click', sendMessage);

// ===============================
// Microfono (solo UI, non logica)
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

  // simulazione: trascrizione finta
  setTimeout(() => {
    const transcript = "Questo è un messaggio dettato di esempio.";
    textInput.value = transcript;
    setState(STATES.IDLE);
    sendMessage();
  }, 600);
}

micButton.addEventListener('mousedown', startRecording);
micButton.addEventListener('touchstart', startRecording);
document.addEventListener('mouseup', stopRecording);
document.addEventListener('touchend', stopRecording);

// ===============================
// Init
// ===============================
setState(STATES.IDLE);
