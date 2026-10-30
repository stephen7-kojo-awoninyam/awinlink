const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { createRequire } = require('node:module');
const crypto = require('node:crypto');

function expoCliRequire() {
  const expoRequire = createRequire(require.resolve('expo/package.json'));
  return createRequire(expoRequire.resolve('@expo/cli/package.json'));
}

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

test('Expo CLI plugin and command schemas retain validation with patched Zod', () => {
  const cli = expoCliRequire();
  const { PluginSchema, DevToolsPluginOutputSchema } = cli('./build/src/start/server/DevToolsPlugin.schema.js');
  const { createMCPDevToolsExtensionSchema } = cli('./build/src/start/server/createMCPDevToolsExtensionSchema.js');
  const descriptor = {
    packageName: 'awinlink-local-test', packageRoot: '/fixture', bannerTitle: false,
    cliExtensions: { description: 'Local test', entryPoint: 'commands.js', commands: [{
      name: 'inspect', title: 'Inspect fixture', environments: ['cli', 'mcp'],
      parameters: [{ name: 'label', type: 'text' }, { name: 'count', type: 'number' }, { name: 'confirm', type: 'confirm' }],
    }] },
  };
  assert.equal(PluginSchema.safeParse(descriptor).success, true);
  assert.equal(PluginSchema.safeParse({ ...descriptor, packageName: '' }).success, false);
  const schema = createMCPDevToolsExtensionSchema(descriptor);
  const input = { command: 'inspect', label: 'Awinlink', count: 2, confirm: true };
  assert.deepEqual(schema.parse(input), input);
  for (const invalid of [{}, { command: 'other' }, { ...input, count: '2' }, { ...input, extra: true }]) {
    assert.equal(schema.safeParse(invalid).success, false);
  }
  const output = [{ type: 'text', text: 'ok', level: 'info' }, { type: 'audio', url: 'https://fixture.invalid/a.mp3' }];
  assert.deepEqual(DevToolsPluginOutputSchema.parse(output), output);
  assert.equal(DevToolsPluginOutputSchema.safeParse([{ type: 'audio', url: 'invalid' }]).success, false);
  assert.equal(cli('zod').toJSONSchema(schema).additionalProperties, false);
});

test('Expo CLI Zod rejects oversized constrained arrays without collecting per-item errors', () => {
  const { z } = expoCliRequire()('zod');
  const schema = z.array(z.number()).max(2);
  assert.deepEqual(schema.parse([1, 2]), [1, 2]);
  const result = schema.safeParse(Array(10000).fill('invalid'));
  assert.equal(result.success, false);
  assert.equal(result.error.issues.length, 1);
  assert.equal(result.error.issues[0].code, 'too_big');
});

test('Expo code signing retains valid RSA signatures and rejects nested DigestAlgorithm padding', () => {
  const certificates = require('@expo/code-signing-certificates');
  const forge = createRequire(require.resolve('@expo/code-signing-certificates'))('node-forge');
  // Ephemeral fixture keys only: exercise the low-exponent advisory case without
  // reading app credentials, writing keys, or weakening signature verification.
  const pem = crypto.generateKeyPairSync('rsa', {
    modulusLength: 2048, publicExponent: 3,
    publicKeyEncoding: { type: 'spki', format: 'pem' },
    privateKeyEncoding: { type: 'pkcs1', format: 'pem' },
  });
  const pair = certificates.convertKeyPairPEMToKeyPair({ privateKeyPEM: pem.privateKey, publicKeyPEM: pem.publicKey });
  const certificate = certificates.generateSelfSignedCodeSigningCertificate({
    keyPair: pair, validityNotBefore: new Date(Date.now() - 60000),
    validityNotAfter: new Date(Date.now() + 86400000), commonName: 'Awinlink dependency fixture',
  });
  certificates.validateSelfSignedCertificate(certificate, pair);
  const payload = Buffer.from('local synthetic manifest');
  const signature = certificates.signBufferRSASHA256AndVerify(pair.privateKey, certificate, payload);
  assert.equal(crypto.verify('sha256', payload, pem.publicKey, Buffer.from(signature, 'base64')), true);
  assert.equal(crypto.verify('sha256', Buffer.from('changed manifest'), pem.publicKey, Buffer.from(signature, 'base64')), false);

  const { asn1 } = forge;
  const node = (type, constructed, value) => asn1.create(asn1.Class.UNIVERSAL, type, constructed, value);
  const digest = forge.md.sha256.create().update(payload.toString('binary')).digest().getBytes();
  const algorithm = [node(asn1.Type.OID, false, asn1.oidToDer(forge.oids.sha256).getBytes()), node(asn1.Type.NULL, false, '')];
  const malformed = node(asn1.Type.SEQUENCE, true, [
    node(asn1.Type.SEQUENCE, true, [...algorithm, node(asn1.Type.NULL, false, '')]),
    node(asn1.Type.OCTETSTRING, false, digest),
  ]);
  const malformedSignature = pair.privateKey.sign(asn1.toDer(malformed).getBytes(), 'NONE');
  let accepted = false;
  try { accepted = pair.publicKey.verify(digest, malformedSignature); } catch (_) { /* rejection is expected */ }
  assert.equal(accepted, false, 'noncanonical nested algorithm elements must never verify');
});
