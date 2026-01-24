// Stato globale per TTS
let isSpeaking = false;
let currentAudio = null;

// Seleziona gli elementi DOM
const app = document.getElementById('genesi-app');
const dialogue = document.getElementById('dialogue');
const statusEl = document.getElementById('status');
const micButton = document.getElementById('mic-button');
const sendButton = document.getElementById('send-button');
const plusButton = document.getElementById('plus-button');
const textInput = document.getElementById('text-input');

// Stati dell'applicazione
const STATES = {
  IDLE: 'idle',
  RECORDING: 'recording',
  THINKING: 'thinking',
  SPEAKING: 'speaking'
};

let currentState = STATES.IDLE;

// Funzione per la sintesi vocale
async function playTTS(text) {
  if (isSpeaking || !text) return;
  try {
    isSpeaking = true;
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    const res = await fetch('/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (!res.ok) throw new Error('TTS error');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    currentAudio = new Audio(url);
    currentAudio.onended = () => {
      isSpeaking = false;
      currentAudio = null;
    };
    await currentAudio.play();
  } catch (e) {
    console.error('TTS failed', e);
    isSpeaking = false;
  }
}

// Aggiorna lo stato del pulsante di invio
function updateSendButtonState() {
  const hasText = textInput.value.trim().length > 0;
  sendButton.disabled = !hasText;
  sendButton.style.opacity = hasText ? "1" : "0.3";
}

// Inizializzazione
function init() {
  // Aggiungi messaggio di benvenuto
  addGenesiMessage("Ciao, sono Genesi. Come posso aiutarti oggi?");
  
  // Gestione input
  textInput.addEventListener('input', updateSendButtonState);
  
  // Eventi di invio
  sendButton.addEventListener('click', sendMessage);
  textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      sendMessage();
    }
  });
  
  // Gestione microfono
  micButton.addEventListener('click', toggleRecording);
  
  // Inizializza lo stato e il pulsante di invio
  setState(STATES.IDLE);
  updateSendButtonState();
}

// Gestione stati
function setState(newState) {
  currentState = newState;
  statusEl.textContent = getStatusText(newState);
  
  // Mostra/nascondi lo stato
  if (newState === STATES.IDLE) {
    statusEl.classList.remove('visible');
  } else {
    statusEl.classList.add('visible');
  }
  
  // Aggiorna UI in base allo stato
  updateUIForState(newState);
}

function getStatusText(state) {
  const statusTexts = {
    [STATES.IDLE]: '',
    [STATES.RECORDING]: 'Ti ascolto…',
    [STATES.THINKING]: 'Genesi sta pensando…',
    [STATES.SPEAKING]: 'Genesi sta parlando…'
  };
  return statusTexts[state] || '';
}

function updateUIForState(state) {
  // Disabilita input durante gli stati attivi
  textInput.disabled = state !== STATES.IDLE && state !== STATES.RECORDING;
  
  // Aggiorna stato del pulsante microfono
  micButton.style.background = state === STATES.RECORDING 
    ? 'rgba(200, 100, 100, 0.2)' 
    : 'rgba(100, 120, 200, 0.1)';
  
  // Aggiorna stato del pulsante invio
  if (state !== STATES.IDLE) {
    sendButton.disabled = true;
  } else {
    updateSendButtonState();
  }
}

// Gestione messaggi
function addUserMessage(text) {
  addMessage(text, 'user');
}

function addGenesiMessage(text) {
  const messageEl = addMessage(text, 'genesi');
  // Riproduci la risposta vocale
  playTTS(text);
  return messageEl;
}

function addMessage(text, sender) {
  const messageEl = document.createElement('div');
  messageEl.className = `message ${sender}`;
  messageEl.textContent = text;
  
  dialogue.appendChild(messageEl);
  scrollToBottom();
  
  return messageEl;
}

function scrollToBottom() {
  dialogue.scrollTop = dialogue.scrollHeight;
}

// Funzione di invio
function sendMessage() {
  const text = textInput.value.trim();
  if (!text) return;

  addUserMessage(text);
  textInput.value = '';

  setState(STATES.THINKING);

  // Simula elaborazione
  setTimeout(() => {
    setState(STATES.SPEAKING);
    addGenesiMessage("Ho ricevuto il tuo messaggio. Come posso aiutarti?");
  }, 1000);
}

// Gestione microfono
function toggleRecording() {
  if (currentState === STATES.IDLE) {
    startRecording();
  } else if (currentState === STATES.RECORDING) {
    stopRecording();
  }
}

function startRecording() {
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
    setTimeout(() => {
      setState(STATES.SPEAKING);
      addGenesiMessage("Ho capito il tuo messaggio vocale.");
    }, 800);
  }, 800);
}

// Avvia l'applicazione
document.addEventListener('DOMContentLoaded', init);