# AGENTS.md — £UVR€

Read this file fully before writing code. When two rules conflict, the
"Non-negotiables" below win. When genuinely blocked on a decision that
this file does not cover, make the smaller change and note it here.

---

## 1. What this project is

£UVR€ is an art-gallery storefront for garments. Two founders (the owner
and one friend) upload clothing pieces as curated art; the public browses
a swipeable gallery and buys one-of-one pieces. Sellers are anonymous to
the public ("blind gallery"): only a per-piece pseudonym is ever exposed.
All handovers are in person, in Montreal. No shipping in v1.

**Current state:** a single-file `index.html` exists — a fully working
frontend demo (marble backdrop, £UVR€ laser logo, auto-framing from image
colors, swipe physics, FLIP dossier expansion, a simulated `LUVRE_API`
backed by localStorage, and a generative-textile renderer used as
placeholder imagery). **Treat `index.html` as the design source of truth.**
Your job is to put a real backend under it, replace the placeholder
imagery with real uploaded photos, and wire up real payments.

## 2. Non-negotiables

1. **Blind seller.** The public API must never return seller email, seller
   id, or any seller identity — only the piece's `pseudonym`. There is a
   regression test for this (see §11); it must never be deleted or skipped.
2. **No prices on the main feed.** Price appears only inside the expanded
   dossier view, exactly as the current demo does.
3. **No card data on our servers, ever.** PayPal is hosted/redirect,
   Interac settles bank-to-bank, crypto settles on-chain/hosted. We stay
   PCI SAQ-A. Never build a card form.
4. **Money is integer cents (CAD)**, from input to database to provider.
   No floats anywhere in the money path.
5. **Only the studio (the two founders) uploads pieces.** There is no
   public seller signup in v1. The old demo's open-registration portal is
   intentionally retired — auth is studio-only.
6. **Design tokens are frozen:** ink color `#cac4ce` for all site text,
   logo "£UVR€" in Cinzel with the existing neon filter, emerald marble
   canvas, auto-frame driven by per-image palette, Joséfin Sans /
   Cormorant Garamond pairing. Do not restyle. New UI (checkout, studio)
   must reuse the existing veil/sheet/toast components and the site's
   curatorial writing voice — no generic e-commerce copy ("Add to cart",
   "Checkout", "Deal") anywhere.
7. **Webhooks are the source of truth** for PayPal and crypto payment
   status; the redirect return path is a convenience only. All webhook
   handlers must verify signatures and be idempotent.

## 3. Reality notes (do not chase impossible things)

- **Interac has no public merchant API for e-Transfer.** Businesses accept
  e-Transfer by publishing an email and asking buyers to include a
  reference code. That is what we build (§8.3). If we later want Interac
  Debit online, that requires an acquirer (Moneris, Bambora, Global
  Payments) — a separate future milestone, not this build. In-person
  Interac tap at handover works today via any POS app; the studio
  "mark paid" action covers it.
- **`rembg` is not perfect.** Background removal will occasionally fail
  (empty alpha, chopped fabric). The pipeline must flag failures and the
  studio UI must let the seller fall back to the original image or re-run
  with different settings. Build the review step from day one.
- **Crypto volatility:** the CAD amount is locked into the charge at
  creation time. Only the provider's `confirmed` event (not `pending`)
  marks an order paid.

## 4. Architecture & repo layout

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (SQLite for dev,
  Postgres for prod), Alembic. CPU-heavy work (background removal) runs
  in an in-process worker thread with a queue table; swap for RQ/Celery
  later if ever needed.
- **Frontend:** the existing single-file frontend, split into static
  assets served by FastAPI. Vanilla JS, no build step, no framework.
- **Payments sit server-side only.** The frontend never holds provider
  secrets; it receives approval/checkout URLs and status.

