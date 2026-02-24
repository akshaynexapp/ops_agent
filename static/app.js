/* ── State ─────────────────────────────────────────────────────────────────── */
const SESSION_STORAGE_KEY = 'ops-agent-session-id';
const USER_STORAGE_KEY = 'ops-agent-user-token';
const USER_HEADER = 'X-User-Token';
let sessionId = null;
try {
  sessionId = localStorage.getItem(SESSION_STORAGE_KEY);
} catch {
  sessionId = null;
}
let userToken = null;
try {
  userToken = localStorage.getItem(USER_STORAGE_KEY);
} catch {
  userToken = null;
}
let currentConvId = null;
let isStreaming = false;
let authMode = 'login';
let isAuthenticated = Boolean(userToken);
let authPanelVisible = false;
let currentUserEmail = null;

/* ── DOM Refs ──────────────────────────────────────────────────────────────── */
const messagesEl = document.getElementById('messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const convListEl = document.getElementById('conv-list');
const mainTitle = document.getElementById('main-title');
const themeToggle = document.getElementById('theme-toggle');
const searchInput = document.getElementById('search-input');
const mobileMenuBtn = document.getElementById('mobile-menu-btn');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const userProfileEl = document.getElementById('user-profile');
const userEmailEl = document.getElementById('user-email');
const logoutBtn = document.getElementById('logout-btn');
const authOverlay = document.getElementById('auth-overlay');
const authPanelEl = authOverlay?.querySelector('.auth-panel');
const authHeading = document.getElementById('auth-heading');
const authSubtitle = document.getElementById('auth-subtitle');
const authForm = document.getElementById('auth-form');
const authFeedback = document.getElementById('auth-feedback');
const authModeToggle = document.getElementById('auth-toggle');
const authSwitchText = document.getElementById('auth-switch-text');
const authSubmitBtn = document.getElementById('auth-submit');
const authEmailInput = document.getElementById('auth-email');
const authPasswordInput = document.getElementById('auth-password');
const authConfirmInput = document.getElementById('auth-confirm');
const authClearBtn = document.getElementById('auth-clear');


function syncSessionId(value) {
  if (!value) return;
  sessionId = value;
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, value);
  } catch {
    // localStorage might be disabled
  }
}


function syncUserToken(value) {
  if (!value) return;
  userToken = value;
  try {
    localStorage.setItem(USER_STORAGE_KEY, value);
  } catch {
    // localStorage might be disabled
  }
}


function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (sessionId) {
    headers['X-Session-Id'] = sessionId;
  }
  if (userToken) {
    headers[USER_HEADER] = userToken;
  }
  return headers;
}


function captureSessionId(response) {
  const sid = response.headers.get('X-Session-Id');
  if (sid) {
    syncSessionId(sid);
  }
}


function captureUserToken(response) {
  const token = response.headers.get(USER_HEADER);
  if (token) {
    syncUserToken(token);
  }
}


function captureAuthHeaders(response) {
  captureSessionId(response);
  captureUserToken(response);
}

function setAuthFeedback(message = '', type = 'error') {
  if (!authFeedback) return;
  authFeedback.textContent = message;
  authFeedback.classList.toggle('success', type === 'success');
}

function setAuthMode(mode) {
  authMode = mode;
  const register = mode === 'register';
  authPanelEl?.classList.toggle('register-mode', register);
  if (authHeading) authHeading.textContent = register ? 'Create an account' : 'Sign in to continue';
  if (authSubtitle) authSubtitle.textContent = register
    ? 'A registered user keeps their conversation history synced across browsers.'
    : 'Every conversation is tied to a registered user.';
  if (authSubmitBtn) authSubmitBtn.textContent = register ? 'Create account' : 'Sign in';
  if (authModeToggle) authModeToggle.textContent = register ? 'Sign in' : 'Create one';
  if (authSwitchText) authSwitchText.textContent = register ? 'Already have an account?' : 'Need a new account?';
  if (authConfirmInput) authConfirmInput.required = register;
}

