(() => {
  'use strict';
  const root = document.querySelector('[data-talent-rosters]');
  if (!root) return;
  const find = selector => root.querySelector(selector);
  const feedback = find('[data-feedback]');
  const workspace = find('[data-workspace]');
  const form = find('[data-create]');
  let working = false, generation = 0;
  const node = (tag, text, className = '') => { const el = document.createElement(tag); el.textContent = text; el.className = className; return el; };
  async function request(path, body) {
    const response = await fetch(path, { credentials: 'same-origin', headers: {
      'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value,
    }, ...(body ? { method: 'POST', body: JSON.stringify(body) } : {}) });
    let data;
    try { data = await response.json(); } catch { throw new Error('Unable to load rosters. Please try again.'); }
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data));
    return data;
  }
  async function all(path) {
    const rows = [];
    while (path) { const page = await request(path); rows.push(...page.results); path = page.next; }
    return rows;
  }
  async function mutate(path, body, onSuccess) {
    if (working) return;
    working = true; root.querySelectorAll('button, input, select').forEach(control => { control.disabled = true; });
    try { await request(path, body); onSuccess?.(); await load(); feedback.textContent = 'Roster updated.'; }
    catch (error) { await load(); feedback.textContent = error.message; }
    finally { working = false; root.querySelectorAll('button, input, select').forEach(control => { control.disabled = false; }); }
  }
  function render(container, rows) {
    container.replaceChildren();
    if (!rows.length) container.append(node('p', 'No talent tags yet.'));
    for (const row of rows) {
      const card = node('article', '', 'card p-3 my-3');
      card.append(node('h3', row.name), node('p', `${row.organization_name} · ${row.tag} · ${row.roster || 'General roster'} · ${row.status}`), node('p', row.talent_details));
      const agreements = node('a', 'View roster agreements'); agreements.href = `/organizations/agreements/?entry=${row.id}`; card.append(agreements);
      let username;
      if (row.actions.includes('LINK')) {
        const label = node('label', 'Link to Awinlink username'); username = node('input', ''); username.maxLength = 150; username.className = 'form-control'; label.append(username); card.append(label);
      }
      const reasonLabel = node('label', 'Reason (optional)'); const reason = node('input', ''); reason.maxLength = 500; reason.className = 'form-control'; reasonLabel.append(reason); if (row.actions.length) card.append(reasonLabel);
      for (const action of row.actions) {
        const button = node('button', { LINK: 'Request profile confirmation', CONFIRM: 'Confirm affiliation', DECLINE: 'Decline', REMOVE: 'Remove tag' }[action], 'btn btn-outline-primary m-1');
        button.type = 'button'; button.disabled = working;
        button.addEventListener('click', () => { if (action === 'REMOVE' && !window.confirm('Remove this tag? Its history will be retained.')) return;
          void mutate(`/api/organizations/talent-tags/${row.id}/`, { action, username: username?.value || '', reason: reason.value }); });
        card.append(button);
      }
      const history = node('button', 'View history', 'btn btn-light m-1'); history.type = 'button'; const events = node('div', '');
      history.addEventListener('click', async () => { try { const rows = await all(`/api/organizations/talent-tags/${row.id}/`); events.replaceChildren(...rows.map(event => node('p', `${event.action} · ${new Date(event.created_at).toLocaleString()}${event.reason ? ' · ' + event.reason : ''}`))); } catch (error) { feedback.textContent = error.message; } });
      card.append(history, events); container.append(card);
    }
  }
  async function load() {
    const current = ++generation, selected = workspace.value;
    find('[data-mine]').replaceChildren(); find('[data-roster]').replaceChildren();
    const [mineResult, spaceResult] = await Promise.allSettled([all('/api/organizations/talent-tags/mine/'), all('/api/organizations/roster-workspaces/')]);
    if (current !== generation) return;
    render(find('[data-mine]'), mineResult.status === 'fulfilled' ? mineResult.value : []);
    const spaces = spaceResult.status === 'fulfilled' ? spaceResult.value : [];
    const active = spaces.find(org => String(org.id) === selected);
    const placeholder = node('option', 'Choose an organization'); placeholder.value = '';
    workspace.replaceChildren(placeholder);
    for (const org of spaces) { const option = node('option', org.name); option.value = String(org.id); option.dataset.manage = String(org.can_manage); workspace.append(option); }
    workspace.value = active ? selected : '';
    form.hidden = !active?.can_manage;
    const failed = [mineResult, spaceResult].find(result => result.status === 'rejected');
    feedback.textContent = failed ? failed.reason.message : '';
    if (active) {
      try {
        const rows = await all(`/api/organizations/${active.id}/roster/`);
        if (current === generation) render(find('[data-roster]'), rows);
      } catch (error) { if (current === generation) { form.hidden = true; feedback.textContent = error.message; } }
    }
  }
  workspace.addEventListener('change', () => { form.reset(); form.hidden = true; void load().catch(error => { form.hidden = true; feedback.textContent = error.message; }); });
  find('[data-refresh]').addEventListener('click', () => { void load().catch(error => { feedback.textContent = error.message; }); });
  form.addEventListener('submit', event => { event.preventDefault(); if (!workspace.value) return; const data = Object.fromEntries(new FormData(form)); delete data.csrfmiddlewaretoken;
    void mutate(`/api/organizations/${workspace.value}/roster/`, data, () => form.reset()); });
  void load().catch(error => { feedback.textContent = error.message; });
})();
