const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise(setImmediate); };

class Element {
  constructor(tag = '') { this.tag = tag; this.children = []; this.listeners = {}; this.dataset = {}; this.value = ''; this.textContent = ''; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(event, fn) { this.listeners[event] = fn; }
  reset() { this.resetCount = (this.resetCount || 0) + 1; }
  querySelector(selector) { return this.elements[selector]; }
  querySelectorAll() { const nodes = []; const walk = node => { if (node.tag === 'button') nodes.push(node); node.children?.forEach(walk); }; Object.values(this.elements).forEach(walk); return nodes; }
  set innerHTML(value) { throw Error('Unsafe markup rendering: ' + value); }
}

test('web roster supports unclaimed creation, profile linking, confirmation and retained history with CSRF', async () => {
  const root = new Element(), calls = [];
  const selectors = ['[data-feedback]', '[data-workspace]', '[data-create]', '[data-mine]', '[data-roster]', '[data-refresh]'];
  root.elements = Object.fromEntries(selectors.map(key => [key, new Element()]));
  const form = root.elements['[data-create]'], workspace = root.elements['[data-workspace]'];
  form.elements = { '[name=csrfmiddlewaretoken]': { value: 'test-csrf' } };
  form.fields = { name: '<img src=x onerror=alert(1)>', tag: 'Player', roster: 'First team', username: '', csrfmiddlewaretoken: 'test-csrf' };
  let entry = { id: 9, name: 'Unclaimed <img>', organization_name: 'Academy', tag: 'Player', roster: 'First team', status: 'UNCLAIMED', actions: ['LINK', 'REMOVE'], talent_details: '' };
  const events = [];
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../../static/js/organization-rosters.js'), 'utf8'), {
    document: { querySelector: () => root, createElement: tag => new Element(tag) },
    FormData: class extends Map { constructor(form) { super(Object.entries(form.fields)); } }, window: { confirm: () => true },
    fetch: async (url, options) => {
      calls.push({ url, options }); let data;
      if (options.method === 'POST') {
        const body = JSON.parse(options.body);
        if (body.action === 'LINK') { assert.equal(body.username, 'talent'); entry.status = 'PENDING'; entry.actions = ['CONFIRM', 'DECLINE', 'REMOVE']; }
        if (body.action === 'CONFIRM') { entry.status = 'CONFIRMED'; entry.actions = ['REMOVE']; }
        if (body.action === 'REMOVE') { entry.status = 'REMOVED'; entry.actions = []; }
        events.push({ id: events.length + 1, action: body.action || 'CREATED', reason: body.reason || '', created_at: '2026-10-21T12:00:00Z' }); data = entry;
      } else if (url.includes('workspaces')) data = { results: [{ id: 7, name: 'Academy', can_manage: true }], next: null };
      else if (url === '/api/organizations/talent-tags/9/') data = { results: events, next: null };
      else data = { results: url.includes('mine') ? [] : [entry], next: null };
      return { ok: true, json: async () => data };
    },
  });
  await flush(); workspace.value = '7'; workspace.selectedOptions = [workspace.children[0]];
  workspace.listeners.change(); await flush(); assert.equal(form.hidden, false);
  form.listeners.submit({ preventDefault() {} }); await flush();
  const created = calls.find(c => c.options.method === 'POST');
  assert.equal(created.options.headers['X-CSRFToken'], 'test-csrf'); assert.equal(created.options.credentials, 'same-origin');
  assert.equal(JSON.parse(created.options.body).username, ''); assert.equal(JSON.parse(created.options.body).csrfmiddlewaretoken, undefined);
  const card = () => root.elements['[data-roster]'].children[0];
  const button = label => card().children.find(n => n.tag === 'button' && n.textContent === label);
  card().children.find(n => n.tag === 'label' && n.textContent.includes('username')).children[0].value = 'talent';
  button('Request profile confirmation').listeners.click(); await flush(); assert.equal(entry.status, 'PENDING');
  button('Confirm affiliation').listeners.click(); await flush(); assert.equal(entry.status, 'CONFIRMED');
  button('Remove tag').listeners.click(); await flush(); assert.equal(entry.status, 'REMOVED');
  await button('View history').listeners.click();
  assert.ok(card().children.at(-1).children.some(n => n.textContent.includes('CONFIRM')));
  assert.ok(card().children.at(-1).children.some(n => n.textContent.includes('REMOVE')));
});

test('web refresh rechecks permissions and preserves personal tags when organization access fails', async () => {
  const root = new Element(); let revoked = false;
  root.elements = Object.fromEntries(['[data-feedback]', '[data-workspace]', '[data-create]', '[data-mine]', '[data-roster]', '[data-refresh]'].map(key => [key, new Element()]));
  const form = root.elements['[data-create]'], workspace = root.elements['[data-workspace]'];
  form.elements = { '[name=csrfmiddlewaretoken]': { value: 'test-csrf' } };
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../../static/js/organization-rosters.js'), 'utf8'), {
    document: { querySelector: () => root, createElement: tag => new Element(tag) }, window: { confirm: () => true },
    fetch: async url => {
      if (url.includes('/7/roster/')) return { ok: false, json: async () => ({ detail: 'Roster access denied' }) };
      const results = url.includes('workspaces') ? (revoked ? [] : [{ id: 7, name: 'Academy', can_manage: true }]) : [{ id: 9, name: 'Personal request', tag: 'Member', status: 'PENDING', actions: ['CONFIRM'], organization_name: 'Academy' }];
      return { ok: true, json: async () => ({ results, next: null }) };
    },
  });
  await flush(); workspace.value = '7'; workspace.listeners.change(); await flush();
  assert.equal(form.resetCount, 1);
  assert.equal(form.hidden, true);
  assert.equal(root.elements['[data-mine]'].children[0].children[0].textContent, 'Personal request');
  assert.equal(root.elements['[data-feedback]'].textContent, 'Roster access denied');
  revoked = true; root.elements['[data-refresh]'].listeners.click(); await flush();
  assert.equal(workspace.value, ''); assert.equal(workspace.children.length, 1);
  assert.equal(root.elements['[data-mine]'].children[0].children[0].textContent, 'Personal request');
  assert.equal(root.elements['[data-roster]'].children.length, 0);
});
