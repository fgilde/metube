# Direct routes

MeTube's normal contract is asynchronous: you add a URL, the queue downloads it, and the file
lands in `DOWNLOAD_DIR`. The direct routes are the synchronous, stateless counterpart for the
"just give me this one thing right now" case: one request, one yt-dlp job into a temporary
directory, the file streamed back, the directory deleted. Nothing is written to `DOWNLOAD_DIR`,
nothing shows up in the queue or the history, nothing is cached.

They are **independent of users**: a login is never required for them. If you want them
protected, set an access key (see [Settings](#settings)); with the key in the link they work
from a media player, a script, another device or a friend's browser.

## Two routes

### `GET /watch?v=…`

Mirrors YouTube's own URL shape, so a YouTube link only needs its host swapped.

| Parameter | Required | Meaning |
|-----------|----------|---------|
| `v` | yes | A YouTube video ID (`PVtSAXSv7Fo`) or any URL yt-dlp understands (`https://vimeo.com/76979871`). |
| `format` | no | `mp4` (default), `mp3` or `jpg`. |
| `ts` | no | `jpg` only: the frame at this position. `42`, `1:30` and `1m30s` all work. Without `ts` you get the thumbnail. |
| `download` | no | `1`/`true`/`yes`/`on` sends the file as an attachment (the browser saves it); otherwise it is shown inline (plays in the tab). |
| `key` | if configured | The access key. Alternatively send it as an `X-Api-Key` header. |

### `GET /dl/<name>.<ext>`

The extension picks the format; the name is either a search or just the file name.

| Part / parameter | Required | Meaning |
|------------------|----------|---------|
| `<ext>` | yes | `mp4`, `mp3` or `jpg` (`jpeg` works too). Anything else is a `400`. |
| `<name>` | yes | Without `url`: a search term — `-`, `_`, `+` and `.` become spaces, so `Green-Day-Basket-Case` searches for *Green Day Basket Case* and the top hit is used. With `url`: only the file name you want. |
| `url` | no | Fetch this URL instead of searching. Playlists collapse to their first item. |
| `ts` | no | As for `/watch`. |
| `download` | no | As for `/watch`. |
| `key` | if configured | As for `/watch`. |

Search uses yt-dlp's own `ytsearch1:` prefix, so "top hit" is whatever the extractor ranks
first; MeTube adds no ranking of its own. The title of what you actually got is in the
`Content-Disposition` header (and in the file name the browser suggests).

## Examples

With an instance at `https://tube.example.org` and no key:

| You want | Link |
|----------|------|
| play a YouTube video in the browser | `https://tube.example.org/watch?v=PVtSAXSv7Fo` |
| save it as a file | `https://tube.example.org/watch?v=PVtSAXSv7Fo&download=1` |
| audio only, as mp3 | `https://tube.example.org/watch?v=PVtSAXSv7Fo&format=mp3` |
| the thumbnail | `https://tube.example.org/watch?v=PVtSAXSv7Fo&format=jpg` |
| a frame at 0:42 | `https://tube.example.org/watch?v=PVtSAXSv7Fo&format=jpg&ts=42` |
| a video from any yt-dlp site | `https://tube.example.org/watch?v=https://vimeo.com/76979871` |
| search by name, top hit as mp3 | `https://tube.example.org/dl/Green-Day-Basket-Case.mp3` |
| search, save as mp4 | `https://tube.example.org/dl/Green-Day-Basket-Case.mp4?download=1` |
| explicit URL, your own file name | `https://tube.example.org/dl/basket-case.mp3?url=https://youtu.be/PVtSAXSv7Fo` |
| a frame at 1:05 from the search hit | `https://tube.example.org/dl/Green-Day-Basket-Case.jpg?ts=1:05` |

With a key, append `&key=…` (or `?key=…` when it is the first parameter):

```
https://tube.example.org/dl/Green-Day-Basket-Case.mp3?key=8f1c…
https://tube.example.org/watch?v=PVtSAXSv7Fo&format=mp3&key=8f1c…
```

The **Settings page** in the app (gear icon, admins) has a link builder that produces exactly
these links for your own instance — with your host, your `URL_PREFIX` and your key — plus a
copy button and an *open* button for every example, so you can test them straight away.

`URL_PREFIX` applies as for every other route: with `URL_PREFIX=/metube` the paths are
`/metube/watch` and `/metube/dl/…`.

### From the command line

```bash
curl -L -o song.mp3 'https://tube.example.org/dl/Green-Day-Basket-Case.mp3?key=8f1c…'
curl -H 'X-Api-Key: 8f1c…' -o frame.jpg 'https://tube.example.org/watch?v=PVtSAXSv7Fo&format=jpg&ts=42'
mpv 'https://tube.example.org/watch?v=PVtSAXSv7Fo&key=8f1c…'
```

## Responses

* `200` with the file. `Content-Type` follows the format (`video/mp4`, `audio/mpeg`,
  `image/jpeg`). `Content-Disposition` carries the title as file name, as an ASCII fallback
  and as RFC 5987 `filename*` for non-ASCII titles.
* Range requests are honoured (`206 Partial Content`), so seeking in a `<video>` works.
* `400` — bad format or extension, empty name, unparsable `ts`, missing `v`, or a URL the SSRF
  guard refuses.
* `403` — an access key is configured and the request carried none or a wrong one.
* `404` — the routes are switched off.
* `502` with a plain-text body `yt-dlp: <message>` — the extractor or ffmpeg failed
  (unavailable video, no search result, `ts` past the end, …).

## Formats

Everything reuses the same selectors the download form produces (`dl_formats.get_format` /
`get_opts`), so the result matches what the queue would have written.

| Format | What you get |
|--------|--------------|
| `mp4` | Video up to 1080p, h264 or av1 in an mp4 container (`bestvideo[ext=mp4]+bestaudio[ext=m4a]`, with a remux fallback for sites without native mp4). The cap is fixed. |
| `mp3` | Best audio, converted to mp3 with the thumbnail embedded as cover and the metadata written — exactly like an audio download from the form. |
| `jpg` without `ts` | The extractor's thumbnail, converted to jpg. |
| `jpg` with `ts` | yt-dlp resolves a video-only mp4 stream (≤720p) without downloading it; ffmpeg seeks to `ts` on that URL and decodes exactly one frame. Only the bytes around the keyframe are transferred. |

`YTDL_OPTIONS`, uploaded cookies, proxies and PO-token settings apply here as well; presets
and per-download overrides are not exposed.

## Settings

| Variable | Default | Meaning |
|----------|---------|---------|
| `DIRECT_ROUTES` | `true` | Enables the routes. When `false` they answer `404` and `robots.txt` does not mention them. |
| `DIRECT_ROUTES_KEY` | empty | When set, every direct request must carry the key as `?key=…` or an `X-Api-Key` header; otherwise `403`. |

Both can also be changed at runtime on the **Settings page** (gear icon in the navbar,
admins): a toggle, the key field and a *Generate* button for a random key. Changes apply to
the next request — no restart — and persist in `STATE_DIR/settings.json`. Precedence, highest
first:

1. an environment variable that is explicitly set — it wins and the field is shown locked;
2. the value last saved from the UI;
3. the default.

The same values are available as `GET /settings` and `POST /settings` (JSON body with
`direct_routes` and/or `direct_routes_key`; a locked field is refused with `400`). Both
endpoints require an admin session once users exist — see [Authentication](authentication).

## Behaviour and limits

* **Temporary storage only.** Files live in a `metube-direct-*` directory under the system temp
  location for the duration of one request. Set `TMPDIR` on the container if `/tmp` is not the
  right place (tmpfs, size limits, read-only root filesystems).
* **Concurrency.** Requests share a semaphore sized by `MAX_CONCURRENT_DOWNLOADS`; extra
  requests wait rather than fail. This is separate from the queue's own worker count.
* **One process per request.** Each fetch runs in a fresh single-worker process so the
  connect-time SSRF guard can be installed exactly as for queue downloads. Startup cost is a fork
  on Linux; on macOS/Windows a spawn that re-imports yt-dlp (~1 s).
* **No cancellation.** If the client disconnects mid-fetch, the job finishes and the file is
  discarded.
* **No caching, no dedup.** Two identical requests do two downloads.
* **robots.txt** disallows `/dl/` and `/watch` while the routes are enabled.

## Security

* On any instance reachable from the internet, set `DIRECT_ROUTES_KEY` or switch the routes
  off: an anonymous fetch that leaves no queue row is a different exposure than the queue.
  Logging in does not protect them — by design, so links can be shared.
* `validate_url` runs on the submitted `v`/`url` before anything is spawned, and
  `install_socket_guard` runs inside the worker process, so redirects and manifest-derived media
  URLs are re-checked at connect time — the same two layers a queue download gets.
  `ALLOW_PRIVATE_ADDRESSES` disables both, as elsewhere.
* The ffmpeg frame grab fetches a media URL outside Python's socket module, so the connect-time
  guard cannot see it. The URL is passed through `validate_url` first; a redirect from an allowed
  host to an internal one during that single fetch is not caught. This is the same gap the
  existing clip feature has (yt-dlp's FFmpegFD fetches the same way).
* Output paths go through `_ConfinedYoutubeDL` with the temp dir as the only allowed root, so a
  hostile title cannot escape it. The served path is always `media.<ext>` inside that dir.
* `<name>` never touches the filesystem; it only becomes a search string.
* The key is compared with `hmac.compare_digest`.

## Upstream status

Proposed upstream as [alexta69/metube#1078](https://github.com/alexta69/metube/pull/1078)
and declined: the maintainer considers a stream-and-forget route a second product outside
MeTube's contract, and objected to the routes arriving switched on without authentication and
to file names being turned into searches. This fork keeps the feature, with the toggle, the key
and the login added in response to the first point.
