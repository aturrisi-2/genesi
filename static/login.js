// login.js — Gestione accesso Genesi Web
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

// SafeStorage helper: ultra-resiliente con memory fallback contro blocchi cookie/localStorage
const SafeStorage = {
    memoryStore: {},
    isSupported: (() => {
        try {
            const testKey = '__storage_test__';
            localStorage.setItem(testKey, testKey);
            localStorage.removeItem(testKey);
            return true;
        } catch (e) {
            return false;
        }
    })(),
    setCookie(name, value, days) {
        try {
            let expires = "";
            if (days) {
                const date = new Date();
                date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
                expires = "; expires=" + date.toUTCString();
            }
            document.cookie = name + "=" + encodeURIComponent(value || "") + expires + "; path=/; SameSite=Lax; Secure";
        } catch (e) {
            console.warn('[SafeStorage] cookie write blocked:', e);
        }
    },
    getCookie(name) {
        try {
            const nameEQ = name + "=";
            const ca = document.cookie.split(';');
            for (let i = 0; i < ca.length; i++) {
                let c = ca[i];
                while (c.charAt(0) === ' ') c = c.substring(1, c.length);
                if (c.indexOf(nameEQ) === 0) return decodeURIComponent(c.substring(nameEQ.length, c.length));
            }
        } catch (e) {
            console.warn('[SafeStorage] cookie read blocked:', e);
        }
        return null;
    },
    eraseCookie(name) {
        try {
            document.cookie = name + '=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT; SameSite=Lax; Secure';
        } catch (e) {
            console.warn('[SafeStorage] cookie erase blocked:', e);
        }
    },
    setItem(key, value) {
        this.memoryStore[key] = value;
        if (this.isSupported) {
            try {
                localStorage.setItem(key, value);
                return;
            } catch (e) {}
        }
        this.setCookie(key, value, 7);
    },
    getItem(key) {
        if (this.isSupported) {
            try {
                const val = localStorage.getItem(key);
                if (val !== null) return val;
            } catch (e) {}
        }
        const cookieVal = this.getCookie(key);
        if (cookieVal !== null) return cookieVal;
        return this.memoryStore[key] || null;
    },
    removeItem(key) {
        delete this.memoryStore[key];
        if (this.isSupported) {
            try {
                localStorage.removeItem(key);
            } catch (e) {}
        }
        this.eraseCookie(key);
    }
};

