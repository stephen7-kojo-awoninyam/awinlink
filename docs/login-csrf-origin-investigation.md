# Login CSRF origin failure

The reported Railway rejection (`Origin checking failed - null`) occurs before
Django checks the submitted token. A secure cookie and rendered CSRF inputs
therefore do not prevent this failure.

`accounts/templates/accounts/base_auth.html` explicitly selected `no-referrer`.
Both login buttons submit ordinary same-origin POST forms. Under the Fetch
standard's [Origin header algorithm](https://fetch.spec.whatwg.org/#append-a-request-origin-header),
non-CORS POST requests (including form navigations) with that policy send
`Origin: null`. Browsers without an Origin header also lack the HTTPS Referer
needed by Django's fallback check. Incognito does not change this document policy.

The minimal fix changes that meta policy to `same-origin`. It preserves the
origin and Referer for internal submissions while withholding referrers from
external destinations. It also overrides the deliberately restrictive HTTP
Referrer-Policy on rendered Google/recovery pages that share this base template.
Their HTTP headers, redirect privacy and cache controls remain unchanged.

Inspected settings include explicit HTTPS trusted origins, Railway forwarded
HTTPS handling, secure cookies, and the enabled CSRF middleware. The configured
Railway hostname is already trusted; adding hostnames cannot make a literal null
origin valid. The login template contains two independent token-bearing forms.
The shared JavaScript does not intercept these submissions or rewrite origin
headers. The service worker only handles push and notification clicks, not fetch.
Application CSP sandbox headers are confined to protected upload responses;
the local login response has no sandbox CSP and has `X-Frame-Options: DENY`.

`accounts.test_login_csrf` uses `Client(enforce_csrf_checks=True)` with
`DEBUG=False`, secure cookies, and Railway-style forwarded HTTPS. It reproduces
the exact null-origin rejection on both endpoints, checks the rendered policy,
tests actual password login/session creation and Google initiation/session
binding (OAuth initialization mocked), tests Referer fallback, and verifies
foreign/null origins and missing/incorrect tokens or cookies still fail.
Run with the isolated in-memory settings:

```powershell
.venv\Scripts\python.exe -B manage.py test accounts.test_login_csrf accounts.test_google_auth accounts.test_password_recovery accounts.test_security_hardening config.test_deployment config.test_production_security --settings=config.rising_talent_test_settings --noinput
```

Production logs were supplied in the task; no production request capture,
Railway configuration inspection, real-browser reproduction, or external OAuth
exchange was performed. An upstream-injected CSP or another external request
transformation cannot be ruled out. Confirmation in production requires a fresh
page load and inspection of the form POST's Origin after the reviewed change
is released. No deployment or production data operations are part of this fix.

Validation: before the template change, the seven new tests produced exactly
one failure (rendered policy was `no-referrer`); both null-origin reproductions
passed. After the change, all 82 tests in the command above passed in 94.115s,
including all seven new regressions. Django system checks and `git diff --check`
also passed. The test database was destroyed by the runner.