function openAuthPanel(message = '', mode = 'login') {
  setAuthMode(mode);
  setAuthFeedback(message);
  authOverlay?.classList.add('visible');
  authPanelVisible = true;
  setInputDisabled(true);
  authEmailInput?.focus();
}

function closeAuthPanel() {
  if (!authPanelVisible) return;
  authOverlay?.classList.remove('visible');
  authPanelVisible = false;
  setAuthFeedback('');
  setInputDisabled(!isAuthenticated);
}

function markAuthenticated(status) {
  isAuthenticated = status;
  setInputDisabled(!status);
}

function updateUserProfile(email) {
  currentUserEmail = email || null;
  if (email && userProfileEl && userEmailEl) {
    userEmailEl.textContent = `Signed in as ${email}`;
    userProfileEl.classList.add('visible');
  } else if (userProfileEl) {
    userProfileEl.classList.remove('visible');
    if (userEmailEl) userEmailEl.textContent = '';
  }
}

async function loadUserProfile() {
  if (!isAuthenticated) {
    updateUserProfile(null);
    return;
  }
  try {
    const res = await fetchWithSession('/api/me');
    if (!res.ok) {
      updateUserProfile(null);
      return;
    }
    const data = await res.json().catch(() => ({}));
    updateUserProfile(data.email || null);
  } catch (err) {
    console.error('Failed to load user profile', err);
    updateUserProfile(null);
  }
}

async function handleLogout() {
  try {
    const res = await fetchWithSession('/api/logout', { method: 'POST' });
    if (!res.ok) {
      console.error('Logout failed', await res.text().catch(() => ''));
    }
  } catch (err) {
    console.error('Logout error', err);
  } finally {
    try {
      localStorage.removeItem(USER_STORAGE_KEY);
      localStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // ignore
    }
    userToken = null;
    sessionId = null;
    markAuthenticated(false);
    updateUserProfile(null);
    showEmptyState();
    openAuthPanel('You have been logged out. Please sign in again.', 'login');
  }
}


async function fetchWithSession(url, opts = {}) {
  const { headers = {}, ...rest } = opts;
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...rest,
    headers: authHeaders(headers),
  });
  captureAuthHeaders(response);
  if (response.status === 401) {
    markAuthenticated(false);
    openAuthPanel('Please sign in or register to continue.', 'login');
  }
  return response;
}

/* ── Theme ─────────────────────────────────────────────────────────────────── */
function initTheme() {
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  updateThemeIcon(saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  const icon = themeToggle.querySelector('.theme-icon');
  const label = themeToggle.querySelector('.theme-label');
  if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
  if (label) label.textContent = theme === 'dark' ? 'Light' : 'Dark';
}

/* ── Sidebar / Mobile ──────────────────────────────────────────────────────── */
function openSidebar() {
  sidebar.classList.add('open');
  sidebarOverlay.classList.add('visible');
}

function closeSidebar() {
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('visible');
}

/* ── Markdown renderer (lightweight) ─────────────────────────────────────── */
function renderMarkdown(text) {
  let html = text
    // Code blocks
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code>${escHtml(code.trim())}</code></pre>`)
    // Inline code
    .replace(/`([^`]+)`/g, (_, c) => `<code>${escHtml(c)}</code>`)
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/_(.+?)_/g, '<em>$1</em>')
    // Headers
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    // Bullet points
    .replace(/^[•\-\*] (.+)$/gm, '<li>$1</li>')
    // Numbered list
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    // Wrap consecutive <li> in <ul>
    .replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
    // Blockquotes
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    // Line breaks → paragraphs
    .split(/\n\n+/).map(p => {
      p = p.trim();
      if (!p) return '';
      if (/^<(h[123]|ul|ol|pre|blockquote)/.test(p)) return p;
      return `<p>${p.replace(/\n/g, '<br>')}</p>`;
    }).join('\n');
  return html;
}

function escHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ── Format timestamp ─────────────────────────────────────────────────────── */
function formatTime(isoString) {
  const d = isoString ? new Date(isoString) : new Date();
  return d.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata',
  });
}

