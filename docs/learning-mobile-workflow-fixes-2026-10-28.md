# Learning mobile workflow fixes — 2026-10-28

Changes apply to the current working tree. No redesign, deployment, production access, dependency changes or schema migration was performed. Existing lesson positions, course records, enrollment history and certificate identities/files are preserved.

## Resulting behavior

- Course quiz availability is checked for every displayed lesson, including lessons appended by cursor pagination. Unchecked, unavailable and failed checks are distinct; pull-to-refresh retries failed checks. A successful check exposes the existing quiz route; question pagination still prevents incomplete submissions.
- The lesson-create API assigns the next order from the entire course, under a course-row transaction lock. Client-supplied order no longer controls append position. Studio omits order from multipart uploads, retains continuation metadata and sorts displayed lessons by persisted order. Existing rows are never renumbered. Creator ownership, pending/approved restrictions and upload/input validation remain enforced.
- Paid lesson previews include an explicit `is_locked` boolean alongside the existing server-side video/notes redaction. Mobile renders a locked explanation and suppresses media controls; free previews and enrolled/creator/admin access retain their existing policy. A fallback handles servers without the new field. This is UI feedback, not an authorization replacement.
- Course progress refreshes on focus, including return from a quiz, and through pull-to-refresh. Completion never updates optimistically. On a partial PDF-generation failure, mobile reloads durable progress and retains the server error. Completed courses expose results navigation and idempotent certificate-generation retry. Legacy fully marked lessons can explicitly retry course finalization after passing required quizzes; the backend still validates completion.
- Certificate results refresh on focus and allow either certificates or attempts to load when the other endpoint fails. Issued certificates without PDFs explain the pending state and link back to their course for retry. The owner-filtered certificate serializer adds read-only `course_id` for that link. Existing download behavior remains unchanged.
- Failed quiz attempts can be retried with answers retained. Successful attempts explain that the learner must mark the lesson complete. Quiz grading and certificate issuance remain server-controlled.
- Course/results state is scoped to account, role and course as appropriate; late requests cannot repopulate another scope. Denied course refreshes remove stale media/progress controls. Review failures do not prevent lessons from loading. Studio ignores superseded lesson-list responses and updates its selected course's lesson count immediately after creation, preserving first-lesson submission readiness. Mobile Studio entry includes SCOUT, matching the existing backend creator roles.

## Validation

- Final targeted mobile regression run: **13 passed, no skips**. Tests execute real screen functions and hooks with deterministic mocked API responses; no live services.
- Full mobile suite on the completed source: **208 run, 205 passed, three opt-in browser tests skipped**, no failures. Evidence: `.audit-learning-mobile-suite-final.log`. The skipped checks cover classroom controls/whiteboard/chat/media, classroom management, and actual browser media recording/playback.
- `npm.cmd run typecheck`: passed on the completed source. Evidence: `.audit-learning-mobile-typecheck-final.log`.
- PostgreSQL workflow suite: **25 passed, no skips**, including a real two-thread lesson-append race (orders 91 and 92, existing order 90 unchanged) and existing completion/certificate races. Evidence: `.audit-learning-mobile-postgres.log` and `.audit-migration-rehearsal/d9f98b2212b341029ff4550f975bf57a/report.json`.
- Full isolated Learning backend suite: **243 run, 230 passed, 13 skipped**, no failures/errors. Evidence: `.audit-learning-mobile-backend.log`. Migration graph and model-drift checks reported no issues.
- PostgreSQL fixture cleanup verified zero remaining rehearsal databases and zero other client connections on the exact workspace data directory. The local cluster was cleanly stopped afterward.

The PostgreSQL and SQLite runners strip service credentials and suppress dotenv; PostgreSQL uses only the verified loopback workspace cluster and a new UUID database. Mobile requests are mocked. Native device media/download behavior and live runtime verification were not exercised.

## Reproduction

```text
cd mobile
node --test tests/learning-workflows.test.cjs tests/quiz-pagination.test.cjs
npm.cmd test
npm.cmd run typecheck
cd ..
.venv/Scripts/python.exe -u -B scripts/audit_production_readiness_local.py learning
.venv/Scripts/python.exe -u -B scripts/rehearse_populated_migrations.py --learning-workflow-tests-only
```

The last command requires the verified local fixture cluster to be running; it creates and removes its own disposable database. Counts overlap and are not additive. Windows PowerShell can format native stderr progress as `NativeCommandError` in redirected logs; the Django test summaries and structured PostgreSQL report establish the test results.

Live release gates remain in the [final security checklist](final-security-release-checklist-2026-10-28.md). Backend workflow policies remain documented in the [backend workflow report](learning-backend-workflow-fixes-2026-10-28.md).
