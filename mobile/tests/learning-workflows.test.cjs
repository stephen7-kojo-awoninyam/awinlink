const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const { pagination } = require('./pagination-helpers.cjs');
const flush = () => new Promise(setImmediate);
class ApiError extends Error { constructor(status, message = 'Request failed') { super(message); this.status = status; } }
const lesson = id => ({ id, title: `Lesson ${id}`, description: '', notes: null, video: null, order: id, duration: 1 });
const course = { id: 1, creator: 99, title: 'Course', description: 'Description', category_name: 'Sport', level: 'BEGINNER', duration: 2, is_free: true, lesson_count: 2, status: 'DRAFT', category: 1 };
const progress = { completed: false, progress_percentage: 0, completed_lessons: 0, total_lessons: 2, completed_lesson_ids: [] };

// Render the real screen and hooks. Requests are deterministic and never use a service.
function fixture(screenPath, request) {
  const slots = [], pending = [], requests = [], routes = [];
  let cursor = 0, user = { id: 7, role: 'SCOUT' }, routeId = '1';
  const changed = (old, deps) => !old || deps.some((v, i) => old.deps[i] !== v);
  const react = {
    useState(initial) { const i = cursor++; if (!slots[i]) slots[i] = { value: typeof initial === 'function' ? initial() : initial };
      return [slots[i].value, next => { slots[i].value = typeof next === 'function' ? next(slots[i].value) : next; }]; },
    useRef(initial) { const i = cursor++; return slots[i] ||= { current: initial }; },
    useCallback(fn, deps) { const i = cursor++; if (changed(slots[i], deps)) slots[i] = { fn, deps }; return slots[i].fn; },
    useEffect(fn, deps) { const i = cursor++; if (changed(slots[i], deps)) { const old = slots[i]; slots[i] = { fn, deps }; pending.push(() => { old?.cleanup?.(); slots[i].cleanup = fn(); }); } },
  };
  const jsx = (type, props) => ({ type, props });
  const modules = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': Object.fromEntries(['ActivityIndicator', 'Image', 'Pressable', 'RefreshControl', 'Text', 'TextInput', 'View', 'ScrollView'].map(x => [x, x])),
    'expo-router': { Stack: { Screen: 'Screen' }, Redirect: 'Redirect', useRouter: () => ({ push: route => routes.push(route), replace: route => routes.push(route) }), useLocalSearchParams: () => ({ id: routeId }),
      useFocusEffect: fn => react.useEffect(fn, [fn]) },
    'expo-document-picker': {}, '@/src/pagination': pagination,
    '@/src/auth/AuthProvider': { useAuth: () => ({ user }) }, '@/src/components/LoadMore': { LoadMore: 'LoadMore' },
    '@/src/components/EmptyState': { EmptyState: 'EmptyState' }, '@/src/components/Page': { Page: 'Page' },
    '@/src/components/MediaPlayer': { VideoPlayer: 'VideoPlayer' }, '@/src/media-download': { downloadMedia: async () => {} },
    '@/src/course-category': { courseCategoryDefault: () => 1 }, '@/src/theme': { colors: {} },
    '@/src/api/client': { ApiError, apiRequest: async (url, options) => { requests.push({ url, options }); return request(url, options); } },
  };
  modules['react-native'].StyleSheet = { create: x => x }; modules['react-native'].Platform = { OS: 'android' };
  function compile(path) {
    const exports = {};
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve(path), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    }).outputText, { exports, Error, FormData, require: name => {
      if (!(name in modules)) throw new Error(`Unmocked module ${name}`); return modules[name];
    } }); return exports;
  }
  modules['@/src/privacy-state'] = compile('../src/privacy-state.ts');
  modules['@/src/paged-state'] = compile('../src/paged-state.ts');
  modules['@/src/learning-theme'] = compile('../src/learning-theme.ts');
  const screen = compile(screenPath).default;
  const collect = node => Array.isArray(node) ? node.flatMap(collect) : node && typeof node === 'object' ? [node, ...collect(node.props?.children)] : [];
  let nodes;
  function render() { cursor = 0; nodes = collect(screen()); while (pending.length) pending.shift()(); return nodes; }
  return { requests, routes, render,
    async settle() { for (let i = 0; i < 5; i++) { render(); await flush(); } return render(); },
    text() { return JSON.stringify(nodes); },
    find(type, text) { return nodes.find(n => n.type === type && JSON.stringify(n.props.children)?.includes(text)); },
    nodes(type) { return nodes.filter(n => n.type === type); },
    refocus() { for (const slot of slots) if (slot?.cleanup) { slot.cleanup(); slot.cleanup = slot.fn(); } },
    setUser(next) { user = next; }, setId(next) { routeId = next; },
  };
}
function courseRequest(overrides = {}) {
  return async (url, options) => {
    if (overrides.request) { const value = overrides.request(url, options); if (value !== undefined) return value; }
    if (url === 'learning/courses/1/') return overrides.course || course;
    if (url.endsWith('/lessons/')) return overrides.lessons || [lesson(1)];
    if (url.endsWith('/modules/')) return overrides.modules || [];
    if (url.includes('/live-sessions/')) return overrides.sessions || { results: [], next: null };
    if (url.endsWith('/progress/')) return overrides.progress === null ? Promise.reject(new ApiError(404)) : progress;
    if (url.endsWith('/reviews/')) return [];
    if (url.endsWith('/quiz/')) return { id: 9, question_count: 1 };
    throw new Error(`Unexpected URL ${url}`);
  };
}

