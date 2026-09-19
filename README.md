# MeTube — fgilde fork

![Build](https://github.com/fgilde/metube/actions/workflows/main.yml/badge.svg)

A self-hosted web UI for [yt-dlp](https://github.com/yt-dlp/yt-dlp): paste a URL, get the file.
This is a fork of [alexta69/metube](https://github.com/alexta69/metube). It keeps everything
upstream does — queue, playlists, subscriptions, formats, cookies, output templates — and adds
what upstream deliberately does not want to own:

* **Direct links.** `/watch?v=<id-or-url>` and `/dl/<name>.<mp3|mp4|jpg>` fetch one item and
  stream it straight back without saving anything. Play it, save it (`&download=1`), take the
  audio (`&format=mp3`), the thumbnail or a single frame (`&format=jpg&ts=42`). Search by name
  (`/dl/Green-Day-Basket-Case.mp3`) or pass any URL yt-dlp understands.
* **Login and users.** A real login screen, admins and users managed in the UI, sessions that
  survive restarts, `curl -u` for scripts. Direct links stay independent of users and are
  protected by an access key instead, so they can be shared.
* **Settings page.** Toggle the direct routes, manage the key, and build ready-to-use links for
  your own instance, with examples for every format and a copy button on each.

Documentation: **[fgilde.github.io/metube](https://fgilde.github.io/metube/)** —
[direct routes](docs/direct-routes.md) · [authentication](docs/authentication.md) ·
[configuration reference](docs/configuration.md).

## Run

```yaml
services:
  metube:
    image: ghcr.io/fgilde/metube:latest
    container_name: metube
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - /path/to/downloads:/downloads
    environment:
      - ADMIN_USERNAME=admin                        # optional: enables the login screen
      - ADMIN_PASSWORD=change-me
      - DIRECT_ROUTES_KEY=some-long-random-string   # optional: protects direct links
```

Images for `linux/amd64` and `linux/arm64` are built on every push to `master` and published
as `ghcr.io/fgilde/metube:latest` plus a date tag. All upstream environment variables apply;
the fork adds `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DIRECT_ROUTES` and `DIRECT_ROUTES_KEY`.

## Why a fork

The direct routes were proposed upstream as
[alexta69/metube#1078](https://github.com/alexta69/metube/pull/1078) and declined: a
stream-and-forget route is a second product outside MeTube's contract, and it must not arrive
unauthenticated. Fair for upstream; for a personal instance the routes are the point. So this
fork carries them, together with the login and the key that the objection asked for, and
tracks upstream for everything else.

## Develop

```bash
# frontend (from ui/)
pnpm install --frozen-lockfile && pnpm run lint && pnpm run build && pnpm exec ng test --watch=false
# backend (from the repo root, after the frontend build)
uv sync --frozen --group dev && python -m compileall app && uv run pytest app/tests/
```

Made by [Florian Gilde](https://gilde.org). MeTube itself is the work of
[alexta69](https://github.com/alexta69) and its contributors; see upstream for the full history.
