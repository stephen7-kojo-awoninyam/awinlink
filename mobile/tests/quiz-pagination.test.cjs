const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const { pagination } = require('./pagination-helpers.cjs');
const flush = () => new Promise(setImmediate);

test('quiz submission waits for every question page and retains earlier answers', async () => {
  const states = [], refs = [], callbacks = [], effects = [];
  let stateIndex = 0, refIndex = 0, callbackIndex = 0, effectIndex = 0;
  const queued = [], requests = [];
  const react = {
    useState(initial) { const i = stateIndex++; if (!(i in states)) states[i] = typeof initial === 'function' ? initial() : initial;
      return [states[i], next => { states[i] = typeof next === 'function' ? next(states[i]) : next; }]; },
    useRef: initial => refs[refIndex++] ||= { current: initial },
    useCallback(fn, deps) { const i = callbackIndex++; if (!callbacks[i] || deps.some((v, j) => callbacks[i].deps[j] !== v)) callbacks[i] = { fn, deps }; return callbacks[i].fn; },
    useEffect(fn, deps) { const i = effectIndex++; if (!effects[i] || deps.some((v, j) => effects[i][j] !== v)) { effects[i] = deps; queued.push(fn); } },
  };
  const question = id => ({ id, question: `Question ${id}`, option_a: 'Yes', option_b: 'No', option_c: 'Maybe', option_d: 'Other' });
  const jsx = (type, props) => ({ type, props });
  const modules = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': { ActivityIndicator: 'ActivityIndicator', Pressable: 'Pressable', Text: 'Text', View: 'View', StyleSheet: { create: x => x } },
    'expo-router': { Stack: { Screen: 'Screen' }, useLocalSearchParams: () => ({ id: '1' }) },
    '@/src/pagination': pagination, '@/src/auth/AuthProvider': { useAuth: () => ({ user: { id: 7 } }) },
    '@/src/components/LoadMore': { LoadMore: 'LoadMore' }, '@/src/components/EmptyState': { EmptyState: 'EmptyState' },
    '@/src/components/Page': { Page: 'Page' }, '@/src/theme': { colors: {} },
    '@/src/api/client': { apiRequest: async (url, options) => {
      requests.push({ url, options });
      if (options) return { score: 2, total_questions: 2, percentage: 100, passed: true };
      if (url.includes('questions')) return pagination.withNextPage([question(1)], 'learning/questions/?cursor=next');
      return { id: 9, title: 'Complete quiz', question_count: 2, passing_score: 70 };
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
  const screen = compile('../app/learning/quiz/[id].tsx').default;
  const collect = node => Array.isArray(node) ? node.flatMap(collect) : node && typeof node === 'object' ? [node, ...collect(node.props?.children)] : [];
  function render() { stateIndex = refIndex = callbackIndex = effectIndex = 0; const nodes = collect(screen()); while (queued.length) queued.shift()(); return nodes; }
  render(); await flush();
  let nodes = render();
  nodes.find(n => n.props.accessibilityRole === 'radio').props.onPress();
  nodes = render();
  let submit = nodes.find(n => n.type === 'Pressable' && JSON.stringify(n.props.children).includes('Submit answers'));
  assert.equal(submit.props.disabled, true); submit.props.onPress(); await flush();
  assert.equal(requests.filter(r => r.options?.method === 'POST').length, 0);
  nodes.find(n => n.type === 'LoadMore').props.onChange(rows => pagination.mergePage(rows, pagination.withNextPage([question(2)], null)));
  nodes = render(); nodes.filter(n => n.props.accessibilityRole === 'radio')[4].props.onPress();
  nodes = render(); submit = nodes.find(n => n.type === 'Pressable' && JSON.stringify(n.props.children).includes('Submit answers'));
  assert.equal(submit.props.disabled, false); submit.props.onPress(); await flush();
  const sent = requests.find(r => r.options?.method === 'POST');
  assert.equal(JSON.stringify(sent.options.body.answers), '{"1":"A","2":"A"}');
});
