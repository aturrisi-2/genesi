//è lui ===
// ===============================
// Stati dell'applicazione
// ===============================
const STATES = {
  IDLE: 'idle',
  THINKING: 'thinking',
  SPEAKING: 'speaking',
  RECORDING: 'recording'
};

const ENABLE_TTS = false;

// ===============================
// DOM
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
// Stato UI
// ===============================
function setState(newState) {
  currentState = newState;
  app.dataset.state = currentState;
}

// ===============================
// Messaggi
// ===============================
function addMessage(text, sender) {
  const messageEl = document.createElement('div');
  messageEl.className = `message ${sender}`;
  messageEl.textContent = text;
  dialogue.appendChild(messageEl);
  dialogue.scrollTop = dialogue.scrollHeight;
}

function addUserMessage(text) {
  addMessage(text, 'user');
}

function addGenesiMessage(text) {
  addMessage(text, 'genesi');
  setState(STATES.IDLE);
}

// ===============================
// INVIO MESSAGGIO (INPUT)
// ===============================
function sendMessage() {
  const text = textInput.value.trim();
  if (!text || currentState !== STATES.IDLE) return;

  addUserMessage(text);
  textInput.value = '';

  setState(STATES.THINKING);

  // risposta mock (per ora)
  setTimeout(() => {
    addGenesiMessage("Ho ricevuto il tuo messaggio. Come posso aiutarti?");
  }, 400);
}

// ===============================
// Event listener input
// ===============================
textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendButton.addEventListener('click', sendMessage);

// ===============================
// Microfono (solo UI, mock)
// ===============================
function startRecording() {
  if (currentState !== STATES.IDLE) return;
  setState(STATES.RECORDING);
  micButton.classList.add('recording');

  setTimeout(stopRecording, 2000);
}

function stopRecording() {
  if (currentState !== STATES.RECORDING) return;

  micButton.classList.remove('recording');
  setState(STATES.THINKING);

  setTimeout(() => {
    addUserMessage("Questo è un messaggio dettato di esempio.");
    setTimeout(() => {
      addGenesiMessage("Ho capito il tuo messaggio vocale.");
    }, 500);
  }, 500);
}

micButton.addEventListener('mousedown', (e) => {
  e.preventDefault();
  startRecording();
});

micButton.addEventListener('touchstart', (e) => {
  e.preventDefault();
  startRecording();
});

document.addEventListener('mouseup', stopRecording);
document.addEventListener('touchend', stopRecording);

// ===============================
// Init
// ===============================
setState(STATES.IDLE);
