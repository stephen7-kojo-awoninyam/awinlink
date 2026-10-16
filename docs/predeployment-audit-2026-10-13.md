# Awinlink pre-deployment audit — 2026-10-13

**Overall readiness: FAIL / HOLD.** Backend regression and browser checks pass after focused repairs. Mobile dependency advisories and unverified deployment infrastructure remain release blockers.

This audit began with read-only inspection. Existing edits and untracked work were preserved. Nothing was staged, reset, deleted, committed, pushed, or deployed. No production database was connected to or modified. Migration execution was limited to isolated SQLite test databases and the synthetic browser database.

## Results

| Area | Verdict | Evidence and limits |
| --- | --- | --- |
| Git preservation | PASS | No staged files at inspection or completion. Substantial existing backend, mobile, UI, and migration work remains modified/untracked. The audit made small repairs within that working tree. |
| Django checks | PASS | `check`: zero issues. `makemigrations --check --dry-run`: no changes detected. |
| Full regression | PASS | **470 tests passed**, final verified process exit code 0. Baseline: 441 tests, five preexisting failures. Isolated final runs used the MD5 test hasher for speed; production password settings were not changed. The baseline and cross-role browser logins used ordinary password hashing. |
| Focused regression | PASS | Competition/messaging/learning/settings run: 77 tests passed. Invitation/signaling security run: 11 passed. Expanded signaling integration run: 11 passed, including actual ASGI JWT sockets and peer relay. All are included in the final suite. |
| Auth, CSRF, permissions | PASS within tested coverage | Public ADMIN registration rejection, role-aware access, JWT authentication, session CSRF, membership capability checks, suspension/revocation, and cross-organization denial passed. Confirmed state-changing web actions now require POST; tests cover 33 additional action guards, recruitment/shortlists, and invitation aliases. Browser requests without CSRF were rejected for event registration, competition registration, enrollment, and applications. |
| Organization membership and invitations | PASS on SQLite | Capability matrix, team token hashing/expiry/consumption, owner backfill, ownership transfer, suspension, and concurrency tests passed. Real PostgreSQL locking remains unverified. Web opportunity-invitation response defects were repaired and tested. |
| Opportunities/applications | PASS | Writable opportunity API input and existing application workflows retained; scope, status, duplicate application, availability, and UI tests passed. Browser application and history routes passed. |
| Events | PASS | Registration/organizer actions and scoped permissions passed. Organizer workspace aggregation crash repaired. Creation remains organization-owned and existing membership permissions remain enforced. |
| Competitions | PASS | Discovery/categories, registration, organizer management, moderation, judging/results, scope and suspension tests passed. Creation capability defect repaired. API list tests corrected without changing list responses. |
| Learning | PASS | Discovery, enrollment, lesson access, progress, quizzes, reviews, studio/approval and API tests passed. Web redirect destinations repaired without changing routes or API names. |
| Notifications | PASS within automated coverage | Recipient scope, read actions, mobile token ownership, push payloads, and signaling delivery tests passed. Actual Expo/APNs/FCM/Web Push delivery was not verified. |
| Messaging / WebRTC signaling | PASS within automated coverage | Conversation/call API permissions and JWT signaling passed. Foreign origins, outsiders, ended calls, and revoked participants are rejected. Actual audio/video and TURN relay on devices remain unverified. |
| Browser / responsive UI | PASS | **264 page checks** at **1440/768/390/320px**: zero document HTTP errors, width mismatches, horizontal page overflow, or JavaScript exceptions. Anonymous plus ATHLETE, ORGANIZATION, SCOUT, COACH and ADMIN. Real session login, CSRF-protected submissions, organizer forms, discovery/details, learner destinations, notifications, messaging, shortlist, recruitment and saved-talent pages checked. Additional DOM checks passed for login, mobile drawer/Escape, discovery filters/reset, quiz submission and completed-lesson web destination; a real synthetic course certificate PDF was generated locally. Desktop/mobile screenshots retained. |
| Migration graph | PASS | 145 disk migrations; graph consistent, no conflicting leaves or model drift. Existing untracked migrations were inspected, not edited. Production migration history was not queried. |
| PostgreSQL compatibility | PARTIAL / blocker | Offline PostgreSQL 17 DDL compilation passed for 98 models / 521 statements, including historical new membership, team-invitation and mobile-token models. No PostgreSQL server was available for execution. This does not establish upgrade, backfill, constraint or locking correctness on PostgreSQL. |
| Python dependencies | PASS for consistency | `pip check`: no broken requirements. A Python vulnerability-advisory scan was not performed. |
| Static assets | PASS | Initial isolated WhiteNoise manifest collection: 182 files copied, 528 post-processed. Final collection rebuilt the changed shared stylesheet: one file copied, 181 unmodified, 481 post-processed. Static JavaScript syntax checks passed. Existing `staticfiles/` was preserved. CDN availability and production media delivery still need staging verification. |
| Expo integration | PASS for build/contracts | TypeScript typecheck passed; dependency tree resolved; 137 expanded mobile API path variants resolve to existing Django routes; public Expo configuration resolved; Expo web export completed successfully. Path resolution does not prove every method, payload, dynamic branch, or native runtime interaction. Offline Expo dependency validation reports itself unreliable, so it is not a substitute for native build validation. |
| Mobile dependency security | **FAIL / blocker** | Network npm audit reports **31 vulnerable package entries: 20 high, 11 moderate, zero critical**. Includes transitive build/signing tooling; exploit reachability in the shipped app has not been established. Automatic suggested fixes include incompatible Expo/React Native/plugin downgrades and were not applied. |
| Railway / Redis / external services | **UNVERIFIED / blocker** | No tracked Railway/Procfile/Dockerfile configuration found. Dashboard startup/pre-deploy settings were not accessible. No production PostgreSQL, Redis, SMTP, Cloudinary, TURN or push-provider connection was made. |
| Secret hygiene | PASS for scoped scan | No tracked `.env`, private-key containers, or matched AWS/live-payment/private-key credential patterns found in tracked and untracked source. Local secret containers are ignored. Registration password/PII printing was removed. This was a scoped current-tree scan, not an exhaustive historical or entropy-based secret audit. |
| Diff hygiene | Existing failure | `git diff --check` still flags two preexisting trailing-whitespace lines: `dashboard/views.py:571` (originally 569), `organizations/views.py:1131`. They were preserved; not a functional blocker. |

