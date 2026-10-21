(() => {
  const $ = id => document.getElementById(id), base = '/api/marketplace/';
  let booking = null, cursor = null, bookingsNext = null, windowsNext = null, submissionsNext = null, eventsNext = null, busy = false;
  const token = () => $('booking-csrf').value;
  async function api(path, method = 'GET', body) {
    const headers = { 'X-CSRFToken': token() };
    if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
    const response = await fetch(base + path, { method, headers, body: body ? body instanceof FormData ? body : JSON.stringify(body) : undefined });
    if (response.status === 204) return null;
    const data = await response.json();
    if (!response.ok) throw Error(JSON.stringify(data));
    return data;
  }
  const relative = next => next ? next.split('/api/marketplace/')[1] : null;
  const run = fn => async event => {
    event?.preventDefault(); $('booking-error').textContent = '';
    if (busy) return;
    busy = true; $('market-bookings').setAttribute('aria-busy', 'true');
    try { await fn(); } catch (error) { $('booking-error').textContent = error.message; }
    finally { busy = false; $('market-bookings').setAttribute('aria-busy', 'false'); }
  };
  function text(parent, tag, content) { const el = document.createElement(tag); el.textContent = content; parent.append(el); return el; }
  function button(parent, label, fn) { const b = text(parent, 'button', label); b.onclick = run(fn); return b; }
  async function windows(path = 'availability/') {
    const page = await api(path); $('availability-results').replaceChildren();
    windowsNext = relative(page.next); $('availability-next').hidden = !windowsNext;
    for (const window of page.results) { const row = text($('availability-results'), 'article', `${window.starts_at} — ${window.ends_at} (${window.timezone})`);
      button(row, 'Delete opening', async () => { await api(`availability/${window.id}/`, 'DELETE'); await windows(); }); }
  }
  async function bookings(path = 'bookings/') {
    const page = await api(path); $('booking-results').replaceChildren();
    bookingsNext = relative(page.next); $('bookings-next').hidden = !bookingsNext;
    for (const row of page.results) button($('booking-results'), `#${row.id}: ${row.title} · ${row.status}`, () => open(row.id));
    if (!page.results.length) text($('booking-results'), 'p', 'No bookings yet. A structured offer becomes a booking when the talent accepts.');
  }
  async function submissions(path) {
    const page = await api(path); submissionsNext = relative(page.next); $('submissions-next').hidden = !submissionsNext;
    for (const row of page.results) {
      const card = text($('booking-submissions'), 'article', `Delivery ${row.sequence}`); text(card, 'p', row.summary);
      if (row.artifact_name) { const link = text(card, 'a', `Download ${row.artifact_name}`); link.href = base + `bookings/${booking.id}/submissions/${row.id}/artifact/`; }
    }
  }
  async function events(path) {
    const page = await api(path); eventsNext = relative(page.next); $('events-next').hidden = !eventsNext;
    for (const row of page.results) text($('booking-events'), 'p', `${row.created_at}: ${row.action} ${row.reason}`);
  }
  async function open(id) {
    const data = await api(`bookings/${id}/`); booking = data;
    $('booking-detail').hidden = false; $('booking-title').textContent = `Booking #${data.id}: ${data.title}`;
    $('booking-summary').textContent = `${data.status} · ${data.amount} ${data.currency} · ${data.starts_at} — ${data.ends_at}\n${data.snapshot.terms}\nCancellation: either participant before the appointment starts; no cancellation after work starts. No online payment.`;
    $('booking-actions').replaceChildren(); $('booking-reason').value = '';
    for (const [key, label] of [['start', 'Start work'], ['complete', 'Confirm completion'], ['request_changes', 'Request changes'], ['cancel', 'Cancel booking']])
      if (data.capabilities[key]) button($('booking-actions'), label, async () => { await api(`bookings/${id}/`, 'POST', { action: key.toUpperCase(), reason: $('booking-reason').value }); await open(id); });
    $('booking-message-form').hidden = !data.capabilities.message;
    $('booking-submission-form').hidden = !data.capabilities.submit;
    $('booking-review-form').hidden = !data.capabilities.review;
    $('booking-review').textContent = data.review ? `${data.review.rating}/5 · ${data.review.text}` : '';
    if (data.capabilities.manage_review) button($('booking-review'), data.review.published ? 'Make review private' : 'Publish review', async () => {
      await api(`bookings/${id}/reviews/`, 'PATCH', { publish: !data.review.published }); await open(id);
    });
    const messages = await api(`bookings/${id}/messages/`); cursor = messages.next_before;
    $('booking-messages').replaceChildren(); for (const row of messages.messages) text($('booking-messages'), 'p', `${row.author}: ${row.body}`);
    $('booking-older').hidden = cursor === null;
    $('booking-submissions').replaceChildren(); await submissions(`bookings/${id}/submissions/`);
    $('booking-events').replaceChildren(); await events(`bookings/${id}/events/`);
    // Starting is available at the appointment time; refresh without reloading the page.
    button($('booking-actions'), 'Refresh booking', () => open(id));
  }
  $('availability-load').onclick = run(() => windows()); $('availability-next').onclick = run(() => windows(windowsNext));
  $('availability-form').onsubmit = run(async () => { await api('availability/', 'POST', Object.fromEntries(new FormData($('availability-form')))); await windows(); });
  $('bookings-load').onclick = run(() => bookings()); $('bookings-next').onclick = run(() => bookings(bookingsNext));
  $('submissions-next').onclick = run(() => submissions(submissionsNext));
  $('events-next').onclick = run(() => events(eventsNext));
  $('booking-older').onclick = run(async () => {
    const id = booking.id, before = cursor, page = await api(`bookings/${id}/messages/?before=${before}`);
    if (id !== booking.id || before !== cursor) return;
    const fragment = document.createDocumentFragment(); for (const row of page.messages) text(fragment, 'p', `${row.author}: ${row.body}`);
    $('booking-messages').prepend(fragment); cursor = page.next_before; $('booking-older').hidden = cursor === null;
  });
  $('booking-message-form').onsubmit = run(async () => { await api(`bookings/${booking.id}/messages/`, 'POST', { body: $('booking-message-form').elements.body.value }); $('booking-message-form').reset(); await open(booking.id); });
  $('booking-submission-form').onsubmit = run(async () => {
    const form = $('booking-submission-form'), data = new FormData(form), file = data.get('artifact');
    if (file instanceof File && !file.name && file.size === 0) data.delete('artifact');
    await api(`bookings/${booking.id}/submissions/`, 'POST', data); form.reset(); await open(booking.id);
  });
  $('booking-review-form').onsubmit = run(async () => {
    const form = $('booking-review-form'), data = Object.fromEntries(new FormData(form)); data.publish = form.elements.publish.checked;
    await api(`bookings/${booking.id}/reviews/`, 'POST', data); form.reset(); await open(booking.id);
  });
  run(async () => { await bookings(); const id = new URLSearchParams(location.search).get('booking'); if (id && /^\d+$/.test(id)) await open(Number(id)); })();
})();
