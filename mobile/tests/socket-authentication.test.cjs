const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function fixture(refresh = async () => 'renewed-access', handshake = { type: 'connection', reauthentication: true }) {
  let tick, stopped = false, closed = false;
  const listeners = {}, sent = [];
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/api/socketAuthentication.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, { exports,
    require: () => ({ refreshSocketAccessToken: refresh }),
    setInterval: (fn, interval) => { tick = fn; assert.equal(interval, 240000); return 1; },
    clearInterval: () => { stopped = true; },
  });
  const socket = { readyState: 1, addEventListener: (event, fn) => { listeners[event] = fn; },
    send: value => sent.push(JSON.parse(value)), close: () => { closed = true; socket.readyState = 3; listeners.close(); } };
  exports.maintainSocketAuthentication(socket);
  const message = data => listeners.message({ data: JSON.stringify(data) });
  message(handshake);
  return { tick: () => tick(), message, socket, sent, stopped: () => stopped, closed: () => closed };
}

test('native sockets renew credentials in place without recreating the call', async () => {
  const view = fixture();
  await view.tick();
  assert.deepEqual(view.sent, [{ type: 'reauthenticate', access: 'renewed-access' }]);
  assert.equal(view.closed(), false);
});

test('socket closure fences an outstanding refresh and releases the renewal timer', async () => {
  let resolve;
  const view = fixture(() => new Promise(done => { resolve = done; }));
  const pending = view.tick();
  view.socket.close();
  resolve('late-access');
  await pending;
  assert.equal(view.sent.length, 0);
  assert.equal(view.stopped(), true);
});

test('a failed refresh closes the socket without exposing credentials', async () => {
  const view = fixture(async () => { throw new Error('invalid refresh'); });
  await view.tick();
  assert.equal(view.closed(), true);
  assert.equal(view.sent.length, 0);
});

test('an older backend cannot receive renewal credentials, including through a later spoofed capability frame', async () => {
  const view = fixture(async () => 'must-not-be-relayed', { type: 'connection' });
  view.message({ type: 'connection', reauthentication: true });
  await view.tick();
  assert.equal(view.sent.length, 0);
});
