# Talent Market MVP

Record-only invoices, fees, refund credits and transaction APIs: [PAYMENT_FOUNDATION.md](PAYMENT_FOUNDATION.md).

Phase 2 implementation, API, permissions, user paths and migration notes: [PHASE_TWO.md](PHASE_TWO.md). No online payments.

Web entry: `/marketplace/` (sidebar). Native entry: Opportunities → Talent Market.
API prefix: `/api/marketplace/`; existing session/CSRF and JWT authentication apply.

- `GET markets/`: existing talent category choices as ecosystems and TalentDomain rows as subecosystem facets. No duplicate taxonomy or profile models. Domains are shared facets across ecosystems, consistent with the existing domain model.
- `GET/POST listings/`, `GET/PATCH listings/<id>/`: talent-owned listings. Publish with `status: PUBLISHED, consent: true`. Every published edit requires renewed consent. Pause with `status: PAUSED`. `mine=1` includes the owner's drafts.
- Listing filters: `q`, `ecosystem`, `subecosystem` (domain ID), `country`, `skill`, `work_type`, `experience`. Results use page-number pagination (24 per page).
- `GET/POST offers/`: immutable offer terms, listing ID, optional organization ID. Personal offers require a verified scout/coach profile and matching account role. Organization offers use the existing manage_recruitment capability, including its membership suspension and legacy owner policy.
- `GET/POST deals/<offer_id>/`: private room and final decisions. POST action ACCEPT requires `consent: true` from the listing talent. Talent may DECLINE; sender may WITHDRAW. Decisions are final. Acceptance records consent and decision timestamps, without a payment or legal-contract workflow.
- `POST deals/<offer_id>/messages/`: body text; author comes from authentication. Final rooms remain readable and cannot receive new messages.
- `GET deals/<offer_id>/` returns the latest 50 messages in insertion order, `next_before` (an exclusive message ID cursor, or null when exhausted), and participant-specific `permissions` for messaging and decisions. `GET deals/<offer_id>/messages/?before=<next_before>` retrieves older pages with the same `messages` and `next_before` shape. New arrivals do not shift older pages. Web and mobile offer **Load older messages** inside a deal room; sending a message reloads the newest page.

Search rejects invalid ecosystem/work-type/experience choices, nonpositive or oversized domain IDs, and oversized text with HTTP 400. Empty search controls are ignored. Mobile passes request objects to the shared API client, which serializes JSON once, preserving Unicode text.

Post-acceptance messaging audit: ACCEPTED, DECLINED and WITHDRAWN are read-only for both participants. No post-acceptance conversation or automatic handoff to direct messages exists. Web `/marketplace/` -> **My deal rooms** -> **Offer #...**, or mobile **Opportunities** -> **Talent Market** -> **My deal rooms** -> **Offer #...**, opens history. Both clients hide message/decision controls after a final decision. Acceptance does not expand access: sender capability revocation, inactive accounts and blocks still deny requests; organization teammates and admins gain no access. The existing row locks continue to serialize messages against final decisions.

Only explicitly published listings on public, active talent profiles appear in discovery. Drafts, paused listings, private/organization-only profiles, and blocked accounts are excluded. Room access belongs to the talent and the original sender; organization teammates and platform admins do not automatically gain access. Sender permissions are checked again on every room request. Blocks prevent either participant from opening the room.

Apply the included migration with `python manage.py migrate` when ready to use the feature locally. Existing data is not automatically published. TalentDomain entries are managed through the existing application; at least one is needed to create a listing. No payment, deployment, or existing-database migration was performed during implementation.

Tests: `python manage.py test marketplace`. Mobile: run TypeScript with `node node_modules/typescript/bin/tsc --noEmit` from mobile.

Regression checks: `.venv\Scripts\python.exe -u -B scripts/vc_audit.py test marketplace --noinput` uses an isolated in-memory SQLite database by default. From `mobile`, `node --test tests/marketplace*.test.cjs` exercises the actual mobile screen and shared JSON encoder with transport fixtures, plus web DOM controls with API fixtures. These checks do not replace native-device testing; PostgreSQL concurrency tests are skipped on SQLite.

Before upgrading an existing database from 0001 to 0002, run `python manage.py audit_marketplace_legacy --database default`. This read-only preflight prints counts and up to 20 IDs/groups per guard, then exits nonzero if any guard would fail. Duplicate counts are groups, not individual offers. On PostgreSQL it uses a repeatable-read, read-only transaction. A clean report is a snapshot: pause market writes and rerun immediately before migration.

Migration 0002 deliberately performs no data repair. Published listings without recorded consent, unknown statuses, duplicate pending personal/organization offers, or inconsistent decision/consent timestamps prevent the upgrade. PostgreSQL rolls the whole migration back on failure, including constraints already added. Valid rows, exact terms, messages and existing timestamps are preserved. Back up the database, review flagged rows with their owners, resolve duplicates through an explicitly authorized decision, and restore consent only from real evidence. Unpublish listings that lack consent through an authorized change; do not invent consent, silently select a winning duplicate, or delete deal history. Keep ambiguous accepted offers for owner review. Rerun preflight before retrying. Migration 0002 itself remains unchanged.

For the full PostgreSQL suite, set `AWINLINK_AUDIT_POSTGRES_URL` to a loopback URL with an `awinlink_audit_` database name and run the audit test command above. Django creates a separate `test_...` database. Set `TALENT_MARKET_TEST_CHROME` to an installed Chrome executable to include real web controls with PostgreSQL, session authentication and CSRF. The suite also uses real loopback HTTP login/JWT workflows, seeded 0001 migration upgrades/rollback checks, and concurrent offer/decision/message races. No deployed services or native devices are used.
