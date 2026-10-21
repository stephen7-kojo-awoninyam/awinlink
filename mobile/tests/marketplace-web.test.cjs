const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const vm = require('node:vm');

test('web room paginates history and reflects participant and final decision permissions', async () => {
  class Element {
    constructor() { this.children = []; this.hidden = false; this.elements = {}; this.parentElement = { hidden: false }; }
    append(value) { this.children.push(value); }
    prepend(value) { this.children.unshift(...value.children); }
    replaceChildren(...values) { this.children = values; }
    add(value) { this.append(value); }
    reset() { this.elements.body.value = ''; }
  }
  const ids = ['notice', 'results', 'room', 'terms', 'messages', 'message', 'accept-consent',
    'older-messages', 'room-policy', 'browse', 'mine', 'deals', 'next', 'search', 'listing', 'offer'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  for (const form of ['listing', 'search']) for (const name of ['ecosystem', 'subecosystem']) elements[form].elements[name] = new Element();
  elements.message.elements.body = { value: 'Hello <img src=x>' };
  const actions = ['ACCEPT', 'DECLINE', 'WITHDRAW'].map(action => Object.assign(new Element(), { dataset: { action } }));
  const calls = [];
  let accepted = false;
  const source = readFileSync(resolve(__dirname, '../../templates/marketplace/market.html'), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
  vm.runInNewContext(source, {
    document: { cookie: 'csrftoken=fixture-csrf', getElementById: id => elements[id],
      createElement: () => new Element(), createDocumentFragment: () => new Element(), querySelectorAll: () => actions },
    Option: class { constructor(text, value) { this.text = text; this.value = value; } },
    URLSearchParams, FormData,
    fetch: async (url, options) => {
      const body = options.body ? JSON.parse(options.body) : undefined;
      calls.push({ url, options, body });
      let data;
      if (url.endsWith('markets/')) data = { ecosystems: [], subecosystems: [] };
      else if (url.includes('listings/')) data = { results: [], next: null };
      else if (url.endsWith('offers/')) data = { results: [{ id: 7, status: 'PENDING' }] };
      else if (url.includes('messages/?before=51')) data = { messages: [{ id: 1, author: 2, body: 'Oldest <img src=x>' }], next_before: null };
      else if (body?.action) { accepted = true; data = {}; }
      else data = { offer: { id: 7, terms: 'Exact terms', status: accepted ? 'ACCEPTED' : 'PENDING' },
        messages: [{ id: 51, author: 1, body: 'Latest' }], next_before: 51,
        permissions: { can_message: !accepted, can_accept: !accepted, can_decline: !accepted, can_withdraw: false } };
      return { ok: true, json: async () => data };
    },
  });
  const flush = async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); };
  await flush(); await elements.deals.onclick();
  await elements.results.children[0].onclick();
  assert.equal(elements.message.hidden, false);
  assert.equal(actions[2].hidden, true);
  await elements['older-messages'].onclick();
  assert.equal(elements.messages.children[0].textContent, '2: Oldest <img src=x>');
  assert.equal(elements.messages.children[1].textContent, '1: Latest');
  assert.equal(elements['older-messages'].hidden, true);
  await elements.message.onsubmit();
  assert.ok(calls.some(x => x.body?.body === 'Hello <img src=x>'));
  assert.equal(elements.messages.children.at(-1).textContent, '1: Latest');
  elements['accept-consent'].checked = true;
  await actions[0].onclick();
  assert.equal(elements.message.hidden, true);
  assert.equal(elements['accept-consent'].parentElement.hidden, true);
  assert.ok(actions.every(x => x.hidden));
  assert.match(elements['room-policy'].textContent, /read-only/);
  assert.ok(calls.some(x => x.body?.action === 'ACCEPT' && x.body.consent));
  assert.ok(calls.every(x => x.options.headers['X-CSRFToken'] === 'fixture-csrf'));
});
