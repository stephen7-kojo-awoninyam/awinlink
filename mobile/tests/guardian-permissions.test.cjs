const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));

function screen({ progressDenied = false } = {}) {
  const states = [], requests = [];
  let index = 0, changed = 0;
  const jsx = (type, props) => ({ type, props });
  const imports = {
    react: { useState(initial) {
      const slot = index++;
      if (!(slot in states)) states[slot] = initial;
      return [states[slot], value => { states[slot] = typeof value === 'function' ? value(states[slot]) : value; }];
    } },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    'react-native': { Pressable: 'Button', Text: 'Text', TextInput: 'Input', View: 'View' },
    '@/src/components/Page': { ui: {} },
    '@/src/pagination': { nextPage: () => null },
    '@/src/api/client': { apiRequest: async (path, options) => {
      requests.push({ path, options });
      if (path.endsWith('courses/')) return [{ id: 42, title: 'Robotics', minimum_age: 0 }];
      if (path.endsWith('learning/')) {
        if (progressDenied) throw new Error('Guardian authorization withdrawn.');
        return [{ course_id: 42, title: 'Robotics', completed_lessons: 2, lesson_count: 5, completed: false }];
      }
      return {};
    } },
  };
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/components/GuardianPermissions.tsx'), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, Error, require(name) { if (!(name in imports)) throw new Error(name); return imports[name]; } });
  const item = { id: 7, contacts: [{ username: 'coach', allow_calls: true }], courses: [{ course_id: 41, title: 'Music', allow_live: true }] };
  const nodes = node => node && typeof node === 'object' ? [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)] : [];
  const render = () => { index = 0; return nodes(exports.GuardianPermissions({ item, onChanged: async () => { changed++; } })); };
  const button = label => render().find(node => node.type === 'Button' && node.props.children?.props?.children === label);
  return { render, button, requests, changed: () => changed };
}

test('guardian contact approval defaults to messages only and submits explicit call permission', async () => {
  const view = screen();
  view.render().find(node => node.type === 'Input').props.onChangeText('new-coach');
  assert.equal(view.render().find(node => node.props?.accessibilityRole === 'checkbox').props.accessibilityState.checked, false);
  view.button('Approve contact').props.onPress(); await flush();
  assert.equal(view.requests[0].path, 'auth/guardians/7/');
  assert.equal(view.requests[0].options.body.action, 'allow_contact');
  assert.equal(view.requests[0].options.body.allow_calls, false);
  assert.equal(view.changed(), 1);
  view.render().find(node => node.type === 'Input').props.onChangeText('new-coach');
  view.render().find(node => node.props?.accessibilityRole === 'checkbox').props.onPress();
  view.button('Approve contact').props.onPress(); await flush();
  assert.equal(view.requests[1].options.body.allow_calls, true);
});

test('course approval uses the guardian-scoped catalogue and live participation is an explicit opt-in', async () => {
  const view = screen();
  view.button('Choose a course to approve').props.onPress(); await flush();
  assert.equal(view.requests[0].path, 'auth/guardians/7/courses/');
  const courseButton = view.render().find(node => node.type === 'Button' && Array.isArray(node.props.children?.props?.children) && node.props.children.props.children.includes('Robotics'));
  assert.ok(courseButton);
  courseButton.props.onPress(); await flush();
  assert.equal(view.requests[1].options.body.action, 'allow_course');
  assert.equal(view.requests[1].options.body.course_id, 42);
  assert.equal(view.requests[1].options.body.allow_live, false);
});

test('withdrawal sends only the chosen resource and denied progress exposes no learning record', async () => {
  const view = screen({ progressDenied: true });
  view.button('Withdraw contact permission').props.onPress(); await flush();
  assert.equal(view.requests[0].options.body.action, 'remove_contact');
  assert.equal(view.requests[0].options.body.username, 'coach');
  view.button('Withdraw learning permission').props.onPress(); await flush();
  assert.equal(view.requests[1].options.body.action, 'remove_course');
  assert.equal(view.requests[1].options.body.course_id, 41);
  view.button('View learning progress').props.onPress(); await flush();
  assert.ok(view.render().find(node => node.props?.accessibilityRole === 'alert' && node.props.children === 'Guardian authorization withdrawn.'));
  assert.equal(view.render().filter(node => String(node.props?.children).includes('2/5')).length, 0);
});
