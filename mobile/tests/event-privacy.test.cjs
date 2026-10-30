const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(value => { resolve = value; }); return { promise, resolve }; };
const event = { id: 7, title: 'Sensitive event marker', description: 'Event description', status: 'PUBLISHED' };

function screen(management = false) {
  let user = { id: 1, role: 'ORGANIZATION' }, index = 0, refIndex = 0, cleanup;
  const states = [], refs = [], focuses = [], replies = new Map();
  const react = {
    useState(initial) { const slot = index++; if (!(slot in states)) states[slot] = typeof initial === 'function' ? initial() : initial;
      return [states[slot], next => { states[slot] = typeof next === 'function' ? next(states[slot]) : next; }]; },
    useRef(initial) { return refs[refIndex++] ||= { current: initial }; },
    useCallback: value => value, useMemo: value => value(),
  };
  const jsx = (type, props) => ({ type, props });
  const apiRequest = async url => {
    if (replies.has(url)) { const value = replies.get(url); if (value instanceof Error) throw value; return value; }
    if (url === 'organizations/me/') return { id: 3 };
    if (url === 'events/categories/') return [{ id: 1, name: 'Category' }];
    if (url === 'events/' || url === 'events/my/') return [event];
    if (url === 'events/registrations/') return [{ id: 9, event: 7, event_title: event.title, talent_name: 'Participant marker', status: 'REGISTERED' }];
    if (url === 'events/7/') return event;
    if (url === 'events/7/media/') return [{ id: 6, media_type: 'IMAGE', file: '/media/events/gallery/private.png', caption: 'Private media marker' }];
    if (url === 'events/7/feedback/list/') return [{ id: 8, rating: 5, comment: 'Private feedback marker', reviewer_name: 'Reviewer' }];
    return [];
  };
  function compile(file, modules) {
    const exports = {};
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve(file), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    }).outputText, { exports, FormData, require: name => modules[name] });
    return exports;
  }
  const pagination = require('./pagination-helpers.cjs').pagination;
  const hook = compile('../src/privacy-state.ts', { react, '@/src/pagination': pagination });
  const modules = {
    '@/src/search-query': { useSearchPath: base => base },
    '@/src/components/LoadMore': { LoadMore: 'LoadMore' },
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': { Text: 'Text', Image: 'Image', View: 'View', Pressable: 'Pressable', TextInput: 'TextInput',
      ActivityIndicator: 'ActivityIndicator', RefreshControl: 'RefreshControl', Platform: { OS: 'ios' }, StyleSheet: { create: value => value } },
    'expo-router': { Redirect: 'Redirect', Stack: { Screen: 'Screen' }, useFocusEffect: fn => focuses.push(fn), useRouter: () => ({ push() {} }) },
    'expo-document-picker': {}, '@/src/api/client': { apiRequest }, '@/src/auth/AuthProvider': { useAuth: () => ({ user }) },
    '@/src/privacy-state': hook, '@/src/components/EmptyState': { EmptyState: 'EmptyState' },
    '@/src/components/Page': { Page: 'Page' }, '@/src/components/AuthorizedImage': { AuthorizedImage: 'AuthorizedImage' },
    '@/src/components/MediaPlayer': { VideoPlayer: 'VideoPlayer' }, '@/src/theme': { colors: {} },
  };
  const module = compile(management ? '../app/event-management.tsx' : '../src/components/DirectoryScreen.tsx', modules);
  function render() { index = 0; refIndex = 0; return management ? module.default() : module.DirectoryScreen({ kind: 'events' }); }
  render();
  return {
    text: () => JSON.stringify(render()),
    account(value) { user = value; render(); }, reply(url, value) { replies.set(url, value); },
    focus() { cleanup?.(); render(); cleanup = focuses.at(-1)(); }, blur() { cleanup?.(); },
    press(label) {
      const nodes = [];
      function text(value) {
        if (typeof value === 'string') return value;
        if (Array.isArray(value)) return value.map(text).join('');
        return value && typeof value === 'object' ? text(value.props?.children) : '';
      }
      function walk(value) {
        if (Array.isArray(value)) { value.forEach(walk); return; }
        if (!value || typeof value !== 'object') return;
        if (value.type === 'Pressable' && text(value).includes(label)) nodes.push(value);
        walk(value.props?.children);
      }
      walk(render()); assert.ok(nodes.length, label); nodes[0].props.onPress();
    },
  };
}