test('quiz availability covers appended lesson pages and preserves the continuation', async () => {
  const f = fixture('../app/learning/[id].tsx', courseRequest({ lessons: pagination.withNextPage([lesson(1)], 'next-lessons') }));
  await f.settle();
  assert.equal(f.nodes('Pressable').filter(n => JSON.stringify(n.props.children).includes('Open quiz')).length, 1);
  const more = f.nodes('LoadMore').find(n => n.props.label === 'Load more lessons');
  assert.equal(pagination.nextPage(more.props.items), 'next-lessons');
  more.props.onChange(rows => pagination.mergePage(rows, pagination.withNextPage([lesson(2)], null)));
  await f.settle();
  assert.equal(f.nodes('Pressable').filter(n => JSON.stringify(n.props.children).includes('Open quiz')).length, 2);
  assert.ok(f.requests.some(r => r.url === 'learning/lessons/2/quiz/'));
  assert.equal(pagination.nextPage(f.nodes('LoadMore')[0].props.items), null);
});

test('quiz errors are unknown, 404 is absent, and refresh retries failed checks', async () => {
  let failed = true;
  const f = fixture('../app/learning/[id].tsx', courseRequest({ lessons: [lesson(1), lesson(2)], request: url => {
    if (url === 'learning/lessons/1/quiz/' && failed) return Promise.reject(new ApiError(503));
    if (url === 'learning/lessons/2/quiz/') return Promise.reject(new ApiError(404));
  } }));
  await f.settle(); assert.match(f.text(), /could not be checked/); assert.match(f.text(), /No quiz for this lesson/);
  failed = false; f.nodes('Page')[0].props.refreshControl.props.onRefresh(); await f.settle();
  assert.ok(f.find('Pressable', 'Open quiz')); assert.doesNotMatch(f.text(), /could not be checked/);
});

test('returning from quiz refreshes server progress and exposes certificate navigation', async () => {
  let completed = false;
  const f = fixture('../app/learning/[id].tsx', courseRequest({ request: url => url.endsWith('/progress/') ? { ...progress, completed, completed_lesson_ids: completed ? [1] : [] } : undefined }));
  await f.settle(); assert.ok(f.find('Pressable', 'Mark lesson complete'));
  completed = true; f.refocus(); await f.settle();
  assert.ok(f.find('Pressable', 'Completed'));
  f.find('Pressable', 'View certificates').props.onPress(); assert.equal(f.routes[0], '/learning/results');
});

test('partial completion error refreshes durable progress and offers certificate retry', async () => {
  let saved = false, fail = true;
  const f = fixture('../app/learning/[id].tsx', courseRequest({ request: (url, options) => {
    if (options?.method === 'POST') { saved = true; if (fail) return Promise.reject(new ApiError(503, 'Progress saved; certificate PDF is temporarily unavailable. Retry completion to generate it.')); return {}; }
    if (url.endsWith('/progress/')) return { ...progress, completed: saved, completed_lesson_ids: saved ? [1] : [] };
  } }));
  await f.settle(); f.find('Pressable', 'Mark lesson complete').props.onPress(); await f.settle();
  assert.match(f.text(), /Progress saved; certificate PDF/);
  assert.equal(f.find('Pressable', 'Completed').props.disabled, true);
  fail = false; f.find('Pressable', 'Retry certificate generation').props.onPress(); await f.settle();
  assert.equal(f.requests.filter(r => r.options?.method === 'POST').length, 2);
  assert.doesNotMatch(f.text(), /temporarily unavailable/);
});

