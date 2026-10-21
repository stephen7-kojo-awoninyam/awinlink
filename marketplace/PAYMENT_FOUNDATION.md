# Market payment foundation

Follow-up findings and regression results: [payment security audit](../docs/market-payment-security-audit-2026-10-21.md).

Invoices, fees, refund credits and transaction records are **RECORD_ONLY**.
Collection is **NONE**. There is no payment provider, checkout, card authorization,
escrow, payout, cash refund, or endpoint that marks a payment collected. An
approved refund records a credit against an invoice obligation, not returned cash.
Provider tokens and client-created financial state are rejected.

## Invoices and fees

Talent explicitly issues one invoice per existing booking. Issue copies the
booking amount, currency, agreed snapshot and participant IDs, never the current
listing price. Repeated issue returns the same invoice, including after void or
credit. Cancelled bookings cannot receive new invoices. Financial access for
existing bookings remains available when new bookings are disabled.

`MARKETPLACE_PLATFORM_FEE_BPS` is an integer environment setting, default **0**,
supported range 0–10000. An invalid rate fails issuance closed. Fees are deducted
from the talent allocation; buyer totals stay equal to the accepted booking:

```
fee = round_half_up(booking_amount * fee_bps / 10000, 2)
talent_allocation = booking_amount - fee
```

A 120.00 GHS invoice at 250 bps records a 3.00 fee and 117.00 talent allocation.
The rate is snapshotted; later configuration changes do not alter invoices.
Amounts use Decimal, two decimal places and a 9,999,999,999.99 limit. This does
not add tax calculation, FX, tax-invoice certification or payment UI.

## Refund credits, voids and transaction history

The original currently authorized buyer requests a positive partial/full credit
with a reason and UUID idempotency key. Pending requests reserve invoice balance;
concurrent requests cannot overreserve it. An identical retry returns the same
request; reuse with changed content returns 409.

Only talent may approve/reject requests, with a decision reason. Exact retries
return the same decision; changed final decisions return 409. Rejection releases
the reservation without a financial transaction. Approval appends one credit
transaction and updates the invoice to PARTIALLY_CREDITED or CREDITED. Cumulative
fee reversals, rounded to cents, prevent penny drift: full credit reverses exactly
the original fee. Neither approval nor rejection changes booking fulfillment.

Talent may void an uncredited invoice with no pending requests, providing a
reason. Void appends a reversal and preserves original records. Booking
cancellation does not implicitly void invoices or decide refunds. No invoice
editing, deletion, settlement, replacement or paid-state API is exposed.

Transactions record positive total/fee/talent allocations and currency; kind
INVOICE_ISSUED establishes an obligation, REFUND_APPROVED or INVOICE_VOIDED
reverses it. They are not cash transactions or a general-purpose accounting ledger.

## API and permissions

All paths start `/api/marketplace/bookings/<booking_id>/invoice/`:

| Method/path | Body / operation |
| --- | --- |
| GET base | Invoice and remaining obligation |
| POST base | `{}` issues/retrieves invoice (talent only) |
| PATCH base | `action: VOID`, `reason` (talent only) |
| GET `refunds/` | Paginated request/decision history |
| POST `refunds/` | `amount`, `reason`, `idempotency_key` (buyer only) |
| POST `refunds/<refund_id>/` | `action: APPROVE` or `REJECT`, `reason` (talent only) |
| GET `transactions/` | Paginated transaction history |

Every request retains the deal ACL: talent and original authorized sender only;
no implicit teammate/admin access. Current organization membership, active
accounts and blocks are rechecked. Session writes require CSRF. All responses,
including failures, use `private, no-store`. Unknown financial/provider fields
are rejected. Refund IDs are scoped to their invoice.

Financial reads/writes lock the buyer organization (if present), booking, participant
accounts, invoice, then refund. Account lock contention returns a retryable 409.
Account locks serialize suspension and new block foreign-key checks; organization
locks serialize membership revocation. Reads reconcile invoice snapshots, original
issuance, refund approvals, fee reversals and aggregate balances against transaction
evidence before exposing financial state. Inconsistent evidence returns 409 and
prevents further decisions, including idempotent replays; it is not silently repaired.
Issuance, balance reservation,
decisions, allocations and history roll back on failure. Constraints enforce
valid states, balanced allocations, bounded credits, unique issuance and one
transaction per approved refund. PostgreSQL establishes concurrency guarantees;
SQLite alone does not provide equivalent row locking.

## Migration and tests

`0005_payment_foundation` adds three tables/constraints without changing existing
rows, backfilling invoices or inventing payments. It has been applied only in
isolated test databases. Reversal after records exist drops the new tables;
preserving history requires a compatible forward migration.

Run `scripts/vc_audit.py test marketplace.test_payments
marketplace.test_payments_postgresql --noinput` with the repository virtualenv.
PostgreSQL tests require an explicit loopback `AWINLINK_AUDIT_POSTGRES_URL` naming
an `awinlink_audit_...` database. Coverage includes Decimal rounding, fee bounds,
idempotency, permissions, privacy, CSRF, concurrent issuance/requests/decisions,
over-refunding, rollback injection and migration preservation. Booking regression
fixtures explicitly enable new bookings while preserving flag-off tests.

Existing staged contents are preserved. Changes are uncommitted; no application
or production migration, real payment, push or deployment was performed.

### Local verification, 2026-10-21

- Broader SQLite payment/market/booking run: 50 passed, one PostgreSQL-only test
  skipped. Three final focused refund/void regressions also passed.
- PostgreSQL: all 30 distinct payment/API, payment concurrency/migration and
  existing booking concurrency cases verified across combined and focused runs.
  The final focused rerun verified both pending/credited void protection and
  injected void-write rollback after correcting a test-fixture editing error.
- Django system checks and `makemigrations --check --dry-run` passed.
- `git diff --check` and `git diff --cached --check` passed. The staged binary
  diff fingerprint was unchanged:
  `113442e1a3392b1025188ace134e58487d03dc5f2d73b43c56bd049a03145738`.
