const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));
function browser(userId = 1) {
  const peers = [], sent = [], elements = new Map(), diagnostics = [];
  class Stream { tracks = []; getTracks() { return this.tracks; } addTrack(track) { this.tracks.push(track); } }
  class Peer {
    candidates = []; tracks = []; connectionState = 'new';
    constructor(config) { this.config = config; peers.push(this); }
    addTrack(track) { this.tracks.push(track); }
    async createOffer() { return { type: 'offer', sdp: 'web-offer' }; }
    async createAnswer() { return { type: 'answer', sdp: 'web-answer' }; }
    async setLocalDescription(value) { this.localDescription = value; }
    async setRemoteDescription(value) { this.remoteDescription = value; }
    async addIceCandidate(candidate) { assert.ok(this.remoteDescription); this.candidates.push(candidate); }
    close() {}
  }
  function element(tagName) {
    return { tagName, children: [], muted: true, playCalls: 0,
      appendChild(child) { this.children.push(child); child.parentElement = this; elements.set(child.id, child); },
      querySelector(tag) { return this.children.find(child => child.tagName === tag); },
      play() { this.playCalls++; return this.blocked ? Promise.reject(new Error('NotAllowedError')) : Promise.resolve(); },
      remove() { elements.delete(this.id); },
    };
  }
  elements.set('remoteVideos', element('div'));
  elements.set('awinlinkCallContainer', element('section'));
  const context = vm.createContext({
    console: { log() {}, warn() {}, error() {}, info: (...args) => diagnostics.push(args) },
    window: { awinlinkCurrentUserId: userId, location: { host: 'app.test' } }, location: { protocol: 'https:' },
    document: { cookie: '', getElementById: id => elements.get(id), createElement: element, querySelectorAll: () => [] },
    RTCPeerConnection: Peer, MediaStream: Stream, WebSocket: { OPEN: 1 },
    fetch: async () => ({ ok: true, json: async () => ({ ice_transport_policy: 'relay', ice_servers: [ { urls: 'stun:stun.test' }, { urls: ['turn:relay.test:3478', 'turns:relay.test:5349'], username: 'temporary', credential: 'secret' } ] }) }),
    setTimeout, clearTimeout, setInterval, clearInterval, setCallStatus() {}, startCallTimer() {}, stopCallTimer() {},
  });
  const source = fs.readFileSync(require.resolve('../../static/js/main.js'), 'utf8');
  vm.runInContext(source.slice(source.indexOf('let localStream = null;'), source.indexOf('let awinlinkUserSocket = null;')), context);
  context.sent = sent;
  vm.runInContext("currentCallId = 42; currentCallType = 'VIDEO'; localStream = new MediaStream(); localStream.addTrack({ id: 'mic', kind: 'audio' }); callSocket = { readyState: 1, send: value => sent.push(JSON.parse(value)) };", context);
  return { peers, sent, elements, diagnostics, run: code => vm.runInContext(code, context), signal: data => { context.signal = data; return vm.runInContext('handleCallSignal(signal)', context); } };
}

test('web uses authenticated TURN configuration and canonical signaling for mobile', async () => {
  const call = browser(); await call.run('loadCallIceServers()');
  await call.signal({ type: 'participant_joined', user_id: 2 });
  const peer = call.peers[0];
  assert.equal(peer.config.iceServers[1].credential, 'secret');
  assert.equal(peer.config.iceTransportPolicy, 'relay');
  assert.equal(peer.tracks.length, 1);
  const offer = call.sent.find(message => message.type === 'offer');
  assert.equal(offer.to_user_id, 2); assert.equal(offer.description.type, 'offer');
  peer.onicecandidate({ candidate: { candidate: 'candidate' } });
  assert.equal(call.sent.at(-1).type, 'ice_candidate');
  assert.equal(call.sent.at(-1).to_user_id, 2);
  const safe = JSON.stringify(call.run('window.getAwinlinkCallDiagnostics()'));
  assert.equal(safe.includes('secret'), false); assert.equal(safe.includes('web-offer'), false);
});

