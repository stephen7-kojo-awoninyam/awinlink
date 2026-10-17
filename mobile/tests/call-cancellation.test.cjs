const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }
function compile(source) { return ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText; }

function nativeScreen({ incoming = false, media = null, accepting = null, ending = null, iceFailure = false } = {}) {
  const effects = [], timers = new Map(), sockets = [], peers = [], requests = [], alerts = [];
  const tracks = [{ stopped: false, stop() { this.stopped = true; }, enabled: true }];
  const stream = { getTracks: () => tracks, getAudioTracks: () => tracks, getVideoTracks: () => [] };
  const states = [];
  let controls, ended, back = 0, captures = 0;
  const react = { useRef: value => ({ current: value }), useState: value => { const slot = states.length; states.push(value); return [value, next => { states[slot] = typeof next === "function" ? next(states[slot]) : next; }]; }, useCallback: fn => fn, useEffect: fn => effects.push(fn) };
  class Socket { static OPEN = 1; readyState = 1; closed = false; constructor() { sockets.push(this); } close() { this.closed = true; } send(payload) { (this.sent ||= []).push(JSON.parse(payload)); } }
  class Peer {
    signalingState = 'stable'; candidates = []; tracks = [];
    constructor(config) { this.config = config; peers.push(this); }
    addTrack(track) { this.tracks.push(track); } close() { this.closed = true; }
    async createOffer() { return { type: 'offer', sdp: 'local-offer' }; }
    async createAnswer() { return { type: 'answer', sdp: 'local-answer' }; }
    async setLocalDescription(value) { this.localDescription = value; }
    async setRemoteDescription(value) { this.remoteDescription = value; }
    async addIceCandidate(value) { this.candidates.push(value); }
  }
  class Stream { tracks = []; getTracks() { return this.tracks; } addTrack(track) { this.tracks.push(track); } }
  const lifecycle = { callHasEnded: () => false, finishCallRequest: (_id, work) => work(), onCallEnded: fn => { ended = fn; return () => {}; } };
  const exports = {};
  vm.runInNewContext(compile(fs.readFileSync(require.resolve('../app/call/[id].tsx'), 'utf8')), {
    exports, WebSocket: Socket, console: { info() {} },
    setTimeout: fn => { const id = timers.size + 1; timers.set(id, fn); return id; },
    setInterval: fn => { const id = timers.size + 1; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id), clearInterval: id => timers.delete(id),
    require: name => ({
      react, 'react/jsx-runtime': { jsx: () => ({}), jsxs: () => ({}) },
      'react-native': { Alert: { alert: (...args) => alerts.push(args) }, StyleSheet: { create: value => value } }, 'react-native-safe-area-context': {},
      'expo-router': { Stack: { Screen() {} }, router: { back: () => { back++; } }, useLocalSearchParams: () => ({ id: '42', mode: incoming ? 'incoming' : 'outgoing', autoAccept: incoming ? 'true' : 'false' }) },
      'react-native-webrtc': { MediaStream: Stream, RTCPeerConnection: Peer, mediaDevices: { getUserMedia: () => { captures++; return media?.promise || Promise.resolve(stream); } } },
      '@/src/auth/AuthProvider': { useAuth: () => ({ user: { id: incoming ? 2 : 1 } }) },
      '@/src/api/client': { getAccessToken: async () => 'token', getWebSocketUrl: value => value,
        apiRequest: async (url, options) => { requests.push(url); if (iceFailure && url.endsWith('/ice-servers/')) throw new Error('Call connectivity is temporarily unavailable.'); if (url.endsWith('/accept/')) return accepting?.promise || { id: 42, participants: [] }; if (url.endsWith('/end/')) return ending?.promise || {}; if (url.endsWith('/incoming/')) return [{ id: 42 }]; return { ice_servers: [], ice_transport_policy: 'relay' }; } },
      '@/src/calls/iceServers': { validatedIceServers: () => [] }, '@/src/theme': { colors: {} },
      '@/src/calls/nativeCallUI': { bindNativeCall: (_id, _in, _name, _video, value) => { controls = value; return () => {}; }, endNativeCall() {}, nativeCallConnected() {}, syncNativeMute() {} },
      '@/src/calls/callLifecycle': lifecycle,
    })[name],
  });
  exports.default();
  const cleanups = effects.map(fn => fn());
  return { alerts, states, stream, tracks, sockets, peers, requests, timers, controls: () => controls, remoteEnd: () => ended(42), back: () => back, captures: () => captures, unmount: () => cleanups.forEach(fn => fn?.()) };
}

test('mobile caller closes media/socket/peers and timers before delayed end API returns', async () => {
  const ending = deferred();
  const screen = nativeScreen({ ending });
  await flush();
  const socket = screen.sockets[0];
  socket.onopen();
  socket.onmessage({ data: JSON.stringify({ type: 'participant_joined', user_id: 2 }) });
  await flush();
  assert.equal(screen.peers.length, 1);
  screen.controls().end();
  assert.equal(screen.tracks[0].stopped, true);
  assert.equal(socket.closed, true);
  assert.equal(screen.peers[0].closed, true);
  assert.equal(screen.timers.size, 0);
  assert.equal(screen.back(), 1);
  ending.resolve({}); await flush(); screen.unmount();
  assert.equal(screen.requests.filter(url => url.endsWith('/end/')).length, 1);
});