test('legacy completed lessons can retry finalization after passing the remaining quiz', async () => {
  let finalized = false;
  const f = fixture('../app/learning/[id].tsx', courseRequest({ request: (url, options) => {
    if (options?.method === 'POST') { finalized = true; return {}; }
    if (url.endsWith('/progress/')) return { ...progress, total_lessons: 1, completed_lessons: 1, completed_lesson_ids: [1], completed: finalized };
  } }));
  await f.settle();
  assert.equal(f.find('Pressable', 'Completed').props.disabled, true);
  f.find('Pressable', 'Refresh course completion').props.onPress(); await f.settle();
  assert.ok(f.find('Pressable', 'Retry certificate generation'));
  assert.equal(f.requests.filter(r => r.options?.method === 'POST').length, 1);
});

test('locked paid previews suppress asset controls; free previews open the focused player route', async () => {
  const asset = { ...lesson(1), video: 'https://media.test/video', notes: 'https://media.test/notes' };
  const locked = fixture('../app/learning/[id].tsx', courseRequest({ course: { ...course, is_free: false }, progress: null, lessons: [{ ...asset, is_locked: true }] }));
  await locked.settle(); assert.match(locked.text(), /Locked lesson preview/);
  assert.equal(locked.nodes('VideoPlayer').length, 0); assert.equal(locked.find('Pressable', 'Open lesson notes'), undefined);
  assert.equal(locked.find('Pressable', 'Paid enrollment unavailable').props.disabled, true);
  assert.equal(locked.requests.some(r => r.url.endsWith('/quiz/')), false);
  const free = fixture('../app/learning/[id].tsx', courseRequest({ progress: null, lessons: [asset] }));
  await free.settle(); assert.equal(free.nodes('VideoPlayer').length, 0); assert.ok(free.find('Pressable', 'Open lesson workspace'));
});

test('review outage leaves lessons usable and denied refresh removes stale media', async () => {
  let denied = false;
  const f = fixture('../app/learning/[id].tsx', courseRequest({ lessons: [{ ...lesson(1), video: 'https://media.test/video' }], request: url => {
    if (url.endsWith('/reviews/')) return Promise.reject(new ApiError(503));
    if (url === 'learning/courses/1/' && denied) return Promise.reject(new ApiError(404));
  } }));
  await f.settle(); assert.equal(f.nodes('VideoPlayer').length, 0); assert.ok(f.find('Pressable', 'Open lesson workspace'));
  assert.match(f.text(), /Unable to load course reviews/);
  denied = true; f.refocus(); await f.settle();
  assert.equal(f.nodes('VideoPlayer').length, 0); assert.equal(f.nodes('EmptyState')[0].props.title, 'Course unavailable');
});

test('late course responses cannot populate a different account or route', async () => {
  let resolve;
  const delayed = new Promise(r => { resolve = r; });
  const f = fixture('../app/learning/[id].tsx', url => url === 'learning/courses/1/' ? delayed : Promise.reject(new ApiError(404)));
  f.render(); await flush(); f.setUser({ id: 8, role: 'ATHLETE' }); f.setId('2'); await f.settle();
  resolve({ ...course, title: 'Private old course' }); await f.settle();
  assert.doesNotMatch(f.text(), /Private old course/); assert.equal(f.nodes('VideoPlayer').length, 0);
});

test('results load independently, explain missing PDFs, refresh, and route retry to course', async () => {
  let attemptsFail = true;
  const f = fixture('../app/learning/results.tsx', async url => {
    if (url.endsWith('my-certificates/')) return [{ id: 1, certificate_id: 'stable-id', course_id: 1, course_title: 'Course', issued_at: '2026-10-28', pdf: null }];
    if (attemptsFail) throw new ApiError(503);
    return [{ id: 1, quiz_title: 'Final quiz', passed: true, percentage: 100 }];
  });
  await f.settle(); assert.match(f.text(), /PDF generation is pending/); assert.match(f.text(), /could not be loaded/);
  f.find('Pressable', 'Return to course').props.onPress(); assert.equal(f.routes[0].params.id, '1');
  attemptsFail = false; f.refocus(); await f.settle(); assert.match(f.text(), /Final quiz/); assert.doesNotMatch(f.text(), /could not be loaded/);
});

