# Awinlink Mobile

React Native app for Android and iOS built with Expo Router and TypeScript. Django remains the source of truth for accounts, ecosystem visibility, feed ranking, notifications, messaging, opportunities, and payments.

## Run locally

1. Install Node.js LTS and Android Studio / Xcode for native builds.
2. Copy `.env.example` to `.env`.
3. Set `EXPO_PUBLIC_API_URL` to the Django server origin. For a physical phone, use the development computer's LAN IP and run Django with `python manage.py runserver 0.0.0.0:8000`; the phone and computer must be on the same network.
4. From this directory, run `npm install`, then `npm start`.
5. Use a custom native build: WebRTC is unavailable in Expo Go. Use `npm run typecheck` to check TypeScript.

Secure access and refresh tokens are stored with `expo-secure-store`. Expired access tokens are refreshed through Django's token refresh endpoint.

## Current API integration

- Authentication: login, registration, current user, and token refresh
- Password recovery, account deletion, content reports, bilateral blocking, and blocked-account settings
- Feed: post list and creation, likes and unlikes
- Feed media uploads and comment listing, creation, and deletion
- Talent discovery: visible talent list and profile details
- Organizations: browse, search, follow, and edit organization profiles
- Organization owners: team roster, roles, suspension, restoration, removal, invitations, and revocation
- Native team invitation acceptance/decline and confirmed ownership transfer
- Profile actions: follow, unfollow, connection request, and start messaging
- Messaging: conversation list, text message history, send, and mark conversation read
- Focused conversations refresh every five seconds and on foreground resume
- Alerts: list notifications, mark one read, and mark all read
- Opportunities: list, details, applications list, and submit an application for talent accounts
- Creation: text posts, portfolio items, opportunities, and competitions, as supported by Django endpoints

Feed ranking and visibility stay on Django. The mobile client never receives a Paystack secret key. Advertising campaign creation and purchase are not enabled in the mobile app because those flows are not supported by its current API integration. Some ecosystem-specific setup and media editing remain available through the Awinlink web experience.
# Native calling setup

For build profiles, verification results, outstanding features, and store blockers, see [RELEASE_READINESS.md](./RELEASE_READINESS.md).

Audio/video calling uses `react-native-webrtc`; Expo Go does not include this native module. Build and install a custom Android/iOS development or production build after changing the WebRTC plugin configuration.

The app uses authenticated Django Channels WebSockets for call signaling and asks Django for ICE servers. STUN is included by default. For calls across restrictive NATs/firewalls, configure coturn with its REST API shared-secret mode and set these **server-side** environment variables:

- `TURN_SERVER_URLS`: comma-separated `turn:`/`turns:` URLs, including desired transports.
- `TURN_SHARED_SECRET`: the same secret configured for coturn `use-auth-secret`.

Django returns one-hour, per-user TURN credentials through the authenticated `/api/messaging/calls/ice-servers/` endpoint. Never add the coturn shared secret to `EXPO_PUBLIC_*` variables or the mobile bundle. A production deployment also needs a working Channels channel layer (Redis for multiple application workers) and HTTPS/WSS.

Native incoming-call alerts use Expo Push Service, which relays to APNs and FCM. Set `EXPO_PUBLIC_EAS_PROJECT_ID` (or the EAS project ID in Expo config), configure Android FCM V1 and iOS APNs credentials in EAS, and build a new native app. Users must allow notifications. The authenticated `/api/notifications/mobile-push/` endpoint stores each device token. Calls are sent as expiring, high-priority notifications with Answer/Decline actions; tapping Answer opens the call flow. This is notification-based call handling, not a CallKit/Android Telecom full-screen call UI. Configure `EXPO_PUSH_ACCESS_TOKEN` on Django only if Expo Push Security is enabled for the EAS project.