test('mobile cancellation while microphone permission is pending stops late stream', async () => {
  const media = deferred();
  const screen = nativeScreen({ media });
  await flush();
  screen.controls().end();
  media.resolve(screen.stream); await flush();
  assert.equal(screen.tracks[0].stopped, true);
  assert.equal(screen.sockets.length, 0);
  assert.equal(screen.timers.size, 0);
});

test('mobile recipient cannot start media from an accept response after caller cancels', async () => {
  const accepting = deferred();
  const screen = nativeScreen({ incoming: true, accepting });
  screen.remoteEnd();
  accepting.resolve({ id: 42, participants: [] }); await flush();
  assert.equal(screen.captures(), 0);
  assert.equal(screen.sockets.length, 0);
  assert.equal(screen.timers.size, 0);
  assert.equal(screen.back(), 1);
});

test('mobile redial waits for cancellation commit and duplicate end requests share one API call', async () => {
  const exports = {};
  vm.runInNewContext(compile(fs.readFileSync(require.resolve('../src/calls/callLifecycle.ts'), 'utf8')), { exports });
  const ending = deferred(); let requests = 0, ready = false;
  const first = exports.finishCallRequest(42, () => { requests++; return ending.promise; });
  assert.equal(exports.finishCallRequest(42, () => { requests++; return Promise.resolve(); }), first);
  const redial = exports.waitForCallEndRequests().then(() => { ready = true; });
  await flush(); assert.equal(ready, false); assert.equal(requests, 1);
  ending.resolve({}); await redial; assert.equal(ready, true);
  let ended = null; const remove = exports.onCallEnded(id => { ended = id; });
  exports.notifyCallEnded(42); assert.equal(ended, 42); assert.equal(exports.callHasEnded(42), true); remove();
});

function webCall({ media = null, endResponse = null, startResponse = null } = {}) {
  const timers = new Map(), sockets = [], streams = [], requests = [], mediaElements = [];
  const response = data => ({ ok: true, json: async () => data });
  const context = vm.createContext({
    console: { log() {}, warn() {}, error() {} },
    window: { awinlinkCurrentUserId: 1, location: { host: 'app.test' } }, location: { protocol: 'https:' },
    document: { cookie: '', getElementById: () => null, querySelectorAll: () => mediaElements },
    navigator: { mediaDevices: { getUserMedia: () => {
      const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
      const stream = { getTracks: () => tracks, tracks }; streams.push(stream); return media?.promise || Promise.resolve(stream);
    } } },
    WebSocket: class { static OPEN = 1; readyState = 1; constructor() { sockets.push(this); Promise.resolve().then(() => this.onopen?.()); } close() { this.closed = true; this.onclose?.(); } },
    fetch: async url => { requests.push(url); if (url.endsWith('/start/')) return startResponse?.promise || response({ id: 41 + requests.filter(value => value.endsWith('/start/')).length, participants: [], status: 'RINGING' }); if (url.endsWith('/end/')) return endResponse?.promise || response({}); return response({ id: 42, participants: [] }); },
    setTimeout: fn => { const id = timers.size + 1; timers.set(id, fn); return id; },
    setInterval: fn => { const id = timers.size + 1; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id), clearInterval: id => timers.delete(id),
    alert() {}, stopCallTimer() {}, setCallStatus() {},
  });
  const source = fs.readFileSync(require.resolve('../../static/js/main.js'), 'utf8');
  vm.runInContext(source.slice(source.indexOf('let localStream = null;'), source.indexOf('let awinlinkUserSocket = null;')), context);
  vm.runInContext('showCallInterface = () => {};', context);
  return { context, streams, sockets, timers, requests, mediaElements, response, run: code => vm.runInContext(code, context) };
}

test('web caller stops audio immediately, serializes redial, and ignores old socket/end responses', async () => {
  const endResponse = deferred(); const call = webCall({ endResponse });
  await call.run("startCall('VOICE', 7)");
  const oldMessage = call.sockets[0].onmessage;
  const audio = { paused: false, srcObject: call.streams[0], pause() { this.paused = true; } }; call.mediaElements.push(audio);
  const ended = call.run('endWebRTCCall()');
  assert.equal(call.streams[0].tracks[0].stopped, true);
  assert.equal(audio.paused, true); assert.equal(audio.srcObject, null);
  assert.equal(call.sockets[0].closed, true); assert.equal(call.timers.size, 0);
  const redial = call.run("startCall('VOICE', 7)"); await flush();
  assert.equal(call.requests.filter(url => url.endsWith('/start/')).length, 1);
  endResponse.resolve(call.response({})); await ended; await redial;
  assert.equal(call.run('currentCallId'), 43);
  oldMessage({ data: JSON.stringify({ type: 'call_ended', call_id: 42 }) });
  assert.equal(call.run('currentCallId'), 43);
  assert.equal(call.streams[1].tracks[0].stopped, false);
});

