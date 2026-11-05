const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(setImmediate);
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }
function fixture(request) {
  let state = null, tick, timerCleared = false, calls = 0;
  const ended = new Set(), sockets = [], effects = [], routes = [];
  const ref = { current: new Set() };
  const react = { useRef: () => ref, useState: () => [state, value => { state = typeof value === 'function' ? value(state) : value; }], useEffect: fn => effects.push(fn) };
  class Socket { constructor() { sockets.push(this); } close() { this.closed = true; } }
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(require.resolve('../src/calls/IncomingCallListener.web.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(code, { exports, WebSocket: Socket,
    setInterval: fn => { tick = fn; return 1; }, clearInterval: () => { timerCleared = true; },
    require: name => ({ react,
      'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
      'react-native': { Pressable: 'button', Text: 'text' },
      'expo-router': { router: { push: route => routes.push(route) } },
      '@/src/auth/AuthProvider': { useAuth: () => ({ user: { id: 1 } }) },
      '@/src/api/client': { getWebSocketUrl: path => path, apiRequest: () => request(++calls) },
      '@/src/api/socketAuthentication': { socketAccessToken: async () => 'token', maintainSocketAuthentication() {} },
      './callLifecycle': { callHasEnded: id => ended.has(id), notifyCallEnded: id => ended.add(id) },
    })[name],
  });
  exports.IncomingCallListener();
  const cleanup = effects.shift()();
  const message = data => sockets[0].onmessage({ data: JSON.stringify(data) });
  function nodes(node) { return !node || typeof node !== 'object' ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)]; }
  return { state: () => state, message, tick: () => tick(), calls: () => calls, cleanup, routes,
    closed: () => sockets[0].closed, timerCleared: () => timerCleared,
    answer: () => nodes(exports.IncomingCallListener()).find(n => n.type === 'button' && n.props.children?.props?.children === 'Answer').props.onPress(),
  };
}
const call = { id: 42, call_type: 'VIDEO', conversation: 1, initiated_by: { username: 'host' } };

test('browser cancellation immediately dismisses alert and fences a stale incoming poll', async () => {
  const pending = deferred();
  const view = fixture(() => pending.promise);
  await flush();
  view.message({ type: 'call_ended', call_id: 42 });
  pending.resolve([call]); await flush(); await flush();
  assert.equal(view.state(), null);
  view.cleanup(); assert.equal(view.closed(), true); assert.equal(view.timerCleared(), true);
});

test('incoming notification during a poll triggers an immediate follow-up request', async () => {
  const pending = deferred();
  const view = fixture(index => index === 1 ? pending.promise : Promise.resolve([call]));
  await flush(); view.message({ type: 'incoming_call', call_id: 42 });
  pending.resolve([]); await flush(); await flush();
  assert.equal(view.calls(), 2); assert.equal(view.state().id, 42);
  view.answer(); assert.equal(view.routes[0].params.id, '42'); assert.equal(view.state(), null);
  await view.tick(); await flush(); assert.equal(view.state(), null);
  view.cleanup();
});
