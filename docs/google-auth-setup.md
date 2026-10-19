# Google signup and login (not deployed)

## Google Cloud and server configuration

1. Create or choose a Google Cloud project. In Google Auth Platform configure Branding, Audience and Data Access (the console may also label this OAuth consent screen). Supply the approved Awinlink application identity, authorized domains, support contact, and reviewed public Terms and Privacy URLs. For an external app in testing, add test users. Complete Google's required production/verification steps before public release.
2. Create an OAuth client of type **Web application**. This implementation brokers both Django and Expo authentication through the Django server; it does not use native Google ID tokens or native Google client IDs. Request only `openid email profile`. No Drive, Gmail or offline access is requested.
3. Add an exact authorized redirect URI, for example `https://YOUR_DOMAIN/accounts/google/callback/`. It must match the configured URI exactly, including the trailing slash. Local development can use `http://localhost:8000/accounts/google/callback/` or `http://127.0.0.1:8000/accounts/google/callback/` as separately registered URIs. Use separate development and production clients.
4. Configure server environment variables:

   ```text
   GOOGLE_OAUTH_CLIENT_ID=YOUR_WEB_CLIENT_ID.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=YOUR_SERVER_ONLY_SECRET
   GOOGLE_OAUTH_REDIRECT_URI=https://YOUR_DOMAIN/accounts/google/callback/
   ```

   Do not put the secret into Expo public environment variables, client code, repository files, logs, or screenshots. Empty configuration fails closed and password authentication remains available. Django's callback URI is configured explicitly; forwarded host headers and request parameters cannot choose it.
5. Apply the reviewed migrations through the normal release process, including `accounts.0007_google_auth`. This change has not run migrations against production. Keep existing Django HTTPS, secure session/CSRF cookie, allowed-host and proxy settings correct; the browser must retain its session cookie across Google's top-level GET callback. Keep outbound HTTPS access available to `oauth2.googleapis.com` and `www.googleapis.com` for token exchange and signing-key retrieval.
6. Configure a shared Django cache across workers for consistent authentication throttling. Public mobile endpoints and web starts are limited to 30 anonymous starts/exchanges per hour per IP; authenticated link requests require a current password. Configure trusted proxy handling deliberately rather than trusting arbitrary forwarded headers. Monitor abuse and tune limits for shared networks. The limiter is supplementary to cryptographic attempt binding.
7. Schedule `python manage.py clear_google_auth_attempts` periodically (for example every 10 minutes) to remove expired attempts and temporary identity claims. Attempts expire after 10 minutes regardless of cleanup. Provider authorization codes, callback query strings, passwords, exchange secrets and JWTs must be redacted from reverse-proxy, request-body, analytics and error logs. Google access/refresh tokens are never stored.

## Django web

Login and registration offer **Continue with Google** using a CSRF-protected POST. Authorization uses a random state, nonce and S256 PKCE verifier. The callback is bound to the initiating browser session. It verifies Google signatures against fixed Google's JWKS, accepts only RS256, checks issuer, configured audience, authorized presenter, expiry, issued-at, nonce, nonempty subject and verified email. It uses the authorization-code token endpoint, not the debugging tokeninfo endpoint or user-supplied profile data.

The callback does not log a user in. A same-browser completion page requires a CSRF-protected POST. An established Google subject logs into its existing account; new subjects must complete username, role, country/phone and organization fields as applicable, and explicitly accept the current Terms. New Google-only accounts have an unusable local password. Roles and onboarding follow existing web routes. Inactive accounts cannot authenticate. Completion consumes its attempt under a database row lock; subject/user uniqueness prevents identity reassignment in racing requests.

Existing password accounts are unchanged. An email collision does **not** sign in, create a duplicate via Google, or link automatically. Sign in using the existing method, open **Link Google** (`/accounts/google/link/`), confirm the current Awinlink password, and complete Google authentication. Linking never replaces an identity owned by another user, changes a role/email, or fabricates Terms acceptance. Google-only accounts cannot use this password-based linking action to replace their identity; no unlink or provider-account replacement is implemented. Existing password recovery stays available for accounts with a usable password. Recovery of a lost Google-only identity requires an independently reviewed support procedure.

## Expo Android and iOS

The existing `expo-web-browser` dependency opens a system authentication browser. The existing `awinlink` app scheme receives the fixed `awinlink://google-complete` callback with a one-use handoff code. Keep `scheme: "awinlink"` in the Expo app configuration and build/install a development or release build with that scheme; Expo Go is not the production test environment for this callback. No Google native SDK, embedded WebView, native Google client secret, or additional Google Android/iOS OAuth client is needed for this brokered flow.

Set `EXPO_PUBLIC_API_URL` to the trusted Django server origin as for the existing API client. Login and registration offer Google; Account and safety offers explicit linking with current-password confirmation. Native clients start at `POST /api/auth/google/start/`; Django returns a Google authorization URL and an unguessable exchange secret. Only its hash is stored server-side. The secret stays in the active screen's memory. After Google returns to the server, the browser redirects to the fixed app URI with a separate one-use `handoff` code. **No Google authorization code, Google token, Awinlink JWT, profile claims or initiating exchange secret enters the URI.** The app completes via `POST /api/auth/google/complete/`, presenting both its private `exchange_secret` and the browser-returned `handoff` over HTTPS. The server stores only hashes of these proofs. A malicious app intercepting the deep link cannot redeem it without the initiating secret; an initiator sharing its authorization URL cannot redeem a victim's login without receiving that victim's callback handoff. Neither proof is sufficient alone. Pending, denied, expired and already-used attempts issue no tokens.

New users receive `signup_required`, choose one of the existing public roles, complete required fields and affirm Terms. Awinlink access/refresh tokens are issued only after completion and use the existing secure session-storage helpers. The Google-returned subject and verified email are authoritative; posted email, role changes on existing users, forged timestamps and ID tokens are not authentication inputs. Reading a policy does not check acceptance. Cancelling or cold-starting after losing the in-memory exchange requires a fresh attempt. Expo web directs users to the Django web sign-in experience rather than attempting a native-scheme callback.

## Validation and release review

Automated tests cover signed token validation with local RSA keys, bad signatures and claims, callback/session binding, callback and exchange replay, nonce/PKCE, all roles, Terms and verified-email enforcement, email collisions, explicit linking, inactive accounts, configuration failure, throttling, cleanup, web sessions/onboarding, native cancellation and token handoff. External Google calls are mocked in these tests.

Before release, manually exercise the actual Google consent flow with configured test clients on desktop, Android and iOS, cancellation, repeated callbacks, expired sessions, Terms changes, linking and Google-only signup. Confirm TLS/proxy/cookie behavior and callback handling on physical device builds. No live credentials, Google Cloud changes, production migrations or deployment were performed here.

Primary references: [Google web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server), [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect), [Expo WebBrowser](https://docs.expo.dev/versions/latest/sdk/webbrowser/).