test('SCOUT studio omits client order even with a partial lesson page', async () => {
  const f = fixture('../app/learning/studio.tsx', async (url, options) => {
    if (url.endsWith('/categories/')) return [{ id: 1, name: 'Sport' }];
    if (url.endsWith('/courses/me/')) return [course];
    if (url.endsWith('/modules/')) return [];
    if (url.endsWith('/readiness/')) return { ready: true, checks: [{ key: 'course', label: 'Course information', ready: true, detail: 'Ready.' }, { key: 'curriculum', label: 'Lesson curriculum', ready: true, detail: '1 lesson.' }, { key: 'quizzes', label: 'Quiz content', ready: true, detail: 'Optional.' }] };
    if (url.includes('/studio/lessons/') && url.endsWith('/quiz/')) return { quiz: null, question_count: 0 };
    if (url.endsWith('/lessons/')) return pagination.withNextPage([lesson(1)], 'next-lessons');
    if (options?.method === 'POST') return { ...lesson(91), title: 'New lesson' };
    throw new Error(url);
  });
  await f.settle(); assert.equal(f.nodes('Redirect').length, 0);
  f.find('Pressable', 'Manage course').props.onPress(); await f.settle();
  f.nodes('TextInput').find(n => n.props.accessibilityLabel === 'Lesson title').props.onChangeText('New lesson'); f.render();
  f.find('Pressable', 'Add lesson').props.onPress(); await f.settle();
  const posted = f.requests.find(r => r.options?.method === 'POST');
  assert.ok(posted); assert.equal(posted.options.body.has('order'), false); assert.equal(posted.options.body.get('title'), 'New lesson');
  const status = f.nodes('Text').find(n => Array.isArray(n.props.children) && n.props.children[0] === 'DRAFT');
  assert.equal(status.props.children[2], 3);
  assert.equal(pagination.nextPage(f.nodes('LoadMore').find(n => n.props.label === 'Load more lessons').props.items), 'next-lessons');
});

test('failed quiz attempts retain answers for retry and passed attempts explain finalization', async () => {
  let passed = false;
  const f = fixture('../app/learning/quiz/[id].tsx', async (url, options) => {
    if (options?.method === 'POST') return { score: passed ? 1 : 0, total_questions: 1, percentage: passed ? 100 : 0, passed,
      question_feedback: [{ question_id: 1, question: 'Question', selected_answer: options.body.answers['1'], selected_text: options.body.answers['1'], correct_answer: 'B', correct_text: 'Right answer', is_correct: passed }] };
    if (url.endsWith('/questions/')) return [{ id: 1, question: 'Question', option_a: 'A', option_b: 'B', option_c: 'C', option_d: 'D' }];
    return { id: 9, title: 'Quiz', passing_score: 70, question_count: 1 };
  });
  await f.settle();
  const radio = f.nodes('Pressable').find(n => n.props.accessibilityRole === 'radio');
  assert.equal(radio.props.accessibilityLabel, 'Question, A. A');
  assert.equal(radio.props.accessibilityState.checked, false);
  radio.props.onPress(); f.render();
  f.find('Pressable', 'Submit answers').props.onPress(); await f.settle();
  assert.match(f.text(), /Not passed yet/); assert.match(f.text(), /70/); assert.match(f.text(), /to pass/); assert.match(f.text(), /Right answer/);
  assert.ok(f.nodes('Text').some(n => n.props.accessibilityLiveRegion === 'polite'));
  assert.ok(f.nodes('Text').some(n => n.props.accessibilityRole === 'header' && n.props.children === 'Not passed yet'));
  f.find('Pressable', 'Try quiz again').props.onPress(); f.render();
  assert.equal(f.find('Pressable', 'Submit answers').props.disabled, false);
  assert.equal(f.nodes('Pressable').find(n => n.props.accessibilityRole === 'radio').props.accessibilityState.checked, true);
  passed = true;
  f.nodes('Pressable').filter(n => n.props.accessibilityRole === 'radio')[1].props.onPress(); f.render();
  f.find('Pressable', 'Submit answers').props.onPress(); await f.settle();
  assert.match(f.text(), /mark this lesson complete/);
  assert.match(f.text(), /Quiz passed/); assert.match(f.text(), /Correct\./); assert.match(f.text(), /Your answer:/);
  assert.equal(f.requests.filter(r => r.options?.method === 'POST').length, 2);
});

