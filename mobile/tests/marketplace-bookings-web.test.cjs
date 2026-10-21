const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const vm = require('node:vm');

test('web text delivery omits the unselected file and preserves authenticated multipart requests', async () => {
  class Element {
    constructor() { this.children = []; this.elements = {}; this.value = ''; this.hidden = false; }
    append(value) { this.children.push(value); }
    replaceChildren(...values) { this.children = values; }
    setAttribute() {}
    reset() {}
  }
  class File { constructor() { this.name = ''; this.size = 0; } }
  class FormData extends Map { constructor(form) { super(Object.entries(form.fields || {})); } }
  const elements = {};
  const get = id => elements[id] ||= new Element();
  get('booking-csrf').value = 'fixture-csrf';
  get('booking-submission-form').fields = { summary: 'Text delivery <img>', artifact: new File() };
  const booking = { id: 7, title: 'Service', status: 'IN_PROGRESS', amount: '20.00', currency: 'GHS',
    snapshot: { terms: 'Exact terms' }, capabilities: { submit: true, message: true }, review: null };
  const requests = [];
  vm.runInNewContext(readFileSync(resolve(__dirname, '../../static/js/marketplace-bookings.js'), 'utf8'), {
    document: { getElementById: get, createElement: () => new Element() },
    FormData, File, URLSearchParams, location: { search: '?booking=7' },
    fetch: async (url, options) => {
      requests.push({ url, options });
      let data;
      if (url.endsWith('/bookings/')) data = { results: [booking], next: null };
      else if (url.endsWith('/messages/')) data = { messages: [], next_before: null };
      else if (url.endsWith('/events/')) data = { results: [], next: null };
      else if (url.endsWith('/submissions/')) {
        if (options.method === 'POST') { booking.status = 'SUBMITTED'; booking.capabilities.submit = false; data = { id: 9 }; }
        else data = { results: booking.status === 'SUBMITTED' ? [{ id: 9, sequence: 1, summary: 'Text delivery <img>' }] : [], next: null };
      } else data = booking;
      return { ok: true, status: options.method === 'POST' ? 201 : 200, json: async () => data };
    },
  });
  for (let i = 0; i < 12; i++) await new Promise(setImmediate);
  assert.equal(get('booking-submission-form').hidden, false);
  await get('booking-submission-form').onsubmit();
  const sent = requests.find(r => r.url.endsWith('/submissions/') && r.options.method === 'POST');
  assert.equal(sent.options.body.get('summary'), 'Text delivery <img>');
  assert.equal(sent.options.body.has('artifact'), false);
  assert.equal(sent.options.headers['Content-Type'], undefined);
  assert.equal(sent.options.headers['X-CSRFToken'], 'fixture-csrf');
  assert.equal(get('booking-submission-form').hidden, true);
  assert.equal(get('booking-error').textContent, '');
  assert.equal(get('booking-submissions').children[0].children[0].textContent, 'Text delivery <img>');
});
