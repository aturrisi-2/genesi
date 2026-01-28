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
const plusButton = document.getElementById('plus-button');
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

  try {
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
  } catch (e) {
    console.error("Connection error during bootstrap", e);
  }
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
// 📱 iOS Message Sending
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
let currentStream = null;

// Funzione PURA per ottenere il tipo MIME supportato
function getSupportedMimeType() {
  const types = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
    'audio/wav'
  ];
  
  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return ''; // Browser default
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
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      } 
    });
    
    currentStream = stream;
    const mimeType = getSupportedMimeType();
    const options = mimeType ? { mimeType } : {};
    
    mediaRecorder = new MediaRecorder(stream, options);
    audioChunks = [];
    
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
        console.log(`Audio chunk: ${event.data.size} bytes`);
      }
    };
    
    mediaRecorder.onstop = async () => {
      // Delay critico per Windows/Chrome flush
      setTimeout(async () => {
        if (currentStream) {
          currentStream.getTracks().forEach(track => track.stop());
        }
        
        const blobType = mimeType || 'audio/webm';
        const audioBlob = new Blob(audioChunks, { type: blobType });
        
        console.log(`Final blob: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
        
        resetMicrophoneState();
        
        // Verifica blob vuoto (alzo soglia sicurezza a 500 byte)
        if (audioBlob.size < 500) {
          console.warn(`Audio too small: ${audioBlob.size} bytes`);
          setState(STATES.IDLE);
          // Opzionale: puoi mostrare un messaggio se vuoi, ma spesso è meglio ignorare i click accidentali
          return;
        }
        
        await transcribeAudio(audioBlob);
      }, 200);
    };
    
    mediaRecorder.start(1000);
    isRecording = true;
    setState(STATES.RECORDING);
    micButton.classList.add('recording');
    
  } catch (error) {
    console.error('Microphone access denied:', error);
    fallbackRecording();
  }
}

function stopRecording() {
  if (!isRecording || !mediaRecorder) return;
  // Non forziamo THINKING qui, aspettiamo che onstop finisca
  mediaRecorder.stop();
}

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

async function transcribeAudio(audioBlob) {
  try {
    const formData = new FormData();
    const fileExtension = audioBlob.type.includes('wav') ? '.wav' : '.webm';
    formData.append('audio', audioBlob, `recording${fileExtension}`);
    
    // Stato intermedio mentre invia
    setState(STATES.THINKING);

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
// Event Listeners (FIX UNIFICATO)
// ===============================

// 1. Send Button
sendButton.addEventListener('click', sendMessage);

// 2. File Upload Function
async function handleFileUpload() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '*/*';
  
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', getUserId());
    
    try {
      const response = await fetch('/upload', {
        method: 'POST',
        body: formData
      });
      
      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`);
      }
      
      const result = await response.json();
      console.log('File uploaded:', result);
      
    } catch (error) {
      console.error('Upload error:', error);
    }
  };
  
  input.click();
}

// 3. Microphone Logic Unificata
const handleMicToggle = (e) => {
  // Previene comportamenti default (zoom, selezione, ecc)
  if (e.type === 'touchstart') {
     e.preventDefault(); 
  }
  
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
};

// Rilevamento capacità Touch
const isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);

if (isTouchDevice) {
  // Mobile / Tablet: Usa touchstart per reattività istantanea
  micButton.addEventListener('touchstart', handleMicToggle, { passive: false });
} else {
  // Desktop: Usa click per stabilità (evita conflitti mousedown su Windows)
  micButton.addEventListener('click', handleMicToggle);
}

// 4. Plus Button Upload
plusButton.addEventListener('click', handleFileUpload);

// 5. Prevenzione chiusura accidentale registrazione (solo mobile)
if (isTouchDevice) {
    document.addEventListener('touchend', (e) => {
        if (e.target !== micButton && isRecording) {
            stopRecording();
        }
    });
}

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