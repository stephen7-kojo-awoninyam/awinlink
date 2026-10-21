(() => {
  'use strict';
  const root = document.querySelector('[data-agreements]'); if (!root) return;
  const form = root.querySelector('[data-agreement-create]'), feedback = root.querySelector('[data-agreement-feedback]');
  const base = '/api/organizations/agreements/'; let busy = false, generation = 0, choices = [], destinations = [];
  const entry = new URLSearchParams(location.search).get('entry');
  const consentActions = new Set(['SUBMIT', 'ACCEPT', 'REQUEST_END', 'ACCEPT_END']);
  const reasonActions = new Set(['DECLINE', 'WITHDRAW', 'REQUEST_END', 'DECLINE_END']);
  const labels = { SUBMIT: 'Submit and consent', ACCEPT: 'Accept terms', DECLINE: 'Decline', WITHDRAW: 'Withdraw', REQUEST_END: 'Request mutual ending', ACCEPT_END: 'Agree to end', DECLINE_END: 'Keep agreement active' };
  const node = (tag, text = '') => { const el = document.createElement(tag); el.textContent = text; return el; };
  async function request(path, body, method = 'POST') {
    const response = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json',
      'X-CSRFToken': form.elements.csrfmiddlewaretoken.value }, ...(body ? { method, body: JSON.stringify(body) } : {}) });
    let data; try { data = await response.json(); } catch { throw Error('Unable to load agreements. Please try again.'); }
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data));
    return data;
  }
  async function all(path) { const rows = []; while (path) { const result = await request(path); rows.push(...result.results); path = result.next; } return rows; }
  const lock = value => { busy = value; root.querySelectorAll('button, input, select, textarea').forEach(el => { el.disabled = value; }); };
  async function mutate(path, body, method, done) {
    if (busy) return; lock(true);
    try { await request(path, body, method); done?.(); await load(); feedback.textContent = 'Agreement updated.'; }
    catch (error) { await load(); feedback.textContent = error.message; }
    finally { lock(false); root.querySelectorAll('[data-agreement-id]').forEach(card => card.updateActions?.()); }
  }
  function termsData(f, transfer) {
    const values = Object.fromEntries(new FormData(f));
    return { title: values.title, terms: values.terms, starts_on: values.starts_on || null, ends_on: values.ends_on || null,
      amount: values.amount === '' ? null : values.amount, currency: values.currency.toUpperCase(),
      destination_tag: transfer ? values.destination_tag : '', destination_roster: transfer ? values.destination_roster : '' };
  }
  function transferFields() {
    const transfer = form.elements.kind.value === 'TRANSFER'; root.querySelector('[data-transfer-fields]').hidden = !transfer;
    form.elements.destination_id.required = transfer; form.elements.destination_tag.required = transfer;
    const selected = form.elements.destination_id.value;
    const origin = choices.find(c => String(c.id) === form.elements.roster_entry_id.value)?.organization_id;
    form.elements.destination_id.replaceChildren(node('option', 'Choose an organization'));
    form.elements.destination_id.firstChild.value = '';
    for (const org of destinations.filter(org => org.id !== origin)) { const option = node('option', org.name); option.value = String(org.id); form.elements.destination_id.append(option); }
    if (destinations.some(org => String(org.id) === selected && org.id !== origin)) form.elements.destination_id.value = selected;
  }
  function editor(row, card) {
    const edit = node('form'); edit.hidden = true;
    for (const key of ['title', 'terms', 'starts_on', 'ends_on', 'amount', 'currency', ...(row.kind === 'TRANSFER' ? ['destination_tag', 'destination_roster'] : [])]) {
      const label = node('label', key.replaceAll('_', ' ')); const input = node(key === 'terms' ? 'textarea' : 'input');
      input.name = key; input.value = row[key] ?? ''; if (key === 'title' || key === 'terms' || key === 'currency') input.required = true;
      input.maxLength = { title: 200, terms: 20000, currency: 3, destination_tag: 80, destination_roster: 100 }[key] || 100;
      if (key.endsWith('_on')) input.type = 'date'; if (key === 'amount') { input.type = 'number'; input.min = '0'; input.step = '.01'; }
      label.append(input); edit.append(label);
    }
    const save = node('button', 'Save revised draft'); save.type = 'submit'; edit.append(save);
    edit.addEventListener('submit', event => { event.preventDefault(); void mutate(base + row.id + '/', { ...termsData(edit, row.kind === 'TRANSFER'), expected_revision: row.revision }, 'PATCH'); });
    const toggle = node('button', 'Revise terms (requires fresh consent)'); toggle.type = 'button';
    toggle.addEventListener('click', () => { edit.hidden = !edit.hidden; }); card.append(toggle, edit);
  }
  function render(rows) {
    const container = root.querySelector('[data-agreement-list]'); container.replaceChildren();
    if (!rows.length) container.append(node('p', 'No agreements available to you yet.'));
    for (const row of rows) {
      const card = node('article'); card.dataset.agreementId = row.id;
      card.append(node('h3', row.title), node('p', `${row.kind} · ${row.status} · Revision ${row.revision}`),
        node('p', `${row.talent_name} · ${row.organization_name}${row.destination_name ? ' → ' + row.destination_name : ''}`),
        node('p', `Roster: ${row.roster_snapshot.roster || 'General'} · ${row.roster_snapshot.tag}`));
      const terms = node('pre', row.terms); terms.className = 'agreement-terms'; card.append(terms);
      if (row.ending_reason) card.append(node('p', `Ending requested: ${row.ending_reason}`));
      if (row.amount !== null) card.append(node('p', `Agreed value: ${row.amount} ${row.currency} · No collection`));
      if (row.starts_on || row.ends_on) card.append(node('p', `${row.starts_on || 'No start date'} — ${row.ends_on || 'No end date'}`));
      if (row.kind === 'TRANSFER') card.append(node('p', `Destination: ${row.destination_tag} · ${row.destination_roster || 'General roster'}`));
      const current = row.consents.filter(c => c.revision === row.revision && (c.purpose === 'ACTIVATE' || c.round === row.end_round));
      for (const c of current) card.append(node('p', `${c.actor_name} · ${c.party} consented to ${c.purpose === 'END' ? 'ending' : 'these terms'}`));
      const check = node('input'); check.type = 'checkbox'; const label = node('label', `I agree to the displayed terms (revision ${row.revision}) and the action selected below.`);
      label.className = 'agreement-consent'; label.prepend(check);
      if (row.actions.some(a => consentActions.has(a.action))) card.append(label);
      const reason = node('input'); reason.maxLength = 1000; const reasonLabel = node('label', 'Decision reason'); reasonLabel.append(reason);
      if (row.actions.length) card.append(reasonLabel);
      const buttons = [];
      for (const action of row.actions) {
        const partyName = action.party === 'TALENT' ? 'talent' : action.party === 'ORIGIN' ? row.organization_name : row.destination_name;
        const button = node('button', `${labels[action.action]} — ${partyName}`); button.type = 'button'; button.dataset.action = action.action; button.dataset.party = action.party;
        button.addEventListener('click', () => { void mutate(base + row.id + '/', { ...action, expected_revision: row.revision, expected_end_round: row.end_round, consent: check.checked, reason: reason.value }); });
        card.append(button); buttons.push({ button, action: action.action });
      }
      card.updateActions = () => { for (const item of buttons) item.button.disabled = busy || (consentActions.has(item.action) && !check.checked) || (reasonActions.has(item.action) && !reason.value.trim()); };
      check.addEventListener('change', card.updateActions); reason.addEventListener('input', card.updateActions); card.updateActions();
      if (row.can_revise) editor(row, card);
      const history = node('div'); history.className = 'agreement-history'; const button = node('button', 'View agreement history'); button.type = 'button';
      button.addEventListener('click', async () => { try { const events = await all(base + row.id + '/history/'); history.replaceChildren(...events.map(e => { const item = node('div'); item.append(node('p', `${e.action} · ${e.actor_name} · revision ${e.revision} · ${new Date(e.created_at).toLocaleString()}${e.reason ? ' · ' + e.reason : ''}`)); if (e.snapshot.terms) { const oldTerms = node('pre', e.snapshot.terms); oldTerms.className = 'agreement-terms'; item.append(oldTerms); } return item; })); } catch (error) { feedback.textContent = error.message; } });
      card.append(button, history); container.append(card);
    }
  }
  async function load() {
    const current = ++generation;
    const results = await Promise.allSettled([all(base + (entry && /^\d+$/.test(entry) ? '?entry=' + entry : '')), all(base + 'roster-choices/'), all(base + 'destinations/')]);
    if (current !== generation) return;
    render(results[0].status === 'fulfilled' ? results[0].value : []);
    choices = results[1].status === 'fulfilled' ? results[1].value : []; destinations = results[2].status === 'fulfilled' ? results[2].value : [];
    const selected = form.elements.roster_entry_id.value || entry;
    form.elements.roster_entry_id.replaceChildren(node('option', 'Choose a confirmed affiliation')); form.elements.roster_entry_id.firstChild.value = '';
    for (const choice of choices) { const option = node('option', `${choice.organization_name} · ${choice.name} · ${choice.tag} · ${choice.roster || 'General'}`); option.value = String(choice.id); form.elements.roster_entry_id.append(option); }
    if (choices.some(c => String(c.id) === selected)) form.elements.roster_entry_id.value = selected;
    form.hidden = !choices.length; transferFields();
    const failed = results.find(r => r.status === 'rejected'); feedback.textContent = failed ? failed.reason.message : '';
  }
  form.elements.kind.addEventListener('change', transferFields);
  form.elements.roster_entry_id.addEventListener('change', () => { const selected = form.elements.roster_entry_id.value; form.reset(); form.elements.roster_entry_id.value = selected; transferFields(); });
  form.addEventListener('submit', event => { event.preventDefault(); const transfer = form.elements.kind.value === 'TRANSFER';
    void mutate(base, { ...termsData(form, transfer), kind: form.elements.kind.value, roster_entry_id: Number(form.elements.roster_entry_id.value), destination_id: transfer ? Number(form.elements.destination_id.value) : null }, 'POST', () => form.reset()); });
  root.querySelector('[data-agreement-refresh]').addEventListener('click', () => { void load().catch(e => { feedback.textContent = e.message; }); });
  void load().catch(error => { feedback.textContent = error.message; });
})();
