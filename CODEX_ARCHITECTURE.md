# Awinlink Architecture & Development Rules

## 1. Project

Awinlink is a global social network for talent discovery, recommendations, opportunities, competitions, events, learning, connections, messaging, and professional growth.

The platform is NOT sports-only.

Talent categories are:

* Sports
* Science & Technology
* Arts
* Others

The Django backend is the source of truth for business rules, permissions, authentication, data models, and API behavior.

The mobile application must consume the existing Django API rather than duplicating backend business logic.

---

## 2. Backend

The project uses:

* Django
* Django REST Framework
* SimpleJWT
* PostgreSQL in production
* Django Channels for realtime functionality

Important Django apps include:

* accounts
* talents
* organizations
* sports
* connections
* messaging
* analytics
* api
* core

Do not assume that sports functionality represents the entire Awinlink product.

---

## 3. User Roles

The exact account roles are:

* ATHLETE
* ORGANIZATION
* SCOUT
* COACH
* ADMIN

ATHLETE represents a general individual/talent and is not limited to sports.

Do not introduce an INSTRUCTOR account role.

Learning profiles may have instructor-related functionality without changing the account role system.

---

## 4. Authentication

The mobile application must use the existing Django authentication/API system.

Do not create a second authentication system.

Use the existing JWT/API authentication pattern.

Tokens and sensitive credentials must not be stored in plain AsyncStorage.

Use SecureStore where appropriate.

---

## 5. API Architecture

Before creating a new API endpoint:

1. Search the existing Django API.
2. Identify the existing URL.
3. Identify the corresponding view/viewset.
4. Identify the serializer.
5. Check permissions.
6. Reuse the existing endpoint if it already supports the required operation.

Only add or modify backend API functionality when the existing API genuinely cannot support the required mobile operation.

Do not create duplicate endpoints simply because the mobile app needs a different screen.

---

## 6. Mobile Architecture

The mobile application should:

* reuse the existing API client
* reuse existing authentication logic
* reuse existing types where possible
* reuse existing components where practical
* follow the existing navigation structure
* avoid duplicate API clients
* avoid duplicate authentication systems
* avoid unnecessary duplicate models/types
* handle loading, empty, error, and success states
* handle API authentication failures appropriately

Do not rewrite working infrastructure merely to introduce a different pattern.

---

## 7. Existing Mobile Core Flows

The mobile app currently contains or is expected to contain core flows including:

### Opportunities

* discovery
* search
* opportunity details
* application submission
* application status
* application history

### Competitions

* browse
* search/filter where supported
* details
* talent registration
* competition creation
* saved draft submission for review

### Events

* browse
* details
* talent registration

### Organizations

* search
* details
* follow
* unfollow

### Profiles

* talent profile editing
* organization profile editing
* portfolio viewing

### Notifications

* notification listing
* mark individual notification as read
* mark all notifications as read

---

## 8. HTTP Methods

Follow REST semantics used by the Django API.

For example:

* Like → POST
* Unlike → DELETE

Do not change API methods arbitrarily.

---

## 9. Important Existing Backend Constraint

The opportunity application serializer previously exposed the required `opportunity` input as read-only.

The mobile application requires that field to be writable so an application can be submitted correctly.

This backend correction has already been made.

Do not revert it.

---

## 10. Important Existing Changes

There are pre-existing edits in:

* api/urls.py
* api/views.py

These edits may belong to earlier backend work.

Unless the current task explicitly requires them:

**DO NOT modify, overwrite, revert, or reformat these files.**

Preserve their existing working-tree state.

---

## 11. Product Rules

Events are organization-owned.

Organizations create opportunities and competitions according to backend permissions.

Competition lifecycle is:

DRAFT → SUBMITTED → APPROVED → PUBLISHED → REGISTRATION_CLOSED → ONGOING → JUDGING → RESULTS → COMPLETED

CANCELLED may occur where supported.

Do not bypass backend approval/moderation rules from mobile.

---

## 12. Role-Aware Features

Specialist functionality must respect the Django role and permission system.

Future mobile functionality may include:

### Scout

* talent discovery
* recommendations
* scouting tools

### Coach

* coached talents
* talent management
* category-aware coach functionality

### Organization

* recruitment
* opportunity management
* application management
* shortlists

### Admin

* moderation
* platform administration

Do not expose privileged operations merely because a mobile screen exists.

---

## 13. Future Mobile Areas

These areas may still require implementation:

* specialist scout tools
* coach tools
* recruitment
* shortlist management
* learning
* competition judging
* competition moderation
* messaging
* messaging groups
* voice/video calls
* attachments
* event publishing
* advertising purchase

Do not fake unsupported backend functionality.

If a required backend API does not exist, identify the dependency instead of inventing unsafe client behavior.

---

## 14. Testing

Before declaring a task complete:

Run:

npm run typecheck

and:

git diff --check

Where backend/API behavior has been modified, run the relevant Django tests as well.

Do not claim that functionality works on a physical device unless it has actually been tested on a device/emulator.

---

## 15. Git Safety

Do not commit automatically unless explicitly instructed.

Do not push automatically unless explicitly instructed.

Never use a blanket destructive operation such as:

git reset --hard

Never discard existing user changes.

Before committing, identify exactly which files belong to the current task.

Do not stage unrelated pre-existing work.

---

## 16. Implementation Philosophy

Awinlink is a large existing product.

Prefer:

* inspect first
* understand existing architecture
* reuse existing code
* make the smallest safe change
* test
* report

Avoid:

* rewriting working systems
* creating duplicate APIs
* creating duplicate authentication
* inventing backend behavior
* bypassing permissions
* changing unrelated files
* making broad refactors without approval

When uncertain, inspect the existing implementation before making assumptions.