test('mobile quiz history explains pass threshold and retries only failed attempts', async () => {
  const f = fixture('../app/learning/results.tsx', async url => {
    if (url.endsWith('my-certificates/')) return [];
    if (url.endsWith('quiz-attempts/me/')) return [{ id: 1, quiz_title: 'Practice', lesson_id: 3, passing_score: 70, score: 1, total_questions: 2, percentage: 50, passed: false, attempted_at: '2026-01-01' }, { id: 2, quiz_title: 'Passed', lesson_id: 4, passing_score: 70, score: 2, total_questions: 2, percentage: 100, passed: true, attempted_at: '2026-01-02' }];
    throw new Error(url);
  });
  await f.settle();
  assert.match(f.text(), /70% needed/);
  assert.equal(f.nodes('Pressable').filter(n => n.props.accessibilityRole === 'button' && String(n.props.accessibilityLabel || '').startsWith('Retry')).length, 1);
  f.find('Pressable', 'Try quiz again').props.onPress();
  assert.equal(f.routes.at(-1).params.id, '3');
});

test('adding the first lesson updates submission readiness without reopening Studio', async () => {
  let created = false;
  const f = fixture('../app/learning/studio.tsx', async (url, options) => {
    if (url.endsWith('/categories/')) return [{ id: 1, name: 'Sport' }];
    if (url.endsWith('/courses/me/')) return [{ ...course, lesson_count: 0 }];
    if (url.endsWith('/lessons/')) return [];
    if (url.endsWith('/readiness/')) return { ready: created, checks: [{ key: 'curriculum', label: 'Lesson curriculum', ready: created, detail: created ? '1 lesson.' : 'Add one.' }] };
    if (url.includes('/studio/lessons/') && url.endsWith('/quiz/')) return { quiz: null, question_count: 0 };
    if (options?.method === 'POST') { created = true; return lesson(1); }
    throw new Error(url);
  });
  await f.settle(); f.find('Pressable', 'Manage course').props.onPress(); await f.settle();
  assert.equal(f.find('Pressable', 'Add a lesson before submitting').props.disabled, true);
  f.nodes('TextInput').find(n => n.props.accessibilityLabel === 'Lesson title').props.onChangeText('First lesson'); f.render();
  f.find('Pressable', 'Add lesson').props.onPress(); await f.settle();
  assert.equal(f.find('Pressable', 'Submit for admin review').props.disabled, false);
  const status = f.nodes('Text').find(n => Array.isArray(n.props.children) && n.props.children[0] === 'DRAFT');
  assert.equal(status.props.children[2], 1);
});

test('Learning home exposes section headings, accessible progress and original routes', async () => {
  const mine = { id: 4, course: 1, course_title: 'My course', lesson_count: 3, completed_lessons: 1, progress_percentage: 33, completed: false };
  const f = fixture('../app/learning.tsx', async url => url === 'learning/courses/'
    ? pagination.withNextPage([{ ...course, average_rating: 4.5, creator_name: 'Instructor' }], 'next-courses')
    : pagination.withNextPage([mine], 'next-enrollments'));
  await f.settle();
  const headings = f.nodes('Text').filter(n => n.props.accessibilityRole === 'header').map(n => n.props.children);
  for (const title of ['Continue Learning', 'Live sessions', 'Explore Courses']) assert.ok(headings.includes(title));
  const bar = f.nodes('View').find(n => n.props.accessibilityRole === 'progressbar');
  assert.equal(bar.props.accessibilityValue.now, 33);
  f.nodes('Pressable').find(n => n.props.accessibilityLabel?.startsWith('Continue My course, 1 of 3 lessons, 33% complete')).props.onPress();
  assert.equal(f.routes.at(-1).params.id, '1');
  f.find('Pressable', 'View live classrooms').props.onPress(); assert.equal(f.routes.at(-1), '/classrooms');
  f.find('Pressable', 'Create and manage courses').props.onPress(); assert.equal(f.routes.at(-1), '/learning/studio');
  f.find('Pressable', 'Certificates & quiz attempts').props.onPress(); assert.equal(f.routes.at(-1), '/learning/results');
  const more = f.nodes('LoadMore');
  assert.equal(pagination.nextPage(more.find(n => n.props.label === 'Load more courses').props.items), 'next-courses');
  assert.equal(pagination.nextPage(more.find(n => n.props.label === 'Load more enrollments').props.items), 'next-enrollments');
});

test('course presentation retains instructor, curriculum, review input and accessible rating controls', async () => {
  const f = fixture('../app/learning/[id].tsx', courseRequest({ course: { ...course, creator_name: 'Jordan Lee' } }));
  await f.settle();
  const headings = f.nodes('Text').filter(n => n.props.accessibilityRole === 'header').map(n => n.props.children);
  for (const title of ['About this course', 'Course curriculum', 'Meet your instructor', 'Live sessions', 'Learner reviews']) assert.ok(headings.includes(title));
  assert.match(f.text(), /Jordan Lee/);
  const stars = f.nodes('Pressable').filter(n => n.props.accessibilityRole === 'radio');
  assert.equal(stars.length, 5); assert.equal(stars[4].props.accessibilityState.checked, true);
  stars[2].props.onPress(); f.render();
  assert.equal(f.nodes('Pressable').filter(n => n.props.accessibilityRole === 'radio')[2].props.accessibilityState.checked, true);
  assert.ok(f.nodes('TextInput').find(n => n.props.accessibilityLabel === 'Course review'));
  assert.equal(f.nodes('View').find(n => n.props.accessibilityRole === 'progressbar').props.accessibilityValue.now, 0);
});