/* ── Render a message bubble ─────────────────────────────────────────────── */
function renderMessage(role, content, timestamp, prepend = false) {
  const isUser = role === 'user';
  const row = document.createElement('div');
  row.className = `message-row ${isUser ? 'user' : 'asst'}`;

  const avatarChar = isUser ? 'U' : '🤖';
  const bubbleContent = isUser ? escHtml(content) : renderMarkdown(content);

  row.innerHTML = `
    <div class="avatar ${isUser ? 'user' : 'asst'}">${avatarChar}</div>
    <div class="bubble-wrap">
      <div class="bubble">${bubbleContent}</div>
      <span class="timestamp">${formatTime(timestamp)}</span>
    </div>
  `;

  if (prepend) {
    messagesEl.insertBefore(row, messagesEl.firstChild);
  } else {
    const emptyState = messagesEl.querySelector('.empty-state');
    if (emptyState) emptyState.remove();
    messagesEl.appendChild(row);
    scrollToBottom();
  }

  return row;
}

/* ── Thinking indicator ─────────────────────────────────────────────────── */
function showThinking() {
  removeThinking();
  const row = document.createElement('div');
  row.className = 'thinking-row';
  row.id = 'thinking-row';
  row.innerHTML = `
    <div class="avatar asst">🤖</div>
    <div class="thinking-bubble">
      <div class="thinking-dots">
        <span></span><span></span><span></span>
      </div>
      Thinking…
    </div>
  `;
  messagesEl.appendChild(row);
  scrollToBottom();
  return row;
}

function removeThinking() {
  const el = document.getElementById('thinking-row');
  if (el) el.remove();
}

/* ── Streaming bubble ─────────────────────────────────────────────────────── */
function createStreamingBubble() {
  removeThinking();
  const row = document.createElement('div');
  row.className = 'message-row asst';
  row.id = 'streaming-row';
  row.innerHTML = `
    <div class="avatar asst">🤖</div>
    <div class="bubble-wrap">
      <div class="bubble" id="streaming-bubble"></div>
      <span class="timestamp" id="streaming-time"></span>
    </div>
  `;
  messagesEl.appendChild(row);
  scrollToBottom();
  return row;
}

let streamingText = '';

function appendStreamChunk(text) {
  streamingText += text;
  const bubble = document.getElementById('streaming-bubble');
  if (bubble) {
    bubble.innerHTML = renderMarkdown(streamingText);
    scrollToBottom();
  }
}

function finalizeStreamingBubble(timestamp) {
  const row = document.getElementById('streaming-row');
  const timeEl = document.getElementById('streaming-time');
  if (row) {
    row.removeAttribute('id');
    if (timeEl) {
      timeEl.removeAttribute('id');
      timeEl.textContent = formatTime(timestamp);
    }
    const bubble = row.querySelector('.bubble');
    if (bubble) bubble.removeAttribute('id');
  }
  streamingText = '';
}

/* ── Scroll ───────────────────────────────────────────────────────────────── */
function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/* ── Load conversations list ─────────────────────────────────────────────── */
async function loadConversations(searchQuery = '') {
  try {
    const res = await fetchWithSession('/api/conversations');
    if (res.status === 401) return;
    const convs = await res.json();

    const filtered = searchQuery
      ? convs.filter(c => c.title.toLowerCase().includes(searchQuery.toLowerCase()))
      : convs;

    convListEl.innerHTML = '';
    if (filtered.length === 0) {
      convListEl.innerHTML = `<div style="padding:12px;text-align:center;color:var(--text-muted);font-size:13px;">No conversations</div>`;
      return;
    }
    filtered.forEach(c => {
      const item = document.createElement('div');
      item.className = `conv-item ${c.id === currentConvId ? 'active' : ''}`;
      item.dataset.id = c.id;
      item.innerHTML = `
        <span class="conv-item-icon">💬</span>
        <span class="conv-item-title" title="${escHtml(c.title)}">${escHtml(c.title)}</span>
        <button class="conv-item-delete" title="Delete" data-id="${c.id}">🗑</button>
      `;
      item.addEventListener('click', (e) => {
        if (e.target.classList.contains('conv-item-delete')) return;
        loadConversation(c.id, c.title);
        closeSidebar();
      });
      item.querySelector('.conv-item-delete').addEventListener('click', (e) => {
        e.stopPropagation();
        deleteConversation(c.id);
      });
      convListEl.appendChild(item);
    });
  } catch (err) {
    console.error('Failed to load conversations:', err);
  }
}