test('event management clears drafts and participants when a permission refresh is denied', async () => {
  const view = screen(true); view.focus(); await flush();
  assert.ok(view.text().includes(event.title)); assert.ok(view.text().includes('Participant marker'));
  view.reply('events/my/', new Error('Permission revoked')); view.focus(); await flush();
  assert.ok(!view.text().includes(event.title)); assert.ok(!view.text().includes('Participant marker'));
});

test('selecting an older event retrieves its own registration beyond the loaded registration page', async () => {
  const view = screen(); view.account({ id: 1, role: 'ATHLETE' });
  view.reply('events/my-registrations/', [{ id: 1, event: 900, status: 'REGISTERED' }]);
  view.reply('events/my-registrations/?event=7', [{ id: 99, event: 7, status: 'REGISTERED' }]);
  view.focus(); await flush(); view.press(event.title); await flush();
  assert.ok(view.text().includes('You are registered.'));
  assert.ok(view.text().includes('Cancel registration'));
});

test('management account switches hide previous data immediately and reject late responses', async () => {
  const view = screen(true); view.focus(); await flush(); assert.ok(view.text().includes(event.title));
  const pending = deferred(); view.reply('events/my/', pending.promise); view.focus();
  view.account({ id: 2, role: 'ORGANIZATION' }); assert.ok(!view.text().includes(event.title));
  pending.resolve([event]); await flush(); assert.ok(!view.text().includes(event.title));
});

test('an earlier successful management request cannot restore data after a newer denial', async () => {
  const view = screen(true), pending = deferred(); view.reply('events/my/', pending.promise); view.focus();
  view.reply('events/my/', new Error('Revoked')); view.focus(); await flush();
  pending.resolve([event]); await flush(); assert.ok(!view.text().includes(event.title));
});

test('switching away and back cannot revive a previous account snapshot before reauthorization', async () => {
  const view = screen(true); view.focus(); await flush(); assert.ok(view.text().includes(event.title));
  view.account({ id: 2, role: 'ATHLETE' });
  view.account({ id: 1, role: 'ORGANIZATION' });
  assert.ok(!view.text().includes(event.title)); assert.ok(!view.text().includes('Participant marker'));
});

test('responses from before an account round trip cannot restore event-management records', async () => {
  const view = screen(true), pending = deferred(); view.reply('events/my/', pending.promise); view.focus();
  view.account({ id: 2, role: 'ATHLETE' }); view.account({ id: 1, role: 'ORGANIZATION' });
  pending.resolve([event]); await flush(); assert.ok(!view.text().includes(event.title));
});

test('event media and feedback are cleared on a denied child response', async () => {
  const view = screen(); view.focus(); await flush(); view.press(event.title); await flush();
  assert.ok(view.text().includes('Private media marker')); assert.ok(view.text().includes('Private feedback marker'));
  assert.ok(view.text().includes('AuthorizedImage'));
  view.press('Back to events'); view.reply('events/7/media/', new Error('Not found'));
  view.press(event.title); await flush();
  assert.ok(!view.text().includes('Private media marker')); assert.ok(!view.text().includes('Private feedback marker'));
  assert.ok(!view.text().includes(event.title));
});

test('a previous account cannot repopulate event details or gallery after switching', async () => {
  const view = screen(), pending = deferred(); view.focus(); await flush();
  view.reply('events/7/media/', pending.promise); view.press(event.title);
  view.account({ id: 2, role: 'ATHLETE' }); assert.ok(!view.text().includes(event.title));
  pending.resolve([{ id: 1, caption: 'Late private marker', media_type: 'IMAGE', file: '/media/events/gallery/private.png' }]);
  await flush(); assert.ok(!view.text().includes('Late private marker')); assert.ok(!view.text().includes(event.title));
});

test('closing event details invalidates pending gallery responses', async () => {
  const view = screen(), pending = deferred(); view.focus(); await flush();
  view.reply('events/7/media/', pending.promise); view.press(event.title); view.press('Back to events');
  pending.resolve([{ id: 1, caption: 'Late private marker' }]); await flush();
  assert.ok(!view.text().includes('Late private marker'));
});