function showPlatformPopup(platform, link) {
    const popup = document.getElementById('platform-popup');
    const btn   = document.getElementById('popup-btn');
    const msg   = document.getElementById('popup-msg');
    btn.href = link;
    if (platform === 'whatsapp') {
        btn.textContent = '↩ Torna su WhatsApp';
        btn.className   = 'popup-btn whatsapp';
        msg.textContent = 'Torna alla chat WhatsApp per continuare.';
    } else {
        btn.textContent = '↩ Torna su Telegram';
        btn.className   = 'popup-btn telegram';
        msg.textContent = 'Torna alla chat Telegram per continuare.';
    }
    popup.classList.add('show');
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('login-form');
    const msg = document.getElementById('msg');
    const btn = document.getElementById('submit-btn');
    const unverifiedBlock = document.getElementById('unverified-block');
    const resendBtn = document.getElementById('resend-btn');
    const resendMsg = document.getElementById('resend-msg');
    let resendCooldown = false;

    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        msg.className = 'msg';
        msg.style.display = '';

        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;

        btn.disabled = true;
        btn.textContent = 'Accesso...';

        try {
            const res = await fetch('/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });
            const data = await res.json();

            if (res.ok) {
                SafeStorage.setItem('genesi_access_token', data.access_token);
                SafeStorage.setItem('genesi_refresh_token', data.refresh_token);
                SafeStorage.setItem('genesi_user_id', data.user_id);
                SafeStorage.setItem('genesi_is_admin', data.is_admin);
                const params = new URLSearchParams(window.location.search);
                const from = params.get('from');

                const redirectUrl = '/?token=' + encodeURIComponent(data.access_token) + 
                                    '&refresh=' + encodeURIComponent(data.refresh_token || '') + 
                                    '&user_id=' + encodeURIComponent(data.user_id || '') + 
                                    '&is_admin=' + encodeURIComponent(data.is_admin || '');

                if (from === 'whatsapp') {
                    const waId = params.get('wa_id') || '';
                    try {
                        if (waId) {
                            await fetch('/api/whatsapp/link-session', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ wa_id: waId, token: data.access_token, email, password }),
                            });
                        }
                        const wl = await fetch('/api/whatsapp/wa-link').then(r => r.json());
                        showPlatformPopup('whatsapp', wl.wa_link || '#');
                    } catch (_) { window.location.href = redirectUrl; }
                    return;
                } else if (from === 'telegram') {
                    try {
                        const bl = await fetch('/api/telegram/bot-link').then(r => r.json());
                        showPlatformPopup('telegram', bl.bot_link || '#');
                    } catch (_) { window.location.href = redirectUrl; }
                    return;
                }
                window.location.href = redirectUrl;
            } else if (res.status === 403 && data.detail && data.detail.includes('non verificato')) {
                // Mostra blocco non verificato
                msg.style.display = 'none';
                unverifiedBlock.style.display = 'block';
            } else {
                msg.textContent = data.detail || 'Credenziali non valide.';
                msg.className = 'msg error';
                unverifiedBlock.style.display = 'none';
            }
        } catch (err) {
            console.error("Login catch block error:", err);
            msg.textContent = 'Errore di connessione o del browser: ' + (err.message || String(err));
            msg.className = 'msg error';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Accedi';
        }
    });

    // Invio mail di verifica
    if (resendBtn) {
        resendBtn.addEventListener('click', async () => {
            if (resendCooldown) return;

            const email = document.getElementById('email').value.trim();
            if (!email) {
                resendMsg.textContent = 'Inserisci la tua email.';
                resendMsg.className = 'msg error';
                return;
            }

            resendBtn.disabled = true;
            resendBtn.textContent = 'Invio email in corso...';
            resendMsg.className = 'msg loading';
            resendMsg.textContent = 'Invio email in corso...';
            resendMsg.style.display = 'block';

            try {
                const res = await fetch('/auth/resend-verification', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email }),
                });
                const data = await res.json();

                if (res.ok) {
                    resendMsg.textContent = data.message || 'Email di verifica inviata con successo.';
                    resendMsg.className = 'msg success';
                    setTimeout(() => {
                        const extra = document.createElement('p');
                        extra.style.marginTop = '8px';
                        extra.style.fontSize = '0.85em';
                        extra.style.opacity = '0.7';
                        extra.textContent = 'Controlla la posta in arrivo e anche la cartella spam.';
                        resendMsg.appendChild(extra);
                    }, 100);

                    resendCooldown = true;
                    let left = 60;
                    resendBtn.disabled = true;
                    const iv = setInterval(() => {
                        left--;
                        resendBtn.textContent = `Rimanda (${left}s)`;
                        if (left <= 0) {
                            clearInterval(iv);
                            resendBtn.textContent = 'Rimanda email di verifica';
                            resendBtn.disabled = false;
                            resendCooldown = false;
                        }
                    }, 1000);
                } else {
                    resendMsg.textContent = data.detail || 'Si è verificato un problema temporaneo.';
                    resendMsg.className = 'msg error';
                }
            } catch (err) {
                resendMsg.textContent = 'Si è verificato un problema temporaneo. Riprova più tardi.';
                resendMsg.className = 'msg error';
            } finally {
                if (!resendCooldown) {
                    resendBtn.disabled = false;
                    resendBtn.textContent = 'Rimanda email di verifica';
                }
            }
        });
    }
});
