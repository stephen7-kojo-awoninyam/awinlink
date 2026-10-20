# Social dashboard redesign

The shared feed and talent dashboard now use a responsive blue-and-white social
layout. The dashboard's role routing, profile requirement, applications,
invitations, portfolio, certificates, profile progress, and conversations remain
available. Both talent-dashboard template locations delegate to a single shared
template, avoiding the previous project/app template override.

## Existing features reused

- For You retains the existing recommendation rollout and advertising placement.
- Following filters that authorized feed to followed people and organizations.
- Reels filters existing authorized video posts; it does not create another upload
  or audience system. Videos use native controls, never autoplay, and pause when
  offscreen or when the page is hidden.
- Stories display the newest ranked post per author from the last 24 hours, up to
  ten authors. They use native dialogs with keyboard navigation, Escape, focus
  restoration, and normal post-link fallbacks. The underlying posts remain posts;
  they are not deleted or unpublished after 24 hours.
- Likes, comments, saves, shares, connection requests, messages, notifications,
  and invitation actions retain their existing Django URLs and CSRF protection.
- The mobile navigation contains Home, Opportunities, Post, Messages, and More.
  Post is centered, with Opportunities immediately to its left. Discover and
  Reels remain available through More, alongside organization tools,
  notifications, and role-specific features.
- Every authenticated application shell has a persistent posting control:
  the central mobile Post button or a fixed desktop Post button. Existing Create
  links also open the shared native-dialog composer. Without JavaScript, they
  retain the regular Django creation page as a fallback.
- The composer sends multipart text/photo/video submissions to the existing
  `create_post` endpoint and uses `PostForm` for validation. Text-only,
  photo-only, and video-only posts are supported. Whitespace, location, or
  metadata alone cannot create an empty post. Validation errors keep the draft
  and selected files. Closing the composer retains the draft and restores focus.

Blocked accounts are excluded from feed/stories, private talent profiles are not
suggested to unauthorized viewers, and a repost cannot reveal an original that
became private. Repost-only items retain their liked/saved state. Stories also
respect items omitted by unified ranking and feedback filtering.

Global search remains available on discovery screens and is also available on
the talent dashboard. The existing no-global-search test now targets Learning,
which actually has no shared search, rather than Discovery, which already did.

## Validation

Run with the isolated local SQLite settings; no deployment is involved:

```powershell
.venv\Scripts\python.exe manage.py test feed.test_post_composer feed.tests core.tests core.test_social_dashboard core.test_mutation_methods --settings=config.recommendation_seed_settings --noinput
node --check static/js/social-dashboard.js
node --check static/js/layout.js
node --check static/js/post-composer.js
```

The current regression run passed 36 tests, including shared posting across
authenticated roles, empty-post rejection, media-only posts, ordinary Django
fallbacks, CSRF, forged-author protection, and suspended-organization denial.
The feed tests also verify that stories do not resurface omitted ranked posts.

Chrome browser checks covered 1440, 1280, 1024, 768, 390, and 320 px widths with
no horizontal overflow. Forty-two workflow checks passed with no JavaScript
exceptions: dashboard rendering, real unread badges, mobile drawer focus,
stories, safe comment rendering, likes, saves, sharing, connections, reels,
messages, notifications, persistent Post controls, modal focus and draft
retention, server upload errors, and text/photo/video-only publishing.
Screenshots use fictional generated content; `post-composer-390.png` captures
the upload-validation error state, and `post-composer-1440.png` shows the desktop
composer.

## Local visual preview

```powershell
.venv\Scripts\python.exe scripts\preview_social_dashboard.py
```

Open `http://127.0.0.1:8776/talents/dashboard/` and sign in as `preview_amina`
with password `LocalPreviewOnly123!`. These are fictional local-only credentials.
The preview binds to loopback and uses `.audit-social-dashboard/preview.sqlite3`
and generated media in that directory. It does not touch `db.sqlite3`, the
recommendation seed database, or real uploads. Stop the preview with Ctrl+C.

With the preview running, browser checks use installed Chrome and Node 25:

```powershell
node scripts\check_social_dashboard.mjs
```

The checker launches its own headless Chrome profile, closes it afterward, and
writes `.audit-social-dashboard/browser-results.json` plus desktop/mobile
screenshots. It writes likes, comments, shares, and connections only to the
fictional preview database. On Windows, browser launch may require the normal
execution approval outside the sandbox.
