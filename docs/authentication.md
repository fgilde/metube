# Authentication and users

Out of the box an instance is open, exactly like upstream MeTube. Authentication switches on
as soon as at least one user exists. The first user normally comes from the environment;
further users are managed in the UI.

## The first admin

```yaml
environment:
  - ADMIN_USERNAME=admin
  - ADMIN_PASSWORD=change-me
```

* Both must be set together; setting only one is a startup error.
* The admin is (re)created on every start from these values: a changed `ADMIN_PASSWORD` wins
  over whatever is stored. Because it comes from the environment it is shown as locked in the
  UI and cannot be edited or deleted there.
* Removing the variables later keeps the user in `users.json`; it simply becomes editable.

You can also start without the environment variables and let the instance stay open, but
then anyone can create the first user through the API. On anything reachable from the
internet, set the admin through the environment.

## Users and roles

The **Users** page (people icon in the navbar, admins only) lists users, adds new ones,
changes passwords and roles, and deletes users.

| Role | Can |
|------|-----|
| `admin` | everything, including the Users page and the Settings page |
| `user` | queue downloads, subscriptions, cookies, the file server — everything except users and settings |

Rules: usernames are 1–64 characters of letters, digits and `. _ @ -`; passwords must not be
empty; the last admin cannot be demoted or deleted; the environment admin cannot be changed
in the UI.

Everything is stored in `STATE_DIR/users.json` (`/downloads/.metube/users.json` in the
container) — password hashes (scrypt, per-user salt) and the secret that signs sessions. Back
that directory up as you would the queue state.

## Sessions

Logging in sets an `HttpOnly` cookie that is valid for 30 days. Sessions are stateless: the
cookie is a signed token, so there is no session table to fill up. The signature includes a
fragment of the password hash, which means a password change or a deleted user invalidates
every session of that user at once. Logging out clears the cookie.

The cookie is marked `Secure` when `HTTPS=true`. Behind a TLS-terminating reverse proxy set
`HTTPS=true` only if MeTube itself speaks TLS; otherwise the cookie is sent over plain HTTP
between proxy and container, which is fine inside a private network.

## Scripts and the API

Every API endpoint accepts `Authorization: Basic <base64 user:password>` as an alternative to
the cookie, so `curl -u user:password` keeps working for scripts and bookmarklets:

```bash
curl -u admin:change-me -X POST http://localhost:8081/add \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://youtu.be/PVtSAXSv7Fo","download_type":"video","quality":"best","format":"mp4"}'
```

The upstream browser extensions and bookmarklets send credentials only for origins named in
`CORS_ALLOWED_ORIGINS`; see the [configuration reference](configuration#sending-links-to-metube).

## What stays public

Without a session these still answer:

* the app shell and its bundles, so the login screen can load;
* `/login`, `/logout`, `/me`, `/version`, `/robots.txt`;
* the direct routes `/watch` and `/dl/…` — they are deliberately independent of users and
  are protected by `DIRECT_ROUTES_KEY` alone, so a link can be handed to a media player,
  another device or a friend without a password. See [Direct routes](direct-routes).

The download directories (`/download/…`, `/audio_download/…`), the queue API, socket.io,
cookies, settings and users all require a session.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/me` | `{ "auth": bool, "user": { "username", "role", "locked" } \| null }` |
| `POST` | `/login` | body `{ "username", "password" }`; sets the cookie, `401` otherwise (after a one-second delay) |
| `POST` | `/logout` | clears the cookie |
| `GET` | `/users` | admin: list users |
| `POST` | `/users` | admin: `{ "username", "password", "role" }` |
| `POST` | `/users/update` | admin: `{ "username", "password"?, "role"? }` |
| `POST` | `/users/delete` | admin: `{ "username" }` |

Validation errors come back as `400` with the reason in the status line; a non-admin gets
`403` on the admin endpoints.