test('web recipient cancellation dismisses ringing and stops media arriving after permission prompt', async () => {
  const media = deferred(); const call = webCall({ media });
  call.run('incomingCallId = 42; incomingCallTimeout = setInterval(() => {}, 1000);');
  const answer = call.run("answerIncomingCall({ call_id: 42, call_type: 'VOICE' })");
  call.run("handleCallEnded({ call_id: 42 })");
  media.resolve(call.streams[0]); await answer;
  assert.equal(call.streams[0].tracks[0].stopped, true);
  assert.equal(call.run('incomingCallId'), null);
  assert.equal(call.run('currentCallId'), null);
  assert.equal(call.sockets.length, 0); assert.equal(call.timers.size, 0);
  call.run("showIncomingCall({ call_id: 42 })"); // Stale incoming event must be ignored.
  assert.equal(call.run('incomingCallId'), null);
});

test('web late start response is cancelled before a queued redial can create a call', async () => {
  const startResponse = deferred(); const call = webCall({ startResponse });
  const started = call.run("startCall('VOICE', 7)"); await flush();
  await call.run('endWebRTCCall()');
  startResponse.resolve(call.response({ id: 42, participants: [], status: 'RINGING' }));
  await started;
  assert.ok(call.requests.some(url => url.endsWith('/42/end/')));
  assert.equal(call.streams[0].tracks[0].stopped, true);
  assert.equal(call.run('currentCallId'), null);
  assert.equal(call.run('isCallStarting'), false);
});

test('web recipient can clear ringing on cancellation and receive the next call immediately', () => {
  const call = webCall();
  call.run('incomingCallId = 42; incomingCallTimeout = setInterval(() => {}, 1000);');
  call.run('handleCallEnded({ call_id: 42 });');
  assert.equal(call.run('incomingCallId'), null);
  assert.equal(call.timers.size, 0);
  // A stale cancellation for the previous call cannot dismiss the new incoming call.
  call.run('incomingCallId = 43; incomingCallTimeout = setInterval(() => {}, 1000); handleCallEnded({ call_id: 42 });');
  assert.equal(call.run('incomingCallId'), 43);
  assert.equal(call.timers.size, 1);
});

test('web no-answer timeout releases media before a slow server response', async () => {
  const endResponse = deferred(); const call = webCall({ endResponse });
  await call.run("startCall('VOICE', 7)");
  [...call.timers.values()][0]();
  assert.equal(call.streams[0].tracks[0].stopped, true);
  assert.equal(call.run('currentCallId'), null);
  assert.equal(call.timers.size, 0);
  endResponse.resolve(call.response({})); await flush();
});

test('mobile drains ICE queued before answer and attaches streamless remote audio', async () => {
  const screen = nativeScreen(); await flush(); const socket = screen.sockets[0]; socket.onopen();
  socket.onmessage({ data: JSON.stringify({ type: 'participant_joined', user_id: 2 }) }); await flush();
  const peer = screen.peers[0];
  socket.onmessage({ data: JSON.stringify({ type: 'ice-candidate', sender_id: 2, target_id: 1, candidate: { candidate: 'early-ice' } }) });
  socket.onmessage({ data: JSON.stringify({ type: 'answer', sender_id: 2, answer: { type: 'answer', sdp: 'remote-answer' } }) });
  await flush(); assert.equal(peer.remoteDescription.sdp, 'remote-answer'); assert.equal(peer.candidates.length, 1);
  const track = { id: 'audio-1', kind: 'audio' }; peer.ontrack({ streams: [], track });
  assert.equal(screen.states[6][2].getTracks()[0], track);
  assert.equal(peer.tracks.length, 1);
  assert.equal(peer.config.iceTransportPolicy, 'relay');
  screen.unmount();
});

test('mobile serializes offer then ICE and sends canonical answer', async () => {
  const screen = nativeScreen({ incoming: true }); await flush(); const socket = screen.sockets[0]; socket.onopen();
  socket.onmessage({ data: JSON.stringify({ type: 'offer', sender_id: 1, to_user_id: 2, description: { type: 'offer', sdp: 'web-offer' } }) });
  socket.onmessage({ data: JSON.stringify({ type: 'ice_candidate', sender_id: 1, to_user_id: 2, candidate: { candidate: 'ice' } }) });
  await flush(); const peer = screen.peers[0];
  assert.equal(peer.remoteDescription.sdp, 'web-offer'); assert.equal(peer.candidates.length, 1);
  assert.equal(socket.sent.find(value => value.type === 'answer').description.type, 'answer');
  screen.unmount();
});

test('native ICE configuration failure shows an alert and ends without capturing media', async () => {
  const screen = nativeScreen({ iceFailure: true }); await flush();
  assert.equal(screen.captures(), 0); assert.equal(screen.sockets.length, 0);
  assert.equal(screen.alerts.length, 1); assert.equal(screen.back(), 1);
  assert.ok(screen.requests.some(url => url.endsWith('/end/')));
});
