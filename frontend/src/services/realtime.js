/**
 * Auto-managed WebSocket connection to the AutoCTI backend.
 * Reconnects with exponential backoff; emits via a tiny pub/sub.
 */
const listeners = new Set();
let socket = null;
let attempts = 0;
let aliveTimer = null;
let lastMessageAt = 0;

function wsUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // In dev (Vite on port 5173), connect directly to backend on 8000.
  // In prod (nginx on port 80/443), use the same host — nginx proxies /api/rt/ws.
  const host = window.location.hostname;
  const port = window.location.port === "5173" ? "8000" : window.location.port;
  const portPart = port ? `:${port}` : "";
  return `${proto}//${host}${portPart}/api/rt/ws`;
}

function emit(msg) {
  for (const fn of listeners) {
    try { fn(msg); } catch (e) { console.error(e); }
  }
}

function connect() {
  try {
    socket = new WebSocket(wsUrl());
  } catch (e) {
    scheduleReconnect();
    return;
  }
  socket.onopen = () => {
    attempts = 0;
    lastMessageAt = Date.now();
    emit({ topic: "_status", state: "connected" });
  };
  socket.onmessage = (ev) => {
    lastMessageAt = Date.now();
    try {
      const msg = JSON.parse(ev.data);
      emit(msg);
    } catch {
      // ignore malformed frames
    }
  };
  socket.onclose = () => {
    emit({ topic: "_status", state: "disconnected" });
    scheduleReconnect();
  };
  socket.onerror = () => { try { socket.close(); } catch {} };
}

function scheduleReconnect() {
  attempts = Math.min(attempts + 1, 8);
  const delay = Math.min(1000 * 2 ** attempts, 15000);
  setTimeout(connect, delay);
}

export function subscribe(fn) {
  listeners.add(fn);
  if (!socket) connect();
  if (!aliveTimer) {
    aliveTimer = setInterval(() => {
      if (Date.now() - lastMessageAt > 90_000) {
        try { socket?.close(); } catch {}
      }
    }, 15_000);
  }
  return () => listeners.delete(fn);
}

export function isConnected() {
  return socket?.readyState === WebSocket.OPEN;
}