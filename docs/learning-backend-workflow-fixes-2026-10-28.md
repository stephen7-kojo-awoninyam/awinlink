# Learning backend workflow fixes

Implemented locally on 2026-10-28. No redesign, mobile UI change, production access, deployment, schema/data migration or provider operation. Existing courses, enrollments, attempts, awards and files were not rewritten or removed.

## Shared rules

`learning.services.LearningService` now supplies the rules used by both Django views and REST handlers:

- Quiz metadata/questions require an active current actor who is the creator, current ADMIN, or an enrolled learner in an approved course. Current role/account state is rechecked for quiz access. Creator/admin preview does not grant an unenrolled attempt. Question responses still exclude correct answers.
- Lesson completion requires the caller's enrollment, a real boolean completion value, and a passed attempt for the lesson's valid required quiz. Invalid/empty quizzes cannot be bypassed using an old attempt. All required lessons and quizzes must be complete before issuing a course award.
- Enrollment-row locks serialize attempts/completion and completion retries. Certificate identity and course completion are committed before external PDF storage. Already completed timestamps, existing certificate IDs and existing PDF bytes remain unchanged on retry.
- Missing PDFs use a certificate-row lock and the existing PDF generator. Completion and download can retry safely. Storage failure returns a redacted 503 on API/download; valid committed progress and the certificate identity remain available for retry. The web completion action reports a warning and keeps its normal redirect.
- Explicitly marking progress incomplete recalculates enrollment completion and clears its completion timestamp. Previously issued certificate rows/files and quiz attempts are retained as award/history records; this is not a certificate-revocation feature.
- New enrollment is allowed only for approved free courses. Web and API use the same rule. Existing paid enrollments remain present and retain supported learning/certificate access; no payment collection was added. Duplicate enrollment remains unique; the API retains its existing duplicate-request response.
- Supported backend creator roles are ATHLETE, ORGANIZATION, SCOUT, COACH and ADMIN. Web and REST creation/submission use the shared policy. Client-side Studio/navigation changes are outside this backend-only task.
- Submission and approval require at least one lesson. Included quizzes require questions, a valid passing-score range, nonempty questions/options and valid answer keys. Invalid existing courses remain stored; future transition attempts return errors rather than silently changing history. Draft/rejected ownership rules, pending/approved edit locks and admin-only moderation remain.
- REST input serializers validate completion, answer mappings/choices and rejection text. Shared grading rejects foreign question IDs, malformed answers and unusable quizzes before writing attempts. Web grading uses that same service. Quiz/question authoring forms now enforce passing-score and answer-choice bounds on the server, not only HTML widgets.

The default REST completion request without a completed field still means true. The existing boolean serializer safely parses supported boolean representations; arbitrary objects/strings are rejected. Partial/empty answer maps on a nonempty valid quiz are scored as submitted, with unanswered questions incorrect; this does not introduce a new mandatory-all-answers policy.

## Preserved controls and contracts

Existing web login, creator/admin decorators, POST/CSRF protections, API authentication, bounded question pagination and answer-key exclusion remain. Completion/scoring outcomes are computed on the server and scoped to the current learner. Existing media ACL/storage rules and download ownership checks remain; PDF generation uses isolated memory storage in tests. No provider URL/signature/exception detail is exposed by the new retry errors.

API response contracts remain course/enrollment/progress/attempt serializers. Passing a quiz still requires a separate explicit lesson-completion action, preserving web behavior. No automatic quiz-to-completion migration, historical membership repair, certificate deletion, paid entitlement inference or forced content publication was introduced.

## Regression coverage and verification

New regressions are in `learning/test_workflow_rules.py`. Coverage includes:

