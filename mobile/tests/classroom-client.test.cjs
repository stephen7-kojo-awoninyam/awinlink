const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { ClassroomClient, objectAt, point, sampledPoints } = require('../src/classrooms/client.js');

const flush = async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve)); };
const track = kind => ({ kind, enabled: true, stopped: false, stop() { this.stopped = true; } });
function stream(tracks = [track('audio'), track('video')]) { return { tracks, getTracks() { return this.tracks; }, getVideoTracks() { return this.tracks.filter(t => t.kind === 'video'); }, getAudioTracks() { return this.tracks.filter(t => t.kind === 'audio'); }, addTrack(t) { this.tracks.push(t); } }; }
class Socket {
  constructor(path) { this.path = path; this.readyState = 1; this.sent = []; }
  send(text) { this.sent.push(JSON.parse(text)); }
  message(data) { this.onmessage?.({ data: JSON.stringify(data) }); }
  close() { this.readyState = 3; this.onclose?.({ code: 1000 }); }
  fail(code) { this.readyState = 3; this.onclose?.({ code }); }
}
class Peer {
  constructor() { this.signalingState = 'stable'; this.senders = []; this.candidates = []; this.closed = false; }
  sender(track) { const sender = { track, async replaceTrack(value) { this.track = value; } }; this.senders.push(sender); return sender; }
  addTrack(track) { return this.sender(track); }
  addTransceiver() { return { sender: this.sender(null) }; }
  async createOffer() { return { type: 'offer', sdp: 'offer-sdp' }; }
  async createAnswer() { return { type: 'answer', sdp: 'answer-sdp' }; }
  async setLocalDescription(value) { this.localDescription = value; this.signalingState = value.type === 'offer' ? 'have-local-offer' : 'stable'; }
  async setRemoteDescription(value) { this.remoteDescription = value; this.signalingState = value.type === 'offer' ? 'have-remote-offer' : 'stable'; }
  async addIceCandidate(value) { this.candidates.push(value); }
  close() { this.closed = true; }
}
function fixture(overrides = {}) {
  const sockets = [], peers = [], captures = [], requests = [], timers = [];
  const session = { id: 7, status: 'LIVE', title: 'Class', my_participant: { id: 10, admission_state: 'ADMITTED', role: 'HOST' }, capabilities: { end: true, participants: true, admit: true, remove: true } };
  let board = { session_id: 7, revision: 0, objects: {}, editors: [], can_edit: true, can_manage: true };
  let nextId = 0;
  const client = new ClassroomClient({ sessionId: 7, onState() {}, uuid: () => `uuid-${++nextId}`,
    schedule(fn, ms) { const timer = { fn, ms, cancelled: false }; timers.push(timer); return timer; }, cancel(timer) { if (timer) timer.cancelled = true; },
    async api(path, method = 'GET', body) {
      requests.push({ path, method, body });
      if (path.includes('ice-servers')) return { ice_servers: [{ urls: 'turn:example.invalid' }] };
      if (path.includes('participants/?')) return { results: [] };
      if (path.endsWith('whiteboard/')) { if (method === 'POST') board = { ...board, revision: board.revision + 1 }; return board; }
      if (path.endsWith('chat/')) return { id: 1, client_id: body.client_id, text: body.text, sender_name: 'Host' };
      return session;
    },
    async socket(path) { const socket = new Socket(path); sockets.push(socket); return socket; },
    async media(options) { const captured = stream([...(options.audio ? [track('audio')] : []), ...(options.video ? [track('video')] : [])]); captures.push(captured); return captured; },
    async display() { const captured = stream([track('video')]); captures.push(captured); return captured; },
    peer() { const peer = new Peer(); peers.push(peer); return peer; }, validateIce: value => value,
    ...overrides });
  async function ready(online = [], participant = 10) {
    await client.join(); const socket = sockets.at(-1);
    socket.message({ type: 'connection', session_id: 7, participant_id: participant, peers: online }); await flush();
    const activity = sockets.at(-1); activity.message({ type: 'snapshot', ...board }); await flush();
    return { socket, activity };
  }
  return { client, sockets, peers, captures, requests, timers, session, ready };
}

