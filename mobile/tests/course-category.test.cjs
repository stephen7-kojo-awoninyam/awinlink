const { test } = require('node:test');
const assert = require('node:assert/strict');
const { courseCategoryDefault } = require('../src/course-category');

test('profile default is selected instead of the first alphabetical category', () => {
  assert.equal(courseCategoryDefault([{ id: 1 }, { id: 2, is_default: true }]), 2);
});
test('manual choice and existing course selection survive refreshes', () => {
  assert.equal(courseCategoryDefault([{ id: 2, is_default: true }], 9), 9);
});
test('missing profile or missing category requires an explicit choice', () => {
  assert.equal(courseCategoryDefault([{ id: 1 }]), null);
  assert.equal(courseCategoryDefault([]), null);
});
