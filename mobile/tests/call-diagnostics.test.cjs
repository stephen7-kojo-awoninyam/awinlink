const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');

function diagnosticsModule() {
  const exports = {};
  const source = fs.readFileSync(require.resolve('../src/calls/callDiagnostics.ts'), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  new Function('exports', output)(exports);
  return exports;
}

test('mobile call diagnostic allowlist removes call IDs, peer IDs, addresses, and arbitrary fields', () => {
  const { safeCallDiagnostic } = diagnosticsModule();
  const row = safeCallDiagnostic('selected_ice_pair', {
    callId: 42, peerId: 99, localType: 'relay', remoteType: 'srflx',
    address: '192.0.2.4', credential: 'secret', packetsLost: 2,
  }, 1000);
  assert.deepEqual(row, { at: 1000, event: 'selected_ice_pair', localType: 'relay', remoteType: 'srflx', packetsLost: 2 });
  assert.equal(safeCallDiagnostic('unexpected', { callId: 42 }), null);
});

test('mobile call screen emits only sanitized diagnostics in development builds', () => {
  const source = fs.readFileSync(require.resolve('../src/calls/CallScreen.tsx'), 'utf8');
  assert.match(source, /if \(__DEV__\)\s*\{\s*const entry = safeCallDiagnostic\(event, detail\);\s*if \(entry\) console\.debug/);
  assert.doesNotMatch(source, /console\.info\('\[Awinlink call\]'/);
});