/* ── Load a conversation's messages ─────────────────────────────────────── */
async function loadConversation(id, title) {
  currentConvId = id;
  mainTitle.textContent = title || 'Chat';
  messagesEl.innerHTML = '';

  // Mark active in sidebar
  document.querySelectorAll('.conv-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.id) === id);
  });

    try {
    const res = await fetchWithSession(`/api/conversations/${id}/messages`);
    if (res.status === 401) return;
    const msgs = await res.json();

    if (msgs.length === 0) {
      showEmptyState();
    } else {
      msgs.forEach(m => renderMessage(m.role, m.content, m.created_at));
      scrollToBottom();
    }
  } catch (err) {
    messagesEl.innerHTML = `<div style="padding:20px;color:var(--danger)">Failed to load messages.</div>`;
  }
}

/* ── New chat ────────────────────────────────────────────────────────────── */
async function newChat() {
  currentConvId = null;
  mainTitle.textContent = 'New Chat';
  messagesEl.innerHTML = '';
  showEmptyState();
  document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
  chatInput.focus();
  closeSidebar();
}

/* ── Delete conversation ──────────────────────────────────────────────────── */
async function deleteConversation(id) {
  if (!confirm('Delete this conversation?')) return;
  try {
    const response = await fetchWithSession(`/api/conversations/${id}`, {
      method: 'DELETE',
    });
    if (response.status === 401) return;
    if (currentConvId === id) {
      newChat();
    }
    loadConversations();
  } catch (err) {
    console.error('Delete failed:', err);
  }
}