test('course curriculum groups sections in section order and preserves flat legacy courses', async () => {
  const rows = [
    { ...lesson(1), title: 'Advanced', order: 1, module: 2 },
    { ...lesson(2), title: 'Foundation', order: 2, module: 1 },
    { ...lesson(3), title: 'Unassigned', order: 3, module: null },
  ];
  const modules = [{ id: 1, title: 'Foundations', order: 1 }, { id: 2, title: 'Advanced section', order: 2 }];
  const sessions = { results: [{ id: 15, classroom: 3, classroom_title: 'Course room', lesson: 2, lesson_title: 'Foundation', module: 1, module_title: 'Foundations', title: 'Foundation Q&A', status: 'LIVE', scheduled_start: null }], next: null };
  const grouped = fixture('../app/learning/[id].tsx', courseRequest({ lessons: rows, modules, sessions }));
  await grouped.settle();
  const labels = grouped.nodes('Text').map(node => node.props.children).filter(value => typeof value === 'string');
  const positions = ['Foundations', 'Foundation', 'Advanced section', 'Advanced', 'Other lessons', 'Unassigned'].map(label => labels.indexOf(label));
  assert.ok(positions.every(position => position >= 0));
  assert.deepEqual(positions, positions.slice().sort((a, b) => a - b));
  assert.match(grouped.text(), /Foundation Q&A/);
  grouped.find('Pressable', 'Open live classroom').props.onPress();
  assert.equal(grouped.routes.at(-1).pathname, '/classroom/[id]');

  const legacy = fixture('../app/learning/[id].tsx', courseRequest({ lessons: rows.map(row => ({ ...row, module: null })) }));
  await legacy.settle();
  assert.doesNotMatch(legacy.text(), /Foundations|Advanced section|Other lessons/);
  assert.ok(legacy.find('Pressable', 'Open lesson workspace'));
});

test('lesson workspace uses one protected player, quiz-gated completion, curriculum and next navigation', async () => {
  const rows = [{ ...lesson(1), module: 1, module_title: 'Foundations' }, { ...lesson(2), module: 2, module_title: 'Practice' }];
  const f = fixture('../app/learning/lesson/[id].tsx', async (url, options) => {
    if (url === 'learning/lessons/1/') return { ...rows[0], course: 1, course_title: 'Course', video: '/media/private/lesson-1.mp4', notes: '/media/private/notes.pdf', captions: '/media/learning/captions/lesson.vtt', caption_language: 'en-US', transcript: 'Full readable transcript.' };
    if (url === 'learning/courses/1/') return { id: 1, title: 'Course', lesson_count: 2 };
    if (url === 'learning/courses/1/lessons/') return rows;
    if (url === 'learning/courses/1/modules/') return [{ id: 1, title: 'Foundations', order: 1 }, { id: 2, title: 'Practice', order: 2 }];
    if (url.startsWith('learning/courses/1/live-sessions/')) return { results: [{ id: 15, classroom_title: 'Course room', lesson: 1, module_title: 'Foundations', title: 'Practice live', status: 'LIVE', scheduled_start: null }], next: null };
    if (url === 'learning/courses/1/progress/') return { ...progress, completed_lesson_ids: [], progress_percentage: 50, completed_lessons: 1 };
    if (url === 'learning/lessons/1/quiz/') return { id: 9, title: 'Quiz', passing_score: 70 };
    if (url === 'learning/quiz-attempts/me/') return [{ quiz: 9, passed: false, percentage: 40 }];
    if (options?.method === 'POST') throw new ApiError(400, 'Pass the lesson quiz before completing this lesson.');
    throw new Error(`Unexpected URL ${url}`);
  });
  await f.settle();
  assert.equal(f.nodes('VideoPlayer').length, 1);
  assert.equal(f.nodes('VideoPlayer')[0].props.captionsUri, '/media/learning/captions/lesson.vtt');
  assert.equal(f.nodes('VideoPlayer')[0].props.captionLanguage, 'en-US');
  const transcriptToggle = f.nodes('Pressable').find(n => JSON.stringify(n.props.children).includes('Read transcript'));
  assert.ok(transcriptToggle);
  assert.equal(transcriptToggle.props.accessibilityState.expanded, false);
  transcriptToggle.props.onPress(); await f.settle();
  assert.ok(f.nodes('Text').some(n => n.props.children === 'Full readable transcript.'));
  assert.match(f.text(), /Latest attempt/);
  assert.match(f.text(), /Practice live/);
  assert.match(f.text(), /Foundations/);
  f.find('Pressable', 'Open live classroom').props.onPress(); assert.equal(f.routes.at(-1).params.id, '15');
  assert.match(f.text(), /Pass quiz to complete lesson/);
  const current = f.nodes('Pressable').find(n => n.props.accessibilityLabel?.includes('current lesson'));
  assert.ok(current);
  f.find('Pressable', 'Next lesson').props.onPress();
  assert.equal(f.routes.at(-1).params.id, '2');
  f.find('Pressable', 'Pass quiz to complete lesson').props.onPress();
  await f.settle();
  assert.ok(f.requests.some(r => r.url === 'learning/lessons/1/progress/' && r.options?.method === 'POST'));
  assert.match(f.text(), /Pass the lesson quiz before completing/);
});