```
luvre/
├── AGENTS.md
├── .env.example
├── requirements.txt
├── index.html              # demo, kept as design reference until fully ported
├── static/
│   ├── index.html          # ported gallery
│   ├── app.css             # extracted styles (tokens unchanged)
│   ├── app.js              # gallery logic ported from the demo
│   └── studio.js           # studio (upload/review/orders) UI
├── app/
│   ├── main.py             # FastAPI app, routes, static mount
│   ├── config.py           # env loading (pydantic-settings)
│   ├── models.py           # SQLAlchemy models
│   ├── schemas.py          # public/studio Pydantic schemas
│   ├── auth.py             # bcrypt + JWT, studio-role guard
│   ├── cli.py              # `python -m app.cli create-founder <email>`
│   ├── services/
│   │   ├── background.py   # rembg pipeline (§9)
│   │   ├── palette.py      # port of the demo's 4-bit quantizer
│   │   ├── plates.py       # 4:5 transparent plate composition
│   │   └── orders.py       # state machine + reference codes + TTL sweep
│   ├── payments/
│   │   ├── paypal.py
│   │   ├── interac.py
│   │   └── crypto.py       # provider behind CRYPTO_PROVIDER env
│   └── workers.py          # queue loop + TTL sweeper
├── tests/
│   ├── conftest.py
│   ├── test_projection.py
│   ├── test_orders.py
│   ├── test_webhooks.py
│   ├── test_background.py
│   └── fixtures/shirt.jpg
└── deploy/docker-compose.yml, nginx/, Caddyfile or similar
```

## 5. Environment

Copy `.env.example` to `.env`; secrets never get committed.

```ini
APP_ENV=dev
SECRET_KEY=                 # openssl rand -hex 32
DATABASE_URL=sqlite:///./luvre.db
MEDIA_DIR=./media
PUBLIC_BASE_URL=http://localhost:8000
ORDER_TTL_HOURS=48

PAYPAL_ENV=sandbox          # sandbox | live
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_WEBHOOK_ID=

CRYPTO_PROVIDER=coinbase    # coinbase | btpay
COINBASE_API_KEY=
COINBASE_WEBHOOK_SECRET=
BTPAY_URL=
BTPAY_API_KEY=
BTPAY_WEBHOOK_SECRET=

INTERAC_TRANSFER_EMAIL=     # the e-Transfer deposit address

REMBG_MODEL=isnet-general-use
REMBG_ALPHA_MATTING=1
```

Setup: `pip install -r requirements.txt`, `python -m app.cli create-founder you@…`
(prompts for password), `uvicorn app.main:app --reload`.

## 6. Data model (core fields)

- **users** — id, email (unique), password_hash, role (`founder`),
  display_name, created_at.
- **pieces** — id, seller_user_id (**private — never serialized publicly**),
  pseudonym (public), title, year, textile, dims, story, care,
  price_cents (int, CAD), status (`draft|published|sold|retired`),
  created_at, published_at.
- **piece_images** — id, piece_id, slot (0 = the hanging, 1–3 = detail
  shots), original_path, cutout_path, plate_path, width, height,
  dominant_palette (JSON, 3 colors — feeds the auto-frame CSS),
  bg_state (`pending|done|failed|review|use_original`), created_at.
- **orders** — id, piece_id, buyer_name, buyer_email, buyer_phone (nullable),
  status (see §7), method (`paypal|interac|crypto|on_delivery`),
  amount_cents, currency (`CAD`), reference_code (unique, e.g. `LV-7K4Q`,
  charset without 0/O/1/I), provider_ref (paypal order id / crypto charge id),
  handover_area (Plateau / Mile End / Downtown / Old Montreal / Villeneuve—
  seller suggests), handover_window, handover_place_note,
  created_at, expires_at, paid_at, completed_at.
- **payment_events** — id, order_id, provider, provider_event_id (unique
  with provider — this is the idempotency key), event_type,
  signature_valid (bool), received_at. Raw payloads stored sanitized
  (no buyer secrets).

## 7. Order state machine

