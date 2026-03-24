/**
 * Genesi Widget — finestra chat embeddabile
 * Uso: <script src="/widget.js"
 *        data-api-url="https://genesi.eu"
 *        data-api-key="LA_TUA_CHIAVE"
 *        data-name="Assistente"
 *        data-color="#7c3aed"
 *        data-welcome="Ciao! Come posso aiutarti?"
 *        data-position="bottom-right"
 *        data-page-context="true">
 *      </script>
 */
(function () {
  'use strict';

  // ── Configurazione da attributi del tag <script> ──────────────────────────
  const _s = document.currentScript
          || document.querySelector('script[data-api-key]')
          || document.querySelector('script[src*="widget.js"]');
  if (!_s) { console.warn('[GenesiWidget] impossibile trovare il tag <script>'); return; }
  const cfg = {
    apiUrl:      (_s.getAttribute('data-api-url')   || '').replace(/\/$/, ''),
    apiKey:      _s.getAttribute('data-api-key')    || '',
    name:        _s.getAttribute('data-name')       || 'Assistente',
    color:       _s.getAttribute('data-color')      || '#7c3aed',
    welcome:     _s.getAttribute('data-welcome')    || 'Ciao! Come posso aiutarti oggi?',
    position:    _s.getAttribute('data-position')   || 'bottom-right',
    pageCtx:     _s.getAttribute('data-page-context') !== 'false',
    avatarUrl:   _s.getAttribute('data-avatar')     || null,
    placeholder: _s.getAttribute('data-placeholder')|| 'Scrivi un messaggio...',
    userName:    _s.getAttribute('data-user-name')  || '',
    userRole:    _s.getAttribute('data-user-role')  || '',
  };

  if (!cfg.apiKey) { console.warn('[GenesiWidget] data-api-key mancante'); return; }
  console.log('[GenesiWidget] init', cfg.name, cfg.apiUrl || '(same-origin)');

  // ── Colori derivati ───────────────────────────────────────────────────────
  function hexToRgb(hex) {
    const r = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return r ? `${parseInt(r[1],16)},${parseInt(r[2],16)},${parseInt(r[3],16)}` : '124,58,237';
  }
  const rgb   = hexToRgb(cfg.color);
  const side  = cfg.position.includes('right') ? 'right' : 'left';
  const color = cfg.color;

  // ── CSS (valori inline, nessuna CSS variable per massima compatibilità) ───
  const css = `
    #gw-btn {
      position: fixed !important;
      ${side}: 24px !important;
      bottom: 24px !important;
      width: 56px !important; height: 56px !important;
      border-radius: 50% !important;
      background: ${color} !important;
      box-shadow: 0 4px 20px rgba(${rgb},.55) !important;
      border: none !important; cursor: pointer !important;
      display: flex !important; align-items: center !important; justify-content: center !important;
      transition: transform .2s, box-shadow .2s;
      z-index: 2147483640 !important;
      padding: 0 !important; margin: 0 !important;
    }
    #gw-btn:hover { transform: scale(1.08) !important; }
    #gw-btn svg { width:26px; height:26px; fill:#fff; flex-shrink:0; }
    #gw-badge {
      position:absolute; top:-3px; ${side === 'right' ? 'right' : 'left'}:-3px;
      width:14px; height:14px;
      background:#ef4444; border-radius:50%;
      border:2px solid #fff; display:none;
    }
    #gw-panel {
      position: fixed !important;
      ${side}: 16px !important;
      bottom: 92px !important;
      width: 360px; max-width: calc(100vw - 32px);
      height: 520px; max-height: calc(100vh - 120px);
      background: #0f0f17 !important;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 16px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.28);
      display: flex !important; flex-direction: column;
      z-index: 2147483639 !important;
      overflow: hidden;
      transform: translateY(16px) scale(.97);
      opacity: 0;
      pointer-events: none;
      transition: transform .22s cubic-bezier(.4,0,.2,1), opacity .22s;
      margin: 0 !important; padding: 0 !important;
    }
    #gw-panel.gw-open {
      transform: translateY(0) scale(1) !important;
      opacity: 1 !important;
      pointer-events: all !important;
    }
    #gw-header {
      display: flex; align-items: center; gap: 10px;
      padding: 14px 16px;
      background: linear-gradient(135deg, rgba(${rgb},.18) 0%, rgba(${rgb},.06) 100%);
      border-bottom: 1px solid rgba(255,255,255,0.07);
      flex-shrink: 0;
    }
    #gw-avatar {
      width:36px; height:36px; border-radius:50%;
      background: ${color};
      display:flex; align-items:center; justify-content:center;
      font-size:18px; flex-shrink:0; overflow:hidden;
    }
    #gw-avatar img { width:100%; height:100%; object-fit:cover; }
    #gw-title { font-family:system-ui,sans-serif; color:#fff; font-size:15px; font-weight:600; }
    #gw-subtitle { font-family:system-ui,sans-serif; color:rgba(255,255,255,.45); font-size:11px; }
    #gw-close {
      margin-left:auto !important; background:none !important; border:none !important; cursor:pointer;
      color:rgba(255,255,255,.4); font-size:20px; line-height:1; padding:4px;
    }
    #gw-close:hover { color:#fff; }
    #gw-messages {
      flex:1; overflow-y:auto; padding:14px 12px;
      display:flex; flex-direction:column; gap:10px;
    }
    #gw-messages::-webkit-scrollbar { width:4px; }
    #gw-messages::-webkit-scrollbar-thumb { background:rgba(255,255,255,.12); border-radius:4px; }
    .gw-msg {
      max-width:82%; font-family:system-ui,sans-serif; font-size:13.5px;
      line-height:1.5; padding:9px 12px; border-radius:12px; word-break:break-word;
    }
    .gw-msg.gw-user {
      align-self:flex-end;
      background: ${color};
      color:#fff; border-bottom-right-radius:4px;
    }
    .gw-msg.gw-bot {
      align-self:flex-start;
      background:rgba(255,255,255,.07);
      color:rgba(255,255,255,.88); border-bottom-left-radius:4px;
    }
    .gw-msg.gw-bot a { color:${color}; }
    .gw-msg.gw-bot strong { color:#fff; }
    .gw-msg.gw-bot code { background:rgba(255,255,255,.1); padding:1px 5px; border-radius:4px; font-size:12px; }
    .gw-typing {
      align-self:flex-start; padding:10px 14px;
      background:rgba(255,255,255,.07); border-radius:12px; border-bottom-left-radius:4px;
      display:flex; gap:5px; align-items:center;
    }
    .gw-dot {
      width:6px; height:6px; border-radius:50%;
      background:rgba(255,255,255,.4);
      animation: gwBounce 1.2s infinite;
    }
    .gw-dot:nth-child(2) { animation-delay:.2s; }
    .gw-dot:nth-child(3) { animation-delay:.4s; }
    @keyframes gwBounce {
      0%,60%,100% { transform:translateY(0); }
      30%          { transform:translateY(-5px); }
    }
    #gw-ctx-bar {
      display:flex; align-items:center; gap:6px; padding:5px 12px;
      background:rgba(${rgb},.08); border-top:1px solid rgba(255,255,255,.05); flex-shrink:0;
    }
    #gw-ctx-bar span {
      font-family:system-ui,sans-serif; font-size:11px; color:rgba(255,255,255,.4); flex:1;
      overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
    }
    #gw-ctx-toggle {
      background:none; border:1px solid rgba(${rgb},.4); cursor:pointer;
      font-size:10px; color:${color}; padding:2px 6px; border-radius:4px;
      font-family:system-ui,sans-serif;
    }
    #gw-footer {
      display:flex; gap:8px; align-items:flex-end; padding:10px;
      border-top:1px solid rgba(255,255,255,.07); flex-shrink:0;
    }
    #gw-input {
      flex:1; background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.1);
      border-radius:10px; padding:9px 12px; color:#fff;
      font-family:system-ui,sans-serif; font-size:13.5px; outline:none; resize:none;
      max-height:100px; min-height:38px; line-height:1.4;
    }
    #gw-input::placeholder { color:rgba(255,255,255,.25); }
    #gw-send {
      width:36px; height:36px; border-radius:50%; flex-shrink:0;
      background:${color}; border:none; cursor:pointer;
      display:flex; align-items:center; justify-content:center;
    }
    #gw-send svg { width:16px; height:16px; fill:#fff; }
    #gw-send:disabled { opacity:.4; cursor:default; }
    #gw-powered {
      text-align:center; padding:4px 0 8px;
      font-family:system-ui,sans-serif; font-size:10px; color:rgba(255,255,255,.2); flex-shrink:0;
    }
    #gw-powered a { color:rgba(255,255,255,.3); text-decoration:none; }
  `;

  // ── Iniezione CSS ─────────────────────────────────────────────────────────
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ── Costruzione HTML ──────────────────────────────────────────────────────
  const avatarInner = cfg.avatarUrl
    ? `<img src="${cfg.avatarUrl}" alt="">`
    : '🤖';

  const html = `
    <button id="gw-btn" aria-label="Apri assistente">
      <div id="gw-badge"></div>
      <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
    </button>

    <div id="gw-panel" role="dialog" aria-label="${cfg.name}">
      <div id="gw-header">
        <div id="gw-avatar">${avatarInner}</div>
        <div>
          <div id="gw-title">${cfg.name}</div>
          <div id="gw-subtitle">Assistente AI</div>
        </div>
        <button id="gw-close" aria-label="Chiudi">✕</button>
      </div>

      <div id="gw-messages"></div>

      <div id="gw-ctx-bar">
        <span id="gw-ctx-label">📄 Contesto pagina attivo</span>
        <button id="gw-ctx-toggle">disattiva</button>
      </div>

      <div id="gw-footer">
        <textarea id="gw-input" rows="1" placeholder="${cfg.placeholder}"></textarea>
        <button id="gw-send" aria-label="Invia">
          <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
      </div>
      <div id="gw-powered">powered by <a href="${cfg.apiUrl}" target="_blank">Genesi AI</a></div>
    </div>
  `;

  const container = document.createElement('div');
  container.innerHTML = html;
  document.body.appendChild(container);

  // ── Riferimenti DOM ───────────────────────────────────────────────────────
  const btn       = document.getElementById('gw-btn');
  const panel     = document.getElementById('gw-panel');
  const badge     = document.getElementById('gw-badge');
  const closeBtn  = document.getElementById('gw-close');
  const messages  = document.getElementById('gw-messages');
  const input     = document.getElementById('gw-input');
  const sendBtn   = document.getElementById('gw-send');
  const ctxBar    = document.getElementById('gw-ctx-bar');
  const ctxLabel  = document.getElementById('gw-ctx-label');
  const ctxToggle = document.getElementById('gw-ctx-toggle');

  // ── Stato ─────────────────────────────────────────────────────────────────
  let isOpen       = false;
  let isBusy       = false;
  let sendPageCtx  = cfg.pageCtx;
  let unread       = 0;

  // conversation_id persistente per utente (localStorage, chiave = apiKey + userName)
  const _convKey = 'gw_conv_' + cfg.apiKey + (cfg.userName ? '_' + cfg.userName.replace(/\s+/g,'_') : '');
  let conversationId = localStorage.getItem(_convKey) || null;

  // ── Apertura / chiusura ───────────────────────────────────────────────────
  function open() {
    isOpen = true;
    panel.classList.add('gw-open');
    btn.style.transform = 'scale(.9)';
    input.focus();
    clearUnread();
    if (messages.children.length === 0) {
      const firstName = cfg.userName ? cfg.userName.split(' ')[0] : '';
      const welcomeMsg = firstName
        ? cfg.welcome.replace(/^(Ciao|Salve|Hello)!?/i, `Ciao ${firstName}!`)
        : cfg.welcome;
      addBotMessage(welcomeMsg);
    }
  }
  function close() {
    isOpen = false;
    panel.classList.remove('gw-open');
    btn.style.transform = '';
  }
  function clearUnread() {
    unread = 0;
    badge.style.display = 'none';
  }
  function addUnread() {
    if (isOpen) return;
    unread++;
    badge.style.display = 'block';
  }

  btn.addEventListener('click', () => isOpen ? close() : open());
  closeBtn.addEventListener('click', close);

  // ── Contesto pagina ───────────────────────────────────────────────────────
  if (!cfg.pageCtx) ctxBar.style.display = 'none';

  ctxToggle.addEventListener('click', () => {
    sendPageCtx = !sendPageCtx;
    ctxToggle.textContent  = sendPageCtx ? 'disattiva' : 'attiva';
    ctxLabel.textContent   = sendPageCtx ? '📄 Contesto pagina attivo' : '📄 Contesto pagina disattivato';
    ctxLabel.style.opacity = sendPageCtx ? '1' : '.5';
  });

  function getPageContext() {
    if (!sendPageCtx) return {};
    const bodyText = (document.body.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 2000);

    // Estrae tutti i link visibili della pagina (testo → URL)
    const links = Array.from(document.querySelectorAll('a[href]'))
      .filter(a => {
        const href = a.getAttribute('href') || '';
        const txt  = (a.textContent || '').trim();
        return txt.length > 1 && !href.startsWith('javascript:') && !href.startsWith('#');
      })
      .map(a => `- ${(a.textContent || '').trim().replace(/\s+/g,' ')}: ${a.href}`)
      .slice(0, 40)
      .join('\n');

    return {
      page_url:     window.location.href,
      page_title:   document.title,
      page_context: bodyText + (links ? `\n\nLINK DISPONIBILI NELLA PAGINA:\n${links}` : ''),
    };
  }

  // ── Rendering messaggi ────────────────────────────────────────────────────
  function escHtml(t) {
    return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  function renderMd(text) {
    let h = escHtml(text);
    h = h.replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    h = h.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
    h = h.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    h = h.replace(/\n/g, '<br>');
    return h;
  }

  function addBotMessage(text) {
    const el = document.createElement('div');
    el.className = 'gw-msg gw-bot';
    el.innerHTML = renderMd(text);
    messages.appendChild(el);
    scrollBottom();
    addUnread();
    return el;
  }

  function addUserMessage(text) {
    const el = document.createElement('div');
    el.className = 'gw-msg gw-user';
    el.textContent = text;
    messages.appendChild(el);
    scrollBottom();
    return el;
  }

  function showTyping() {
    const el = document.createElement('div');
    el.className = 'gw-typing';
    el.id = 'gw-typing';
    el.innerHTML = '<div class="gw-dot"></div><div class="gw-dot"></div><div class="gw-dot"></div>';
    messages.appendChild(el);
    scrollBottom();
  }
  function hideTyping() {
    const el = document.getElementById('gw-typing');
    if (el) el.remove();
  }

  function scrollBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  // ── Auto-resize textarea ──────────────────────────────────────────────────
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
  });

  // ── Invio messaggio ───────────────────────────────────────────────────────
  async function sendMessage() {
    const text = input.value.trim();
    if (!text || isBusy) return;

    isBusy = true;
    sendBtn.disabled = true;
    input.value = '';
    input.style.height = 'auto';

    addUserMessage(text);
    showTyping();

    try {
      const body = {
        message: text,
        ...getPageContext(),
      };
      if (conversationId) body.conversation_id = conversationId;
      if (cfg.userName) body.user_name = cfg.userName;
      if (cfg.userRole) body.user_role = cfg.userRole;

      const res = await fetch(`${cfg.apiUrl}/api/widget/chat`, {
        method:  'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Widget-Key': cfg.apiKey,
        },
        body: JSON.stringify(body),
      });

      hideTyping();

      if (!res.ok) {
        addBotMessage('Si è verificato un errore. Riprova tra poco.');
        return;
      }

      const data = await res.json();
      if (data.conversation_id) {
        conversationId = data.conversation_id;
        localStorage.setItem(_convKey, conversationId);
      }
      addBotMessage(data.response || '...');

    } catch (err) {
      hideTyping();
      addBotMessage('Connessione non riuscita. Verifica la rete e riprova.');
      console.error('[GenesiWidget]', err);
    } finally {
      isBusy = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

})();
