# Market payment-record security audit — 2026-10-21

Scope: Market invoice, refund-credit and transaction APIs/services. This is the
record-only Market foundation, not an audit of separate advertising payment code
or an external payment provider. All data used was synthetic and isolated in
SQLite memory or explicitly named loopback PostgreSQL audit databases.

## Findings fixed

**Permission check/commit race (medium).** Financial operations locked bookings
but not organization memberships or participant accounts. Membership revocation,
account suspension or a new block could complete between the ACL check and the
financial write's commit. Operations now lock the buyer organization first,
booking, participant accounts, invoice and refund, rechecking the deal ACL after
account locks. Organization membership services share the organization lock.
Account updates and new block foreign-key checks serialize against account locks.
Account locks use NOWAIT to avoid waiting into foreign-key lock-order cycles;
contention returns 409 with no partial financial changes and is safe to retry.

**Inconsistent financial evidence was trusted (integrity defense).** The code
trusted invoice aggregate balances and idempotent retries without reconciling
their transaction evidence. An accidental/internal write resetting credited
totals could permit duplicate credits; deleted approval records could leave
apparently final refund states. These are not public API write capabilities.
Reads, decisions and retries now fail closed with 409 when snapshots, participant
IDs, booking amounts/currency, fee policy, original issuance, refund approvals,
fee reversals or aggregate totals disagree. Refund requesters and decision actors
must match their actual parties. No record is silently repaired or marked paid.
Reads hold the same locks so concurrent legitimate writes do not produce mixed
snapshots during reconciliation.

## Controls verified

- No collection/provider integration or mark-paid operation exists in these
  Market APIs. Invoice statuses have no PAID state; responses retain RECORD_ONLY
  and collection NONE. A refund approval records a credit, never returned cash.
- Fake paid/provider fields, client fees, amounts on issuance, and direct
  transaction writes are rejected. Database checks reject forged paid statuses
  and unsupported payment transaction kinds.
- Unique invoice/issuance records, UUID request idempotency, one transaction per
  approved refund, pending balance reservations, and serialized decisions prevent
  duplicate obligations and credits. Exact retries retain original records;
  conflicting retries fail. Split refunds reverse exactly the original fee.
- Talent/buyer roles remain distinct. Outsiders, teammates and platform admins
  gain no implicit financial access. Revoked senders, inactive accounts and blocks
  lose access. Refund IDs are scoped to their invoice. Session writes require
  CSRF, and financial/error responses are private and not stored by caches.
- Failed final refund writes roll back invoice balances, approval state and
  transaction records together; retry after rollback creates one approval.

## Validation

- SQLite payment and adversarial API tests: 29 passed.
- PostgreSQL payment/security/concurrency and migration tests: 39 passed,
  including concurrent duplicate issuance/requests/approval, membership revocation,
  block/suspension commit ordering, and retry after account lock contention.
- Django checks and migration consistency passed; no schema migration is needed
  for these audit corrections.
- Both `git diff --check` and `git diff --cached --check` passed. Staged binary
  diff SHA-256 stayed
  `113442e1a3392b1025188ace134e58487d03dc5f2d73b43c56bd049a03145738`.

The tests simulate corrupt records using isolated ORM writes to prove that
inconsistency fails closed. They do not establish protection against a database
administrator who can consistently rewrite both source records and all evidence.
Reconciliation reads the complete per-invoice history; very large histories will
need performance measurement before expanding this foundation. No real payment,
provider callback, production data, or deployed service was exercised.

Existing staged work was preserved. Audit corrections remain unstaged. No commit,
push, deployment, application migration or production-data change was performed.