test('browser bundle matches the shared native controller exactly', () => {
  assert.equal(readFileSync(resolve(__dirname, '../../static/js/classroom-client.js'), 'utf8'), readFileSync(resolve(__dirname, '../src/classrooms/client.js'), 'utf8'));
});
test('join uses authenticated services, participant signaling and deterministic offers', async () => {
  const f = fixture(); const { socket } = await f.ready([{ participant_id: 20, user_id: 200, generation: 'new', role: 'LEARNER' }]);
  assert.equal(f.client.state.connected, true);
  assert.equal(f.requests.find(r => r.path.endsWith('join/')).body.connection_id, 'uuid-1');
  assert.deepEqual(socket.sent[0], { type: 'offer', recipient_id: 20, description: { type: 'offer', sdp: 'offer-sdp' } });
  assert.equal(f.peers[0].senders.length, 2);
  await f.client.dispose(); assert.equal(f.peers[0].closed, true); assert.ok(f.captures[0].getTracks().every(t => t.stopped));
});
test('waiting learners cannot capture or signal, and server join denials stop acquired media', async () => {
  const f = fixture(); f.session.my_participant.admission_state = 'WAITING'; await f.client.join();
  assert.equal(f.captures.length, 0); assert.equal(f.sockets.length, 0);
  const g = fixture({ api: async path => path.endsWith('join/') ? Promise.reject(Object.assign(new Error('Denied'), { status: 403 })) : path.includes('ice-servers') ? { ice_servers: [] } : { status: 'LIVE', my_participant: { admission_state: 'ADMITTED' }, capabilities: {} } });
  await g.client.join(); assert.ok(g.captures[0].getTracks().every(t => t.stopped)); assert.equal(g.sockets.length, 0);
});
test('leave during a permission prompt fences and stops late media acquisition', async () => {
  let resolveMedia; const f = fixture({ media: () => new Promise(resolve => { resolveMedia = resolve; }) });
  const joining = f.client.join(); await flush(); await f.client.leave();
  const late = stream(); resolveMedia(late); await joining;
  assert.ok(late.getTracks().every(t => t.stopped)); assert.equal(f.sockets.length, 0);
});
test('reconnect uses fresh UUID, drops remote media and ignores an old socket close', async () => {
  const f = fixture(); const { socket } = await f.ready([{ participant_id: 20, generation: 'one' }]);
  socket.fail(1013); assert.equal(f.peers[0].closed, true); assert.equal(f.client.state.connected, false);
  const retry = f.timers.find(t => !t.cancelled && t.ms === 1000); await retry.fn(); await flush();
  const second = f.sockets.at(-1); assert.notEqual(second.path, socket.path);
  second.message({ type: 'connection', session_id: 7, participant_id: 10, peers: [] }); await flush();
  socket.fail(4403); assert.equal(f.client.state.connected, true);
  await f.client.dispose();
});
test('removal, session ending and connection replacement close all owned media without auto-takeover', async () => {
  for (const code of [4403, 4409, 4410]) {
    const f = fixture(); const { socket } = await f.ready([{ participant_id: 20, generation: 'one' }]);
    socket.fail(code); assert.equal(f.client.wanted, false); assert.equal(f.client.state.board, null);
    assert.equal(f.client.state.chat.length, 0); assert.ok(f.captures[0].getTracks().every(t => t.stopped));
    assert.equal(f.timers.filter(t => !t.cancelled).length, 0);
  }
});
test('peer generation changes rebuild RTC and stale descriptions are refused', async () => {
  const f = fixture(); const { socket } = await f.ready([{ participant_id: 20, generation: 'one' }]);
  socket.message({ type: 'presence', session_id: 7, peers: [{ participant_id: 20, generation: 'two' }] }); await flush();
  assert.equal(f.peers[0].closed, true); assert.equal(f.peers.length, 2);
  socket.message({ type: 'answer', session_id: 7, sender_participant_id: 20, sender_generation: 'one', description: { type: 'answer', sdp: 'old' } }); await flush();
  assert.equal(f.peers[1].remoteDescription, undefined);
  socket.message({ type: 'answer', session_id: 7, sender_participant_id: 20, sender_generation: 'two', description: { type: 'answer', sdp: 'current' } }); await flush();
  assert.equal(f.peers[1].remoteDescription.sdp, 'current'); await f.client.dispose();
});
test('ICE is queued until a remote description and strips null usernameFragment', async () => {
  const f = fixture(); const { socket } = await f.ready([{ participant_id: 20, generation: 'one' }]);
  socket.message({ type: 'ice_candidate', session_id: 7, sender_participant_id: 20, sender_generation: 'one', candidate: { candidate: 'ice' } }); await flush();
  assert.equal(f.peers[0].candidates.length, 0);
  socket.message({ type: 'answer', session_id: 7, sender_participant_id: 20, sender_generation: 'one', description: { type: 'answer', sdp: 'current' } }); await flush();
  assert.equal(f.peers[0].candidates.length, 1);
  f.peers[0].onicecandidate({ candidate: { toJSON: () => ({ candidate: 'ice', sdpMid: '0', sdpMLineIndex: 0, usernameFragment: null }) } });
  assert.equal('usernameFragment' in socket.sent.at(-1).candidate, false); await f.client.dispose();
});
test('an early offer arriving before presence is buffered for its matching generation', async () => {
  const f = fixture(); const { socket } = await f.ready([], 20);
  socket.message({ type: 'offer', session_id: 7, sender_participant_id: 10, sender_generation: 'first', description: { type: 'offer', sdp: 'early' } }); await flush();
  socket.message({ type: 'presence', session_id: 7, peers: [{ participant_id: 10, generation: 'first' }] }); await flush();
  assert.equal(socket.sent.at(-1).type, 'answer'); await f.client.dispose();
});
test('viewer joins reserve audio/video receivers and can enable a device later', async () => {
  const f = fixture(); await f.client.toggle('camera'); await f.client.toggle('microphone');
  await f.ready([{ participant_id: 20, generation: 'one' }]); assert.equal(f.captures[0].tracks.length, 0);
  await f.client.toggle('camera'); assert.equal(f.peers[0].senders[1].track.kind, 'video');
  await f.client.toggle('microphone'); assert.equal(f.peers[0].senders[0].track.kind, 'audio');
  await f.client.toggle('microphone'); assert.equal(f.peers[0].senders[0].track.enabled, false); await f.client.dispose();
});
test('screen sharing replaces and restores video while preserving audio', async () => {
  const f = fixture(); await f.ready([{ participant_id: 20, generation: 'one' }]);
  const camera = f.peers[0].senders[1].track, microphone = f.peers[0].senders[0].track;
  await f.client.share(); const screen = f.peers[0].senders[1].track;
  assert.notEqual(screen, camera); assert.equal(f.client.state.sharing, true);
  await f.client.share(); assert.equal(f.peers[0].senders[1].track, camera); assert.equal(screen.stopped, true);
  assert.equal(f.peers[0].senders[0].track, microphone); await f.client.dispose();
});
test('board revisions never go backwards and grants/offline checks guard UI writes', async () => {
  const f = fixture(); await f.ready();
  f.client.acceptBoard({ ...f.client.state.board, revision: 5 }); f.client.acceptBoard({ ...f.client.state.board, revision: 2 });
  assert.equal(f.client.state.board.revision, 5);
  f.client.state.board.can_edit = false; await assert.rejects(f.client.boardCommand('add', {}), /read only/);
  f.client.state.board.can_edit = true; f.client.state.board.can_manage = false; await assert.rejects(f.client.boardCommand('clear'), /Host/);
  f.client.state.activityConnected = false; await assert.rejects(f.client.boardCommand('add', {}), /reconnecting/); await f.client.dispose();
});
test('chat delivery is deduplicated and arbitrary host actions are unavailable', async () => {
  const f = fixture(); await f.ready(); await f.client.chat('Hi');
  f.client.acceptChat([{ id: 1, text: 'Hi' }]); assert.equal(f.client.state.chat.length, 1);
  await assert.rejects(f.client.action('start'), /unavailable/); await f.client.dispose();
});
test('normalized board geometry clamps input and hit-tests objects', () => {
  assert.deepEqual(point(-1, 2), [0, 1]); assert.equal(objectAt({ a: { id: 'a', x: .1, y: .1, w: .2, h: .2 } }, .2, .2), 'a');
});
test('native stroke sampling bounds rendering while keeping endpoints and persisted geometry', () => {
  const points = Array.from({ length: 2048 }, (_, i) => [i / 2048, i / 2048]);
  const sampled = sampledPoints(points, 64);
  assert.equal(sampled.length, 64); assert.equal(sampled[0], points[0]); assert.equal(sampled.at(-1), points.at(-1));
  assert.equal(points.length, 2048);
});
test('native screen sharing configuration is idempotent for Kotlin and Java', () => {
  const { enableService } = require('../plugins/withClassroomScreenShare.cjs');
  for (const [source, language] of [['override fun onCreate() { super.onCreate()\n loadReactNative(this) }', 'kt'], ['public void onCreate() { super.onCreate(); initialize(); }', 'java']]) {
    const configured = enableService(source, language);
    assert.match(configured, /enableMediaProjectionService = true/);
    assert.equal(enableService(configured, language), configured);
    assert.ok(configured.includes(language === 'java' ? 'initialize();' : 'loadReactNative(this)'));
  }
});
test('signaling bursts are paced and queued messages are fenced when a peer reconnects', async () => {
  let clock = 0;
  const f = fixture({ clock: () => clock });
  const { socket } = await f.ready([{ participant_id: 20, generation: 'first' }]);
  for (let i = 0; i < 80; i++) f.client.send({ type: 'ice_candidate', recipient_id: 20, candidate: { candidate: String(i) } });
  assert.equal(socket.sent.length, 20); assert.ok(f.client.signalQueue.length > 0);
  await f.client.presence([{ participant_id: 20, generation: 'second' }], f.client.epoch); await flush();
  clock = 2000; f.client.flushSignals();
  assert.equal(socket.sent.filter(message => message.type === 'ice_candidate').length, 19);
  await f.client.dispose(); assert.equal(f.client.signalQueue.length, 0);
});
test('declining screen capture restores camera state without stopping the call', async () => {
  const f = fixture({ display: async () => { throw new Error('Screen picker cancelled'); } });
  await f.ready(); await assert.rejects(f.client.share(), /cancelled/);
  assert.equal(f.client.state.sharing, false); assert.equal(f.client.state.connected, true); await f.client.dispose();
});
test('host roster pagination keeps the selected page during refreshes', async () => {
  const f = fixture({ api: async path => path.includes('participants/?') ? {
    results: [{ id: path.includes('page=2') ? 200 : 20 }], next: path.includes('page=2') ? null : 'next', previous: path.includes('page=2') ? 'previous' : null,
  } : { id: 7, status: 'LIVE', capabilities: { participants: true } } });
  await f.client.load(); assert.equal(f.client.state.participants[0].id, 20);
  await f.client.changeRosterPage(1); assert.equal(f.client.state.participants[0].id, 200);
  await f.client.load(); assert.equal(f.client.state.rosterPage, 2); assert.equal(f.client.state.participants[0].id, 200);
  await f.client.changeRosterPage(-1); assert.equal(f.client.state.rosterPage, 1); await f.client.dispose();
});
test('native reconnect cannot reacquire the camera or microphone in the background', async () => {
  let foreground = true;
  const f = fixture({ canCapture: () => foreground }); const { socket } = await f.ready();
  foreground = false; socket.fail(4401);
  const retry = f.timers.find(timer => !timer.cancelled && timer.ms === 1000); await retry.fn();
  assert.equal(f.captures.length, 1); assert.equal(f.client.wanted, false);
  assert.match(f.client.state.error, /Return to Awinlink/); await f.client.dispose();
});
test('a failed socket setup compensates its successful REST attendance join', async () => {
  const f = fixture({ socket: async () => { throw new Error('Socket creation failed'); } });
  await f.client.join();
  const join = f.requests.find(request => request.path.endsWith('join/'));
  assert.ok(join);
  assert.ok(f.requests.some(request => request.path.endsWith('leave/') && request.body.connection_id === join.body.connection_id));
  assert.ok(f.captures[0].getTracks().every(t => t.stopped));
});
test('leaving during screen-track replacement cannot resurrect a released preview', async () => {
  const f = fixture(); await f.ready([{ participant_id: 20, generation: 'one' }]);
  let resume;
  f.peers[0].senders[1].replaceTrack = () => new Promise(resolve => { resume = resolve; });
  const sharing = f.client.share(); await flush(); await f.client.leave(); resume(); await sharing;
  assert.equal(f.client.state.sharing, false); assert.equal(f.client.state.localStream, null);
});
test('chat catchup follows server pagination rather than skipping a second history page', async () => {
  const f = fixture(); const { activity } = await f.ready();
  activity.message({ type: 'chat_history', messages: [{ id: 100, text: 'first batch' }], has_more: true, next_after: 100 }); await flush();
  await f.timers.find(timer => !timer.cancelled && timer.ms === 150).fn();
  assert.ok(activity.sent.some(message => message.type === 'chat_history' && message.after === 100));
  await f.client.dispose();
});