test('course curriculum opens a dedicated mobile workspace instead of mounting a player per row', async () => {
  const f = fixture('../app/learning/[id].tsx', courseRequest({ lessons: [lesson(1), { ...lesson(2), video: '/media/private/lesson-2.mp4' }] }));
  await f.settle();
  assert.equal(f.nodes('VideoPlayer').length, 0);
  f.nodes('Pressable').filter(n => JSON.stringify(n.props.children).includes('Open lesson workspace'))[1].props.onPress();
  assert.equal(f.routes.at(-1).pathname, '/learning/lesson/[id]');
  assert.equal(f.routes.at(-1).params.id, '2');
});

test('creator studio previews, edits curriculum, authors quiz questions and follows readiness', async () => {
  let quiz = null, question = null, editedLesson = null, module = null;
  const f = fixture('../app/learning/studio.tsx', async (url, options) => {
    if (url.endsWith('/categories/')) return [{ id: 1, name: 'Sport' }];
    if (url.endsWith('/courses/me/')) return [{ ...course, lesson_count: 1 }];
    if (url.endsWith('/courses/1/lessons/')) return [editedLesson || lesson(1)];
    if (url.endsWith('/courses/1/modules/')) {
      if (options?.method === 'POST') { module = { id: 5, title: options.body.title, description: '', order: 1 }; return module; }
      return module ? [module] : [];
    }
    if (url === 'learning/modules/5/' && options?.method === 'PATCH') { module = { ...module, ...options.body }; return module; }
    if (url.endsWith('/readiness/')) return { ready: !!question, checks: [
      { key: 'course', label: 'Course information', ready: true, detail: 'Ready.' },
      { key: 'curriculum', label: 'Lesson curriculum', ready: true, detail: '1 lesson.' },
      { key: 'quizzes', label: 'Quiz content', ready: !!question, detail: question ? 'Quiz complete.' : 'Needs quiz questions.' },
    ] };
    if (url === 'learning/studio/lessons/1/quiz/') {
      if (options?.method === 'POST') { quiz = { id: 9, lesson: 1, title: options.body.title, passing_score: 70, question_count: 0 }; return quiz; }
      return { quiz, question_count: quiz?.question_count || 0 };
    }
    if (url === 'learning/studio/quizzes/9/questions/') {
      if (options?.method === 'POST') { question = { id: 11, quiz: 9, ...options.body }; quiz.question_count++; return question; }
      return question ? [question] : [];
    }
    if (url === 'learning/lessons/1/' && options?.method === 'PATCH') { editedLesson = { ...lesson(1), title: options.body.get('title'), module: options.body.get('module') === 'none' ? null : Number(options.body.get('module')), caption_language: options.body.get('caption_language'), transcript: options.body.get('transcript') }; return editedLesson; }
    throw new Error(`Unexpected studio URL ${url}`);
  });
  await f.settle();
  f.find('Pressable', 'Manage course').props.onPress(); await f.settle();
  assert.match(f.text(), /Publishing checklist/);
  assert.equal(f.find('Pressable', 'Complete checklist to submit').props.disabled, true);
  f.nodes('TextInput').find(n => n.props.accessibilityLabel === 'New section title').props.onChangeText('Foundations'); f.render();
  f.find('Pressable', 'Add section').props.onPress(); await f.settle();
  assert.equal(module.title, 'Foundations');
  f.find('Pressable', 'Preview as learner').props.onPress();
  assert.equal(f.routes.at(-1).pathname, '/learning/[id]');
  f.find('Pressable', 'Edit lesson').props.onPress(); f.render();
  const sectionChoice = f.nodes('Pressable').find(node => node.props.accessibilityLabel === 'Assign lesson to section Foundations');
  assert.ok(sectionChoice, f.text());
  sectionChoice.props.onPress(); f.render();
  f.nodes('TextInput').find(n => n.props.accessibilityLabel === 'Lesson title').props.onChangeText('Revised lesson'); f.render();
  assert.ok(f.nodes('TextInput').some(n => n.props.accessibilityLabel === 'Caption language'));
  assert.ok(f.nodes('TextInput').some(n => n.props.accessibilityLabel === 'Lesson transcript'));
  f.nodes('TextInput').find(n => n.props.accessibilityLabel === 'Caption language').props.onChangeText('en-US');
  f.nodes('TextInput').find(n => n.props.accessibilityLabel === 'Lesson transcript').props.onChangeText('Readable lesson transcript.'); f.render();
  f.find('Pressable', 'Save lesson changes').props.onPress(); await f.settle();
  assert.equal(editedLesson.title, 'Revised lesson');
  assert.equal(editedLesson.module, 5);
  assert.equal(editedLesson.caption_language, 'en-US');
  assert.equal(editedLesson.transcript, 'Readable lesson transcript.');
  f.find('Pressable', 'Add optional quiz').props.onPress(); f.render();
  f.nodes('TextInput').find(n => n.props.accessibilityLabel === 'Quiz title').props.onChangeText('Practice check'); f.render();
  f.find('Pressable', 'Create quiz').props.onPress(); await f.settle();
  f.find('Pressable', 'Refresh questions').props.onPress(); await f.settle();
  f.nodes('TextInput').find(n => n.props.accessibilityLabel === 'Quiz question').props.onChangeText('Which answer is right?');
  for (const [label, value] of [['Answer choice A', 'A'], ['Answer choice B', 'B'], ['Answer choice C', 'C'], ['Answer choice D', 'D']]) {
    f.render(); f.nodes('TextInput').find(n => n.props.accessibilityLabel === label).props.onChangeText(value);
  }
  f.render(); f.nodes('Pressable').find(n => n.props.accessibilityLabel === 'Mark choice B correct').props.onPress(); f.render();
  f.find('Pressable', 'Add quiz question').props.onPress(); await f.settle();
  assert.equal(question.correct_answer, 'B');
  assert.equal(f.find('Pressable', 'Submit for admin review').props.disabled, false);
  assert.ok(f.requests.some(r => r.url === 'learning/studio/questions/11/' && r.options?.method === 'PATCH') === false);
});

