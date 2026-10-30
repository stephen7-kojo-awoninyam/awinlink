# Admin login and production settings hardening

S10 and S11 are remediated in the local working tree. No deployment, live Railway
configuration change, credential rotation or application data migration was
performed. Existing administrators, passwords, permissions, sessions, courses and
files are preserved. No schema migration is required.

## Login protection

The default Django admin uses SecureAdminSite via AdminConfig.default_site. The
existing model registry, admin URL namespace, forms and staff/superuser permission
rules are retained. An application ADMIN role alone still does not grant Django
staff access.

These password sign-in routes now consume the same `login` policy and cache keys:

* `/admin/login/`
* `/accounts/login/`
* `/api/auth/login/`
* `/delete-account/sign-in/` (the ancillary Django LoginView could otherwise bypass
  the admin budget)

The default budget remains 60 attempts per IP and 10 per normalized identity per
900-second fixed window. Unicode NFKC normalization and case folding match the
existing web/API policy. Long submitted identities are bounded before normalization.
Counter keys contain salted digests, not raw usernames, IPs or passwords.

CSRF protection runs before credential checks. GET/HEAD do not consume attempts.
Exhausted POST requests return 429 with Retry-After and no-store headers before
password authentication. Missing/invalid policies and unavailable required cache
protection return controlled 503 responses without provider URLs or credentials.
Budgets expire; no account is permanently locked, demoted or disabled. Existing
successful-login redirects and account-deletion sign-in behavior are retained.

Production requires a supported shared atomic cache: Django's built-in Redis or
Memcached backend. Process-local, file and database cache backends are not accepted
as production authentication counters. Redis remains the configured Railway path.
This does not replace edge capacity limits or administrator MFA/SSO.

## Explicit environment mode

| Environment | Result |
| --- | --- |
| AWINLINK_ENV omitted | Production; DEBUG defaults false; explicit strong SECRET_KEY required |
| AWINLINK_ENV=production | Same production policy |
| AWINLINK_ENV=development | Deliberate local development; DEBUG defaults true |
| Railway/Render runtime metadata | Production automatically; development mode and DEBUG=true rejected |
| Invalid/blank mode or invalid boolean | Startup error with the supplied value withheld |

The same settings path protects WSGI, ASGI and management/worker entrypoints.
DEBUG=true alone is no longer a development opt-in. The isolated recommendation
sandbox settings explicitly opt into local development and reject production mode.
Local fixture/audit wrappers also declare their development mode explicitly.

Local PowerShell example:

```powershell
$env:AWINLINK_ENV = 'development'
$env:DEBUG = 'true'
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Do not set development mode on a hosted service. No `.env` file was edited by this
change. Production commands must receive the same production configuration as the
application; missing/weak secrets no longer silently select development behavior.

## Railway compatibility and production transport

Railway needs no new mode flag: its runtime metadata selects production. Existing
Railway host/origin generation, canonical recovery origin, Redis settings, email
provider selection, Cloudinary selection and HTTPS proxy behavior are preserved.
Production always enables HTTPS redirects, secure session/CSRF cookies, HttpOnly
session cookies and Lax SameSite behavior. Wildcard ALLOWED_HOSTS and HTTP CSRF
trusted origins are rejected. Existing strong-secret validation remains in effect.

Forwarded TLS headers are trusted automatically on Railway/Render, preserving
HTTPS termination without redirect loops. Generic hosts default to not trusting
client-supplied forwarded TLS headers. When an operator controls a sanitizing proxy,
`AWINLINK_TRUST_PROXY_HEADERS=true` enables the standard X-Forwarded-Proto handling.
The Django upstream must not be exposed directly in that configuration; the proxy
must strip/overwrite spoofed TLS headers. Login IP identity still uses the existing
`PASSWORD_RESET_TRUSTED_IP_HEADER` / `PASSWORD_RESET_TRUSTED_PROXY_COUNT` policy;
the TLS option does not automatically trust arbitrary forwarded IP headers.

Railway/Render retain the existing one-year HSTS, include-subdomains and preload
defaults. Generic production hosts use one-year HSTS with include-subdomains and
preload disabled by default. The latter two settings can be explicitly configured
with boolean SECURE_HSTS_INCLUDE_SUBDOMAINS and SECURE_HSTS_PRELOAD values after
domain readiness is established. Browser HSTS state cannot be recalled by a code
rollback. Actual ingress/header behavior was not tested against a live provider.

See [Django's deployment checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/)
and [proxy/security guidance](https://docs.djangoproject.com/en/6.0/topics/security/).

## Checks and validation

Deployment security checks report `awinlink.E001` for an unsupported/missing shared
authentication cache and `awinlink.E002` if shared protection is disabled in
production. They inspect configuration without connecting to Redis. Runtime login
still fails closed if a configured cache is unavailable. A healthy live connection
and correctly sanitized ingress remain operational requirements.

Before a separately authorized release, run `manage.py check --deploy --fail-level
ERROR` with the intended production settings. This task instead runs the security
checks with synthetic Railway settings and blocks Redis network commands during
the check itself.

Regression coverage includes CSRF, normal staff/superuser login and permissions,
nonstaff ADMIN denial, registry/URL preservation, cross-route normalized budgets,
untrusted proxy headers, expiry, outage/error redaction, unsafe cache backends,
invalid policy, production mode/secret/HTTPS settings and independent WSGI/ASGI/CLI
startup. The broader suite also checks prior role/privacy controls and socket
revocation. Older privacy assertions were aligned with no-store/private headers
and hidden-object 404 responses. The idle-socket expiry fixture now loads ASGI
before minting a short token and allows a reliable connection window; application
token lifetimes and expiry enforcement are unchanged.

Validation completed: the 478-test backend regression run passed with eight skips;
the isolated two-worker Redis test passed separately. Synthetic Django deployment
security checks, fresh-process WSGI/ASGI/command checks and whitespace checks passed.
Migration drift check reported no changes. No live ingress/provider testing was done.

Run the isolated backend suite with the workspace Python:

```powershell
.venv\Scripts\python.exe -u -B scripts/test_security_phase1.py accounts config dashboard api core organizations.test_permissions organizations.test_workflow_permissions messaging.test_socket_revocation messaging.test_signaling_security learning.test_classroom_security learning.test_classroom_signaling talents.test_verification_security portfolio --fast
.venv\Scripts\python.exe -u -B scripts/test_admin_security_redis.py
.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.rising_talent_test_settings
```

The Redis runner uses the existing workspace test binary, creates a password-
protected loopback-only memory fixture, disables persistence, caps memory and
removes only its own temporary fixture. It never uses the ordinary REDIS_URL or
stops an existing service. Two separate Django processes synchronize before racing
10 requests against one three-attempt identity budget: exactly three requests
reach mocked password verification, and seven receive 429. All requests are
in-process test HTTP calls; no live admin account or deployed service is exercised.
