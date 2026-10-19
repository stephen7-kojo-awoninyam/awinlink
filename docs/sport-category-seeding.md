Sport category seeding
=====================

Preview with `python manage.py seed_sport_categories --dry-run`, then apply with
`python manage.py seed_sport_categories` against the intended database.

The command adds positions, disciplines and specializations for existing Sport
rows using the 20 sports in the organization domain seed. It does not create
sports, edit descriptions or names, delete duplicates, or change profile links.
Unknown sports are reported and skipped; extend `sports/category_seeds.py` with
reviewed categories when adding another sport. Common aliases are supported.

Category matching is scoped to each sport and ignores case and whitespace.
Existing duplicates are retained. Missing categories are inserted in batches
inside one transaction; repeated runs add nothing once coverage is complete.
Dry runs perform no inserts. Parent row locks serialize command runs on databases
supporting `SELECT FOR UPDATE`; the model has no category uniqueness constraint,
so unrelated application writers are not covered by that guarantee. SQLite does
not support these row locks: run one seeder at a time there.

No migration, deployment, or Railway change is required by this implementation.
