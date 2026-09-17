# Direct streaming routes

MeTube's normal contract is asynchronous: you add a URL, the queue downloads it, and the
file lands in `DOWNLOAD_DIR`. The two routes described here add a synchronous, stateless
counterpart for the "just give me this one thing right now" case:

* `GET /watch?v=<id-or-url>` — the video as an mp4, mirroring YouTube's own URL shape so a
  YouTube link only needs its host swapped.
* `GET /dl/<name>.<ext>` — pick the format by file extension (`mp4`, `mp3`, `jpg`), and either
  search for `<name>` or fetch an explicit `?url=`.

Both run one yt-dlp job per request into a per-request temporary directory, stream that single
file back, and delete the directory once the response body has been sent. Nothing is written to
`DOWNLOAD_DIR`, nothing shows up in the queue or the history, nothing is cached.

## Settings

| Variable | Default | Meaning |
|----------|---------|---------|
| `DIRECT_ROUTES` | `true` | Enables `/watch` and `/dl/…`. When `false` the routes answer `404` and `robots.txt` does not mention them. |
| `DIRECT_ROUTES_KEY` | empty | When set, every direct request must carry the key as `?key=<value>` or an `X-Api-Key` header; otherwise `403`. Requests carrying the key are exempt from Basic auth (see below). |
| `BASIC_AUTH_USERNAME` / `BASIC_AUTH_PASSWORD` | empty | Set both to put the whole instance (UI, REST API, socket.io, file server) behind HTTP Basic auth. Setting only one is a startup error. Environment only. |

`DIRECT_ROUTES` and `DIRECT_ROUTES_KEY` can also be changed at runtime from the UI: the gear
icon in the navbar opens a settings dialog with the toggle, the key field and a *Generate*
button. Changes apply immediately (no restart) and persist in `STATE_DIR/settings.json`.
Precedence, highest first:

1. an environment variable that is explicitly set — it wins and the field is shown locked in
   the UI;
2. the value last saved from the UI;
3. the default.

The same values are available over HTTP as `GET /settings` and `POST /settings`
(JSON body with `direct_routes` and/or `direct_routes_key`; a locked field is refused with
`400`). Both endpoints sit behind Basic auth like the rest of the API.

How the two credentials combine:

| Basic auth | Key | UI / API | `/watch`, `/dl/…` |
|------------|-----|----------|-------------------|
| off | unset | open | open |
| off | set | open | key required |
| on | unset | password | password |
| on | set | password | key required, password not needed |

The last row is the intended "share a link" setup: the UI stays behind the password, while a
`/dl/….mp3?key=…` URL works from another device, a script or a media player without it.

```yaml
environment:
  - DIRECT_ROUTES=true
  - DIRECT_ROUTES_KEY=some-long-random-string
  - BASIC_AUTH_USERNAME=flo
  - BASIC_AUTH_PASSWORD=change-me
```

The container health check authenticates with the Basic auth credentials automatically when
they are set. CORS preflight (`OPTIONS`) requests are never challenged, since browsers send them
without credentials.

## Routes

### `GET /watch`

| Parameter  | Required | Meaning |
|------------|----------|---------|
| `v`        | yes      | A YouTube video ID (`PVtSAXSv7Fo`) or any URL yt-dlp understands. |
| `download` | no       | `1`/`true`/`yes`/`on` sends `Content-Disposition: attachment`; default is `inline` (plays in the browser). |
| `key`      | if `DIRECT_ROUTES_KEY` is set | The configured key. |

Always returns an mp4 (h264/av1 up to 1080p, see *Format selection*).

```
/watch?v=PVtSAXSv7Fo                 -> plays inline
/watch?v=PVtSAXSv7Fo&download=1      -> browser saves "<title>.mp4"
/watch?v=https://vimeo.com/76979871  -> any yt-dlp supported URL works too
```

### `GET /dl/<name>.<ext>`

| Part / parameter | Required | Meaning |
|------------------|----------|---------|
| `<name>`         | yes      | Search term. `-`, `_`, `+` and `.` become spaces: `Greenday-Basketcase` searches for `Greenday Basketcase`. Ignored as a search when `url` is given. |
| `<ext>`          | yes      | `mp4` (video), `mp3` (audio), `jpg`/`jpeg` (image). Anything else is a 400. |
| `url`            | no       | Fetch this URL instead of searching. Playlists collapse to their first item. |
| `download`       | no       | As for `/watch`. |
| `ts`             | no       | `jpg` only: grab the frame at this position. Accepts `90`, `1:30` or `1m30s`. Without `ts` the extractor's thumbnail is returned. |
| `key`            | if `DIRECT_ROUTES_KEY` is set | The configured key. |

