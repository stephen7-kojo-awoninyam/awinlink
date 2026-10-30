const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function compile(path, modules = {}) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve(path), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, { exports, URL, require: name => modules[name] });
  return exports;
}
const pagination = compile('../src/pagination.ts');
const pagedState = react => compile('../src/paged-state.ts', { react, '@/src/pagination': pagination });
module.exports = { pagination, pagedState };
