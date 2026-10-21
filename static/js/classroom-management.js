/* Classroom setup uses the same permission-checked REST services as native. */
(() => {
  'use strict';
  const root = document.getElementById('classroom-management');
  if (!root) return;
  const node = (tag, text) => { const n = document.createElement(tag); n.textContent = text || ''; return n; };
  const error = node('p'); error.setAttribute('role', 'alert'); root.append(error);
  const report = e => { error.textContent = e.message; };
  async function api(path, method = 'GET', body) {
    const url = new URL(path.startsWith('/api/') || /^https?:/.test(path) ? path : `/api/learning/${path}`, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/learning/')) throw new Error('Invalid classroom URL.');
    const response = await fetch(url, { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    if (response.status === 204) return null;
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.fields ? Object.entries(data.error.fields).map(([k,v]) => `${k}: ${v}`).join('; ') : data.error?.detail || data.detail || 'Classroom request failed.');
    return data;
  }
  function button(parent, title, action) {
    const b = node('button', title); b.type = 'button'; b.className = 'lc-button lc-button-secondary';
    b.onclick = async () => { b.disabled = true; error.textContent = ''; try { await action(); } catch(e) { report(e); } finally { b.disabled = false; } }; parent.append(b); return b;
  }
  function field(parent, label, type = 'text', required = true) {
    const wrapper = node('label', label + ' '), input = node('input'); input.type = type; input.required = required;
    if (type === 'number') { input.min = '1'; input.step = '1'; }
    if (type === 'text') input.maxLength = 250;
    wrapper.append(input); parent.append(wrapper); return input;
  }
  function usernamePicker(parent, room, purpose, label) {
    const holder = node('div'), input = field(holder, label, 'text', false);
    input.maxLength = 150; input.autocomplete = 'off';
    const status = node('p'), results = node('div'); status.setAttribute('role', 'status');
    holder.append(status, results); parent.append(holder);
    let selected = null, generation = 0, next = null;
    input.oninput = () => { generation++; selected = null; next = null; results.replaceChildren(); status.textContent = ''; more.hidden = true; };
    async function search(append = false) {
      const query = input.value.trim(), current = ++generation;
      if (query.length < 2) { status.textContent = 'Enter at least 2 username characters.'; return; }
      selected = null; status.textContent = 'Searching...';
      const page = await api(append ? next : `classrooms/${room.id}/users/?purpose=${purpose}&q=${encodeURIComponent(query)}`);
      if (current !== generation) return;
      if (!append) results.replaceChildren();
      next = page.next; more.hidden = !next;
      for (const user of page.results) button(results, `@${user.username} (${user.display_name})`, () => {
        selected = user; status.textContent = `Selected @${user.username}`;
      });
      status.textContent = results.children.length ? 'Choose a username below.' : 'No eligible users found.';
    }
    button(holder, 'Search usernames', () => search());
    const more = button(holder, 'More usernames', () => search(true)); more.hidden = true;
    return () => { if (!selected) throw new Error('Search and select a username first.'); return selected.id; };
  }
  function select(parent, label, items) {
    const wrapper = node('label', label + ' '), input = node('select'); input.required = true;
    for (const item of items) { const option = node('option', item.title); option.value = item.id; input.append(option); }
    wrapper.append(input); parent.append(wrapper); return input;
  }
  function form(parent, title, submit, build) {
    const details = node('details'), summary = node('summary', title), f = node('form'); f.className = 'vc-toolbar';
    details.append(summary, f); parent.append(details); const payload = build(f);
    const b = node('button', submit); b.className = 'lc-button'; f.append(b);
    f.onsubmit = async e => { e.preventDefault(); b.disabled = true; error.textContent = ''; try { await payload(); } catch(e) { report(e); } finally { b.disabled = false; } };
    return details;
  }
  async function paged(parent, path, render) {
    const list = node('div'); parent.append(list); let next = path;
    const more = button(parent, 'Load more', async () => { const page = await api(next); page.results.forEach(item => render(list, item)); next = page.next; more.hidden = !next; });
    more.click();
  }
  const inbox = node('section'); inbox.append(node('h2', 'Classroom invitations')); root.append(inbox);
  button(inbox, 'Refresh invitations', async () => { inbox.querySelectorAll('[data-inbox]').forEach(n => n.remove()); const holder = node('div'); holder.dataset.inbox = 'true'; inbox.append(holder);
    await paged(holder, 'classroom-invitations/', (list, invitation) => {
      const row = node('article'); row.append(node('p', `${invitation.classroom_title} · ${invitation.status}${invitation.is_expired ? ' · expired' : ''}`), node('p', invitation.message)); list.append(row);
      if (invitation.status === 'PENDING' && !invitation.is_expired) {
        row.append(node('p', 'Accepting enrolls you in this course. Session admission is separate.'));
        for (const action of ['accept', 'decline']) button(row, action === 'accept' ? 'Accept invitation' : 'Decline invitation', async () => { await api(`classroom-invitations/${invitation.id}/${action}/`, 'POST', {}); location.reload(); });
      }
    });
  }).click();
  api('courses/me/').then(courses => { if (!courses.length) return;
    form(root, 'Create classroom', 'Create classroom', f => {
      const course = select(f, 'Course', courses), title = field(f, 'Classroom title'), capacity = field(f, 'Seats', 'number'); capacity.value = '50'; capacity.max = '2147483647';
      return async () => { await api('classrooms/', 'POST', { course: Number(course.value), title: title.value, capacity: Number(capacity.value) }); location.reload(); };
    });
  }).catch(report);
  window.AwinClassroomManagement = { room(parent, room) {
    if (room.capabilities?.manage) {
      const management = node('section'); parent.append(management);
      button(management, 'Schedule session', async () => {
        const lessons = await api(`courses/${room.course}/lessons/`);
        if (!lessons.length) throw new Error('Add a course lesson before scheduling a session.');
        const existing = management.querySelector('[data-schedule]'); if (existing) { existing.open = true; return; }
        const details = form(management, 'Session schedule (local time)', 'Schedule session', f => {
          const lesson = select(f, 'Lesson', lessons), title = field(f, 'Session title'), start = field(f, 'Starts', 'datetime-local'), end = field(f, 'Ends', 'datetime-local');
          return async () => { await api(`classrooms/${room.id}/sessions/`, 'POST', { lesson: Number(lesson.value), title: title.value, scheduled_start: new Date(start.value).toISOString(), scheduled_end: new Date(end.value).toISOString() }); location.reload(); };
        }); details.dataset.schedule = 'true'; details.open = true;
      });
      form(management, 'Invite learner', 'Send invitation', f => {
        const recipient = usernamePicker(f, room, 'invite', 'Recipient username'), message = field(f, 'Message', 'text', false); message.maxLength = 1000;
        return async () => { await api(`classrooms/${room.id}/invitations/`, 'POST', { recipient: recipient(), message: message.value }); message.value = ''; error.textContent = 'Invitation sent. Use Sent invitations to review it.'; };
      });
      button(management, 'Sent invitations', async () => {
        management.querySelector('[data-sent]')?.remove(); const holder = node('div'); holder.dataset.sent = 'true'; management.append(holder);
        await paged(holder, `classrooms/${room.id}/invitations/`, (list, invitation) => {
          const row = node('p', `@${invitation.recipient_username} · ${invitation.status}${invitation.is_expired ? ' · expired' : ''}`); list.append(row);
          if (invitation.status === 'PENDING' && !invitation.is_expired) button(row, 'Revoke invitation', async () => { await api(`classrooms/${room.id}/invitations/${invitation.id}/revoke/`, 'POST', {}); row.textContent = 'Invitation revoked'; });
        });
      });
    }
    if (room.capabilities?.staff) {
      const staff = node('section'); parent.append(staff); staff.append(node('p', 'Staff changes are available while no session is live.'));
      form(staff, 'Add cohost', 'Add cohost', f => { const user = usernamePicker(f, room, 'cohost', 'Cohost username'); return async () => { await api(`classrooms/${room.id}/staff/`, 'POST', { user: user(), role: 'COHOST' }); error.textContent = 'Cohost assigned. Refresh staff to review.'; }; });
      button(staff, 'Refresh staff', async () => {
        staff.querySelector('[data-staff]')?.remove(); const holder = node('div'); holder.dataset.staff = 'true'; staff.append(holder);
        await paged(holder, `classrooms/${room.id}/staff/`, (list, member) => {
          const row = node('p', `@${member.username} (${member.display_name}) · ${member.role}`); list.append(row);
          if (member.role === 'COHOST') {
            button(row, 'Remove cohost', async () => { if (!confirm(`Remove ${member.display_name} as cohost?`)) return; await api(`classrooms/${room.id}/staff/`, 'POST', { user: member.user, role: 'REMOVE' }); row.remove(); });
            button(row, 'Make host', async () => { if (!confirm(`Transfer host to ${member.display_name}? The current host becomes a cohost.`)) return; await api(`classrooms/${room.id}/staff/`, 'POST', { user: member.user, role: 'HOST' }); location.reload(); });
          }
        });
      });
    }
  } };
})();