## Preexisting failures and confirmed repairs

The baseline failures were recorded before updating expectations:

1. `CompetitionWorkflowTests.test_api_create_is_organization_only_and_drafts_are_not_public`: expected only the newly created draft although the fixture already contained a published competition. Corrected the expected IDs.
2. `OrganizationMembershipCompetitionCapabilityTests.test_membership_capabilities_scope_competition_create_edit_and_lists`: omitted the competition created earlier in the test. Corrected the expected IDs. This exposed a previously masked real defect: the create API requested `VIEW_COMPETITIONS`. It now requests `MANAGE_COMPETITIONS`; viewers and recruiters cannot create.
3. `HomeFeedTests.test_home_feed_loads_without_an_unbound_events_error`: expected a logout link although logout correctly uses a CSRF-protected POST form. Corrected the markup assertion; retained POST logout.
4. `OrganizationTests.test_organization_directory_loads_and_filters_inactive_records`: anonymous pages overriding `content` rendered blank because that block was inside the authenticated shell branch. Moved the shared block outside that branch, retaining the public home block and authenticated navigation.
5. `OpportunityRecommendationTests.test_opportunity_score_weights_important_skills_and_fit`: omitted the existing five-point domain-and-skill bonus. Corrected the expected score and added a lower-weight skill comparison. Scoring behavior was preserved.

Additional defects confirmed during inspection/browser testing:

