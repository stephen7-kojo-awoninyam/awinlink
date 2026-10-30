Organization badges for talents, coaches and scouts
==================================================

Roster entries now link to exactly one talent, coach or scout profile. The
existing talent IDs, roster IDs, consent statuses and history rows are preserved
by `organizations.0014_coach_scout_roster_badges`. No accounts or profiles are
created when adding an unclaimed entry. Username linking resolves the account's
current role and requires an active account with its corresponding profile.

All Sports, Science and technology, Arts and Others profiles are supported;
neither organization category nor profile category limits roster affiliation.
Use the existing roster forms on web or mobile to nominate a profile. Its owner
can confirm, decline, remove and read history through the existing personal tags
workspace. Organization membership alone cannot confirm a person's badge.
Existing recruitment capabilities and organization membership checks still
govern management; staff and administrator flags do not bypass them.

Only confirmed affiliations for active organizations and active profile owners
appear in public badge lists. Talent profile visibility and blocks remain
enforced. Coach and scout profiles have no separate visibility setting; their
explicit affiliation confirmation permits badge publication. Declining or
removing an affiliation hides it without deleting history. Linking an unclaimed
entry, or issuing a new request after a decline/removal, requires fresh consent.

The existing talent badge API remains compatible. The new authenticated endpoint
`GET /api/organizations/profile-badges/<user_id>/` returns confirmed affiliations
for any supported profile type, using an account ID. Organization public rosters
include every supported profile type. Responses add `coach_id`, `scout_id`,
`user_id`, `profile_type`, `profile_name`, `category` and `category_name`. Public responses omit
private actions and history. Private roster/history endpoints retain their
existing URLs and action payloads.

Web badges appear on coach profiles, scout dashboards and organization profiles.
Mobile badges appear on account profiles and organization profiles, with the same
personal confirmation and history controls. Existing talent agreements remain
talent-scoped; coach/scout entries do not offer talent-only agreement links.

The migration blocks reversal when coach/scout links exist, including removed
entries, to avoid losing their owner, consent and history links. It does not
rewrite or delete existing roster records.

Checks:

* `python manage.py test organizations.test_profile_badges organizations.test_rosters organizations.test_agreements`
* `node --test mobile/tests/organization-rosters.test.cjs mobile/tests/organization-rosters-web.test.cjs`
* In `mobile`, `node node_modules/typescript/bin/tsc --noEmit`

Changes are local. No deployment or application database migration was performed.
