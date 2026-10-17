const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

test('query-string uses iterative patched decoder and preserves route parameters', () => {
  const query = require('query-string');
  const decoderPath = require.resolve('decode-uri-component', { paths: [require.resolve('query-string')] });
  const decode = require(decoderPath);
  assert.match(decoderPath.replaceAll('\\', '/'), /decode-uri-component-cjs/);
  for (const [input, expected] of [['hello+world', 'hello world'], ['%E2%9C%93', '✓'], ['%41%FE%42', 'A%FEB'], ['%C2', '�'], ['%FE%FF', '��'], ['%G1', '%G1']]) assert.equal(decode(input), expected);
  const parsed = query.parse('title=hello+world&token=abc%2Bdef&name=%E2%9C%93');
  assert.equal(parsed.title, 'hello world'); assert.equal(parsed.token, 'abc+def'); assert.equal(parsed.name, '✓');
  const long = '%FE'.repeat(5000) + '%41';
  const start = performance.now();
  assert.equal(query.parse(`bad=${long}`).bad, '%FE'.repeat(5000) + 'A');
  assert.ok(performance.now() - start < 2000, 'malformed route input must not trigger recursive/exponential decoding');
});

test('Xcode generator remains compatible with patched CommonJS UUID', () => {
  const xcode = require('xcode');
  const uuidPath = require.resolve('uuid', { paths: [require.resolve('xcode')] });
  const uuid = require(uuidPath);
  assert.equal(typeof uuid.v4, 'function');
  const project = xcode.project(path.join(__dirname, 'not-written.pbxproj'));
  project.hash = { project: { objects: {} } };
  const ids = new Set(Array.from({ length: 100 }, () => project.generateUuid()));
  assert.equal(ids.size, 100);
  for (const id of ids) assert.match(id, /^[A-F0-9]{24}$/);
});

test('EAS validates and resolves Android/iOS profiles with patched schema dependencies', async () => {
  const { EasJsonAccessor, EasJsonUtils } = require('@expo/eas-json');
  const accessor = EasJsonAccessor.fromProjectPath(path.resolve(__dirname, '..'));
  const raw = await accessor.readAsync();
  assert.equal(raw.submit, undefined);
  for (const platform of ['android', 'ios']) {
    const production = await EasJsonUtils.getBuildProfileAsync(accessor, platform, 'production');
    assert.equal(production.distribution, 'store');
    assert.equal(production.credentialsSource, 'remote');
    const device = await EasJsonUtils.getBuildProfileAsync(accessor, platform, 'preview-device');
    assert.equal(device.distribution, 'internal');
    if (platform === 'ios') assert.equal(device.simulator, false);
    else assert.equal(device.buildType, 'apk');
  }
});

test('EAS command discovery retains the modern minimatch API required by oclif', () => {
  const core = require.resolve('@oclif/core', { paths: [require.resolve('eas-cli/package.json')] });
  const minimatch = require(require.resolve('minimatch', { paths: [core] }));
  assert.equal(typeof minimatch.minimatch, 'function');
  assert.equal(minimatch.minimatch('build/android', 'build/**'), true);
});