All transitions go through one guarded function
(`services/orders.transition(order, event)`); nothing else mutates status.

| from            | event              | to                | trigger                                  |
|-----------------|--------------------|-------------------|------------------------------------------|
| created         | provider_ready     | awaiting_payment  | PayPal order / crypto charge created / Interac instructions issued |
| created         | reserve_on_delivery| reserved          | buyer chose pay-at-handover (Montreal)   |
| awaiting_payment| payment_confirmed  | paid              | verified webhook, or studio mark-paid    |
| reserved        | payment_confirmed  | paid              | studio mark-paid (cash / Interac tap)    |
| paid            | handover_scheduled | handover_scheduled| studio sets time + place                 |
| handover_scheduled | handover_done   | completed         | studio marks                             |
| awaiting_payment / reserved | ttl_expired / cancelled | cancelled | sweeper after ORDER_TTL_HOURS, or studio |
| paid            | refund_issued      | refunded          | studio, manual, rare                     |

Entering **paid** flips the piece to `sold`. Unpaid states hold the piece
(reserved against other buyers) until TTL expiry.

## 8. Payments

Checkout lives in the dossier's offer row: "Acquire — CAD 3,900" opens a
veil-styled sheet where the buyer picks a method and leaves contact
details. **Guest checkout only in v1 — no buyer accounts.** Buyers track
their order on a status page reached by order id + email code.

### 8.1 PayPal
1. `POST /api/orders` (method `paypal`) → server creates the order via
   PayPal Orders v2 (`intent=CAPTURE`, amount in CAD) and returns the
   approval URL. Frontend redirects. (Redirect flow, not embedded JS
   buttons — keeps our checkout sheet clean.)
2. On return: server captures; webhook `PAYMENT.CAPTURE.COMPLETED` is the
   authoritative confirmation.
3. Verify webhooks by calling PayPal's
   `/v1/notifications/verify-webhook-signature` with `PAYPAL_WEBHOOK_ID`.
4. Ship in sandbox first; flipping `PAYPAL_ENV=live` is the only change.

### 8.2 Crypto
1. `POST /api/orders` (method `crypto`) → server creates a charge
   (Coinbase Commerce default; BTCPay behind the same interface if the
   founders choose self-custody) for the locked CAD amount, returns the
   hosted checkout URL.
2. Webhook handler verifies the HMAC signature (Coinbase: `X-CC-Webhook-
   Signature` = HMAC-SHA256 of `"{timestamp}.{raw_body}"` with the shared
   secret — verify against the raw request body, before any parsing).
   BTCPay equivalent: its webhook secret header.
3. Only `confirmed` → `payment_confirmed`. `pending` updates a note only.

### 8.3 Interac e-Transfer (Canada)
1. `POST /api/orders` (method `interac`) → order goes to `awaiting_payment`
   with a unique reference code and TTL.
2. Checkout + status page show the instructions in the site voice:
   "Send an Interac e-Transfer of CAD $X to {INTERAC_TRANSFER_EMAIL},
   message {reference}. The piece is held for you for 48 hours."
3. The studio marks the transfer received (`mark-paid`). Later automation
   (email parsing / bank partner API) is explicitly out of scope for v1.

### 8.4 Pay at handover (Montreal only)
Buyer picks a general area + preferred window at checkout; order goes to
`reserved` with the same TTL. At the meetup the founders accept cash or
Interac tap (any POS app), then `mark-paid` → schedule → complete.

## 9. Background removal pipeline (Python — required)

Module: `app/services/background.py`.

- **Library:** `rembg` (ONNX). One global session, created at worker
  startup, model from `REMBG_MODEL` (default `isnet-general-use`;
  `birefnet-general` if the installed rembg supports it). Never create a
  session per request. Pre-download model weights in the Docker image.
