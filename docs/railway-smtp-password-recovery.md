# Railway SMTP configuration for password recovery

For Railway Free, use the [Resend HTTPS setup](railway-resend-password-recovery.md)
and `deploy/email/railway-resend.env.example`. The SMTP instructions below remain
available for deployments whose Railway plan supports SMTP.

Prepared 2026-10-18. Local changes only. No Railway variables changed, SMTP
connection attempted, real message sent, provider account changed, or deployment
performed during this task.

## Current production status

A read-only Railway variable inspection at 2026-10-18 19:44:45 UTC found:

| Setting | Configured? |
| --- | --- |
| EMAIL_HOST | No |
| EMAIL_HOST_USER | No |
| EMAIL_HOST_PASSWORD | No |
| DEFAULT_FROM_EMAIL | No explicit value; existing code fallback only |
| EMAIL_SENDER_DOMAIN | No |
| PASSWORD_RESET_BASE_URL | No explicit value; existing HTTPS Railway-domain fallback |
| REDIS_URL | Yes; value withheld |

Effective default transport is STARTTLS on port 587, not implicit TLS. The SMTP
configuration is **not ready**. Sender ownership/provider authorization, DNS
authentication, TLS connectivity, SMTP authentication and inbox delivery remain
unverified. A valid-looking fallback address is not evidence of a verified sender.
The inspection used Railway variables, not the running container's filesystem.
Presence-only findings are stored locally in `.audit-email/railway-configuration.json`.

