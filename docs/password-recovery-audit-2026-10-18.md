# Forgot Password audit and fixes

Date: 2026-10-18. Web and Expo changes are local only. Nothing deployed; no
production settings or data changed; no production email sent.

## Findings and changes

The existing implementation already used Django's password-reset token generator
and password forms. Web recovery had no rate limit; the API throttle was separate
and depended on a process-local default cache. Email links used the request host,
the web email used an HTML template as its plain-text body, API confirmation did
not lock the account before checking the token, and the mobile screen did not
handle new links arriving while mounted or provide a completed state.

Both channels now share recovery policy in `accounts/recovery.py`:

- Django `default_token_generator` tokens and `SetPasswordForm` validation.
  Expiry defaults to one hour (`PASSWORD_RESET_TIMEOUT=3600`). Changing password,
  email or login state invalidates old tokens according to Django's token rules.
- Recovery uses the registered account email, case-insensitively, for active
  accounts with usable passwords. It never treats a username as an email or sends
  recovery mail to an alternate address supplied by the caller.
- Known, unknown, inactive and unusable-account email requests have the same
  success response. SMTP failures also preserve that response and log only a
  constant warning without recipient, token, password or exception details.
- Web/API share fixed-window limits: five requests per client address/hour,
  three deliveries per normalized email/hour, and twenty confirmation attempts
  per client address/15 minutes. Email suppression remains a generic success;
  client-address limits return 429 with Retry-After. Redis failures fail closed
  with a generic 503. Identifiers in cache keys are keyed hashes, not raw emails.
- When `REDIS_URL` is configured, a dedicated Django Redis cache alias supplies
  atomic counters shared across workers. Development falls back to default
  cache; a multi-worker deployment must use a shared cache.
- Email links use trusted `PASSWORD_RESET_BASE_URL`, never the request Host or
  forwarded host. Production links require an HTTPS origin. Mail has both plain
  text and HTML, expiry instructions, and mobile/browser options.
- PostgreSQL account row locks span token recheck, password validation and save
  on both web and API. Two concurrent consumers cannot both succeed.
- Web retains Django's session-held reset token and redirect to a URL without
  the raw token. Recovery responses use no-store and no-referrer protections;
  web forms retain CSRF protection. API recovery requires no existing session.
- Password size is bounded, confirmation must match, and all configured Django
  password validators apply. A reset does not automatically log the account in.
  Existing JWT revocation settings reject old access/refresh tokens after reset.

Generic content does not make SMTP delivery constant-time. Delivery is still
synchronous and registered/unknown requests can differ in latency. A strict
timing-enumeration requirement would need a durable background mail queue;
this implementation does not claim constant-time account recovery.

## Routes and UI

| Purpose | Route |
| --- | --- |
| Web email request | `/accounts/password-reset/` |
| Web generic sent page | `/accounts/password-reset/done/` |
| Web email-token link / new-password form | `/accounts/reset/<uidb64>/<token>/` |
| Web completed page | `/accounts/reset/done/` |
| Public API email request | `POST /api/auth/password-reset/` with `email` |
| Public API confirmation | `POST /api/auth/password-reset/confirm/` with `uid`, `token`, `new_password1`, `new_password2` |
| Expo screen | `/password-reset`; supports `awinlink://password-reset?uid=...&token=...` |

Existing route names remain compatible. Expo has request, sent, new-password,
manual-code fallback and completed states. Deep links arriving while mounted
replace the old credentials and clear entered passwords; raw query parameters
are removed from navigation state. Normal deep links show password fields only.
Rapid repeated taps send one request. Success clears password/token state and
local auth credentials and offers sign-in. Invalid/expired links offer a new
request. Login screens already link to Forgot Password on both platforms.

The custom app scheme is retained for installed apps, with an HTTPS browser
fallback. This work does not provision verified universal/app links or change
production domain associations.

## Production email configuration verification

Read-only Railway variable inspection of `awinlink` in `production` reported:

| Setting | Observation |
| --- | --- |
| `EMAIL_HOST` | Not configured |
| `EMAIL_HOST_USER` | Not configured |
| `EMAIL_HOST_PASSWORD` | Not configured |
| `DEFAULT_FROM_EMAIL` | Not explicitly configured; code has a fallback sender |
| `REDIS_URL` | Configured; value not disclosed or tested against production |
| `PASSWORD_RESET_BASE_URL` | Not explicitly configured |
| SMTP defaults | Port 587, STARTTLS enabled, implicit SSL disabled |
| DEBUG variable | Not explicitly enabled |

**Email delivery is a deployment blocker:** the Railway SMTP configuration is
incomplete. No SMTP authentication, sender authorization, DNS records or inbox
delivery was tested. The presence of a fallback sender does not prove it is
authorized by an email provider. Runtime container configuration was not accessed.
Sanitized presence-only evidence is in
`.audit-password-reset/production-email-config.json` (local, ignored by Git).

Before a separately authorized deployment, configure provider-approved SMTP
host, credentials and sender, and explicitly set the canonical HTTPS
`PASSWORD_RESET_BASE_URL`. Do not put mail credentials in Expo public variables.
Use either STARTTLS/587 or implicit TLS/465 as required by that provider. The
updated settings support `EMAIL_USE_SSL`, select the appropriate default port,
disable STARTTLS by default when implicit SSL is selected, and set a ten-second
SMTP timeout. Do not explicitly enable both TLS modes.

Railway's edge supplies `X-Real-IP`; recovery trusts that header by default only
in a Railway environment. Other deployments default to REMOTE_ADDR and may opt
into a known sanitizing proxy topology using `PASSWORD_RESET_TRUSTED_IP_HEADER`
or `PASSWORD_RESET_TRUSTED_PROXY_COUNT`. Do not expose a direct untrusted path
that can forge the selected header. See [Railway's documented request headers](https://docs.railway.com/networking/public-networking/specs-and-limits).

After configuration, a separately authorized staging/device test should confirm
actual inbox arrival, sender identity, browser link, installed-app link and token
expiry. No delivery or configuration change was made during this audit.

## Validation

- PostgreSQL 17.11: 69 accounts/API/deployment tests passed, including two
  simultaneous API confirmations and a web-versus-API token race. Only disposable
  loopback audit databases were used.
- Expanded recovery tests cover registered/unknown/inactive/unusable accounts,
  canonical email links despite an untrusted Host, multipart mail, mail failure
  redaction, shared web/API limits, per-email suppression across IPs, cache failure,
  malformed payloads, password policies, expiry, token tampering, swapped accounts,
  email/password changes, single use, CSRF, no-store/no-referrer and web completion.
- Mobile suite: 74 passed, two existing real-browser tests skipped. All seven
  focused recovery interaction tests passed again after the final screen changes.
- Expo TypeScript check passed. No emulator/physical-device or SMTP delivery test
  was performed.
- No account model changes or new database migration are required.

Commands used:

```powershell
.venv\Scripts\python.exe -u -B scripts/vc_audit.py test accounts api config.test_deployment --noinput
# PostgreSQL run used an explicit loopback AWINLINK_AUDIT_POSTGRES_URL.
npm.cmd --prefix mobile test
npm.cmd --prefix mobile run typecheck
```
