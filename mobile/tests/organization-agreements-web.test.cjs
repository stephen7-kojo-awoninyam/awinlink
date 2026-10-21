const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'); const path = require('node:path'); const vm = require('node:vm');
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise(setImmediate); };
class Element {
  constructor(tag = '') { this.tag = tag; this.children = []; this.listeners = {}; this.dataset = {}; this.elements = {}; this.value = ''; this.textContent = ''; }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(event, fn) { this.listeners[event] = fn; }
  querySelector(key) { return this.elements[key]; }
  get firstChild() { return this.children[0]; }
  querySelectorAll(selector) { const all = []; const walk = n => { all.push(n); n.children.forEach(walk); }; Object.values(this.elements).forEach(walk); return all.filter(n => selector === '[data-agreement-id]' ? n.dataset.agreementId : ['button', 'input', 'textarea', 'select'].includes(n.tag)); }
  reset() { this.resetCount = (this.resetCount || 0) + 1; }
  set innerHTML(value) { throw Error('Unsafe markup: ' + value); }
}
test('web drafts require a separate explicit submission and never render terms as markup', async () => {
  const root = new Element(), form = new Element('form'), list = new Element(), calls = []; let current = null, choiceFailure = false;
  root.elements = { '[data-agreement-create]': form, '[data-agreement-feedback]': new Element(), '[data-agreement-list]': list, '[data-transfer-fields]': new Element(), '[data-agreement-refresh]': new Element('button') };
  for (const name of ['roster_entry_id', 'kind', 'title', 'terms', 'starts_on', 'ends_on', 'amount', 'currency', 'destination_id', 'destination_tag', 'destination_roster', 'csrfmiddlewaretoken']) form.elements[name] = new Element(name.includes('_id') || name === 'kind' ? 'select' : 'input');
  form.elements.kind.value = 'CONTRACT'; form.elements.currency.value = 'GHS'; form.elements.csrfmiddlewaretoken.value = 'fixture-csrf';
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../../static/js/organization-agreements.js'), 'utf8'), {
    document: { querySelector: () => root, createElement: tag => new Element(tag) }, location: { search: '' }, URLSearchParams,
    FormData: class extends Map { constructor(f) { super(Object.entries(f.elements).map(([key, value]) => [key, value.value])); } },
    fetch: async (url, options) => {
      calls.push({ url, options }); let data;
      if (url.includes('roster-choices')) { if (choiceFailure) return { ok: false, json: async () => ({ detail: 'Permission changed' }) }; data = { results: [{ id: 5, organization_id: 1, organization_name: 'Academy', name: 'Talent', tag: 'Player' }], next: null }; }
      else if (url.includes('destinations')) data = { results: [{ id: 2, name: 'Destination' }], next: null };
      else if (options.method === 'POST') {
        const body = JSON.parse(options.body);
        if (body.action) { assert.equal(body.consent, true); assert.equal(body.expected_revision, 1); current.status = 'PENDING'; current.actions = [{ action: 'WITHDRAW', party: 'ORIGIN' }]; }
        else current = { ...body, id: 7, status: 'DRAFT', revision: 1, end_round: 0, organization_name: 'Academy', talent_name: 'Talent', roster_snapshot: { roster: 'First team', tag: 'Player' }, consents: [], actions: [{ action: 'SUBMIT', party: 'ORIGIN' }], can_revise: true };
        data = current;
      } else data = { results: current ? [current] : [], next: null };
      return { ok: true, json: async () => data };
    },
  });
  await flush(); form.elements.roster_entry_id.value = '5'; form.elements.title.value = 'Private contract'; form.elements.terms.value = '<img src=x onerror=alert(1)> Exact terms';
  form.listeners.submit({ preventDefault() {} }); await flush();
  const posts = () => calls.filter(c => c.options.method === 'POST');
  assert.equal(posts().length, 1); assert.equal(JSON.parse(posts()[0].options.body).consent, undefined);
  assert.equal(posts()[0].options.headers['X-CSRFToken'], 'fixture-csrf'); assert.equal(posts()[0].options.credentials, 'same-origin');
  const card = list.children[0], submit = card.children.find(n => n.dataset.action === 'SUBMIT');
  assert.equal(submit.disabled, true); assert.equal(card.children.find(n => n.tag === 'pre').textContent, form.elements.terms.value);
  const label = card.children.find(n => n.className === 'agreement-consent'); label.children[0].checked = true; label.children[0].listeners.change();
  assert.equal(submit.disabled, false); submit.listeners.click(); await flush(); assert.equal(posts().length, 2); assert.equal(current.status, 'PENDING');
  choiceFailure = true; root.elements['[data-agreement-refresh]'].listeners.click(); await flush();
  assert.equal(form.hidden, true); assert.equal(list.children[0].children[0].textContent, 'Private contract');
});