Railway permits outbound SMTP only on Pro and higher plans. Free, Trial and Hobby
need an HTTPS transactional email integration instead. The current project plan
was not inspected; confirm eligibility before planning SMTP. Do not upgrade or
redeploy as part of this no-change task. [Railway outbound networking](https://docs.railway.com/networking/outbound-networking)

## Variable names and secure values

The ready-to-fill template is `deploy/email/railway.env.example`. It is not an
applied configuration; credentials are blank and the `.example` domains must be
replaced. Put settings on the **awinlink backend service in production**, not in
Expo, `EXPO_PUBLIC_*`, a public client bundle, shell arguments, or committed `.env`.
Do not paste credentials into chat or diagnostic output.

| Variable | Required value / role |
| --- | --- |
| DEBUG | `False` so production selects Django's SMTP backend |
| EMAIL_HOST | Transactional provider SMTP hostname, without scheme, port or credentials |
| EMAIL_PORT | `587` for the Postmark STARTTLS example |
| EMAIL_USE_TLS | `True` for STARTTLS |
| EMAIL_USE_SSL | `False` for STARTTLS; never enable both TLS flags |
| EMAIL_TIMEOUT | `10` seconds; parser accepts bounded values from 1 through 60 |
| EMAIL_HOST_USER | Secret: provider's SMTP username/access key |
| EMAIL_HOST_PASSWORD | Secret: provider's SMTP password/secret key |
| DEFAULT_FROM_EMAIL | Explicit provider-approved mailbox, e.g. `Awinlink <recovery@your-real-domain>` |
| EMAIL_SENDER_DOMAIN | Exact domain after `@` in that approved sender; used by the readiness checker |
| PASSWORD_RESET_BASE_URL | Canonical HTTPS web origin, without path, query, fragment or embedded credentials |
| PASSWORD_RESET_TIMEOUT | `3600` seconds, unless an explicitly reviewed expiry is needed |
| REDIS_URL | Keep the existing shared Redis service reference for cross-worker recovery limits |

Django's standard SMTP backend supports transactional SMTP without a vendor SDK.
For a concrete Postmark configuration use `smtp.postmarkapp.com`, STARTTLS/587
(2525 is another supported option), and credentials scoped to its transactional
message stream. A stream SMTP token supplies an Access Key as username and Secret
Key as password. With a Server API Token instead, Postmark uses it for both
fields; its Account API Token is not the SMTP credential. Default transactional
stream is `outbound`. [Postmark SMTP documentation](https://postmarkapp.com/developer/user-guide/send-email-with-smtp)

Do not use `smtp-broadcasts.postmarkapp.com` for recovery. Postmark does not support
implicit TLS/465. Other providers may support implicit TLS: for those, use their
documented host with `EMAIL_USE_SSL=True`, `EMAIL_USE_TLS=False`, and port 465.
The parser selects 465 automatically when SSL is enabled and no port is supplied.
[Postmark connection requirements](https://postmarkapp.com/support/article/common-smtp-connection-errors)

## Sender verification boundary

Before a later authorized configuration change, the operator must confirm the
exact From address or sending domain is approved in the provider dashboard and
SMTP access is enabled. Review the provider-generated DKIM, custom Return-Path
and DMARC configuration with the domain administrator. Do not invent DNS values
or replace existing records blindly. Postmark documents its authentication and
domain verification process in [domain verification](https://postmarkapp.com/support/article/how-do-i-verify-a-domain).

The local checker validates one mailbox, forbids CR/LF/header injection and example
senders, requires an explicitly configured sender, and compares its domain with
EMAIL_SENDER_DOMAIN. That comparison is only a configuration consistency check;
it does not establish domain ownership or provider approval. No provider API,
DNS mutation, sender-verification message or verification-triggering endpoint
was called.

## Safe readiness check

Offline default:

```powershell
.venv\Scripts\python.exe -B manage.py check_email_delivery --json
```

This command:

- Loads configuration without migration checks or database queries.
- Checks SMTP backend, required credentials, TLS mode/port consistency, finite
  timeout, From mailbox/domain and the canonical HTTPS recovery origin.
- Renders plain-text/HTML recovery templates using a dummy account and an invalid
  dummy token, then builds MIME in memory with a fixed Message-ID to avoid DNS.
- Never opens SMTP, resolves a server, reads a user, generates a usable token,
  calls send(), or outputs a credential, sender address, reset link or mail body.
- Returns a nonzero status when not ready. JSON includes fixed issue codes,
  `emails_sent: 0`, `sender_authorization: not_verified_with_provider` and
  `inbox_delivery: not_tested`.

Configuration parse errors name the invalid setting without repeating its value.
Both TLS flags, malformed booleans, invalid port and unbounded timeout fail early.

An **optional** future operator command can verify transport without sending:

```powershell
.venv\Scripts\python.exe -B manage.py check_email_delivery --smtp-handshake --json
```

It refuses invalid configuration first, uses certificate/hostname verification
with TLS 1.2 or newer, and performs only EHLO, STARTTLS where applicable, AUTH,
NOOP and QUIT. It has no recipient/send option and never issues MAIL FROM,
RCPT TO, DATA, VRFY, sendmail or send_message. Failure replies and exception text
are suppressed. It authenticates to the provider and may create provider access
logs; it does **not** prove sender authorization or message delivery. This task
tested that path using mocks only, never a live SMTP server.

`scripts/check_railway_email_configuration.py` performs presence-only Railway
metadata inspection without importing Django settings or connecting to SMTP.
It requires explicit project/environment/service IDs, verifies production service
identity, captures variable output only in memory, and saves only redacted results.
It does not change settings or run the handshake.

No readiness result from this task should be described as a successful delivery
test. A real inbox test requires a separate explicit request.

## Validation

The 26 focused SMTP/deployment tests passed. They cover STARTTLS, implicit TLS,
mutually exclusive flags, invalid numeric/boolean values, sender/domain matching,
header injection, provider endpoint/port selection, missing credentials, template
errors and diagnostic redaction. Mocked protocol tests verify authentication occurs
after verified TLS and no message-submission methods are called. A SimpleTestCase
checks that the default command performs no SMTP connection, DNS lookup, email
send or database access.

The unconfigured local offline check correctly returned nonzero and rendered the
email templates successfully. Production metadata inspection also correctly
returned nonzero for missing configuration, without attempting SMTP.

The broader accounts/API/deployment regression run completed 88 tests: 86 passed
and the two PostgreSQL-only reset-race tests were skipped on SQLite. No new model
or migration was introduced. `git diff --check` passed.
