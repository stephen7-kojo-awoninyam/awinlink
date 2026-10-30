# ADMIN role escalation fix

The public onboarding role endpoint no longer accepts ADMIN or arbitrary role
values. Registration and onboarding share an explicit allowlist: ATHLETE,
ORGANIZATION, SCOUT and COACH. Public registration (web, REST and Google signup)
also rejects submitted staff, superuser, active-state, group and permission fields.
The registration API keeps its existing explicit ADMIN rejection and uses the
shared registration form for the other authorization checks.

Onboarding now requires an authenticated session and GET/POST, keeps CSRF
protection, and validates submitted roles with RoleSelectionForm. Invalid POSTs
return 400 with a visible error. The legacy TALENT button maps to ATHLETE;
accounts previously saved with the legacy TALENT value can complete onboarding.
Coach/scout redirects use the existing category-selection routes.

The endpoint locks and re-reads the current user before updating only the role
column. Existing ADMIN accounts, staff and superusers return to the dashboard
without changing their role or permissions. A concurrent trusted admin promotion
therefore cannot be overwritten by a stale onboarding request. Unknown existing
role values require review instead of being silently reclassified.

The API profile serializers/field allowlists and JWT authentication already use
database authority rather than submitted role claims. Regression tests now verify
talent, organization, coach/scout and account API requests cannot mutate that
authority; forged role claims and refresh-request fields do not grant moderation.
Legitimate role-based admins retain login, Google login and moderation access even
when they are not Django staff/superusers. Staff/superuser flags, groups and direct
permissions are preserved.

## Scope and data preservation

This fixes S01 from the security audit. It does not address the other ranked
findings. No account rows, courses, rosters, sessions or existing administrators
were modified, and no schema migration was added. Trusted server-side provisioning
of administrators remains supported.

Existing ADMIN assignments cannot be classified as legitimate or malicious from
the role value alone. This change does not automatically demote or revoke existing
administrators; historical assignments require a separately authorized review.

Nothing was deployed. The fix is local until a separately requested deployment.

## Validation

Security acceptance tests live in `accounts/test_role_security.py`. The original
S01 exploit characterization was removed from the open-findings reproduction
module and replaced by these denial and legitimate-access checks.

The tests cover CSRF-valid escalation, malformed/admin role variants, permission
injection, session authentication, public roles, legacy TALENT values, registration
and Google signup, profile API mass assignment, JWT claims, legitimate admins,
stale request objects and a PostgreSQL row-lock concurrency scenario.

Commands (isolated fixtures only):

```powershell
.venv\Scripts\python.exe -u -B scripts/test_security_phase1.py accounts api onboarding dashboard organizations.test_permissions organizations.test_workflow_permissions config.test_deployment --fast
.venv\Scripts\python.exe -u -B scripts/rising_talent_audit.py accounts.test_role_security
.venv\Scripts\python.exe -u -B manage.py makemigrations --check --dry-run --settings=config.rising_talent_test_settings
```

The final PostgreSQL security suite passed: **23 tests**, including concurrent
trusted administrator promotion, with no skips. The broad SQLite regression run
passed: **222 tests, 3 skipped**. SQLite cannot
exercise row locks; the PostgreSQL runner verifies that the local cluster's data
directory is inside this workspace, creates a unique disposable test database,
and destroys it afterwards. PostgreSQL tests use the regular password hasher.
Migration drift check: **no changes detected**. Scoped whitespace checks passed.
