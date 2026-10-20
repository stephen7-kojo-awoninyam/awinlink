const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));

function setup(conversationId = 4) {
  const sockets = [], timers = new Map(), states = [];
  let cleanup, updates = 0, foreground;
  const exports = {};
  class Socket {
    static OPEN = 1;
    readyState = 1;
    sent = [];
    constructor(url, protocols, options) { this.options = options; sockets.push(this); }
    send(value) { this.sent.push(JSON.parse(value)); }
    close() { this.closed = true; this.onclose?.(); }
    event(data) { this.onmessage({ data: JSON.stringify(data) }); }
  }
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/messaging/useMessaging.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, {
    exports, WebSocket: Socket, Date, Math,
    setTimeout: (fn, delay) => { const key = {}; timers.set(key, { fn, delay }); return key; },
    clearTimeout: key => timers.delete(key), setInterval: () => 1, clearInterval() {},
    require: name => ({
      react: { useCallback: fn => fn, useRef: current => ({ current }), useState: () => ['', value => states.push(value)] },
      'expo-router': { useFocusEffect: fn => { cleanup = fn(); } },
      'react-native': { Platform: { OS: 'ios' }, AppState: { currentState: 'active', addEventListener: (_, fn) => { foreground = fn; return { remove() {} }; } } },
      '@/src/auth/AuthProvider': { useAuth: () => ({ user: { id: 1 } }) },
      '@/src/api/client': { getAccessToken: async () => 'fresh-token', getWebSocketUrl: path => path },
      '@/src/api/socketAuthentication': { socketAccessToken: async () => 'fresh-token', maintainSocketAuthentication() {} },
    })[name],
  });
  const hook = exports.useMessaging(async () => { updates++; }, conversationId);
  return { sockets, timers, states, hook, cleanup: () => cleanup(), updates: () => updates, foreground: state => foreground(state) };
}

test('messaging reconnect catches up and cleanup cancels retries', async () => {
  const view = setup(); await flush();
  assert.equal(view.sockets[0].options.headers.Authorization, 'Bearer fresh-token');
  view.sockets[0].onopen();
  view.sockets[0].close();
  assert.equal(view.timers.size, 1);
  const [key, retry] = [...view.timers][0]; view.timers.delete(key); retry.fn(); await flush();
  assert.equal(view.sockets.length, 2);
  view.sockets[1].onopen();
  assert.ok(view.updates() >= 3);
  view.cleanup();
  assert.equal(view.sockets[1].closed, true);
  assert.equal(view.timers.size, 0);
});

test('typing expires, sends server-scoped payload, and read events do not loop', async () => {
  const view = setup(); await flush();
  const socket = view.sockets[0];
  const before = view.updates();
  socket.event({ type: 'messages_read', conversation_id: 4 });
  socket.event({ type: 'message_created', conversation_id: 5 });
  assert.equal(view.updates(), before);
  socket.event({ type: 'message_created', conversation_id: 4 });
  assert.equal(view.updates(), before + 1);
  socket.event({ type: 'typing', conversation_id: 4, user_id: 2, username: 'Friend', is_typing: true });
  assert.match(view.states.at(-1), /Friend is typing/);
  [...view.timers.values()][0].fn();
  assert.equal(view.states.at(-1), '');
  view.hook.sendTyping('hello'); view.hook.sendTyping('hello again'); view.hook.sendTyping('');
  assert.equal(socket.sent.length, 2);
  assert.equal(socket.sent[0].conversation_id, 4);
  assert.equal(socket.sent[1].is_typing, false);
  view.cleanup();
});

test('inbox updates on message and cross-device read events', async () => {
  const view = setup(null); await flush();
  const before = view.updates();
  view.sockets[0].event({ type: 'messages_read', conversation_id: 4 });
  view.sockets[0].event({ type: 'message_created', conversation_id: 7 });
  assert.equal(view.updates(), before + 2);
  view.cleanup();
});
