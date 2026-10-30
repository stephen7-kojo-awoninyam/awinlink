Rising Talent intelligence, version 1
===================================

Rising Talent identifies recent, explainable momentum across Sports, Science and
technology, Arts and Others. It is a deterministic evidence score, not a trained
prediction of future success. Achievements are self-reported because the current
achievement model has no verification state. It supports human review; it never
automatically contacts a talent, creates an invitation or adds anyone to a roster.

Detection
---------

| Signal | Points | Limit |
| --- | --- | --- |
| Distinct public skill topics | 5 per topic | 25 |
| Distinct achievements earned in the last 90 days | 10 per achievement | 30 |
| New skill topics since a recorded baseline | 10 per topic | 30 |
| Last 30 days' achievement count minus the previous 30 days | 5 per positive increase | 15 |

The score is capped at 100. Qualifying requires at least 45 points, two distinct
skills, at least one recent dated achievement, and positive skill or achievement
growth. Missing longitudinal data earns zero skill-growth points, with an explicit
explanation. Skill baselines must be 7–90 days old. Daily snapshots retain the
first observation that day; repeated runs do not manufacture growth.

Evidence reads load only scoring fields, one usable baseline, and at most 501
skills or recent achievement rows per profile. More than 500 skills or 500 recent
achievement rows pauses automatic matching with an explicit explanation rather
than assigning a misleading score from truncated evidence.

Skill aliases reuse existing topic normalization, so replacing AI with Artificial
intelligence does not count as a new skill. Duplicate normalized achievement
titles with the same earned date count once. Missing, future and out-of-window
earned dates are ignored, regardless of when an achievement was uploaded.
Achievement growth compares two equal 30-day windows and never awards negative
points. Followers, likes, messages, private portfolio/performance activity,
location, demographics and verification status are not score inputs. Sensitive
skill topics use the existing recommendation sensitivity exclusions.

Matching and consent
--------------------

Discovery and alerts have separate explicit consent, both off by default. Existing
profiles and other recommendation consent are not changed or enrolled. Active
public ATHLETE accounts (Awinlink's account role for talents of every category)
can enable discovery. Organizations, scouts and coaches choose a category and
up to 50 skill interests. Both category and normalized skill overlap must match;
there are no unrelated fallback recommendations. Results rank by evidence score
and use talent ID for stable ties. Lists return at most 50 matches.

Organization recipients must select an organization for which they currently
have VIEW_TALENTS capability. Existing membership suspension, role reduction,
inactive organization and legacy-owner rules apply. Staff/admin flags do not
bypass these checks. Active coach/scout profiles may use personal matching.
Inferred-interest consent, biographies and private behavior are not used to
configure recipients' interests.

Every match read and alert creation rechecks public visibility, discovery consent,
active accounts, current organization access and both directions of account
blocks. Organization matching also respects the organization's owner's blocks.
The owner's own assessment is available only to that owner while eligible.
Other users receive coarse evidence counts, matched public skills and plain
language explanations, never raw snapshots, achievement descriptions or contact
details. HTTP responses are private and non-cacheable.

Turning off discovery removes snapshots, alert associations and the associated
notifications immediately. Saving a private talent profile withdraws discovery
consent; making it public later does not re-enroll it. Bulk database changes that
bypass signals are still enforced at match/delivery time and purged on the next
batch run. A dedicated Turn off Rising Talent action works even after organization
access is revoked or stored matching choices become invalid. It disables both
consent flags; individual flags can also be changed independently through the API.

Alerts and operation
--------------------

Alerts reuse the central notification service, Web Push, native Expo transport
and authenticated websocket delivery. Notifications contain a generic message
and a Rising Talent destination, without talent names, talent IDs, skills or
scores. Native notification taps, in-app alerts and web links open the current
privacy-checked Rising Talent list. Delivery checks eligibility again after
commit, and native transport checks it again before sending.

There is at most one alert per recipient/talent/calendar week and five new alerts
per recipient/day. Unique database constraints and consent-row locks protect
duplicate job execution. Withdrawal removes talent associations and notifications,
while an opaque keyed-hash receipt retains rate limits until expiry. Repeated
opt-in cycles cannot bypass another user's alert limits. Suppressing notifications does not prevent a recipient
from browsing their currently relevant public matches. Alert associations and
baselines older than 90 days are removed by the batch command.

After a later deployment/migration, an operator can schedule a daily execution:

```
python manage.py detect_rising_talent --dry-run
python manage.py detect_rising_talent
python manage.py detect_rising_talent --batch-size 100 --max-recipients 1000
python manage.py detect_rising_talent --recipient-after LAST_COMPLETED_PREFERENCE_ID
```

Dry runs compute counts without writes, baseline creation or notification delivery.
Normal runs record eligible baselines, prune expired/ineligible evidence and
create relevant opted-in alerts. No scheduler, deployment, production command
or application database migration has been executed as part of this change.

The job emits a checkpoint after each completed recipient group. Resume after
that preference ID; an interrupted group can be repeated safely. Recipient and
candidate groups are bounded at 100. Scoring is shared within a recipient group;
only five compact candidate IDs per recipient are retained. Already-notified
weekly candidates are excluded before selection, so they do not starve new
matches. Alert creation and delivery recheck one current candidate rather than
recomputing a global ranking. Daily quotas use indexed timestamp ranges and
respect local daylight-saving boundaries. Deduplication also honors configured
`SECRET_KEY_FALLBACKS` after signing-key rotation; retain the relevant fallback
while that week's receipts remain applicable.

Interfaces
----------

* Web: `/rising-talent/`, linked from the sidebar, with preferences, the owner's
  assessment, scored matches and explanations.
* Mobile: Rising Talent in Profile, plus notification routes and a protected screen.
* `GET/PATCH /api/rising-talent/preferences/`: authenticated user's settings only.
* `GET /api/rising-talent/options/?q=...`: category choices, searchable non-sensitive
  skills (50 per query) and organizations visible to the current account.
* `GET /api/rising-talent/matches/`: current matches and the user's own eligible
  assessment, including version, score components, thresholds and explanations.

Validation
----------

```
python manage.py test recommendations.test_rising_talent recommendations.test_interest_learning recommendations.test_unified learning.test_classroom_notifications notifications.tests organizations.test_profile_badges --settings=config.rising_talent_test_settings
node --test mobile/tests/rising-talent.test.cjs mobile/tests/organization-rosters.test.cjs mobile/tests/native-calls.test.cjs
```

The dedicated test settings use an in-memory SQLite database, in-memory media,
local caches and plain static storage. They do not need collected production
assets. Run the mobile TypeScript check from `mobile` with
`node node_modules/typescript/bin/tsc --noEmit`.

The thresholds are explicit initial heuristics. A future evaluation should use
reviewed outcomes and category-specific error analysis before interpreting these
scores as evidence of real-world potential. The [job audit](rising-talent-job-audit.md)
adds disposable PostgreSQL concurrency checks and a synthetic scale fixture.
Real-device push delivery still requires a separate environment check; mocked
transport does not establish that property.