test('web queues early ICE, accepts mobile SDP, and handles streamless tracks', async () => {
  const call = browser(2);
  await call.signal({ type: 'ice_candidate', sender_id: 1, to_user_id: 2, candidate: { candidate: 'early' } });
  await call.signal({ type: 'offer', sender_id: 1, to_user_id: 2, description: { type: 'offer', sdp: 'mobile-offer' } });
  const peer = call.peers[0]; assert.equal(peer.candidates.length, 1);
  assert.equal(call.sent.find(message => message.type === 'answer').description.type, 'answer');
  peer.ontrack({ streams: [], track: { id: 'remote-audio', kind: 'audio' } }); await flush();
  const video = call.elements.get('remote-video-1');
  assert.equal(video.srcObject.getTracks()[0].kind, 'audio'); assert.equal(video.muted, false); assert.equal(video.playCalls, 1);
});

test('web elects one offerer for either join order and ignores signals for other users', async () => {
  const call = browser(2);
  await call.signal({ type: 'participant_joined', user_id: 1 });
  await call.signal({ type: 'ready', sender_id: 1, to_user_id: 2 });
  assert.equal(call.peers.length, 0); assert.equal(call.sent[0].type, 'ready');
  await call.signal({ type: 'offer', sender_id: 1, to_user_id: 3, description: { type: 'offer', sdp: 'other' } });
  assert.equal(call.peers.length, 0);
});

test('browser playback rejection exposes a working audio enable control', async () => {
  const call = browser();
  call.run("currentCallType = 'VOICE'; addRemoteVideo(2, new MediaStream());"); await flush();
  const audio = call.elements.get('remote-audio-2'); audio.blocked = true;
  call.run('playCallMedia(document.getElementById("remote-audio-2"))'); await flush();
  const button = call.elements.get('remote-audio-2-play'); assert.equal(button.textContent, 'Enable call audio');
  assert.equal(button.parentElement, call.elements.get('awinlinkCallContainer'));
  audio.blocked = false; button.onclick(); await flush();
  assert.equal(call.elements.has('remote-audio-2-play'), false); assert.equal(audio.muted, false);
});

test('mobile ICE validation preserves TURN credentials and rejects unusable URLs', () => {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/calls/iceServers.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports });
  const relay = { urls: ['turn:relay.test', 'turns:relay.test'], username: 'temporary', credential: 'secret' };
  assert.equal(exports.validatedIceServers([relay])[0], relay);
  for (const invalid of [null, [], [{ urls: [] }], [{ urls: 'https://bad.test' }]]) assert.match(exports.validatedIceServers(invalid)[0].urls, /^stun:/);
});

test('web offerer drains ICE after mobile answer and reports media counters without addresses', async () => {
  const call = browser(); await call.signal({ type: 'ready', sender_id: 2, to_user_id: 1 });
  await call.signal({ type: 'ice_candidate', sender_id: 2, candidate: { candidate: 'early-remote' } });
  await call.signal({ type: 'answer', sender_id: 2, description: { type: 'answer', sdp: 'mobile-answer' } });
  const peer = call.peers[0]; assert.equal(peer.candidates.length, 1);
  peer.getStats = async () => new Map([
    ['rtp', { type: 'inbound-rtp', kind: 'audio', bytesReceived: 4096 }],
    ['transport', { type: 'transport', selectedCandidatePairId: 'pair' }],
    ['pair', { type: 'candidate-pair', localCandidateId: 'local', remoteCandidateId: 'remote' }],
    ['local', { candidateType: 'relay', address: 'private-address' }],
    ['remote', { candidateType: 'srflx', address: 'private-address' }],
  ]);
  await call.run('window.sampleAwinlinkCallStats()');
  const rows = call.run('window.getAwinlinkCallDiagnostics()');
  assert.equal(rows.find(row => row.event === 'inbound_media').bytesReceived, 4096);
  assert.equal(rows.find(row => row.event === 'selected_ice_pair').localType, 'relay');
  assert.equal(JSON.stringify(rows).includes('private-address'), false);
});

test('web refuses failed ICE configuration without exposing response credentials', async () => {
  const call = browser();
  call.run("fetch = async () => ({ ok: false, json: async () => ({ credential: 'private-value' }) });");
  await assert.rejects(call.run('loadCallIceServers()'), /Unable to load call network configuration/);
  assert.equal(call.peers.length, 0);
  assert.equal(JSON.stringify(call.run('window.getAwinlinkCallDiagnostics()')).includes('private-value'), false);
});