- Event organizer page returned 500 because the `certificates` annotation conflicted with the reverse relation. Renamed it `certificate_count` and added an actual workspace response/aggregate test.
- Railway HTTPS/cookie/email configuration was gated on `RENDER`; Render trusted origins were overwritten. Production hardening now also follows `DEBUG=False`; Railway detection supplies a secure default, and Railway/custom hosts and trusted origins can be configured. Four isolated settings tests cover these cases.
- Browser WebSockets lacked origin validation. Added allowed-host origin validation with an exception only for validated JWT native sockets with no Origin header. Foreign browser origins remain rejected even when a JWT is present.
- Signaling accepted non-object JSON and binary frames that could crash the consumer. Added error responses. Open call sockets now recheck active account, call state, conversation participation, and call-participant state before relaying.
- Learning web redirects with colliding global API names led to JSON API pages. Changed redirects to existing web callbacks and asserted canonical web destinations. Routes and API names were retained.
- Web opportunity invitations mutated state on GET and could accept via a conversation query using removed fields. Responses now require CSRF-protected POST, lock the invitation, reject replay, record response time, and atomically create the existing conversation/participant structure. Updated existing buttons to POST forms. Tests cover recipient scope, CSRF, replay, conversation membership and rollback.
- Registration debug prints exposed full submitted passwords and personal details. Removed them and added a logging regression test.
- Recruitment stage changes and shortlist add/remove/star actions mutated on GET. They now require POST; existing controls use CSRF forms and positive/negative tests retain capability checks and successful actions.
- The same confirmed GET-mutation pattern affected event registration/management/media deletion, learning like/enroll/submit, connection responses/follows, feed likes/saves, admin account/talent status toggles, portfolio/profile record deletion, personal follows/bookmarks, and conversation start. Added POST guards and converted existing links to forms while retaining URLs and action bodies. A regression test verifies GET and CSRF-less POST rejection across 33 actions. Existing already-safe read/edit/POST workflows remain intact; ordinary profile initialization, lesson-progress initialization and view/read tracking were not classified as destructive action defects.
- Legacy `/talents/invitations/...` response URLs now use the repaired invitation workflow. The shortlist invitation link reversed a nonexistent one-argument route; restored routing to the existing opportunity-selection view under the distinct `invite_talent_profile` name. Existing routes were retained.
- The coach saved-talent message control supplied a user ID to a talent-profile-ID route. Corrected the ID and added a saved-talent page assertion. Shared styles retain the link/control appearance after POST-form conversion.

**New regressions remaining: none in the final backend suite or 264-page browser checks.** Initial browser evidence and failed intermediate test logs remain available for comparison. An existing messaging permission test was updated to use POST for conversation start while retaining its denial assertion. Audit helper selector, optional-argument, namespace, timing and recruitment-path mistakes were corrected separately and were not application defects.

## Release blockers and exact next steps

1. **Resolve or explicitly mitigate the npm advisories before releasing mobile/build tooling.** Triage the installed `braces` and `node-forge` chains and each remaining advisory. The reviewed [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) lists no patched version; the [node-forge advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv) concerns RSA signature verification. Review reachability and compatible upstream fixes/mitigations. Do not apply the suggested Expo 44 / React Native 0.72 downgrades. Rerun `npm.cmd audit --omit=dev`, typecheck, export, and native builds after the reviewed change.
2. **Execute migrations and the entire suite on a disposable PostgreSQL instance**, then validate an upgrade using an appropriately sanitized staging snapshot. Do not use production credentials. The audit runner supports only a loopback URL whose database name begins `awinlink_audit_` and creates a separate `test_` database:

   ```powershell
   $env:AWINLINK_AUDIT_POSTGRES_URL = '<postgresql URL to localhost/127.0.0.1 with awinlink_audit_ database>'
   $env:AWINLINK_AUDIT_LOG = 'audit-postgresql-regression.log'
   $env:AWINLINK_AUDIT_FAST_TESTS = '1'
   .venv\Scripts\python.exe -u -B audit_predeployment.py test --noinput --verbosity 2
   ```

   Check partial uniqueness, case-insensitive username constraints, owner-link backfill conflicts, token replay, and ownership/invitation concurrency on PostgreSQL. The existing data backfill raises on conflicting active owners; reconcile such records in staging before approving a release plan. Production history/backup/restore verification remains a later authorized operation.
