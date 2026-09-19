# MeTube — the fgilde fork

A self-hosted web UI for [yt-dlp](https://github.com/yt-dlp/yt-dlp): paste a URL, get the
file. This fork of [alexta69/metube](https://github.com/alexta69/metube) keeps everything
upstream does and adds the pieces upstream chose not to own:

* **Direct links** — `/watch?v=…` and `/dl/<name>.<mp3|mp4|jpg>` fetch one item and stream it
  straight back, without saving anything. Play it, save it, grab the audio, the thumbnail or a
  single frame. Search by name or pass any URL yt-dlp understands.
* **Login and users** — a real login screen, admins and users, managed in the UI. Direct links
  stay independent of users and are protected by an access key instead.
* **Settings page** — toggle the direct routes, manage the key, and build ready-to-use links for
  your own instance with examples for every format.

[Direct routes](direct-routes) · [Authentication](authentication) · [Configuration reference](configuration) ·
[Source on GitHub](https://github.com/fgilde/metube) · [gilde.org](https://gilde.org)

## Run it

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
      - ADMIN_USERNAME=admin          # optional: enables the login screen
      - ADMIN_PASSWORD=change-me
      - DIRECT_ROUTES_KEY=some-long-random-string   # optional: protects direct links
```

Images are built for `linux/amd64` and `linux/arm64` on every push to `master` and published as
`ghcr.io/fgilde/metube:latest` plus a date tag.

## Try a link

With the container running on `http://localhost:8081`:

```
http://localhost:8081/watch?v=PVtSAXSv7Fo
http://localhost:8081/watch?v=PVtSAXSv7Fo&format=mp3&download=1
http://localhost:8081/dl/Green-Day-Basket-Case.mp3
http://localhost:8081/dl/whatever.jpg?url=https://youtu.be/PVtSAXSv7Fo&ts=42
```

Append `&key=…` (or `?key=…`) once `DIRECT_ROUTES_KEY` is set. The settings page inside the app
builds these links for your instance, key included.

## Why a fork

The direct routes were proposed upstream as
[alexta69/metube#1078](https://github.com/alexta69/metube/pull/1078) and declined: the
maintainer considers a stream-and-forget route a second product outside MeTube's contract,
and wanted no unauthenticated surface. Both points are fair for upstream; for a personal
instance the routes are the point. So this fork carries them, together with the login and
key that the objection asked for, and tracks upstream for everything else.

Made by [Florian Gilde](https://gilde.org).
