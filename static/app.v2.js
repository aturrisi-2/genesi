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
// 🎙️ Microphone Recording System
// ===============================
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let recordingStartedAt = 0;

// 🎯 MIME types per compatibilità cross-browser
function getSupportedMimeType() {
  const types = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/wav'
  ];
  
  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return 'audio/webm'; // fallback
}

// 🎤 Inizia registrazione reale
async function startRecording() {
  if (currentState !== STATES.IDLE || isRecording) return;
  
  try {
    // Richiesta permessi microfono
    const stream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      } 
    });
    
    // Setup MediaRecorder
    const mimeType = getSupportedMimeType();
    mediaRecorder = new MediaRecorder(stream, { mimeType });
    audioChunks = [];
    
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };
    
    mediaRecorder.onstop = async () => {
  stream.getTracks().forEach(track => track.stop());

  setTimeout(async () => {
    const audioBlob = new Blob(audioChunks, { type: mimeType });

    if (audioBlob.size < 1000) {
      console.warn("Audio troppo corto, scartato");
      setState(STATES.IDLE);
      micButton.classList.remove('recording');
      return;
    }

    await transcribeAudio(audioBlob);

    setState(STATES.IDLE);
    micButton.classList.remove('recording');
  }, 150);
};

    // Inizia registrazione
    mediaRecorder.start();
    recordingStartedAt = Date.now(); // ⬅️ AGGIUNTA
    isRecording = true;
    setState(STATES.RECORDING);
    micButton.classList.add('recording');
    
  } catch (error) {
    console.error('Microphone access denied:', error);
    // Fallback a comportamento precedente se permessi negati
    fallbackRecording();
  }
}

// 🛑 Ferma registrazione
function stopRecording() {
  if (!isRecording || !mediaRecorder) return;

  // 🛡️ iOS Safari: ignora stop troppo rapido
  const elapsed = Date.now() - recordingStartedAt;
  if (elapsed < 300) {
    return;
  }

  mediaRecorder.stop();
  isRecording = false;
  micButton.classList.remove('recording');
  setState(STATES.THINKING);
}


// 🔄 Fallback per iOS/vecchi browser
function fallbackRecording() {
  setState(STATES.RECORDING);
  micButton.classList.add('recording');
  
  setTimeout(() => {
    micButton.classList.remove('recording');
    setState(STATES.THINKING);
    
    setTimeout(() => {
      textInput.value = "Microfono non supportato. Scrivi il messaggio.";
      setState(STATES.IDLE);
    }, 600);
  }, 1500);
}

// 📤 Trascrizione audio via STT
async function transcribeAudio(audioBlob) {
  try {
    // Converti blob in formato compatibile
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    
    // Invia a endpoint STT (esistente o nuovo)
    const response = await fetch('/stt', {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      throw new Error(`STT Error: ${response.status}`);
    }
    
    const result = await response.json();
    const transcribedText = result.text?.trim() || '';
    
    if (transcribedText) {
      // Inserisci testo nell'input e invia
      textInput.value = transcribedText;
      setState(STATES.IDLE);
      sendMessage();
    } else {
      setState(STATES.IDLE);
      addGenesiMessage("Non ho capito. Riprova a parlare.");
    }
    
  } catch (error) {
    console.error('STT Error:', error);
    setState(STATES.IDLE);
    addGenesiMessage("Errore trascrizione audio. Riprova.");
  }
}

// ===============================
// Event Listeners
// ===============================
sendButton.addEventListener('click', sendMessage);

// 🎙️ Microphone events (tap singolo/doppio)
micButton.addEventListener('mousedown', (e) => {
  e.preventDefault();
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
});

micButton.addEventListener('touchstart', (e) => {
  e.preventDefault();
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
});

// Previeni comportamento default globale
document.addEventListener('mouseup', (e) => {
  if (e.target !== micButton && isRecording) {
    stopRecording();
  }
});

document.addEventListener('touchend', (e) => {
  if (e.target !== micButton && isRecording) {
    stopRecording();
  }
});

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
