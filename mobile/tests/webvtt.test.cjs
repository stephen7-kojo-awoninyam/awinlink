const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/webvtt.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const moduleExports = {};
vm.runInNewContext(compiled, { exports: moduleExports });

test('WebVTT parser returns timed readable cues and strips presentation markup', () => {
  const cues = moduleExports.parseWebVtt('WEBVTT\n\n00:00:01.250 --> 00:00:03.000\n<b>Hello</b> learner\n');
  assert.deepEqual(JSON.parse(JSON.stringify(cues)), [{ start: 1.25, end: 3, text: 'Hello learner' }]);
});

test('WebVTT parser rejects malformed headers and cues', () => {
  assert.throws(() => moduleExports.parseWebVtt('<html>'), /Invalid WebVTT/);
  assert.throws(() => moduleExports.parseWebVtt('WEBVTT\n\n00:02.000 --> 00:01.000\nBackwards'), /Invalid caption cue/);
});