- **Per uploaded image, async:** store original → enqueue → worker runs
  removal (alpha matting on by default: fg 240 / bg 15 / erode 12 —
  expose "re-run without matting" in the studio) → compose the **plate**:
  a 1200×1500 transparent 4:5 canvas with the cutout centered (this is
  what the gallery hangs) → run `palette.py` on the cutout's opaque
  pixels only (port the demo's 4-bit bucket quantizer, keep the
  min-distance pick of 3 colors) → save `dominant_palette` → `bg_state=done`.
- **QC flags:** if opaque-pixel coverage is < 3% or > 97%, set
  `bg_state=review` and use the original image as the plate until the
  seller decides. Studio review UI: side-by-side original/cutout, buttons
  for *approve*, *use original*, *re-run (matting on/off)*.
- **Detail shots (slots 1–3):** pipeline runs on them too, but the seller
  can choose *use original* per image — macros sometimes want context.
- **Upload hardening:** max 25 MB, sniff the real MIME with Pillow (never
  trust the client), decode fully (rejects polyglots), generate UUID
  filenames, never use user filenames in paths.

## 10. API surface (summary)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | /api/auth/login | — | studio login → JWT |
| GET  | /api/me | studio | session check |
| POST | /api/pieces | studio | create draft + upload images (multipart) |
| GET  | /api/pieces | public | published pieces, **projected** (§2.1) |
| GET  | /api/pieces/{id} | public | dossier data, projected |
| PATCH| /api/pieces/{id} | studio | edit fields |
| POST | /api/pieces/{id}/publish · /retire · /mark-sold | studio | lifecycle |
| POST | /api/images/{id}/rerun-background | studio | re-run with options |
| POST | /api/orders | public | start checkout → per-method payload |
| GET  | /api/orders/{id}?code=… | buyer | status page (reference/email code) |
| POST | /api/orders/{id}/paypal/return | public | capture attempt after redirect |
| POST | /webhooks/paypal · /webhooks/crypto | signed | payment events |
| GET  | /api/studio/orders | studio | order desk |
| POST | /api/studio/orders/{id}/mark-paid · /schedule · /complete · /cancel | studio | fulfillment |

The public piece projection contains exactly: `id, pseudonym, title,
year, micro, textile, dims, price_cents, story, care, images[{slot,
plate_url, palette}]`. Anything else is a leak.

Frontend port note: the demo's `window.LUVRE_API` methods map 1:1 onto
these endpoints — replace their bodies with `fetch` calls; keep the
same method names and promise shapes so `app.js` changes minimally.
The generative-textile renderer stays in the codebase as a dev fixture
generator for tests, not as product imagery.

## 11. Milestones & definition of done

- **M0 — Skeleton.** FastAPI serves the ported gallery; `/api/pieces`
  returns seed data; studio login works; tests run in CI or `make test`.
- **M1 — Upload + background removal.** Full piece CRUD; upload JPEG →
  cutout + plate + palette appear in the gallery with the auto-frame
  reacting; review/re-run/use-original all work; failed removals flagged.
  *DoD: an end-to-end manual pass plus the background smoke test green.*
- **M2 — Orders + Interac.** Order creation, reference codes, status
  page, TTL sweeper, studio mark-paid, piece→sold, cancel path.
  *DoD: a full offline purchase completes via tests and by hand.*
- **M3 — PayPal.** Sandbox end-to-end; webhook verified + idempotent
  (replay test); live keys documented.
- **M4 — Crypto.** Charge creation + signed webhook + confirmed-only
  payment; status page shows "settling / settled".
- **M5 — Handover.** Area/window captured at checkout; studio scheduling;
  completed flow; sold plaque state in the gallery (dimmed, "Acquired").
- **M6 — Deploy.** Docker Compose (app + Postgres + reverse proxy with
  HTTPS), `pg_dump` nightly cron, founder bootstrap documented, secrets
  in the host env. Recommend a Montreal-region VPS (OVH BHS) —
  low latency for local buyers, data residency sanity.

