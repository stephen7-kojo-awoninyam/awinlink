/* Actual mobile agreement client -> JWT HTTP -> isolated PostgreSQL. */
const fs = require('node:fs'); const vm = require('node:vm'); const path = require('node:path');
const assert = require('node:assert/strict'); const ts = require('../mobile/node_modules/typescript');
const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
assert.ok(['localhost', '127.0.0.1'].includes(new URL(fixture.origin).hostname));
async function request(user, route, body, method = 'POST') {
  const response = await fetch(fixture.origin + '/api/organizations/' + route, { headers: { Authorization: `Bearer ${fixture.tokens[user]}`, 'Content-Type': 'application/json' },
    ...(body ? { method, body: JSON.stringify(body) } : {}) });
  const data = await response.json(); if (!response.ok) throw Error(`${response.status}: ${JSON.stringify(data)}`); return data;
}
function client(user) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../mobile/src/organizations/agreements.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, require: () => ({ apiRequest: (url, options = {}) => request(user, url.replace(/^organizations\//, ''), options.body, options.method) }) });
  return module.exports;
}
(async () => {
  const origin = client('origin'), talent = client('talent'), destination = client('destination');
  let contract;
  for (const kind of ['CONTRACT', 'SPONSORSHIP', 'AMBASSADOR']) {
    let row = await request('origin', 'agreements/', { roster_entry_id: fixture.entry, kind, title: kind + ' mobile', terms: 'Exact mobile terms ✓', amount: '50.00', currency: 'GHS' });
    await assert.rejects(() => request('talent', `agreements/${row.id}/`), /404/);
    await assert.rejects(() => origin.agreementAction(row, { action: 'SUBMIT', party: 'ORIGIN' }, false, ''), /400/);
    row = await origin.agreementAction(row, { action: 'SUBMIT', party: 'ORIGIN' }, true, '');
    await assert.rejects(() => request('outsider', `agreements/${row.id}/`), /404/);
    if (kind === 'CONTRACT') {
      const old = row;
      row = await request('origin', `agreements/${row.id}/`, { expected_revision: row.revision, terms: 'Revised mobile terms' }, 'PATCH');
      row = await origin.agreementAction(row, { action: 'SUBMIT', party: 'ORIGIN' }, true, '');
      await assert.rejects(() => talent.agreementAction(old, { action: 'ACCEPT', party: 'TALENT' }, true, ''), /409/);
    }
    row = await talent.agreementAction(row, { action: 'ACCEPT', party: 'TALENT' }, true, ''); assert.equal(row.status, 'ACTIVE');
    if (kind === 'CONTRACT') contract = row;
  }
  contract = await talent.agreementAction(contract, { action: 'REQUEST_END', party: 'TALENT' }, true, 'Campaign completed');
  assert.equal(contract.status, 'ENDING'); assert.equal(contract.ending_reason, 'Campaign completed');
  contract = await origin.agreementAction(contract, { action: 'ACCEPT_END', party: 'ORIGIN' }, true, ''); assert.equal(contract.status, 'ENDED');
  let transfer = await request('origin', 'agreements/', { roster_entry_id: fixture.entry, kind: 'TRANSFER', title: 'Mobile transfer', terms: 'All three parties agree',
    destination_id: fixture.destination, destination_tag: 'Player', destination_roster: 'First team' });
  transfer = await origin.agreementAction(transfer, { action: 'SUBMIT', party: 'ORIGIN' }, true, '');
  transfer = await talent.agreementAction(transfer, { action: 'ACCEPT', party: 'TALENT' }, true, ''); assert.equal(transfer.status, 'PENDING');
  transfer = await destination.agreementAction(transfer, { action: 'ACCEPT', party: 'DESTINATION' }, true, ''); assert.equal(transfer.status, 'COMPLETED');
  const history = await request('talent', `agreements/${transfer.id}/history/`);
  assert.ok(history.results.some(e => e.action === 'TRANSFER_COMPLETED'));
  console.log(JSON.stringify({ passed: true, checks: ['all four types', 'explicit consent', 'JWT privacy', 'revision invalidation', 'mutual ending', 'three-party transfer', 'history'] }));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
