const { test } = require('node:test');
const assert = require('node:assert/strict');
const { assertLegalPageReady } = require('../scripts/legal-page-check.cjs');

test('legal preflight rejects reachable draft policies even when operator details are complete', () => {
  for (const body of ['Awinlink Draft for legal review.', '<body data-legal-status="draft">Awinlink</body>', "<body data-legal-status='draft'>Awinlink</body>"]) {
    assert.throws(() => assertLegalPageReady(body), /drafts/);
  }
});

test('legal preflight rejects missing identities and incomplete contacts', () => {
  for (const body of ['Awinlink Release information is awaiting completion', 'Awinlink A monitored privacy contact has not yet been configured.',
    'Awinlink A public support email has not yet been configured.']) {
    assert.throws(() => assertLegalPageReady(body), /incomplete/);
  }
  assert.throws(() => assertLegalPageReady('Unrelated page'), /identify Awinlink/);
  assert.doesNotThrow(() => assertLegalPageReady('Awinlink policy with completed details'));
});