/* ── Empty state ─────────────────────────────────────────────────────────── */
function showEmptyState() {
  const suggestions = [
    'What is disk storage remaining?',
    'How much RAM is used?',
    'Check CPU usage',
    'Show nginx error log',
    'What files are in the workspace?',
    'How long has the server been running?',
  ];

  messagesEl.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">🖥️</div>
      <div class="empty-title">Ops Assistant</div>
      <div class="empty-sub">Ask me anything about your server in plain English. No commands needed.</div>
      <div class="suggestions">
        ${suggestions.map(s => `<button class="suggestion-chip" data-msg="${escHtml(s)}">${escHtml(s)}</button>`).join('')}
      </div>
    </div>
  `;

  messagesEl.querySelectorAll('.suggestion-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      chatInput.value = btn.dataset.msg;
      autoResize();
      sendMessage();
    });
  });
}

/* ── Send message ────────────────────────────────────────────────────────── */
async function sendMessage() {
  const msg = chatInput.value.trim();
  if (!msg || isStreaming) return;
  if (!isAuthenticated) {
    openAuthPanel('Sign in or register to continue.');
    return;
  }

  isStreaming = true;
  setInputDisabled(true);
  chatInput.value = '';
  autoResize();

  // Show user message immediately
  renderMessage('user', msg, null);

  // Show thinking
  showThinking();

  try {
    const body = { message: msg };
    if (currentConvId) body.conversation_id = currentConvId;

    const response = await fetchWithSession('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const err = await response.json();
      removeThinking();
      renderMessage('assistant', `⚠️ Error: ${err.error || 'Something went wrong.'}`, null);
      isStreaming = false;
      setInputDisabled(false);
      return;
    }

    // SSE streaming
    streamingText = '';
    let streamingBubbleCreated = false;

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;

        try {
          const data = JSON.parse(jsonStr);

          if (data.type === 'session') {
            syncSessionId(data.session_id);
            continue;
          }
          if (data.type === 'conv_id') {
            currentConvId = data.conv_id;
            mainTitle.textContent = data.title || 'Chat';
            loadConversations();
          } else if (data.type === 'token') {
            if (!streamingBubbleCreated) {
              createStreamingBubble();
              streamingBubbleCreated = true;
            }
            appendStreamChunk(data.text);
          } else if (data.type === 'done') {
            finalizeStreamingBubble(data.created_at);
          } else if (data.type === 'error') {
            removeThinking();
            if (!streamingBubbleCreated) {
              renderMessage('assistant', `⚠️ ${data.text}`, null);
            }
          }
        } catch (e) {
          // ignore parse errors
        }
      }
    }

  } catch (err) {
    removeThinking();
    renderMessage('assistant', `⚠️ Connection error: ${err.message}`, null);
  } finally {
    isStreaming = false;
    setInputDisabled(false);
    chatInput.focus();
    loadConversations();
  }
}

/* ── Input helpers ───────────────────────────────────────────────────────── */
function setInputDisabled(disabled) {
  chatInput.disabled = disabled;
  sendBtn.disabled = disabled;
}

function autoResize() {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + 'px';
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  if (!authEmailInput || !authPasswordInput) return;
  const email = authEmailInput.value.trim().toLowerCase();
  const password = authPasswordInput.value;
  const confirm = authConfirmInput?.value || '';

  if (!email || !password) {
    setAuthFeedback('Email and password are required.');
    return;
  }
  if (authMode === 'register' && password !== confirm) {
    setAuthFeedback('Passwords must match.');
    return;
  }

  const payload = { email, password };
  if (authMode === 'register') {
    payload.confirm_password = confirm;
  }

  if (authSubmitBtn) authSubmitBtn.disabled = true;
  setAuthFeedback('');

  try {
    const endpoint = authMode === 'register' ? '/api/register' : '/api/login';
    const response = await fetchWithSession(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      setAuthFeedback(result.error || 'Authentication failed.');
      return;
    }
    markAuthenticated(true);
    await loadUserProfile();
    closeAuthPanel();
    loadConversations();
  } catch (err) {
    setAuthFeedback('Unable to reach the server.');
  } finally {
    if (authSubmitBtn) authSubmitBtn.disabled = false;
  }
}

/* ── Event listeners ─────────────────────────────────────────────────────── */
chatInput.addEventListener('input', autoResize);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener('click', sendMessage);
themeToggle.addEventListener('click', toggleTheme);

document.getElementById('btn-new-chat').addEventListener('click', newChat);

searchInput.addEventListener('input', (e) => {
  loadConversations(e.target.value);
});

mobileMenuBtn.addEventListener('click', () => {
  if (sidebar.classList.contains('open')) {
    closeSidebar();
  } else {
    openSidebar();
  }
});

sidebarOverlay.addEventListener('click', closeSidebar);

authForm?.addEventListener('submit', handleAuthSubmit);
authModeToggle?.addEventListener('click', () => {
  const nextMode = authMode === 'login' ? 'register' : 'login';
  setAuthMode(nextMode);
  setAuthFeedback('');
  authEmailInput?.focus();
});
authClearBtn?.addEventListener('click', () => {
  try {
    localStorage.removeItem(USER_STORAGE_KEY);
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // ignore
  }
  userToken = null;
  sessionId = null;
  markAuthenticated(false);
  updateUserProfile(null);
  openAuthPanel('Tokens cleared. Please sign in again.', 'login');
});
logoutBtn?.addEventListener('click', handleLogout);

/* ── Init ────────────────────────────────────────────────────────────────── */
initTheme();
showEmptyState();
loadConversations();
setInputDisabled(!isAuthenticated);
if (!isAuthenticated) {
  openAuthPanel('Sign in or register to continue.', 'login');
} else {
  loadUserProfile();
}
chatInput.focus();