test('creator studio preserves existing paid drafts and disables their submission', async () => {
  const paid = { ...course, id: 42, title: 'Legacy paid course', is_free: false, status: 'DRAFT', lesson_count: 1 };
  let patched;
  const f = fixture('../app/learning/studio.tsx', async (url, options) => {
    if (url.endsWith('/categories/')) return [{ id: 1, name: 'Sport' }];
    if (url.endsWith('/courses/me/')) return [paid];
    if (url.endsWith('/courses/42/lessons/')) return [lesson(1)];
    if (url.endsWith('/courses/42/modules/')) return [];
    if (url.endsWith('/readiness/')) return { ready: true, checks: [
      { key: 'course', label: 'Course information', ready: true, detail: 'Ready.' },
      { key: 'curriculum', label: 'Lesson curriculum', ready: true, detail: '1 lesson.' },
      { key: 'quizzes', label: 'Quiz content', ready: true, detail: 'Ready.' },
    ] };
    if (url.endsWith('/quiz/')) return Promise.reject(new ApiError(404));
    if (url === 'learning/courses/42/' && options?.method === 'PATCH') { patched = options.body; return { ...paid, ...options.body }; }
    throw new Error(`Unexpected studio URL ${url}`);
  });
  await f.settle();
  f.find('Pressable', 'Manage course').props.onPress(); await f.settle();
  assert.ok(f.find('Pressable', 'Paid publishing unavailable')?.props.disabled);
  assert.match(f.text(), /existing paid course is preserved, but cannot be submitted/);
  f.find('Pressable', 'Save course changes').props.onPress(); await f.settle();
  assert.equal(patched.is_free, false);
});