## 12. Testing requirements (pytest, all must pass before merge)

- `test_projection.py` — public endpoints never contain seller keys
  (`seller_user_id`, `email`, `password_hash`); response key sets match
  §10 exactly.
- `test_orders.py` — state machine rejects illegal transitions; reference
  codes unique + restricted charset; TTL expiry cancels; entering `paid`
  marks piece sold; all amounts ints.
- `test_webhooks.py` — fixed HMAC vectors for the crypto signature;
  replayed event ids are no-ops; invalid signatures → 400 and no state
  change.
- `test_background.py` — fixture image: output has alpha; coverage within
  3–90%; palette extracted has 3 entries; failure path sets `review`.

## 13. Security checklist

bcrypt passwords; JWT with expiry; login rate-limited; ORM-only SQL;
uploads per §9 hardening; CORS locked to `PUBLIC_BASE_URL`; HTTPS-only in
prod; webhook signature verification mandatory; `.env` git-ignored;
buyer data minimized (email + name + optional phone only — Quebec Law 25
mindset); nightly encrypted backups off-box.

## 14. Conventions

Python: type hints on public functions, `ruff` + `black`, UTC everywhere
(display `America/Toronto`). Frontend: vanilla JS, CSS tokens only via
`:root`, keep the demo's easing/physics constants untouched. Copy: keep
the curatorial voice. Update this file whenever a decision here changes.

## 15. Explicitly out of scope for v1

Shipping/rates · buyer accounts · public seller signup · Interac Debit
online via acquirer · automated e-Transfer reconciliation · refunds UI
beyond a manual DB action · multi-currency · EN/FR toggle (revisit — it
is Montreal, and cheap to add later).

## 16. Port notes (M0 — demo reconciled)

- `index.html` (repo root) arrived after the backend skeleton was cut, so
  `static/` was re-ported from the real demo: `app.css` is the demo's
  `<style>` verbatim (minus the retired registration-tab rules),
  `app.js` is the demo's script with only the transport swapped, and all
  motion/easing/physics constants are untouched.
- Wire-to-wall field mapping lives in `fromProjection` (`static/app.js`):
  `pseudonym → maker`, `price_cents (int) → price` display string
  (`CAD 3,900`), `images[0].plate_url → img`,
  `images[0].palette → _palette` (feeds `fixtureParams`, which synthesizes
  renderer inputs for pieces awaiting their plate in M1).
- The demo's SEED collection + generative renderer survive in `app.js` as
  the dev-fixture fallback: they hang only when `/api/pieces` is
  unreachable or the wall is empty — never alongside real data.
- The Consign portal is studio-only: no tabs, no `register`, single
  email+key form → `POST /api/auth/login`. `register` still exists on
  `window.LUVRE_API` (promise-shape compat) but throws a retired error.
- `tests/test_static_port.py` guards the retirement (fails on
  `Create access` / `Cut a key` / `auth/register` relics) and the frozen
  tokens. It must never be deleted or skipped — same as `test_projection`.

## 17. M1 notes (upload — revised: background removal scratched)

- The founders cut their own plates by hand, so `rembg` is out:
  no `bg_jobs`, no worker, no review endpoints, no onnx weights.
  `store_upload` validates (Pillow-sniffed MIME, 25 MB, UUID names),
  cover-crops the photo to a 1200×1500 4:5 plate (center-weighted),
  and extracts the palette from the hung plate. `bg_state` is `done`
  at upload; the column stays for a future pipeline.
- `POST /api/pieces` branches on content-type: JSON (fields only) or
  multipart (`images[]`, max 4 — slot 0 the hanging, 1–3 details).
  `price_cents`/`year` whole digits only (floats → 400).