- Outsider, anonymous, inactive, stale-role and revoked-enrollment quiz access; draft isolation; creator/admin previews; answer-key exclusion.
- Quiz-gated completion, all-lessons/all-quizzes eligibility, web/API interchange, generated PDF download and safe retries after storage failure.
- Stable certificate IDs/timestamps/bytes, legacy award preservation and existing paid-enrollment access.
- Free-only enrollment on web/API, duplicate enrollment, and retained CSRF denial.
- All five creator roles; submission/approval readiness; malformed completion/answers/rejection and authoring inputs with no unauthorized writes.
- Real PostgreSQL duplicate-completion and concurrent-final-lesson races, asserting one award/PDF and no stale final completion state.

Existing moderation fixtures now include a real lesson so their successful submission/approval assertions satisfy the readiness contract. The UI test for a failed quiz-gated completion now asserts no completed progress instead of requiring creation of a blank row on a rejected request. Neither change weakens the business rule.

The first PostgreSQL run exposed a regression-fixture error: explicitly closing a streamed download response triggered request-finished connection cleanup inside TestCase's transaction. Consuming Django's closing streaming iterator fixed the fixture; the corrected 20-test run passed, including both concurrency checks. That initial failed run is not counted as application verification.

Recorded broader runs:

- Initial focused Learning/UI/categories/moderation/mobile-backend checks: 45 passed.
- Full Learning suite at that stage: **231 run, 219 passed, 12 skipped**, no failures/errors; graph conflicts absent and makemigrations --check reported no changes. Evidence: `.audit-learning-workflows-all.log`.
- Broader security suite: **363 run, 361 passed, two Redis-only skips**, no failures/errors. Evidence: `.audit-learning-workflows-security.log`.
- Subsequent focused run: 49 run, 47 passed, two PostgreSQL-only skips. Corrected PostgreSQL workflow run: 20 passed, no skips. These preceded the final additional download/legacy-preservation cases; final targeted results follow below.

Final verification of the completed change:

- **PostgreSQL: all 24 workflow/concurrency tests passed, no skips**, in 9.931 seconds. `.audit-learning-workflows-postgres-verified.log`; `.audit-migration-rehearsal/70e85d12d2954e1b9e4a0b414adadc93/report.json`; exit zero, no owned database left.
- **Focused SQLite/UI/moderation/categories: 53 run, 51 passed, two PostgreSQL-only skips**, no failures/errors. `.audit-learning-workflows-verified.log`; migration graph/model drift checks passed.
- The full Learning and broader security runs above were not repeated after the final focused PDF-download/legacy-preservation refinements; those changes are included in both final targeted runs. Counts overlap and must not be added into a claimed single suite.

Tests use stripped service credentials/dotenv suppression, isolated SQLite or a verified workspace-only UUID-named PostgreSQL database, memory/local cache and nondelivery email. New PDF tests use InMemoryStorage. No production data, Cloudinary mutation, real email or live device workflow was exercised.

Reproduction:

```text
.venv/Scripts/python.exe -u -B scripts/audit_production_readiness_local.py learning
.venv/Scripts/python.exe -u -B scripts/audit_production_readiness_local.py learning.test_workflow_rules learning.tests learning.test_mobile_lessons learning.test_ui learning.test_categories
.venv/Scripts/python.exe -u -B scripts/rehearse_populated_migrations.py --learning-workflow-tests-only
```

The PostgreSQL runner requires the verified loopback workspace cluster and owns/drops only its new fixture database. Its existing keepdb setting merely delegates cleanup to that owning context, with a separate lifecycle timeout. It does not reuse a production database.

Cleanup verified no remaining rehearsal databases or other database clients (`.audit-migration-rehearsal/learning-workflow-cleanup.json`). The workspace PostgreSQL cluster was then cleanly stopped, restoring its initial stopped state.

## Scope limits

No UI/UX, mobile Studio gate, pagination metadata, learning preview policy or course-revision redesign was attempted. Existing paid access is preserved but paid enrollment remains unavailable. PostgreSQL concurrency tests are small fixtures, not production-scale load verification. Live runtime, backups, media/CDN and release approval remain subject to the [final security checklist](final-security-release-checklist-2026-10-28.md).
