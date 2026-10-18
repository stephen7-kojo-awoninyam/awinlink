# Resend HTTPS password recovery on Railway Free

Prepared 2026-10-18. Code and example configuration are local only. No provider
API request, real email, production configuration change or deployment occurred.
All delivery-path tests use mocked HTTP responses.

Railway Free, Trial and Hobby block outbound SMTP but support transactional email
through HTTPS APIs. This transport calls Resend's fixed
`https://api.resend.com/emails` endpoint, without using SMTP or requiring an SMTP
plan upgrade. [Railway outbound networking](https://docs.railway.com/networking/outbound-networking),
[Resend API](https://resend.com/docs/api-reference/introduction).

## Railway backend environment variables

Use `deploy/email/railway-resend.env.example` as a template. It has a blank secret
and non-working `.example` domains; replace these in a separately authorized
configuration change. No values were applied to Railway during this task.

| Name | Purpose |
| --- | --- |
| EMAIL_PROVIDER | Set explicitly to `resend` to select `accounts.email_backends.resend.EmailBackend`. |
| RESEND_API_KEY | Secret Resend sending API key, scoped to the verified sending domain where possible. |
| RESEND_TIMEOUT | `10` by default; accepted range 1–60 seconds. |
| DEFAULT_FROM_EMAIL | Explicit, provider-approved From mailbox, optionally with the Awinlink display name. |
| EMAIL_SENDER_DOMAIN | Exact domain of that mailbox; checked for configuration consistency. |
| PASSWORD_RESET_BASE_URL | Real canonical HTTPS web origin, without credentials/path/query/fragment. |
| PASSWORD_RESET_TIMEOUT | Existing expiry, default `3600` seconds. |
| REDIS_URL | Existing shared Redis reference; retains cross-worker recovery rate limits. |
| DEBUG | `False` in production. |

Only store the API key on the backend service. Do not put it in Expo variables,
URLs, command arguments, source code or shared diagnostic output. Do not paste
credentials into chat. A key's presence alone never enables Resend delivery:
`EMAIL_PROVIDER=resend` is required. Existing defaults remain SMTP in production
and console in local development; `EMAIL_PROVIDER=smtp` remains available.
Unused SMTP host/credentials/TLS settings are not required or parsed for Resend.

The code uses Python's standard HTTPS client; no Resend SDK/dependency install or
database migration is required. No configurable API URL is provided, preventing
accidental routing of bearer credentials to another endpoint.

Before a future activation, verify the sending domain and intended From address
in Resend and restrict the sending key appropriately. The checker rejects the
shared `resend.dev` onboarding sender for recovery. Domain matching alone is not
evidence of provider verification. See [Resend key permissions](https://resend.com/changelog/new-api-key-permissions).
Disable provider open/click tracking for the
recovery sending domain so reset links and their tokens are not rewritten for
analytics; the backend does not add tracking or analytics parameters.

## Delivery and security behavior

The Django backend maps the existing plain-text and HTML content to Resend's
`text` and `html` fields. It supports normal To/Cc/Bcc, reply-to, safe custom
headers and ordinary file attachments. Bcc recipients remain separate from public
headers. Envelope/header injection is rejected. It never uploads templates to
the provider or generates a replacement token.

Authentication uses a bearer API key in the HTTPS Authorization header and an
application User-Agent. TLS certificate/hostname verification is mandatory, with
TLS 1.2 or newer. The client ignores ambient HTTP proxies and refuses redirects.
Response parsing is limited to 64 KiB and success requires a nonempty provider
message ID. No credential, recipient, email body, token, provider reply, or raw
network exception is logged or included in the raised error.
[Resend authentication](https://resend.com/docs/api-reference/introduction),
[send-email request format](https://resend.com/docs/api-reference/emails/send-email).

Each message object receives a random idempotency key that is reused when that
same object is submitted again. No automatic network retries or SMTP fallback
occur. A timeout can follow provider acceptance; idempotency is not a durable
cross-process job queue or a promise of inbox delivery.

Web/mobile recovery retains registered-email eligibility, generic responses,
shared rate limiting, canonical reset URLs, expiry, Django password validation,
single-use token invalidation, CSRF on web, sensitive-data protection and atomic
confirmation. Provider failures are swallowed by the existing recovery form with
one constant warning and the same public success response as an unknown email.
Delivery remains synchronous; generic responses do not imply constant-time
protection against timing-based account enumeration.

## Safe configuration check — no sending

With the intended environment configured locally or in a future approved
deployment, run:

```powershell
.venv\Scripts\python.exe -B manage.py check_email_delivery --json
```

For Resend the default check validates API-key syntax/presence, timeout, explicit
sender/domain consistency and canonical HTTPS origin. It renders both existing
templates and builds MIME entirely in memory with a dummy account and unusable
dummy token. It does not instantiate the delivery backend, perform DNS, read
accounts, open a socket, call Resend, or send an email. JSON contains only status
and fixed issue messages; `emails_sent` is always zero. Incomplete configuration
returns a nonzero exit code without exposing values.

`--smtp-handshake` is explicitly refused for Resend and does not fall back to
SMTP or an API request. There is no live Resend probe or send/test-recipient flag.
The read-only Railway metadata checker in
`scripts/check_railway_email_configuration.py` also recognizes `EMAIL_PROVIDER`
and reports only the presence of `RESEND_API_KEY`; it never contacts Resend.

A passing offline check does not authenticate the key, check account quota,
verify domain DNS/provider approval, or demonstrate inbox delivery. These remain
unverified. No production Resend activation or credential inspection was needed
for this implementation.

## Tests

The focused 47-test SMTP/Resend/deployment run passed. Coverage includes:

- Explicit backend selection, ignored SMTP values in Resend mode, redacted invalid
  settings, missing API key, sender/domain checks and rejected onboarding sender.
- Fixed HTTPS endpoint, bearer authentication, verified TLS, redirect refusal,
  disabled proxies, idempotency, multipart content and supported envelope fields.
- Header injection, oversized/malformed provider responses, 429/rejected responses,
  certificate failures, timeouts, fail-silent behavior and no automatic retries.
- Web/API recovery using mocked Resend delivery, existing templates, valid Django
  tokens, successful confirmation, replay rejection, unknown-account suppression,
  unchanged generic failure responses and secret-free warning logs.
- Offline configuration checking with no HTTP/SMTP connection, DNS, send call or
  account access. No real delivery API request is made by any test.

The broader regression run completed 109 tests: 107 passed and the two existing
PostgreSQL-only reset-race tests were skipped on SQLite. The offline command was
also run with Resend selected and an empty key; it correctly returned nonzero,
rendered the templates, and reported zero emails sent. Compilation and diff
checks passed. No account schema changes were introduced.

Run using the isolated audit test runner:

```powershell
.venv\Scripts\python.exe -B scripts/vc_audit.py test accounts.test_resend_email accounts.test_email_configuration config.test_deployment --noinput
```
