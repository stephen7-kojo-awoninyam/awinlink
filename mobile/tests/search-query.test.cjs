const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

test('directory searches encode filters, debounce requests and never reuse another endpoint', () => {
  let state, previous, cleanup, nextId = 0;
  const timers = new Map();
  const react = {
    useState(initial) { state ??= initial; return [state, value => { state = value; }]; },
    useEffect(fn, deps) { if (!previous || deps[0] !== previous[0]) { cleanup?.(); previous = deps; cleanup = fn(); } },
  };
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/search-query.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, { exports, require: () => react,
    setTimeout: (fn, delay) => { assert.equal(delay, 250); timers.set(++nextId, fn); return nextId; },
    clearTimeout: id => timers.delete(id),
  });
  assert.equal(exports.searchPath('talents/', ' @Jane & Doe '), 'talents/?search=Jane%20%26%20Doe');
  assert.equal(exports.useSearchPath('talents/', ''), 'talents/');
  assert.equal(exports.useSearchPath('talents/', 'J'), 'talents/');
  assert.equal(exports.useSearchPath('talents/', 'Jane'), 'talents/');
  assert.equal(timers.size, 1, 'Replaced keystrokes cancel the older request timer');
  [...timers.values()][0]();
  assert.equal(exports.useSearchPath('talents/', 'Jane'), 'talents/?search=Jane');
  assert.equal(exports.useSearchPath('scouts/talents/', 'Jane'), 'scouts/talents/');
  cleanup(); assert.equal(timers.size, 0);
});
