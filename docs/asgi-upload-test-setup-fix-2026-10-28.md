# ASGI upload regression and test database setup

Fixed locally on 2026-10-28. No deployment or production configuration/data changes.

## Cause and change

The readiness runner called `makemigrations --check --dry-run` before Django's test database setup. That command reads migration history and opens the initial `:memory:` SQLite connection. Django's SQLite backend deliberately ignores `close()` for in-memory databases. When the test runner switched the configured name to its shared test URI, the existing main-thread connection still pointed at the unnamed database. Migrations and test users were created there, while new ASGI worker connections opened the named database without tables. Real JWT authentication during multipart parsing then raised `no such table: accounts_user`, producing HTTP 500.

The readiness runner now executes the migration dry-run inside `DiscoverRunner.run_checks()`, after Django creates and migrates the test database. The first connection therefore uses the named shared test URI. Graph checks remain in place, and the migration command still checks model drift without writing migration files. There is no runtime upload/security bypass or application middleware change.

## Regression coverage

`config/test_http_limits.py` now exercises the real ASGI app with chunked multipart requests, real users and tokens, upload handlers and resource limits. Checks cover:

- A separate database worker can read the committed test user, detecting the original setup defect directly.
- A valid upload returns 201, preserves original bytes and releases the single global upload slot.
- Anonymous and invalid-token uploads return 401 without creating a post; denied requests release capacity.
- Session-authenticated uploads without CSRF return 403.
- Active file extensions and invalid video signatures return 400 with no-store responses.
- Body limits return 413 before multipart parsing.
- Shared byte quotas still return 429 with Retry-After.

HTTP header names are normalized in the test helper because matching is case-insensitive; application response headers are unchanged. Existing authentication, CSRF, signature validation, byte budgets, lease cleanup and fail-closed resource behavior remain enabled.

## Verification

The original single-test reproduction passed after moving the migration check. The focused run passed all 49 tests:

```text
.venv/Scripts/python.exe -u -B scripts/audit_production_readiness_local.py config.test_http_limits config.test_upload_security config.test_upload_quotas
```

Broader verification uses the default readiness suite:

```text
.venv/Scripts/python.exe -u -B scripts/audit_production_readiness_local.py
```

The final broader run completed **363 tests: 361 passed, two skipped, no failures or errors**. The skipped tests require the separate shared-Redis admin fixture. Migration graph conflicts remained empty, model drift was absent, and targeted diff whitespace checks passed. The local ASGI upload verification gate is cleared; the other production readiness gates remain open.

Local logs: `.audit-asgi-upload-focused-final.log` and `.audit-asgi-upload-broader-final.log`. The runner disables dotenv and outbound networking, preserves Windows runtime paths, and uses disposable in-memory SQLite/cache/Channels, temporary media and nondelivery email. These tests do not establish live PostgreSQL/Redis/TURN/CDN or Railway readiness.
