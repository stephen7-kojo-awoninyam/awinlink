const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const item = title => ({ id: 8, title, description: 'Portfolio details', item_type: 'PROJECT', image: '/media/portfolio/images/work.png', created_at: '2026-10-27', link: '' });

function screen(personal = false) {
  let user = { id: 1, role: 'ATHLETE' }, route = '4', stateIndex = 0, refIndex = 0, cleanup;
  let reply = [], profileDenied = false;
  const states = [], refs = [], focuses = [], requests = [];
  const react = {
    useState(initial) { const slot = stateIndex++; if (!(slot in states)) states[slot] = typeof initial === 'function' ? initial() : initial;
      return [states[slot], next => { states[slot] = typeof next === 'function' ? next(states[slot]) : next; }]; },
    useRef: initial => refs[refIndex++] ||= { current: initial },
    useCallback: fn => fn, useEffect() {},
  };
  const apiRequest = async url => {
    requests.push({ url, userId: user?.id });
    if (url.startsWith('portfolio/')) {
      if (reply instanceof Error) throw reply;
      return reply;
    }
    if (url.startsWith('talents/')) {
      if (profileDenied) throw new Error('Profile unavailable');
      return { id: Number(url.split('/')[1]), user: { id: 100, username: 'Portfolio owner marker' } };
    }
    return [];
  };
  const jsx = (type, props) => ({ type, props });
  const privacy = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/privacy-state.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, { exports: privacy, require: name => name === 'react' ? react : require('./pagination-helpers.cjs').pagination });
  const exports = {};
  const path = personal ? '../app/portfolio.tsx' : '../app/talent/[id].tsx';
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve(path), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, require: name => ({
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    '@/src/privacy-state': privacy,
    '@/src/components/LoadMore': { LoadMore: 'LoadMore' },
    'react-native': { Text: 'Text', Image: 'Image', View: 'View', Pressable: 'Pressable', StyleSheet: { create: value => value } },
    'expo-router': { Redirect: 'Redirect', Stack: { Screen: 'Screen' }, useFocusEffect: fn => focuses.push(fn),
      useLocalSearchParams: () => ({ id: route }), useRouter: () => ({ push() {} }) },
    '@/src/api/client': { apiRequest }, '@/src/auth/AuthProvider': { useAuth: () => ({ user }) },
    '@/src/components/Page': { Page: 'Page', ui: {} }, '@/src/components/EmptyState': { EmptyState: 'EmptyState' },
    '@/src/components/SafetyActions': { SafetyActions: 'SafetyActions' },
    '@/src/components/AuthorizedImage': { AuthorizedImage: 'AuthorizedImage' },
    '@/src/organizations/Badges': { OrganizationBadges: 'OrganizationBadges' }, '@/src/theme': { colors: {} },
  })[name] });
  function render() { stateIndex = 0; refIndex = 0; return exports.default(); }
  render();
  return {
    text: () => JSON.stringify(render()), requests,
    reply(value) { reply = value; }, denyProfile(value = true) { profileDenied = value; },
    account(value) { user = value; render(); }, route(value) { route = value; render(); },
    focus() { cleanup?.(); cleanup = focuses.at(-1)(); }, blur() { cleanup?.(); },
  };
}

test('own portfolio renders an authorized response and clears it after access denial', async () => {
  const view = screen(true); view.reply([item('Owner private work')]); view.focus(); await flush();
  assert.ok(view.text().includes('Owner private work'));
  view.reply(new Error('Forbidden')); view.focus(); await flush();
  assert.ok(!view.text().includes('Owner private work'));
  assert.ok(view.text().includes('Portfolio unavailable'));
});

test('switching accounts hides private work before another request completes', async () => {
  const view = screen(true); view.reply([item('Account one secret')]); view.focus(); await flush();
  assert.ok(view.text().includes('Account one secret'));
  view.account({ id: 2, role: 'ATHLETE' });
  assert.ok(!view.text().includes('Account one secret'));
  view.reply([item('Account two work')]); view.focus(); await flush();
  assert.ok(view.text().includes('Account two work'));
});