3. **Review the actual Railway settings and environment in staging.** Pin a Django-6-compatible Python runtime (the local environment uses Python 3.13). Verify `DEBUG=False`, a strong unique `SECRET_KEY`, PostgreSQL `DATABASE_URL`, `REDIS_URL`, public/custom `ALLOWED_HOSTS`, and HTTPS `CSRF_TRUSTED_ORIGINS`. Automatic detection uses Railway's provided `RAILWAY_ENVIRONMENT_NAME`, confirmed against its [variables reference](https://docs.railway.com/variables/reference). The local dev configuration currently produces six `check --deploy` warnings; a synthetic production profile passes, but actual Railway settings have not been validated. Run `python manage.py check --deploy --fail-level WARNING` against the reviewed staging configuration.
4. **Verify the ASGI startup and separate release command.** Proposed values for review, not executed:

   - Start: `daphne -b 0.0.0.0 -p "$PORT" config.asgi:application`
   - Build/static stage: install reviewed `requirements.txt`, then `python manage.py collectstatic --noinput`
   - Pre-deploy, only after the PostgreSQL upgrade review and explicit release authorization: `python manage.py migrate --noinput`

   Confirm proxy forwarding, HTTPS/WSS, custom host acceptance, and a suitable existing health-check URL. Keep migrations out of every worker startup. Railway supports distinct [startup and pre-deploy settings](https://docs.railway.com/deployments); actual dashboard values must be verified.
5. **Test Redis across at least two ASGI workers** in staging: notification fan-out, user/call groups, reconnect, worker replacement and Redis outage recovery. The local fallback is an in-memory layer and does not establish distributed signaling readiness. The browser audit used Daphne with synthetic data; automated signaling used the in-memory test layer. The [Channels security documentation](https://channels.readthedocs.io/en/stable/topics/security.html) explains origin validation for session-authenticated sockets.
6. **Complete native device/provider acceptance.** Set reviewed Android package/iOS bundle IDs, EAS project identity and platform push credentials. Use development/production native builds because Expo Go does not contain `react-native-webrtc`. Verify login/refresh/logout, cross-role workflows, background incoming-call push, notification navigation, microphone/camera permissions, audio/video, network changes/reconnect, and forced TURN relay on Android and iOS. Verify SMTP password-reset delivery, Cloudinary upload/read behavior, Web Push and Expo/APNs/FCM delivery in staging. Provider credentials and TURN shared secrets stay server-side.
7. **Review the release artifact inventory.** Entire `mobile/`, new UI assets/templates/helpers/tests, four existing new migrations, and organization/notification API support contain untracked work. A deployment from the current committed tree would omit that work. Review/package the intended files after user approval; no staging or commit was performed by this audit. `.gitignore` intentionally ignores local Cloudflare/worker files and `pyproject.toml`/locks/`requirements.render.txt`; confirm the chosen build artifact does not rely on those ignored files. Run a Python dependency-advisory scan before release as well.

## Evidence and reproduction

- `audit-inventory.json`, `audit-completed-inventory.log`: final Git/configuration/graph/secret-pattern inventory; no secret values recorded.
- `audit-baseline-tests.log`: original five failures; contains synthetic fixture submissions from the old debug prints.
- `audit-final-readiness-tests.log`: final 470-test successful run, process exit 0. Earlier `audit-verified-regression.log` records the 462-test milestone.
- `audit-focused-tests.log`, `audit-fixed-focused-tests.log`, `audit-security-tests.log`, `audit-native-signaling-tests.log`: focused results and the masked capability failure.
- `audit-production-profile-check.log`: synthetic production profile, zero deployment-check issues; `audit-deploy-check.log`: six local dev warnings.
- `audit-postgresql.json`: offline DDL evidence; no server execution.
- `audit-static.log`, `audit-final-static.log`: isolated manifest collection.
- `audit-browser-results.json`: initial browser defects; `audit-browser-final-results.json`: 252-page passing rerun.
- `audit-browser-release-results.json`: 264 verified checks, including the corrected recruitment route and saved-talent destination. `audit-browser-expanded-results.json` retains the intermediate helper's four incorrect `/recruitment/` requests.
- `audit-get-mutation-candidates.json`: static review candidates; includes intended initialization/tracking and unused legacy functions, not proof that every candidate is a vulnerability.
- `audit-browser-interactions.json`: DOM interaction results; the initial completion observation was too early and was corrected to wait for the destination state.
- `audit-final-*-1440.png`, `audit-final-*-390.png`: desktop/mobile visual captures.
- `audit-mobile-contracts.json`: 137 resolved expanded path variants; `audit-mobile-dependencies.log`, `audit-expo-public-config.log`, `audit-expo-export.log`: mobile validation.
- `audit-mobile-security-retry.json`: successful npm advisory response. The first request was blocked by the sandbox; the approved read-only retry succeeded.

Reproduce the isolated SQLite suite:

```powershell
$env:AWINLINK_AUDIT_FAST_TESTS = '1'
$env:AWINLINK_AUDIT_LOG = 'audit-recheck-regression.log'
.venv\Scripts\python.exe -u -B audit_predeployment.py test --noinput --verbosity 2
```

The runner overrides database, channel layer, mail, storage and web-push configuration for isolation. Default execution never uses the configured production database. Audit databases/media/build/browser profiles and evidence have been retained; generated `.audit-*` directories are ignored. Temporary audit Daphne and Chrome processes were stopped. No production migration or deployment commands above were executed.
