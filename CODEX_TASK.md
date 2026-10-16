# Awinlink Mobile — Core Flow Completion & Audit

## Objective

Inspect the existing Awinlink repository and continue implementing the mobile application using the existing Django backend architecture.

The goal is to bring the mobile application as close as safely possible to feature parity with the existing Django product without breaking existing backend functionality.

You have access to the actual repository. Inspect the files directly.

Do not ask the developer to paste source code that already exists in the repository.

---

# PHASE 1 — AUDIT

Before making changes:

1. Inspect the complete mobile directory.
2. Inspect the existing API client/service layer.
3. Inspect mobile navigation.
4. Inspect authentication and SecureStore usage.
5. Inspect mobile types.
6. Inspect reusable components.
7. Inspect all mobile screens already created.
8. Inspect the Django API endpoints used by the mobile app.
9. Inspect the corresponding Django views/viewsets and serializers.
10. Inspect permissions for each endpoint.

Create an internal understanding of the architecture before implementing anything.

---

# PHASE 2 — VERIFY EXISTING MOBILE FLOWS

Verify these flows against the actual Django backend:

## Opportunities

* discovery
* search
* details
* application submission
* application status
* application history

## Competitions

* browsing
* details
* talent registration
* competition creation
* draft saving
* submit draft for review

## Events

* browsing
* details
* talent registration

## Organizations

* search
* organization details
* follow
* unfollow

## Profiles

* talent profile editing
* organization profile editing
* portfolio viewing

## Notifications

* notification listing
* mark one as read
* mark all as read

Do not assume a UI is complete merely because the screen exists.

Trace each operation through:

Mobile screen → API client → URL → Django view → serializer → database/action.

---

# PHASE 3 — FIX INCOMPLETE CORE FLOWS

If any of the above core flows are incomplete, fix them.

Follow the existing architecture.

Do not create duplicate APIs if an existing endpoint can be reused.

If a backend endpoint requires a small safe correction to support the mobile flow, make that correction.

However:

DO NOT modify or overwrite the existing pre-existing changes in:

* api/urls.py
* api/views.py

unless the modification is absolutely required for the current mobile task.

If either file must be modified, preserve all existing changes and make only the minimum required addition.

---

# PHASE 4 — ROLE AND PERMISSION SAFETY

Verify that mobile operations respect the Django backend's existing permissions.

Check:

* ATHLETE
* ORGANIZATION
* SCOUT
* COACH
* ADMIN

Do not expose organization-only actions to normal talents.

Do not expose scout/coach/admin functionality to unauthorized users.

Do not bypass competition approval or moderation.

Do not bypass event ownership rules.

Do not implement client-side permission checks as a replacement for backend permissions.

The backend remains authoritative.

---

# PHASE 5 — IMPLEMENT THE NEXT CORE MOBILE FEATURES

After auditing and fixing the existing flows, implement the next highest-value mobile features that are fully supported by the existing backend.

Prioritize in this order:

## 1. Talent discovery

Implement or complete:

* talent search
* filtering
* talent detail
* profile viewing
* follow/unfollow where supported
* recommendation/discovery presentation where the existing API supports it

Reuse the existing Django talent discovery/recommendation APIs.

Do not invent recommendation algorithms inside the mobile app.

---

## 2. Connections

Implement the mobile connection/follow experience using the existing connections API.

Respect existing endpoint names, permissions, and HTTP methods.

Unlike must use DELETE where the backend expects DELETE.

Like must use POST where the backend expects POST.

---

## 3. Applications

Complete application-related mobile interfaces supported by the API.

Include:

* application history
* application status
* application details where supported
* appropriate loading/error/empty states

---

## 4. Notifications

Ensure notification actions work correctly.

Support:

* list notifications
* mark individual notification read
* mark all notifications read
* refresh state after the action
* unread indicators where the API supports them

---

# PHASE 6 — SPECIALIST FEATURES

After the core flows are stable, inspect the backend support for:

## Scout

Determine which existing API endpoints support:

* talent discovery
* recommendations
* scout actions
* saved/recommended talents

Implement only what the backend already supports safely.

## Coach

Determine which existing API endpoints support:

* coached talents
* talent management
* category-aware coaching functionality

Implement only supported operations.

## Organization

Determine which existing API endpoints support:

* recruitment
* applications
* shortlists
* opportunity management

Implement only supported operations.

Do not create fake client-only workflows for missing backend functionality.

---

# PHASE 7 — LEARNING

Inspect the existing Django learning models, views, serializers, and API routes.

Determine what is already mobile-ready.

If the API is sufficiently complete, implement:

* learning discovery
* course/content details
* enrollment where supported
* learner progress where supported

Learning must not depend on an INSTRUCTOR account role.

Do not introduce an INSTRUCTOR account role.

---

# PHASE 8 — MESSAGING

Inspect the existing messaging API and realtime implementation.

Determine what can safely be supported by mobile.

Prioritize:

1. conversations
2. messages
3. unread state
4. attachments if the API supports them

Then inspect:

* groups
* WebRTC calls
* realtime Channels/WebSocket behavior

Do not implement a fake realtime system.

If backend infrastructure is incomplete or unreliable, report it instead of hiding the problem.

---

# PHASE 9 — COMPETITIONS

Inspect the complete competition lifecycle.

Ensure mobile respects:

DRAFT
→ SUBMITTED
→ APPROVED
→ PUBLISHED
→ REGISTRATION_CLOSED
→ ONGOING
→ JUDGING
→ RESULTS
→ COMPLETED

and CANCELLED where supported.

Implement judging/moderation only where the backend permissions and APIs explicitly support it.

---

# PHASE 10 — EVENTS

Inspect event APIs.

Implement supported:

* browsing
* details
* registration
* organization-owned event management where safely supported

Do not invent event publishing APIs.

If publishing requires backend support that does not exist, report it as a backend dependency.

---

# PHASE 11 — QUALITY

After implementation:

Run:

npm run typecheck

Run:

git diff --check

If backend code was modified, run appropriate Django tests.

Fix errors caused by the current implementation.

Do not make unrelated refactors.

---

# PHASE 12 — GIT SAFETY

DO NOT:

* commit
* push
* reset
* discard user changes

In particular, preserve the existing working-tree edits in:

* api/urls.py
* api/views.py

At the end, provide a concise report containing:

## Completed

List everything actually implemented.

## Backend Changes

List every Django file changed and why.

## Mobile Changes

List every mobile file changed and why.

## API Map

For each implemented flow, provide:

Mobile feature → HTTP method → endpoint → Django view/serializer

## Remaining

List functionality that cannot safely be completed because backend/API support is missing.

## Validation

Report:

* npm run typecheck
* git diff --check
* Django tests if run

## Git Status

Confirm that:

* no commit was made
* no push was made
* unrelated existing changes were preserved

Do not claim 100% mobile parity unless every major Django capability has actually been implemented and tested.
