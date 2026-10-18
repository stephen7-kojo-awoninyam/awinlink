# Talent Market MVP

Web entry: `/marketplace/` (sidebar). Native entry: Opportunities → Talent Market.
API prefix: `/api/marketplace/`; existing session/CSRF and JWT authentication apply.

- `GET markets/`: existing talent category choices as ecosystems and TalentDomain rows as subecosystem facets. No duplicate taxonomy or profile models. Domains are shared facets across ecosystems, consistent with the existing domain model.
- `GET/POST listings/`, `GET/PATCH listings/<id>/`: talent-owned listings. Publish with `status: PUBLISHED, consent: true`. Every published edit requires renewed consent. Pause with `status: PAUSED`. `mine=1` includes the owner's drafts.
- Listing filters: `q`, `ecosystem`, `subecosystem` (domain ID), `country`, `skill`, `work_type`, `experience`. Results use page-number pagination (24 per page).
- `GET/POST offers/`: immutable offer terms, listing ID, optional organization ID. Personal offers require a verified scout/coach profile and matching account role. Organization offers use the existing manage_recruitment capability, including its membership suspension and legacy owner policy.
- `GET/POST deals/<offer_id>/`: private room and final decisions. POST action ACCEPT requires `consent: true` from the listing talent. Talent may DECLINE; sender may WITHDRAW. Decisions are final. Acceptance records consent and decision timestamps, without a payment or legal-contract workflow.
- `POST deals/<offer_id>/messages/`: body text; author comes from authentication. Final rooms remain readable and cannot receive new messages. GET room returns up to the earliest 200 messages.

Only explicitly published listings on public, active talent profiles appear in discovery. Drafts, paused listings, private/organization-only profiles, and blocked accounts are excluded. Room access belongs to the talent and the original sender; organization teammates and platform admins do not automatically gain access. Sender permissions are checked again on every room request. Blocks prevent either participant from opening the room.

Apply the included migration with `python manage.py migrate` when ready to use the feature locally. Existing data is not automatically published. TalentDomain entries are managed through the existing application; at least one is needed to create a listing. No payment, deployment, or existing-database migration was performed during implementation.

Tests: `python manage.py test marketplace`. Mobile: run TypeScript with `node node_modules/typescript/bin/tsc --noEmit` from mobile.
