// reset-password.js — Gestione reimpostazione password Genesi Web
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
    const form = document.getElementById('reset-form');
    const msg = document.getElementById('msg');
    const btn = document.getElementById('submit-btn');

    if (!form) return;

    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');

    if (!token) {
        msg.textContent = 'Link non valido. Richiedi un nuovo reset.';
        msg.className = 'msg error';
        btn.disabled = true;
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        msg.className = 'msg';
        msg.style.display = '';

        const password = document.getElementById('password').value;
        const password2 = document.getElementById('password2').value;

        if (password !== password2) {
            msg.textContent = 'Le password non coincidono.';
            msg.className = 'msg error';
            return;
        }

        btn.disabled = true;
        btn.textContent = 'Reimpostazione...';

        try {
            const res = await fetch('/auth/reset-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, new_password: password }),
            });
            const data = await res.json();

            if (res.ok) {
                msg.textContent = data.message || 'Password reimpostata! Ora puoi accedere.';
                msg.className = 'msg success';
                form.reset();
                setTimeout(() => { window.location.href = '/login'; }, 2000);
            } else {
                msg.textContent = data.detail || 'Errore durante il reset.';
                msg.className = 'msg error';
            }
        } catch (err) {
            msg.textContent = 'Errore di connessione.';
            msg.className = 'msg error';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Reimposta password';
        }
    });
});
