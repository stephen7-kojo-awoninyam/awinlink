/* Shared browser/native classroom controller. Generated browser copy: build-classroom-client.cjs. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.AwinClassroom = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function uuid() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
    else for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  const terminal = new Set([4400, 4403, 4404, 4409, 4410, 1003, 1009]);
  function stop(stream) { stream?.getTracks().forEach(track => track.stop()); stream?.release?.(); }
  function point(x, y) { return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))]; }
  function objectAt(objects, x, y) {
    return Object.values(objects).reverse().find(o => {
      const points = o.points || [[o.x, o.y], [o.x + (o.w || .2), o.y + (o.h || o.size || .06)]];
      const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
      return x >= Math.min(...xs) - .02 && x <= Math.max(...xs) + .02 && y >= Math.min(...ys) - .02 && y <= Math.max(...ys) + .02;
    })?.id;
  }
  function sampledPoints(points, maximum = 128) {
    if (points.length <= maximum) return points;
    return Array.from({ length: maximum }, (_, i) => points[Math.round(i * (points.length - 1) / (maximum - 1))]);
  }
  class ClassroomClient {
    constructor(options) {
      this.options = options; this.id = options.sessionId;
      if (!Number.isSafeInteger(this.id) || this.id <= 0) throw new Error('Invalid classroom session.');
      this.api = options.api; this.newId = options.uuid || uuid;
      this.schedule = options.schedule || ((fn, delay) => setTimeout(fn, delay));
      this.cancel = options.cancel || (timer => clearTimeout(timer));
      this.state = { status: 'Not joined', error: '', session: null, participants: [], peers: [],
        localStream: null, remoteStreams: {}, board: null, chat: [], connected: false,
        activityConnected: false, camera: true, microphone: true, sharing: false, busy: false,
        rosterPage: 1, rosterHasNext: false, rosterHasPrevious: false };
      this.rosterPage = 1;
      this.peers = new Map(); this.earlySignals = []; this.epoch = 0; this.wanted = false; this.retryCount = 0;
      this.activityEpoch = 0; this.activityRetryCount = 0; this.disposed = false;
      this.signalQueue = []; this.signalTokens = 20; this.signalClock = options.clock || (() => Date.now()); this.signalRefill = this.signalClock();
    }
    emit(values = {}) { Object.assign(this.state, values); if (!this.disposed) this.options.onState({ ...this.state }); }
    error(error) { this.emit({ error: error?.message || 'Classroom operation failed.' }); }
    path(suffix = '') { return `learning/sessions/${this.id}/${suffix}`; }
    async load() {
      const session = await this.api(this.path());
      if (this.disposed) return;
      this.emit({ session });
      if (session.capabilities?.participants) {
        const page = this.rosterPage;
        let roster;
        try { roster = await this.api(this.path(`participants/?page_size=100&page=${page}`)); }
        catch (error) {
          if (error.status !== 404 || page === 1) throw error;
          this.rosterPage = 1; return this.load();
        }
        if (!this.disposed && page === this.rosterPage) this.emit({ participants: roster.results || [], rosterPage: page,
          rosterHasNext: !!roster.next, rosterHasPrevious: !!roster.previous });
      } else this.emit({ participants: [], rosterHasNext: false, rosterHasPrevious: false });
      return session;
    }
    async changeRosterPage(delta) {
      if (![1, -1].includes(delta) || !this.state.session?.capabilities?.participants) return;
      if (delta === 1 ? !this.state.rosterHasNext : !this.state.rosterHasPrevious) return;
      this.rosterPage += delta; await this.load();
    }
    async action(action, participantId) {
      if (this.state.busy) return;
      const cap = this.state.session?.capabilities;
      if (action !== 'request-admission' && !cap?.[action]) throw new Error('This action is unavailable.');
      this.emit({ busy: true, error: '' });
      try {
        const path = participantId ? `participants/${participantId}/${action}/` : `${action}/`;
        await this.api(this.path(path), 'POST', {});
        await this.load();
        if (action === 'end' || action === 'cancel') await this.leave();
      } finally { this.emit({ busy: false }); }
    }
    async join(media = { camera: this.state.camera, microphone: this.state.microphone }) {
      if (this.disposed || this.state.busy || this.wanted) return;
      this.wanted = true; this.retryCount = 0;
      this.emit({ camera: media.camera, microphone: media.microphone, error: '' });
      await this.connect();
    }
    async connect() {
      const epoch = ++this.epoch;
      let connectionId = null;
      this.emit({ status: this.retryCount ? 'Reconnecting…' : 'Joining…', busy: true, connected: false });
      try {
        const session = await this.load(); // Existing API refreshes an expired native JWT before opening sockets.
        if (epoch !== this.epoch || !this.wanted) return;
        if (session.status !== 'LIVE' || session.my_participant?.admission_state !== 'ADMITTED') {
          throw new Error('The session must be live and you must be admitted before joining.');
        }
        const ice = await this.api('messaging/calls/ice-servers/');
        if (epoch !== this.epoch || !this.wanted) return;
        this.iceServers = this.options.validateIce(ice.ice_servers);
        if (![undefined, "all", "relay"].includes(ice.ice_transport_policy)) throw new Error("Invalid ICE transport policy.");
        this.icePolicy = ice.ice_transport_policy || "all";
        if (this.options.canCapture && !this.options.canCapture()) {
          const error = new Error('Return to Awinlink and join the classroom again.'); error.name = 'SecurityError'; throw error;
        }
        const stream = await this.options.media({ video: this.state.camera, audio: this.state.microphone });
        if (epoch !== this.epoch || !this.wanted) { stop(stream); return; }
        this.local = stream; this.emit({ localStream: stream });
        connectionId = this.newId(); this.connectionId = connectionId;
        await this.api(this.path('join/'), 'POST', { connection_id: connectionId });
        if (epoch !== this.epoch || !this.wanted) {
          await this.api(this.path('leave/'), 'POST', { connection_id: connectionId }).catch(() => {});
          return;
        }
        const socket = await this.options.socket(`ws/learning/sessions/${this.id}/?connection_id=${connectionId}`);
        if (epoch !== this.epoch || !this.wanted) { socket.close(); return; }
        this.socket = socket;
        socket.onmessage = event => {
          if (this.current(epoch, socket)) {
            try { this.receive(JSON.parse(String(event.data)), epoch).catch(error => this.current(epoch, socket) && this.error(error)); }
            catch (error) { this.error(error); }
          }
        };
        socket.onclose = event => { if (this.current(epoch, socket)) this.closed(event.code); };
        socket.onerror = () => { if (this.current(epoch, socket)) this.emit({ error: 'Signaling connection failed.' }); };
        this.readyTimer = this.schedule(() => { if (this.current(epoch, socket) && !this.state.connected) this.closed(1013); }, 15000);
      } catch (error) {
        if (epoch !== this.epoch) { await this.abandon(connectionId); return; }
        this.error(error);
        // A server denial or media denial never leaves capture running or loops permission prompts.
        if (this.retryCount && ![401, 403, 404].includes(error.status) && !['NotAllowedError', 'NotFoundError', 'SecurityError'].includes(error.name)) {
          this.closed(1013);
        } else { this.wanted = false; this.cleanup(); this.emit({ status: 'Unable to join', busy: false }); }
        await this.abandon(connectionId);
      }
    }
    async abandon(connectionId) {
      if (!connectionId) return;
      if (this.connectionId === connectionId) this.connectionId = null;
      // UUID-scoped leave cannot close a later reconnect with a new UUID.
      try { await this.api(this.path('leave/'), 'POST', { connection_id: connectionId }); }
      catch { /* Offline cleanup is recovered by reconnect/session ending. */ }
    }
    current(epoch, socket) { return !this.disposed && this.wanted && epoch === this.epoch && socket === this.socket; }
    send(payload) {
      if (this.socket?.readyState !== 1 || !this.state.connected) throw new Error('Classroom is reconnecting.');
      if (this.signalQueue.length >= 512) throw new Error('Signaling is busy. Reconnect the classroom.');
      this.signalQueue.push({ payload, epoch: this.epoch, generation: this.peers.get(payload.recipient_id)?.generation });
      this.flushSignals();
    }
    flushSignals() {
      this.cancel(this.signalTimer);
      const now = this.signalClock();
      this.signalTokens = Math.min(20, this.signalTokens + Math.max(0, now - this.signalRefill) * .015); this.signalRefill = now;
      while (this.signalQueue.length && this.signalTokens >= 1 && this.socket?.readyState === 1) {
        const entry = this.signalQueue.shift();
        if (entry.epoch !== this.epoch || entry.generation !== this.peers.get(entry.payload.recipient_id)?.generation) continue;
        this.signalTokens -= 1; this.socket.send(JSON.stringify(entry.payload));
      }
      if (this.signalQueue.length && this.wanted) this.signalTimer = this.schedule(() => this.flushSignals(), 75);
    }
    async receive(message, epoch) {
      if (message.session_id && message.session_id !== this.id) return;
      if (message.type === 'connection') {
        this.cancel(this.readyTimer); this.participantId = message.participant_id;
        this.stableTimer = this.schedule(() => { if (epoch === this.epoch && this.state.connected) this.retryCount = 0; }, 10000);
        this.emit({ status: 'Connected', connected: true, busy: false, error: '' });
        await this.presence(message.peers, epoch);
        if (epoch === this.epoch && this.wanted) void this.connectActivity(epoch);
      } else if (message.type === 'presence') await this.presence(message.peers, epoch);
      else if (['offer', 'answer', 'ice_candidate'].includes(message.type)) {
        const record = this.peers.get(message.sender_participant_id);
        if (!record) { if (this.earlySignals.length < 64) this.earlySignals.push(message); return; }
        if (record.generation !== message.sender_generation) return;
        record.serial = record.serial.then(() => this.signal(record, message)).catch(error => this.valid(record) && this.error(error));
        await record.serial;
      } else if (['removed', 'replaced', 'session_ended'].includes(message.type)) {
        this.closed(message.type === 'session_ended' ? 4410 : message.type === 'replaced' ? 4409 : 4403);
      } else if (message.type === 'error') this.emit({ error: message.detail || 'Signaling was refused.' });
    }
    valid(record) { return this.wanted && record.epoch === this.epoch && this.peers.get(record.id) === record; }
    async presence(peers, epoch) {
      if (!Array.isArray(peers) || epoch !== this.epoch) return;
      const ids = new Set(peers.map(p => p.participant_id));
      for (const [id, record] of this.peers) {
        if (!ids.has(id) || peers.find(p => p.participant_id === id)?.generation !== record.generation) this.dropPeer(id);
      }
      this.emit({ peers });
      for (const info of peers) {
        if (epoch !== this.epoch) return;
        if (!this.peers.has(info.participant_id)) {
          const record = this.makePeer(info, epoch);
          // A single deterministic offerer avoids initial negotiation glare on browser and native engines.
          if (this.participantId < record.id) {
            record.serial = record.serial.then(() => this.offer(record)).catch(error => this.valid(record) && this.error(error));
          }
        }
      }
      const queued = this.earlySignals.splice(0);
      for (const message of queued) {
        const record = this.peers.get(message.sender_participant_id);
        if (record?.generation === message.sender_generation) await this.receive(message, epoch);
      }
    }
    makePeer(info, epoch) {
      const pc = this.options.peer(this.iceServers, this.icePolicy);
      const record = { id: info.participant_id, generation: info.generation, pc, epoch, serial: Promise.resolve(), candidates: [], senders: {} };
      this.peers.set(record.id, record);
      for (const kind of ['audio', 'video']) {
        const track = kind === 'video' ? this.display?.getVideoTracks()[0] || this.local?.getVideoTracks()[0] : this.local?.getAudioTracks()[0];
        record.senders[kind] = track ? pc.addTrack(track, this.local) : pc.addTransceiver(kind, { direction: 'sendrecv', streams: [this.local] }).sender;
      }
      pc.onicecandidate = event => {
        if (!this.valid(record) || !this.state.connected) return;
        let candidate = event.candidate?.toJSON ? event.candidate.toJSON() : event.candidate;
        if (candidate) {
          candidate = { candidate: candidate.candidate, sdpMid: candidate.sdpMid, sdpMLineIndex: candidate.sdpMLineIndex,
            ...(typeof candidate.usernameFragment === 'string' && candidate.usernameFragment ? { usernameFragment: candidate.usernameFragment } : {}) };
        }
        try { this.send({ type: 'ice_candidate', recipient_id: record.id, candidate: candidate || null }); }
        catch (error) { if (this.valid(record)) { this.error(error); this.closed(1013); } }
      };
      pc.ontrack = event => {
        if (!this.valid(record)) return;
        const stream = event.streams?.[0];
        if (stream) this.emit({ remoteStreams: { ...this.state.remoteStreams, [record.id]: stream } });
      };
      pc.onconnectionstatechange = () => {
        if (!this.valid(record)) return;
        if (pc.connectionState === 'failed') this.closed(1013);
        else if (pc.connectionState === 'disconnected') {
          this.cancel(record.disconnectTimer);
          record.disconnectTimer = this.schedule(() => { if (this.valid(record) && pc.connectionState === 'disconnected') this.closed(1013); }, 5000);
        } else if (pc.connectionState === 'connected') this.cancel(record.disconnectTimer);
      };
      return record;
    }
    async offer(record) {
      if (!this.valid(record) || record.pc.signalingState !== 'stable') return;
      const description = await record.pc.createOffer();
      if (!this.valid(record)) return;
      await record.pc.setLocalDescription(description);
      if (this.valid(record)) this.send({ type: 'offer', recipient_id: record.id,
        description: { type: 'offer', sdp: record.pc.localDescription.sdp } });
    }
    async signal(record, message) {
      if (!this.valid(record)) return;
      const pc = record.pc;
      if (message.type === 'ice_candidate') {
        if (!message.candidate) return;
        if (pc.remoteDescription) await pc.addIceCandidate(message.candidate);
        else if (record.candidates.length < 128) record.candidates.push(message.candidate);
        return;
      }
      if (message.type === 'answer' && pc.signalingState !== 'have-local-offer') return;
      if (message.type === 'offer' && pc.signalingState !== 'stable') return;
      await pc.setRemoteDescription(message.description);
      if (!this.valid(record)) return;
      for (const candidate of record.candidates.splice(0)) {
        if (!this.valid(record)) return;
        await pc.addIceCandidate(candidate);
      }
      if (message.type === 'offer') {
        const answer = await pc.createAnswer();
        if (!this.valid(record)) return;
        await pc.setLocalDescription(answer);
        if (this.valid(record)) this.send({ type: 'answer', recipient_id: record.id,
          description: { type: 'answer', sdp: pc.localDescription.sdp } });
      }
    }
    dropPeer(id) {
      const record = this.peers.get(id); if (!record) return;
      this.cancel(record.disconnectTimer); this.peers.delete(id); record.pc.close();
      const streams = { ...this.state.remoteStreams }; delete streams[id]; this.emit({ remoteStreams: streams });
    }
    async connectActivity(epoch) {
      const activityEpoch = ++this.activityEpoch;
      try {
        // Refresh JWT through the existing HTTP client before a separate activity reconnect.
        await this.api(this.path());
        const socket = await this.options.socket(`ws/learning/sessions/${this.id}/whiteboard/`);
        if (!this.wanted || epoch !== this.epoch || activityEpoch !== this.activityEpoch) { socket.close(); return; }
        this.activity = socket;
        const current = () => this.wanted && epoch === this.epoch && activityEpoch === this.activityEpoch && this.activity === socket;
        socket.onmessage = event => {
          if (!current()) return;
          try {
            const data = JSON.parse(String(event.data));
            if (data.type === 'snapshot' && data.session_id === this.id) {
              this.activityRetryCount = 0; this.emit({ activityConnected: true }); this.acceptBoard(data);
              if (!this.chatRequested) { this.chatRequested = true; socket.send(JSON.stringify({ type: 'chat_history', after: this.lastChatId || 0 })); }
            } else if (data.type === 'chat') this.acceptChat([data.message]);
            else if (data.type === 'chat_history') {
              this.acceptChat(data.messages);
              if (data.has_more && Number.isSafeInteger(data.next_after) && data.next_after > 0) {
                // Stay below the activity socket's rate limit while paging gaps.
                this.cancel(this.chatTimer);
                this.chatTimer = this.schedule(() => {
                  if (current()) socket.send(JSON.stringify({ type: 'chat_history', after: data.next_after }));
                }, 150);
              }
            }
            else if (data.type === 'error') this.emit({ error: `Classroom activity: ${data.code}` });
          } catch (error) { this.error(error); }
        };
        socket.onclose = event => {
          if (!current()) return;
          this.emit({ activityConnected: false }); this.chatRequested = false;
          if (terminal.has(event.code)) this.closed(event.code);
          else this.retryActivity(epoch);
        };
        socket.onerror = () => { if (current()) this.emit({ error: 'Chat and whiteboard connection failed.' }); };
      } catch (error) {
        if (epoch !== this.epoch || !this.wanted) return;
        this.error(error);
        if ([401, 403, 404].includes(error.status)) this.closed(error.status === 401 ? 4401 : 4403);
        else this.retryActivity(epoch);
      }
    }
    retryActivity(epoch) {
      if (!this.wanted || epoch !== this.epoch) return;
      if (this.activityRetryCount++ < 5) this.activityTimer = this.schedule(() => this.connectActivity(epoch), Math.min(30000, 1000 * 2 ** this.activityRetryCount));
      else this.emit({ error: 'Chat and whiteboard disconnected. Reconnect the classroom.' });
    }
    acceptBoard(board) {
      if (!this.state.board || board.revision >= this.state.board.revision) this.emit({ board });
    }
    acceptChat(messages) {
      const merged = new Map(this.state.chat.map(m => [m.id, m]));
      for (const message of messages || []) merged.set(message.id, message);
      const chat = [...merged.values()].sort((a, b) => a.id - b.id).slice(-200);
      this.lastChatId = chat.at(-1)?.id || 0; this.emit({ chat });
    }
    async boardCommand(action, payload = {}) {
      if (!this.state.connected || !this.state.activityConnected || !this.state.board?.can_edit) throw new Error('Whiteboard is read only or reconnecting.');
      if (this.boardPending) throw new Error('Wait for the previous board change.');
      if (['clear', 'permission'].includes(action) && !this.state.board.can_manage) throw new Error('Host permission is required.');
      this.boardPending = true;
      const epoch = this.epoch;
      try {
        await this.api(this.path('whiteboard/'), 'POST', {
          operation_id: this.newId(), base_revision: this.state.board.revision, action, payload });
      } finally {
        try { const board = await this.api(this.path('whiteboard/')); if (epoch === this.epoch && this.wanted) this.acceptBoard(board); }
        finally { this.boardPending = false; }
      }
    }
    async chat(text) {
      if (!this.state.connected || !this.state.activityConnected || !text.trim()) throw new Error('Join the classroom before sending chat.');
      const data = this.pendingChat?.text === text ? this.pendingChat : { client_id: this.newId(), text };
      const epoch = this.epoch;
      this.pendingChat = data;
      const message = await this.api(this.path('chat/'), 'POST', data);
      if (this.pendingChat === data) this.pendingChat = null;
      if (epoch === this.epoch && this.wanted) this.acceptChat([message]);
    }
    async toggle(kind) {
      if (!this.state.connected || !this.local) { this.emit({ [kind]: !this.state[kind] }); return; }
      if (kind === 'camera' && this.state.sharing) throw new Error('Stop screen sharing before changing the camera.');
      const mediaKind = kind === 'camera' ? 'video' : 'audio';
      const enabled = !this.state[kind];
      let track = this.local.getTracks().find(t => t.kind === mediaKind);
      if (!track && enabled) {
        if (this.options.canCapture && !this.options.canCapture()) throw new Error('Return to Awinlink before enabling a media device.');
        const epoch = this.epoch;
        const stream = await this.options.media({ video: mediaKind === 'video', audio: mediaKind === 'audio' });
        if (epoch !== this.epoch || !this.wanted) { stop(stream); return; }
        track = stream.getTracks().find(t => t.kind === mediaKind);
        if (!track) { stop(stream); throw new Error('Media device unavailable.'); }
        this.local.addTrack(track);
        stream.release?.(false); // The retained local stream now owns this native track.
        await Promise.all([...this.peers.values()].map(record => record.senders[mediaKind].replaceTrack(track)));
        if (epoch !== this.epoch || !this.wanted) return;
      }
      if (track) track.enabled = enabled;
      this.emit({ [kind]: enabled, localStream: this.local });
    }
    async share() {
      if (!this.state.connected) return;
      if (this.sharingPending) return;
      if (this.display) return this.stopSharing();
      if (!this.options.display) throw new Error('Screen sharing is unavailable on this device.');
      const epoch = this.epoch;
      this.sharingPending = true;
      this.emit({ sharing: true });
      let stream;
      try { stream = await this.options.display(); }
      catch (error) { if (epoch === this.epoch) this.emit({ sharing: false }); throw error; }
      finally { this.sharingPending = false; }
      if (epoch !== this.epoch || !this.wanted) { stop(stream); return; }
      const track = stream.getVideoTracks()[0];
      if (!track) { stop(stream); this.emit({ sharing: false }); throw new Error('No screen was selected.'); }
      try {
        this.display = stream;
        await Promise.all([...this.peers.values()].map(record => record.senders.video.replaceTrack(track)));
        if (epoch !== this.epoch || !this.wanted || this.display !== stream) return;
        track.onended = () => { if (this.display === stream) this.stopSharing().catch(error => this.error(error)); };
        this.emit({ sharing: true, localStream: stream });
      } catch (error) {
        if (epoch !== this.epoch || !this.wanted || this.display !== stream) return;
        this.display = null; stop(stream); await this.stopSharing(); throw error;
      }
    }
    async stopSharing() {
      const epoch = this.epoch;
      const display = this.display; this.display = null;
      if (display) display.getVideoTracks().forEach(track => { track.onended = null; });
      stop(display);
      const results = await Promise.allSettled([...this.peers.values()].map(record => record.senders.video.replaceTrack(this.local?.getVideoTracks()[0] || null)));
      if (epoch !== this.epoch || !this.wanted) return;
      this.emit({ sharing: false, localStream: this.local });
      if (results.some(result => result.status === 'rejected')) throw new Error('Unable to restore the camera. Leave and rejoin the classroom.');
    }
    closed(code) {
      if (!this.wanted) return;
      const connectionId = this.connectionId;
      ++this.epoch; this.cleanup();
      void this.abandon(connectionId);
      if (terminal.has(code)) {
        this.wanted = false;
        this.emit({ busy: false, status: code === 4410 ? 'Session ended' : 'Classroom access closed', error: code === 4409 ? 'Another connection replaced this one. Join again to take over.' : 'Your classroom connection is no longer authorized.' });
      } else if (this.retryCount++ < 5) {
        this.emit({ status: 'Reconnecting…', busy: false });
        this.retryTimer = this.schedule(() => this.connect(), Math.min(30000, 1000 * 2 ** (this.retryCount - 1)));
      } else { this.wanted = false; this.emit({ status: 'Disconnected', busy: false, error: 'Unable to reconnect. Join again when your connection is ready.' }); }
    }
    cleanup() {
      this.cancel(this.readyTimer); this.cancel(this.activityTimer); this.cancel(this.signalTimer); this.cancel(this.stableTimer); this.cancel(this.chatTimer); ++this.activityEpoch;
      this.signalQueue = []; this.signalTokens = 20; this.signalRefill = this.signalClock();
      const socket = this.socket, activity = this.activity; this.socket = null; this.activity = null;
      socket?.close(); activity?.close(); this.chatRequested = false;
      this.earlySignals = [];
      for (const id of [...this.peers.keys()]) this.dropPeer(id);
      if (this.display) this.display.getVideoTracks().forEach(track => { track.onended = null; });
      stop(this.display); stop(this.local); this.display = null; this.local = null;
      this.lastChatId = 0;
      this.emit({ connected: false, activityConnected: false, peers: [], localStream: null, remoteStreams: {}, sharing: false, board: null, chat: [] });
    }
    async leave() {
      this.wanted = false; ++this.epoch; this.cancel(this.retryTimer);
      const connectionId = this.connectionId; this.connectionId = null;
      this.cleanup(); this.emit({ status: 'Left classroom', busy: false, board: null, chat: [] });
      if (connectionId) {
        try { await this.api(this.path('leave/'), 'POST', { connection_id: connectionId }); }
        catch (error) { this.error(error); }
      }
    }
    dispose() { this.disposed = true; return this.leave(); }
  }
  return { ClassroomClient, uuid, point, objectAt, sampledPoints };
});
