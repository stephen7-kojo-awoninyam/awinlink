Course categories
=================

Run `python manage.py migrate` to add Sports, Science and technology, Arts,
and Others on existing installations and fresh databases.

To restore missing defaults later, run `python manage.py seed_course_categories`
(optionally `--database ALIAS`). Repeated runs create no duplicates. Existing
category names, descriptions, IDs, custom categories and courses are preserved.
Reversing the data migration retains categories to avoid cascading course deletion.

The Create course and Edit course forms use the database categories, including
custom entries, in alphabetical order. Their native select works with keyboard
and mobile pickers and retains a submitted category when another field is invalid.

New courses default to the creator's coach, talent or scout profile category.
Organization profiles use a matching category name. Missing profiles or unmatched
categories leave the selection empty. The category remains editable; existing
courses and submitted selections always retain their selected category.
The category API exposes `is_default` for mobile clients using the same mapping.

Run focused regression checks with:
`python manage.py test learning.test_categories learning.test_ui`
