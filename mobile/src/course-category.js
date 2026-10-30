// Keep a creator's explicit choice when category data refreshes.
function courseCategoryDefault(categories, current = null) {
  return current ?? categories.find(category => category.is_default)?.id ?? null;
}

module.exports = { courseCategoryDefault };
