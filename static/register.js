// register.js — Gestione registrazione Genesi Web
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

function showPlatformPopup(platform, link) {
    const popup = document.getElementById('platform-popup');
    const btn   = document.getElementById('popup-btn');
    const msg   = document.getElementById('popup-msg');
    btn.href = link;
    if (platform === 'whatsapp') {
        btn.textContent = '↩ Torna su WhatsApp';
        btn.className   = 'popup-btn whatsapp';
        msg.textContent = 'Account creato! Torna su WhatsApp per iniziare.';
    } else {
        btn.textContent = '↩ Torna su Telegram';
        btn.className   = 'popup-btn telegram';
        msg.textContent = 'Account creato! Torna su Telegram per iniziare.';
    }
    popup.classList.add('show');
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('register-form');
    const msg = document.getElementById('msg');
    const btn = document.getElementById('submit-btn');

    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        msg.className = 'msg';
        msg.style.display = '';

        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        const password2 = document.getElementById('password2').value;

        if (password !== password2) {
            msg.textContent = 'Le password non coincidono.';
            msg.className = 'msg error';
            return;
        }

        btn.disabled = true;
        btn.textContent = 'Registrazione...';

        try {
            const res = await fetch('/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });
            const data = await res.json();

            if (res.ok) {
                const params = new URLSearchParams(window.location.search);
                const from = params.get('from');
                if (from === 'telegram') {
                    try {
                        const bl = await fetch('/api/telegram/bot-link').then(r => r.json());
                        showPlatformPopup('telegram', bl.bot_link || '#');
                    } catch (_) {}
                } else if (from === 'whatsapp') {
                    const waId = params.get('wa_id') || '';
                    try {
                        const loginRes = await fetch('/auth/login', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ email, password }),
                        });
                        if (loginRes.ok) {
                            const loginData = await loginRes.json();
                            if (waId && loginData.access_token) {
                                await fetch('/api/whatsapp/link-session', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ wa_id: waId, token: loginData.access_token, email, password }),
                                });
                            }
                        }
                        const wl = await fetch('/api/whatsapp/wa-link').then(r => r.json());
                        showPlatformPopup('whatsapp', wl.wa_link || '#');
                    } catch (_) {}
                } else {
                    msg.innerHTML = `<strong>Registrazione completata!</strong><br>${data.message || 'Puoi ora accedere.'}`;
                    msg.className = 'msg success';
                    msg.style.display = '';
                    form.reset();
                    setTimeout(() => { window.location.href = '/login'; }, 3000);
                }
            } else {
                let errorMsg = 'Errore durante la registrazione.';
                if (typeof data.detail === 'string') {
                    errorMsg = data.detail;
                } else if (Array.isArray(data.detail)) {
                    errorMsg = data.detail.map(err => err.msg).join('<br>');
                }
                msg.innerHTML = errorMsg;
                msg.className = 'msg error';
                msg.style.display = '';
            }
        } catch (err) {
            msg.textContent = 'Errore di connessione.';
            msg.className = 'msg error';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Registrati';
        }
    });
});