Search uses yt-dlp's own `ytsearch1:` prefix, so "best match" is whatever the extractor ranks
first; MeTube adds no ranking of its own. Check the title in the `Content-Disposition` header
(or the browser's suggested file name) if it matters.

```
/dl/Greenday-Basketcase.mp3                     -> top search hit as mp3, inline
/dl/Greenday-Basketcase.mp3?download=1          -> same, saved as "<title>.mp3"
/dl/something.mp4?url=https://youtu.be/PVtSAXSv7Fo
/dl/whatever.jpg?url=https://youtu.be/PVtSAXSv7Fo        -> the video's thumbnail
/dl/whatever.jpg?url=https://youtu.be/PVtSAXSv7Fo&ts=42  -> the frame at 0:42
/dl/Greenday-Basketcase.jpg?ts=1:05                      -> search, then the frame at 1:05
```

`URL_PREFIX` applies as for every other route: with `URL_PREFIX=/metube` the paths are
`/metube/watch` and `/metube/dl/...`.

## Responses

* `200` with the file. `Content-Type` follows the extension (`video/mp4`, `audio/mpeg`,
  `image/jpeg`). `Content-Disposition` carries the extractor's title as file name, both as an
  ASCII fallback and as RFC 5987 `filename*` for non-ASCII titles.
* Range requests are honoured (`206 Partial Content`), so `<video>` seeking works.
* `400` — bad extension, empty name, unparsable `ts`, missing `v`, or a URL the SSRF guard
  refuses.
* `401` — Basic auth is on and the request carried no valid credentials (and no key applies).
* `403` — `DIRECT_ROUTES_KEY` is set and the request carried no key or a wrong one.
* `502` with a plain-text body `yt-dlp: <message>` — the extractor or ffmpeg failed
  (unavailable video, no search result, `ts` past the end, ...).

## Format selection

Everything reuses `dl_formats.get_format` / `get_opts`, i.e. the same selectors the download
form produces:

| ext   | yt-dlp format / options |
|-------|-------------------------|
| `mp4` | `get_format('video', 'auto', 'mp4', '1080')` with a `/bv*+ba/b` fallback and `merge_output_format=mp4`, so sites without native mp4 still remux into one. The 1080p cap is a fixed default. |
| `mp3` | `get_format('audio', ..., 'mp3', 'best')` plus `get_opts('audio', ...)` — FFmpegExtractAudio, embedded thumbnail and metadata, exactly like an audio download from the form. |
| `jpg` without `ts` | The thumbnail path from the form (`skip_download`, `writethumbnail`, convert to jpg). |
| `jpg` with `ts` | yt-dlp resolves a video-only mp4 stream (`bv*[ext=mp4][height<=720]/b[ext=mp4]/b`) without downloading it; ffmpeg then seeks to `ts` on that URL (with the extractor's HTTP headers) and decodes exactly one frame. Only the bytes around the keyframe are transferred, not the whole video. |

`YTDL_OPTIONS` (including the runtime `cookiefile` override and `impersonate`) is layered
underneath, so cookies, proxies and PO-token settings apply here as well. Presets and
per-download overrides are not exposed on these routes.

## Behaviour and limits

* **Temporary storage only.** Files live in a `metube-direct-*` directory under the system
  temp location for the duration of one request. Set `TMPDIR` on the container if `/tmp` is
  not the right place (tmpfs, size limits, read-only root filesystems).
* **Concurrency.** Requests share a semaphore sized by `MAX_CONCURRENT_DOWNLOADS`; extra
  requests wait rather than fail. This is separate from the queue's own worker count.
* **One process per request.** Each fetch runs in a fresh single-worker process pool so the
  connect-time SSRF guard can be installed exactly as for queue downloads. Startup cost is a
  fork on Linux; on macOS/Windows a spawn that re-imports yt-dlp (~1 s).
* **No cancellation.** If the client disconnects mid-fetch, the job finishes and the file is
  discarded.
* **No caching, no dedup.** Two identical requests do two downloads.
* **robots.txt** disallows `/dl/` and `/watch` while the routes are enabled.

## Security

* On by default. On any instance reachable from the internet, set `DIRECT_ROUTES_KEY` (or
  Basic auth, or a reverse proxy that authenticates), or switch the routes off: an anonymous
  fetch that leaves no queue row is a different exposure than the queue.
* `validate_url` runs on the submitted `v`/`url` before anything is spawned, and
  `install_socket_guard` runs inside the worker process, so redirects and manifest-derived
  media URLs are re-checked at connect time — the same two layers a queue download gets.
  `ALLOW_PRIVATE_ADDRESSES` disables both, as elsewhere.
* The ffmpeg frame grab fetches a media URL outside Python's socket module, so the connect-time
  guard cannot see it. The URL is passed through `validate_url` first; a redirect from an
  allowed host to an internal one during that single fetch is not caught. This is the same gap
  the existing clip feature has (yt-dlp's FFmpegFD fetches the same way).
* Output paths go through `_ConfinedYoutubeDL` with the temp dir as the only allowed root, so a
  hostile title cannot escape it. The served path is always `media.<ext>` inside that dir.
* `<name>` never touches the filesystem; it only becomes a search string.
* Credentials are compared with `hmac.compare_digest`. Basic auth sends the password with
  every request, so use it over HTTPS (`HTTPS=true` or a TLS-terminating proxy).

## Upstream status

Proposed upstream as alexta69/metube#1078 and declined: the maintainer considers a
stream-and-forget route a second product outside MeTube's contract, and objected to the
routes arriving switched on without authentication and to file names being turned into
searches. This fork keeps the feature, with the toggle, the key and Basic auth added in
response to the first point.
