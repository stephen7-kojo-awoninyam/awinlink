# Agreement and transfer security audit — 2026-10-21

Scope: agreement API, service transitions, private history, web/mobile consent
controls, PostgreSQL row locking, and transactional rollback. All fixtures were
synthetic; databases were in-memory SQLite or explicitly named loopback audit
PostgreSQL test databases. No application database migration or data change was
performed.

## Findings and corrections

1. **Consent coercion (medium).** DRF's standard BooleanField accepted strings
   such as `"yes"` and numeric `1` as consent. The agreement action serializer now
   accepts only JSON booleans. Consent-producing transitions still require actual
   `true`; omitted/false consent cannot create approval evidence. Both existing
   clients already send JSON booleans.
2. **Private roster existence oracle (low).** Creation looked up the roster
   before checking management scope. A valid but unauthorized roster identifier
   could yield a different response from a nonexistent identifier, including a
   source/destination comparison error. Creation now scopes that lookup to the
   caller's agreement-management organizations; both return 404. The service
   continues to recheck authority under the organization lock.
3. **Account safety check/commit race (medium).** Organization/member and roster
   decisions already shared locks, but account suspension or a new account block
   could commit after the final safety checks and before the agreement commit.
   Decisions now lock the actor, talent, organization owners, and earlier
   signers' account rows in ID order. PostgreSQL suspension updates and block
   foreign-key checks therefore serialize against the decision. Account locks
   use NOWAIT: contention returns a retryable 409 without consent/roster writes,
   avoiding a wait cycle with block foreign-key locks acquired in another order.
   A safety change that wins serialization is observed by the subsequent checks;
   a later safety change does not retroactively undo a completed agreement.
4. **Stored digest defense.** Consent-producing transitions recompute the terms
   digest before recording approval. An accidental write outside the revision
   service cannot reuse approvals for different stored terms. This is integrity
   defense against inconsistent data, not protection from an administrator who
   can rewrite both terms and their audit evidence.

## Verified boundaries

- Only source/destination owners or managers may represent their organization;
  only the linked talent may represent the talent. Recruiters, viewers, unrelated
  users, and platform administrators receive no implicit agreement authority.
- Unsubmitted drafts and subsequent private revisions stay private. Previously
  shared revisions/history remain readable without disclosing newer draft terms.
  Authorized list/detail/history responses use `private, no-store`.
- Old revisions, old ending rounds, duplicate consent, forged parties, and
  absent consent cannot authorize activation. Removed/unclaimed affiliations,
  inactive participants, blocked relationships, and revoked prior signers are
  checked. Session writes require CSRF; unauthenticated reads are rejected.
- Three-party transfers move only the named source affiliation. Duplicate final
  approval, revision versus approval, withdrawal versus approval, removal versus
  approval, and membership revocation versus approval are tested on PostgreSQL.
- Destination uniqueness conflicts and injected failures in roster history,
  agreement persistence, and agreement event writes roll back source status,
  destination creation, approval evidence, and both histories together.
- Migration 0013 reverse/reapply preserves preexisting unrelated roster/profile/
  organization rows. Reversing that schema after agreements exist would drop its
  agreement tables; it is not a data-preserving operational rollback. Use forward
  compatible changes when retaining agreement history.

## Validation

Regression coverage is in `organizations/test_agreements.py` and
`organizations/test_agreement_postgresql.py`, with actual JWT HTTP workflows in
`organizations/test_agreement_e2e.py` and web/mobile UI regressions under
`mobile/tests/organization-agreements*.test.cjs`.

- SQLite agreement API/security tests: 22 passed.
- Combined PostgreSQL agreement, concurrency, migration preservation, and actual
  mobile-client JWT HTTP tests: 32 passed.
- Final PostgreSQL NOWAIT/account-suspension/block-commit and approval/revocation
  lock regressions: 5 passed, including retry after a contended account lock.
- Web/mobile agreement UI regressions: 5 passed.
- Django system checks and migration consistency check passed.
- `git diff --check` and `git diff --cached --check` passed. The staged binary
  diff SHA-256 remained
  `113442e1a3392b1025188ace134e58487d03dc5f2d73b43c56bd049a03145738`.

This audit did not repeat physical Android/iOS rendering or external electronic
signature validation. SQLite tests do not establish row-lock behavior; the
concurrency assertions run against PostgreSQL. Existing staged contents are
preserved and all audit corrections are unstaged. No commit, push, or deployment
was performed.
