// forgot-password.js — Gestione password dimenticata Genesi Web
// Spostato in file esterno per superare blocchi di script in linea (CSP / Ermes)

// Self-healing: pulizia Service Worker e Cache Storage in caso di contesti bloccati o stale
try {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.getRegistrations().then((registrations) => {
            for (const registration of registrations) {
                registration.unregister().catch(() => {});
            }
        }).catch(() => {});
    }
} catch (e) {
    console.warn('[Self-Healing] serviceWorker access blocked:', e);
}

try {
    if ('caches' in window) {
        caches.keys().then((keys) => {
            for (const key of keys) {
                caches.delete(key).catch(() => {});
            }
        }).catch(() => {});
    }
} catch (e) {
    console.warn('[Self-Healing] caches access blocked:', e);
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('forgot-form');
    const msg = document.getElementById('msg');
    const btn = document.getElementById('submit-btn');

    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        msg.className = 'msg';
        msg.style.display = '';

        const email = document.getElementById('email').value.trim();
        btn.disabled = true;
        btn.textContent = 'Invio...';

        try {
            const res = await fetch('/auth/forgot-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            });
            const data = await res.json();
            msg.textContent = data.message || 'Se l\'email è registrata, riceverai un link.';
            msg.className = 'msg success';
            form.reset();
        } catch (err) {
            msg.textContent = 'Errore di connessione.';
            msg.className = 'msg error';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Invia link';
        }
    });
});