test('switching away and back requires fresh authorization for profile and personal portfolio', async () => {
  for (const personal of [true, false]) {
    const view = screen(personal); view.reply([item('Previous identity secret')]); view.focus(); await flush();
    assert.ok(view.text().includes('Previous identity secret'));
    view.account({ id: 2, role: 'ATHLETE' }); view.account({ id: 1, role: 'ATHLETE' });
    assert.ok(!view.text().includes('Previous identity secret'));
  }
});

test('late responses from before an account round trip cannot restore profile or portfolio data', async () => {
  for (const personal of [true, false]) {
    const view = screen(personal), pending = deferred(); view.reply(pending.promise); view.focus();
    view.account({ id: 2, role: 'ATHLETE' }); view.account({ id: 1, role: 'ATHLETE' });
    pending.resolve([item('Late identity secret')]); await flush();
    assert.ok(!view.text().includes('Late identity secret'));
    assert.ok(!view.text().includes('Portfolio owner marker'));
  }
});

test('an old own-portfolio response cannot cross accounts or restore data after blur', async () => {
  for (const change of ['account', 'blur']) {
    const view = screen(true), pending = deferred(); view.reply(pending.promise); view.focus();
    if (change === 'account') view.account({ id: 2, role: 'ATHLETE' }); else view.blur();
    pending.resolve([item('Late private work')]); await flush();
    assert.ok(!view.text().includes('Late private work'));
  }
});

test('changing from a talent role removes portfolio management and ignores its pending data', async () => {
  const view = screen(true), pending = deferred(); view.reply(pending.promise); view.focus();
  view.account({ id: 1, role: 'SCOUT' });
  pending.resolve([item('Old talent work')]); await flush();
  assert.ok(view.text().includes('Redirect'));
  assert.ok(!view.text().includes('Old talent work'));
});

test('denied profile or portfolio responses clear the entire profile display', async () => {
  for (const denied of ['profile', 'portfolio']) {
    const view = screen(); view.reply([item('Sensitive portfolio work')]); view.focus(); await flush();
    assert.ok(view.text().includes('Sensitive portfolio work'));
    if (denied === 'profile') view.denyProfile(); else view.reply(new Error('Not found'));
    view.focus(); await flush();
    assert.ok(!view.text().includes('Sensitive portfolio work'));
    assert.ok(!view.text().includes('Portfolio owner marker'));
    assert.ok(view.text().includes('Profile unavailable'));
  }
});

test('an earlier profile load cannot restore private content after a newer denial', async () => {
  const view = screen(), pending = deferred(); view.reply(pending.promise); view.focus();
  view.reply(new Error('No access')); view.focus(); await flush();
  pending.resolve([item('Older authorized work')]); await flush();
  assert.ok(!view.text().includes('Older authorized work'));
  assert.ok(view.text().includes('Profile unavailable'));
});

test('same-profile responses from a previous account cannot repopulate portfolio data', async () => {
  const view = screen(), pending = deferred(); view.reply(pending.promise); view.focus();
  view.account({ id: 2, role: 'ATHLETE' });
  pending.resolve([item('Previous account private work')]); await flush();
  assert.ok(!view.text().includes('Previous account private work'));
  view.reply(new Error('No permission')); view.focus(); await flush();
  assert.ok(view.text().includes('Profile unavailable'));
});

test('profile navigation cannot reuse the previous talent portfolio while loading', async () => {
  const view = screen(); view.reply([item('Talent four work')]); view.focus(); await flush();
  assert.ok(view.text().includes('Talent four work'));
  view.route('5');
  assert.ok(!view.text().includes('Talent four work'));
  view.reply([item('Talent five work')]); view.focus(); await flush();
  assert.ok(view.text().includes('Talent five work'));
});
