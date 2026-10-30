const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const { pagination } = require('./pagination-helpers.cjs');
const flush = () => new Promise(setImmediate);

test('saved/followed state and rows remain usable when their directory or relationship page is unloaded', async () => {
  let user = { id: 1, role: 'SCOUT' }, stateIndex = 0, refIndex = 0;
  const states = [], refs = [], focuses = [], calls = [], routes = [];
  const react = {
    useState(initial) { const i = stateIndex++; if (!(i in states)) states[i] = typeof initial === 'function' ? initial() : initial;
      return [states[i], next => { states[i] = typeof next === 'function' ? next(states[i]) : next; }]; },
    useRef: initial => refs[refIndex++] ||= { current: initial }, useCallback: fn => fn, useMemo: fn => fn(),
  };
  const jsx = (type, props) => ({ type, props });
  const modules = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': { ActivityIndicator: 'ActivityIndicator', Image: 'Image', Pressable: 'Pressable', Text: 'Text', View: 'View', TextInput: 'TextInput', RefreshControl: 'RefreshControl', StyleSheet: { create: x => x } },
    'expo-router': { Redirect: 'Redirect', Stack: { Screen: 'Screen' }, useFocusEffect: fn => focuses.push(fn), useRouter: () => ({ push: path => routes.push(path) }) },
    '@/src/auth/AuthProvider': { useAuth: () => ({ user }) }, '@/src/pagination': pagination,
    '@/src/search-query': { useSearchPath: base => base }, '@/src/components/LoadMore': { LoadMore: 'LoadMore' },
    '@/src/components/Page': { Page: 'Page' }, '@/src/components/EmptyState': { EmptyState: 'EmptyState' }, '@/src/theme': { colors: {} },
    '@/src/api/client': { apiRequest: async (path, options) => {
      calls.push({ path, options });
      if (options) return {};
      if (path.endsWith('/bookmarks/')) return [{ id: 99, talent: 999, talent_name: 'Saved outside directory', notes: 'Private saved marker' }];
      if (path.endsWith('/following/')) return [{ id: 79, talent: 789, talent_name: 'Following outside directory' }];
      return [{ id: 10, user: { username: 'Directory talent' }, specialist_bookmark_id: 4, specialist_follow_id: 5 }];
    } },
  };
  function compile(path) {
    const exports = {};
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve(path), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    }).outputText, { exports, require: name => modules[name] });
    return exports;
  }
  modules['@/src/privacy-state'] = compile('../src/privacy-state.ts');
  const screen = compile('../app/specialist.tsx').default;
  const collect = node => Array.isArray(node) ? node.flatMap(collect) : node && typeof node === 'object' ? [node, ...collect(node.props?.children)] : [];
  function render() { stateIndex = refIndex = 0; return collect(screen()); }
  const text = node => typeof node === 'string' ? node : Array.isArray(node) ? node.map(text).join('') : node?.props ? text(node.props.children) : '';
  const button = label => render().find(n => n.type === 'Pressable' && text(n) === label);
  render(); focuses.at(-1)(); await flush();
  assert.ok(button('Following')); assert.ok(button('Remove saved'));
  assert.ok(JSON.stringify(render()).includes('Saved outside directory'));
  button('Saved outside directoryPrivate saved marker').props.onPress();
  assert.equal(routes[0].params.id, '999');
  button('Remove saved').props.onPress(); await flush();
  assert.ok(calls.some(call => call.path === 'scouts/bookmarks/4/delete/' && call.options.method === 'DELETE'));
  assert.ok(button('Save talent'));
  button('Following').props.onPress(); await flush();
  assert.ok(calls.some(call => call.path === 'scouts/talents/10/unfollow/' && call.options.method === 'DELETE'));
  user = { id: 2, role: 'SCOUT' };
  assert.ok(!JSON.stringify(render()).includes('Private saved marker'));
});