- `GET /api/studio/pieces` (full studio view — the one API addition
  beyond §10's table) feeds the studio desk.
- The studio file input posts real multipart; the gallery's `imagePlate`
  path hangs `plate_url` the moment it exists.

## 18. M2 notes (orders + Interac — built)

- `POST /api/orders` accepts `interac` (→ `awaiting_payment` with the
  §8.3 instructions) and `on_delivery` (→ `reserved`, area required);
  `paypal`/`crypto` → 400 until M3/M4. Amount is always the piece's
  `price_cents`; buyer input never sets money.
- Unpaid orders hold the piece: second commissions → 409, and held
  pieces leave the public feed until TTL expiry / cancel / completion.
  Reference codes are dealt unique (collision loop, not just hope).
- Buyer status: `GET /api/orders/{id}?code=LV-XXXX` — the reference IS
  the key; wrong/missing code → 404. No buyer accounts, ever.
- Studio desk (`GET /api/studio/orders`, `mark-paid /schedule
  /complete /cancel`) lives in the atelier portal; the dossier's
  Enquire button opens the commission sheet (method, contact, quarter,
  hour) plus an ask-after-it lookup. Sold pieces hang until M5 gives
  them their Acquired plaque — Enquiring on one 404s for now.

## 19. M3 notes (PayPal — built, sandbox)

- `POST /api/orders` with `paypal` creates a PayPal Orders v2 `CAPTURE`
  order (locked CAD decimal on PayPal's wire only — cents everywhere
  inside) and returns `approval_url`; the sheet shows the reference
  first, then a Continue button (user gesture, no popup trap).
- Return/cancel roads point at `/?commission={id}[&cancelled=1]`;
  boot opens the ask-after-it lookup with the number prefilled.
  `POST /api/orders/{id}/paypal/return` attempts capture but never
  marks paid — only `PAYMENT.CAPTURE.COMPLETED` (verified via
  `verify-webhook-signature` with `PAYPAL_WEBHOOK_ID`) does that.
  Webhook order matching: `resource.custom_id` (our reference) first,
  PayPal order id second; replays are no-ops via `payment_events`.
- Ship in sandbox: fill `PAYPAL_CLIENT_ID/SECRET/WEBHOOK_ID`, create a
  sandbox webhook for `PAYMENT.CAPTURE.COMPLETED`, run a live round
  trip, then flip `PAYPAL_ENV=live` — the only change. Missing keys →
  503, never a half-made commission (rollback before raise).

## 20. M4 notes (crypto — manual wallet, revised)

- The provider flow (Coinbase/BTCPay in `app/payments/crypto.py`)
  is shelved: buyers send to the founders' own wallet
  (`CRYPTO_DEPOSIT_ADDRESS` in host env — never committed), then
  press "I've sent it" and paste the transaction hash as proof
  (`POST /api/orders/{id}/tx-hash`, guarded by the reference code).
  The desk verifies on-chain with its own eyes, then `mark-paid`.
- `POST /api/orders` with `crypto` needs no keys and returns no
  `checkout_url` — just the instructions naming the address. The
  status page says "watching the chain" once a hash is kept; the
  order stays `awaiting_payment` until the studio settles it.
- The studio desk shows the pasted hash per commission (`tx_hash`
  column, `9c2f1a8df16c6` revision — existing dev DBs need
  `alembic stamp 75e1a8df16c6 && alembic upgrade head` once).
- Three coins: ETH + USDC on Ethereum (one address shape),
  BTC on its own. The buyer picks the coin at checkout
  (`pay_currency`, `4f8a2c1d9e3b` revision — validated, no silent
  default); instructions name that coin's address
  (`CRYPTO_{ETH,BTC,USDC}_ADDRESS` in host env — never committed).
  The desk links each pasted hash to its explorer (Etherscan for
  ETH/USDC, mempool.space for BTC) — verification stays one click.
- The old automated webhook path still verifies + records (kept for
  later), but nothing in the manual flow calls it.

## 21. M5 notes (handover — the Acquired plaque)

- The wall already captured quarter + hour (M2) and the desk already
  scheduled + completed; M5's work was the sold state made visible.
- The public projection gains one key: `status` (`published` | `sold`
  only — `project_piece` refuses anything else, so drafts can never
  leak through the projector). `test_projection`'s exact-key set
  covers it; anything beyond those keys is still a leak.
- The gallery dims sold hangings (`saturate(.35) brightness(.72)`,
  tokens untouched) and swaps the plaque to **Acquired**; the dossier
  replaces price + Enquire with the single word. Enquiring on a sold
  piece still 404s server-side — the hidden button is manners, the
  404 is the lock.
- The ask-after-it lookup now names the hour and place once the desk
  sets them (`handover_place_note` joined the buyer status view —
  fulfillment detail, not identity).

## 22. M6 notes (deploy — boxed)

- `Dockerfile` (3.12-slim) + `deploy/docker-compose.yml` (app +
  Postgres 16 + Caddy with automatic HTTPS) + `deploy/Caddyfile`.
  Secrets live in the host env (`DOMAIN/SECRET_KEY/POSTGRES_PASSWORD`
  required); the container boots with `alembic upgrade head`.
- Postgres-ready: `psycopg[binary]` in requirements, generic
  `sqlalchemy.JSON` (the sqlite-dialect import would not survive
  Postgres), `alembic/` with env + reviewed initial revision.
  `GET /api/health` feeds the compose healthchecks.
- `deploy/backup.sh` + crontab line in `README.md`: nightly
  `pg_dump -Fc`, 14 nights local, rsync off-box. Founder bootstrap,
  money keys, and the OVH BHS recommendation live in `README.md`.
- Dev still runs on SQLite via `DATABASE_URL`; nothing in `app/`
  assumes Postgres beyond the generic JSON type.
- Staging: root `render.yaml` (free web + free Postgres, staging only —
  it sleeps, the DB is time-limited, uploads vanish with no disk).
  `app/db.py` normalizes Heroku-style `postgres://` URLs and the
  config tolerates a schemeless `PUBLIC_BASE_URL`, both for Render's
  wiring. Production stays `deploy/` on the VPS.

## 23. Access (no accounts — the knock is the key)

- There are no accounts, no passwords, no founder rows that matter:
  `app/auth.py`, `app/cli.py`, and `tests/test_founders.py` were
  deleted. Studio endpoints take no credentials; the money roads
  already pay Raph directly, so the desk holds nothing worth stealing
  but the hanging itself.
- The door is unlisted twice over, in order: three touches on the
  £UVR€ wordmark within a breath reveal the entry (nothing more),
  and three touches on the entry open the desk
  (`https://<host>/#atelier` opens it straight away). Every visit
  starts shut — nothing remembers the knock, by design. Tell Raph
  privately — never in print, never in a screenshot.
  `test_door_is_unlisted` guards it.
- Plain truth, stated once: the knock keeps honest visitors out; it
  does not stop anyone technical (the JS is readable, the endpoints
  are open). This is the founders' explicit trade for a desk with
  no login machinery. If real money ever demands more, say so and
  the password lock returns.
````

A few decisions I baked in that your coder should hear from you directly:

- **Interac:** there's no direct Interac merchant API — the standard Canadian approach is the e-Transfer reference-code flow I specced (buyer sends the transfer with a code like `LV-7K4Q`, you mark it received in the studio). That plus pay-at-handover covers Interac fully on day one, with zero processor fees.
- **Crypto:** Coinbase Commerce is the default for speed, but the doc puts it behind a `CRYPTO_PROVIDER` flag so you can swap to self-hosted BTCPay later without touching the order flow.
- **The demo stays the design contract** — the doc freezes your `#cac4ce` ink, the £UVR€ logo, the marble, and the auto-frame engine, and forbids generic e-commerce language so the site keeps its voice as real payments get bolted on.
- **Guest checkout, studio-only accounts:** you and your friend are the only logins in v1; buyers just pay and get a status page. That's the smallest system that actually sells.
