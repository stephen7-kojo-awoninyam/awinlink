/* Browser session-cookie adapter; no call globals or call media are modified. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const core = window.AwinClassroom;
  const element = (tag, text, className) => { const node = document.createElement(tag); if (text) node.textContent = text; if (className) node.className = className; return node; };
  async function api(path, method = 'GET', body) {
    if (!/^(learning|messaging)\//.test(path)) throw new Error('Invalid classroom API path.');
    const response = await fetch(`/api/${path}`, { method, credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '' },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { const error = new Error((data.error?.fields ? Object.entries(data.error.fields).map(([key, value]) => `${key}: ${value}`).join('; ') : data.error?.detail) || data.detail || `Request failed (${response.status}).`); error.status = response.status; throw error; }
    return data;
  }
  const nextPath = value => {
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/learning/')) throw new Error('Invalid pagination link.');
    return url.pathname.slice(5) + url.search;
  };
  if (byId('classroom-directory')) {
    const directory = byId('classroom-directory'); let next = 'learning/classrooms/?page_size=20';
    const more = byId('vc-more');
    async function load() {
      more.disabled = true; byId('vc-error').textContent = '';
      try {
        const result = await api(next);
        if (!result.results.length && !directory.children.length) directory.append(element('p', 'No classrooms available. Enroll in a course to discover its classrooms.'));
        for (const room of result.results) {
          const section = element('section'); section.append(element('h2', room.title), element('p', `${room.capacity} seats`));
          const button = element('button', 'View sessions', 'lc-button'); section.append(button); directory.append(section);
          window.AwinClassroomManagement?.room(section, room);
          let sessionsPath = `learning/classrooms/${room.id}/sessions/?page_size=20`;
          button.onclick = async () => {
            button.disabled = true;
            try {
              const sessions = await api(sessionsPath);
              if (!sessions.results.length) section.append(element('p', 'No sessions scheduled.'));
              for (const session of sessions.results) {
                const link = element('a', `${session.title} · ${session.status.toLowerCase()}${session.scheduled_start ? ' · ' + new Date(session.scheduled_start).toLocaleString() : ''}`);
                link.href = `/learning/sessions/${session.id}/classroom/`; section.append(link);
              }
              sessionsPath = sessions.next ? nextPath(sessions.next) : null;
              button.hidden = !sessionsPath; button.textContent = 'More sessions';
            } catch (error) { byId('vc-error').textContent = error.message; }
            finally { button.disabled = false; }
          };
        }
        next = result.next ? nextPath(result.next) : null; more.hidden = !next;
      } catch (error) { byId('vc-error').textContent = error.message; more.hidden = false; more.textContent = 'Try again'; }
      finally { more.disabled = false; }
    }
    more.onclick = load; void load(); return;
  }
  const root = byId('vc-classroom'); if (!root || !core) return;
  let state, drawing = null, pollBusy = false, chatWorking = false;
  const canvas = byId('vc-board'), context = canvas.getContext('2d');
  const client = new core.ClassroomClient({ sessionId: Number(root.dataset.sessionId), api,
    socket: async path => new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/${path}`),
    media: constraints => constraints.audio || constraints.video ? navigator.mediaDevices.getUserMedia(constraints) : Promise.resolve(new MediaStream()),
    display: navigator.mediaDevices?.getDisplayMedia ? () => navigator.mediaDevices.getDisplayMedia({ video: true, audio: false }) : undefined,
    peer: (iceServers, iceTransportPolicy) => new RTCPeerConnection({ iceServers, iceTransportPolicy }),
    validateIce: value => Array.isArray(value) && value.length ? value.filter(s => s && (typeof s.urls === 'string' || Array.isArray(s.urls))) : [{ urls: 'stun:stun.l.google.com:19302' }],
    onState: render });
  const run = action => Promise.resolve().then(action).catch(error => { byId('vc-error').textContent = error.message; });
  function render(next) {
    state = next;
    byId('vc-status').textContent = `${state.session?.status || ''} · ${state.status}${state.session?.my_participant ? ' · ' + state.session.my_participant.admission_state.toLowerCase() : ''}`;
    byId('vc-error').textContent = state.error;
    byId('vc-join').disabled = state.busy || state.connected || state.status === 'Reconnecting…' || state.session?.status !== 'LIVE' || state.session?.my_participant?.admission_state !== 'ADMITTED';
    byId('vc-leave').disabled = !state.connected && !state.busy && state.status !== 'Reconnecting…';
    for (const kind of ['camera', 'microphone']) { byId(`vc-${kind}`).checked = state[kind]; byId(`vc-${kind}`).disabled = state.busy || (kind === 'camera' && state.sharing); }
    byId('vc-share').hidden = !navigator.mediaDevices?.getDisplayMedia || !state.connected;
    byId('vc-share').textContent = state.sharing ? 'Stop sharing' : 'Share screen';
    for (const button of root.querySelectorAll('[data-action]')) {
      const action = button.dataset.action;
      button.hidden = action === 'request-admission' ? !!state.session?.my_participant || !['LIVE', 'SCHEDULED'].includes(state.session?.status) : !state.session?.capabilities?.[action];
      button.disabled = state.busy;
    }
    renderGrid(); renderRoster(); renderBoard(); renderChat();
    byId('vc-message').disabled = !state.connected || !state.activityConnected;
    byId('vc-send').disabled = !state.connected || !state.activityConnected || chatWorking;
  }
  function renderGrid() {
    const grid = byId('vc-grid');
    const entries = [{ id: 'local', label: state.sharing ? 'Your screen' : 'You', stream: state.localStream },
      ...state.peers.map(peer => ({ id: String(peer.participant_id), label: `${state.participants.find(p => p.id === peer.participant_id)?.display_name || 'Participant ' + peer.user_id} · ${peer.role.toLowerCase()}`, stream: state.remoteStreams[peer.participant_id] }))];
    for (const tile of [...grid.children]) if (!entries.some(entry => entry.id === tile.dataset.peer)) { tile.querySelector('video').srcObject = null; tile.remove(); }
    for (const entry of entries) {
      let tile = [...grid.children].find(node => node.dataset.peer === entry.id);
      if (!tile) { tile = element('article', '', 'vc-tile'); tile.dataset.peer = entry.id;
        const video = element('video'); video.autoplay = true; video.playsInline = true; video.muted = entry.id === 'local';
        tile.append(video, element('div', 'Camera off', 'vc-placeholder'), element('p')); grid.append(tile); }
      const video = tile.querySelector('video');
      if (video.srcObject !== entry.stream) { video.srcObject = entry.stream || null; if (entry.stream) video.play().catch(() => { video.controls = true; }); }
      video.hidden = !entry.stream;
      tile.querySelector('.vc-placeholder').hidden = !!entry.stream;
      tile.querySelector('p').textContent = entry.label;
    }
  }
  function renderRoster() {
    const roster = byId('vc-roster'); roster.replaceChildren();
    if (!state.session?.capabilities?.participants) return;
    roster.append(element('h3', 'Admission and host controls', 'vc-section-title'));
    for (const participant of state.participants) {
      const row = element('div', '', 'vc-roster-row');
      row.append(element('span', `${participant.display_name} · ${participant.role.toLowerCase()} · ${participant.admission_state.toLowerCase()}`));
      const learner = participant.role === 'LEARNER', self = participant.id === state.session.my_participant?.id;
      const manageable = !self && participant.role !== 'HOST' && (state.session.my_participant?.role !== 'COHOST' || learner);
      for (const action of ['admit', 'remove']) {
        if (!manageable || !state.session.capabilities[action] || (action === 'admit' ? participant.admission_state === 'ADMITTED' : participant.admission_state !== 'ADMITTED')) continue;
        const button = element('button', action === 'admit' ? 'Admit' : 'Remove', 'lc-button lc-button-secondary'); button.disabled = state.busy;
        button.onclick = () => run(() => { if (action === 'remove' && !confirm(`Remove ${participant.display_name}?`)) return; return client.action(action, participant.id); }); row.append(button);
      }
      if (learner && participant.admission_state === 'ADMITTED' && state.board?.can_manage && state.activityConnected) {
        const allowed = state.board.editors.includes(participant.id);
        const button = element('button', allowed ? 'Revoke drawing' : 'Allow drawing', 'lc-button lc-button-secondary');
        button.onclick = () => run(() => client.boardCommand('permission', { participant_id: participant.id, allowed: !allowed })); row.append(button);
      }
      roster.append(row);
    }
    if (state.rosterHasNext || state.rosterHasPrevious) {
      const navigation = element('div', '', 'vc-toolbar'); navigation.append(element('span', `Participant page ${state.rosterPage}`));
      for (const [label, delta, available] of [['Previous participants', -1, state.rosterHasPrevious], ['More participants', 1, state.rosterHasNext]]) {
        const button = element('button', label, 'lc-button lc-button-secondary'); button.disabled = !available;
        button.onclick = () => run(() => client.changeRosterPage(delta)); navigation.append(button);
      }
      roster.append(navigation);
    }
  }
  function paint(object) {
    const w = canvas.width, h = canvas.height; context.strokeStyle = object.color; context.fillStyle = object.color;
    context.lineWidth = object.width * w; context.lineCap = 'round'; context.lineJoin = 'round'; context.beginPath();
    if (object.kind === 'stroke') { object.points.forEach(([x, y], index) => index ? context.lineTo(x * w, y * h) : context.moveTo(x * w, y * h)); context.stroke(); }
    else if (object.kind === 'text') { context.font = `${object.size * w}px sans-serif`; context.textBaseline = 'top'; object.text.split('\n').forEach((line, i) => context.fillText(line, object.x * w, object.y * h + i * object.size * w * 1.2)); }
    else if (object.kind === 'rectangle') context.strokeRect(object.x * w, object.y * h, object.w * w, object.h * h);
    else if (object.kind === 'ellipse') { context.ellipse((object.x + object.w / 2) * w, (object.y + object.h / 2) * h, object.w * w / 2, object.h * h / 2, 0, 0, Math.PI * 2); context.stroke(); }
    else { context.moveTo(object.x * w, object.y * h); context.lineTo((object.x + object.w) * w, (object.y + object.h) * h); context.stroke(); }
  }
  function renderBoard() {
    context.clearRect(0, 0, canvas.width, canvas.height);
    for (const object of Object.values(state.board?.objects || {})) paint(object);
    if (drawing?.object && state.board?.can_edit && state.activityConnected) paint(drawing.object);
    byId('vc-board-status').textContent = state.activityConnected ? state.board?.can_edit ? 'Editing enabled' : 'View only — your host controls editing' : 'Waiting for classroom connection';
    byId('vc-undo').disabled = !state.activityConnected || !state.board?.can_edit;
    byId('vc-clear').hidden = !state.board?.can_manage; byId('vc-clear').disabled = !state.activityConnected;
    for (const control of byId('vc-board-tools').querySelectorAll('input,select')) control.disabled = !state.activityConnected || !state.board?.can_edit;
    const accessible = byId('vc-board-content'); accessible.replaceChildren();
    for (const object of Object.values(state.board?.objects || {})) accessible.append(element('li', object.kind === 'text' ? object.text : `${object.kind} in ${object.color}`));
  }
  function renderChat() {
    const log = byId('vc-chat'); const bottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 30;
    const existing = new Set([...log.children].map(node => Number(node.dataset.message)));
    for (const message of state.chat) if (!existing.has(message.id)) {
      const row = element('p'); row.dataset.message = String(message.id); row.append(element('strong', `${message.sender_name}: `), document.createTextNode(message.text)); log.append(row);
    }
    const ids = new Set(state.chat.map(m => m.id)); for (const row of [...log.children]) if (!ids.has(Number(row.dataset.message))) row.remove();
    if (bottom) log.scrollTop = log.scrollHeight;
  }
  function position(event) { const rect = canvas.getBoundingClientRect(); return core.point((event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height); }
  canvas.onpointerdown = event => {
    if (!state.activityConnected || !state.board?.can_edit) return;
    const [x, y] = position(event), kind = byId('vc-tool').value;
    if (kind === 'erase') { const id = core.objectAt(state.board.objects, x, y); if (id) run(() => client.boardCommand('erase', { ids: [id] })); return; }
    const object = { id: core.uuid(), kind, color: byId('vc-color').value, width: .004 };
    if (kind === 'text') { const text = byId('vc-board-text').value; if (!text.trim()) return; run(() => client.boardCommand('add', { ...object, x, y, text, size: .025 })); return; }
    Object.assign(object, kind === 'stroke' ? { points: [[x, y], [x, y]] } : { x, y, w: 0, h: 0 });
    drawing = { start: [x, y], object, pointer: event.pointerId }; canvas.setPointerCapture(event.pointerId);
  };
  canvas.onpointermove = event => {
    if (!drawing || drawing.pointer !== event.pointerId || !state.activityConnected || !state.board?.can_edit) return;
    const [x, y] = position(event), object = drawing.object;
    if (object.kind === 'stroke') { if (object.points.length < 2048) object.points.push([x, y]); }
    else if (object.kind === 'line') { object.w = x - drawing.start[0]; object.h = y - drawing.start[1]; }
    else { object.x = Math.min(x, drawing.start[0]); object.y = Math.min(y, drawing.start[1]); object.w = Math.abs(x - drawing.start[0]); object.h = Math.abs(y - drawing.start[1]); }
    renderBoard();
  };
  canvas.onpointerup = event => { if (!drawing || drawing.pointer !== event.pointerId) return; const object = drawing.object; drawing = null; renderBoard(); run(() => client.boardCommand('add', object)); };
  canvas.onpointercancel = () => { drawing = null; renderBoard(); };
  byId('vc-join').onclick = () => run(() => client.join({ camera: byId('vc-camera').checked, microphone: byId('vc-microphone').checked }));
  byId('vc-leave').onclick = () => run(() => client.leave());
  for (const kind of ['camera', 'microphone']) byId(`vc-${kind}`).onchange = () => run(() => client.toggle(kind));
  byId('vc-share').onclick = () => run(() => client.share());
  for (const button of root.querySelectorAll('[data-action]')) button.onclick = () => run(() => { const action = button.dataset.action; if (['end', 'cancel'].includes(action) && !confirm(`${action === 'end' ? 'End' : 'Cancel'} this session for everyone?`)) return; return client.action(action); });
  byId('vc-undo').onclick = () => run(() => client.boardCommand('undo'));
  byId('vc-clear').onclick = () => run(() => { if (confirm('Clear the board for everyone?')) return client.boardCommand('clear'); });
  byId('vc-chat-form').onsubmit = event => { event.preventDefault(); if (chatWorking) return; chatWorking = true; byId('vc-send').disabled = true;
    run(async () => { await client.chat(byId('vc-message').value); byId('vc-message').value = ''; }).finally(() => { chatWorking = false; render(client.state); }); };
  const poll = setInterval(() => { if (pollBusy) return; pollBusy = true; run(() => client.load()).finally(() => { pollBusy = false; }); }, 5000);
  addEventListener('pagehide', () => { clearInterval(poll); void client.dispose(); }, { once: true });
  void run(() => client.load());
})();
