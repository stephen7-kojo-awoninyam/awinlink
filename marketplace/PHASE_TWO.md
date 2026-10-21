# Talent Market Phase 2

No payment collection, checkout, balances, payout or refund operations exist in this feature. Prices are agreed service prices; every booking reports `collection: NONE`.

## User paths

- Web: sidebar **Talent Market** (`/marketplace/`) -> **Create or edit my listing**. Configure QUOTE_ONLY/FIXED/HOURLY, currency, duration, preparation buffer and **Enable scheduled bookings**. Published changes require renewed consent. **Edit my listing** prefills the owner's current settings.
- Web: **My bookings and availability** (`/marketplace/bookings/`) -> **My availability** -> add explicit UTC-offset opening intervals and an IANA display timezone. Openings apply across all the talent's listings. Reserved openings cannot be deleted.
- Buyer: **Use listing** -> choose a free opening, review the displayed price/rate and duration, propose a price for QUOTE_ONLY, and **Send offer**. Listing revision and explicit-offset appointment start are required for booking-enabled listings. The resulting deal displays the immutable total and time. Talent explicitly accepts -> **Open booking**.
- Booking: participants see terms, total, schedule, activity/reasons, fulfillment chat and delivery versions. Talent can **Start work** at/after the scheduled start, then **Submit delivery**, optionally attaching one private file up to 2 MiB. Buyer can **Request changes** with a reason or **Confirm completion**. No time-based automatic completion exists.
- Either authorized participant can cancel a CONFIRMED booking before its scheduled start, with a reason. This releases the reservation and leaves the offer ACCEPTED. Work already started cannot be cancelled. Rescheduling requires an explicit cancellation and a new offer; no automatic replacement, dispute adjudication, organization handoff or no-show decision is implemented.
- After completion, only the original authorized buyer can leave one immutable rating/text review. Public publication is opt-in and can subsequently be withdrawn or granted. **View verified reviews** exposes only published, visible reviews on public active published listings, with generic reviewer labels and visibility-aware averages. Private booking details never appear in public review responses.
- Mobile: **Opportunities -> Talent Market** contains pricing, opening selection and structured offers. **My bookings and availability** opens `/market-bookings`, including activity, chat, delivery, private attachments and reviews. Android file saving asks for a destination; iOS uses the share sheet; web downloads a Blob. Artifact bytes are fetched through the same authorized API client, without credential-bearing public URLs.

## API

All paths are relative to `/api/marketplace/`. Session/CSRF and existing JWT authentication apply. Existing listing and offer endpoints are reused.

| Path | Operations |
| --- | --- |
| `listings/`, `listings/<id>/` | Existing create/PATCH with pricing, currency, duration, buffer and booking opt-in; `revision` is read-only |
| `offers/` | Existing POST plus `starts_at`, `expected_revision`, optional `negotiated_amount` for QUOTE_ONLY |
| `deals/<id>/` | Existing explicit-consent acceptance; a v2 acceptance creates one booking atomically |
| `availability/` | GET own paginated openings; POST an owner opening |
| `availability/?listing=<id>` | Paginated free intervals for a visible, enabled listing; subtracts reservations and buffers, without buyer metadata |
| `availability/<id>/` | Owner DELETE when no reservation overlaps |
| `bookings/` | Paginated bookings passing current participant authorization |
| `bookings/<id>/` | GET details/capabilities; POST START/COMPLETE/REQUEST_CHANGES/CANCEL |
| `bookings/<id>/messages/` | GET newest 50 fulfillment messages with exclusive `before` cursor; POST while nonterminal |
| `bookings/<id>/events/` | Paginated private action/reason history |
| `bookings/<id>/submissions/` | GET paginated newest delivery versions; talent POST summary and optional multipart artifact |
| `bookings/<id>/submissions/<submission>/artifact/` | Authorized attachment download; `?encoding=base64` provides authenticated mobile transport |
| `bookings/<id>/reviews/` | Buyer POST rating/text and explicit `publish`; PATCH publication visibility |
| `listings/<id>/reviews/` | Paginated publication-consented reviews and average, subject to listing/profile visibility and blocks |

ISO datetime input must include Z or an explicit offset. Openings start within the next 365 days and span at most 31 days. Service durations are 1–1440 minutes; buffers are 0–240 minutes per side. Fixed/hourly totals are computed server-side using Decimal and half-up cent rounding. Quote-only totals are explicit positive proposals. No FX or implicit advertising currency applies. Unknown/NaN/negative/zero amounts are rejected. A stale listing revision or lost availability returns 409.

## Authorization and data integrity

`can_offer` and `require_participant` remain authoritative. Talent owns listing/calendar configuration. Only the talent and original currently authorized sender can access private booking resources. Admin flags, organization ownership and teammate/recruiter membership do not grant access to someone else's deal. Revocation, inactive accounts/organizations and blocks continue to deny access, without cancelling or completing a booking. Notification delivery rechecks recipient booking authorization.

Legacy negotiation messages remain separate and read-only after a final offer decision. New fulfillment messages reuse DealMessage with a server-assigned FULFILLMENT scope. Terminal booking chat is read-only. Artifacts are bounded binary data in PostgreSQL, not public media/Cloudinary objects; downloads recheck booking and submission ownership and use private/no-store headers.

Acceptance locks the offer then the shared TalentProfile row, checks opening coverage and all provider reservations, and creates the booking, consent decision, event and notification records in one transaction. PostgreSQL independently excludes overlapping `[busy_start, busy_end)` ranges for the same talent, including buffers, across all listings. Only CANCELLED reservations release their interval. Adjacent intervals may touch. Booking/action locks serialize delivery versions, decisions and terminal messaging. Failed acceptance leaves the offer pending and creates no booking/event.

## Migrations and rollback

0001 and 0002 are unchanged. Run the existing `audit_marketplace_legacy` preflight before an environment still needs 0002. Never invent historical consent or delete deal history to make a migration pass.

- `0003_phase_two` adds fields/tables and checks. Old listings receive QUOTE_ONLY/no base price, booking disabled and revision 1. Old offers remain version 1 with null quote/time fields and empty snapshots. Old messages receive NEGOTIATION scope. No booking, availability, delivery, completion or review is inferred from old rows.
- `0004_booking_overlap` installs `btree_gist` and adds the PostgreSQL exclusion constraint. The database role needs the appropriate extension privilege, or an operator must provision the extension first. SQLite skips this PostgreSQL-specific constraint; service validation there is not a substitute for PostgreSQL concurrency guarantees.
- `MARKETPLACE_CURRENCY` defaults to GHS. `MARKETPLACE_BOOKINGS_ENABLED` defaults to true, but individual legacy listings remain disabled. For a future rollout, set the global flag false while migrating and updating every worker/client, then explicitly enable it after all migrations succeed. Version-1 offers retain their behavior. Version-2 offers require a version-aware client.
- To stop new reservations, set the global flag false: new structured proposals/acceptances are rejected, while existing booking fulfillment remains accessible. Retain schema and data. Do not downgrade to Phase 1-only acceptance code or reverse migrations after bookings exist. Back up and validate a compatible forward change instead.

Local tests use only isolated audit databases. Run `.venv\Scripts\python.exe -u -B scripts/vc_audit.py test marketplace --noinput` with an explicit loopback `AWINLINK_AUDIT_POSTGRES_URL` naming an `awinlink_audit_...` database. Set `TALENT_MARKET_TEST_CHROME` for real web controls. From `mobile`, run `npm.cmd run typecheck` and `node --test tests/marketplace*.test.cjs`. Physical-device save/share dialogs still require Android/iOS validation.
