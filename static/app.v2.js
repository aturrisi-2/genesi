// Stati dell'applicazione
const STATES = {
  IDLE: 'idle',
  THINKING: 'thinking',
  SPEAKING: 'speaking',
  RECORDING: 'recording'
};
const ENABLE_TTS = false;

// Seleziona gli elementi DOM
const app = document.getElementById('genesi-app');
const dialogue = document.getElementById('dialogue');
const textInput = document.getElementById('text-input');
const sendButton = document.getElementById('send-button');
const micButton = document.getElementById('mic-button');

// Stato globale
let currentState = STATES.IDLE;
let currentAudio = null;

// Imposta lo stato corrente
function setState(newState) {
  currentState = newState;
  app.dataset.state = currentState;
}

// Aggiunge un messaggio alla chat
function addMessage(text, sender) {
  const messageEl = document.createElement('div');
  messageEl.className = `message ${sender}`;
  messageEl.textContent = text;
  dialogue.appendChild(messageEl);
  dialogue.scrollTop = dialogue.scrollHeight;
  return messageEl;
}

// Aggiunge un messaggio dell'utente
function addUserMessage(text) {
  addMessage(text, 'user');
}

// Gestisce l'invio del messaggio
async function addGenesiMessage(text) {
  const messageEl = addMessage(text, 'genesi');
  
// Gestisce l'invio del messaggio dall'input
function sendMessage() {
  const text = textInput.value.trim();
  if (!text || currentState !== STATES.IDLE) return;

  // messaggio utente
  addUserMessage(text);
  textInput.value = '';

  // stato thinking
  setState(STATES.THINKING);

  // risposta (per ora statica / mock)
  setTimeout(() => {
    addGenesiMessage("Ho ricevuto il tuo messaggio. Come posso aiutarti?");
  }, 400);
}

  // 🔒 TTS DISABILITATO: niente speaking, niente audio
  setState(STATES.IDLE);

  return messageEl;
}


// Gestione input da tastiera
textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Gestione click sul pulsante di invio
sendButton.addEventListener('click', sendMessage);

// Gestione microfono (solo UI)
function startRecording() {
  if (currentState !== STATES.IDLE) return;
  setState(STATES.RECORDING);
  micButton.classList.add('recording');

  // Simula registrazione per 2-4 secondi
  setTimeout(() => {
    if (currentState === STATES.RECORDING) {
      stopRecording();
    }
  }, 2000 + Math.random() * 2000);
}

function stopRecording() {
  if (currentState !== STATES.RECORDING) return;
  
  micButton.classList.remove('recording');
  setState(STATES.THINKING);
  
  // Simula trascrizione
  setTimeout(() => {
    const transcript = "Questo è un messaggio dettato di esempio.";
    addUserMessage(transcript);
    
    // Simula risposta
    setTimeout(async () => {
      const response = "Ho capito il tuo messaggio vocale.";
      await addGenesiMessage(response);
    }, 500);
  }, 500);
}

// Gestione click sul pulsante microfono
micButton.addEventListener('mousedown', (e) => {
  e.preventDefault();
  startRecording();
});

micButton.addEventListener('touchstart', (e) => {
  e.preventDefault();
  startRecording();
});

document.addEventListener('mouseup', () => {
  if (currentState === STATES.RECORDING) {
    stopRecording();
  }
});

document.addEventListener('touchend', (e) => {
  if (currentState === STATES.RECORDING) {
    e.preventDefault();
    stopRecording();
  }
});

// Aggiorna lo stato iniziale
setState(STATES.IDLE);