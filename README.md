# £UVR€ — a blind gallery of garments

One-of-one garments, hung like art, handed over in person in Montreal.
Sellers are anonymous to the public (only a per-piece pseudonym is ever
exposed); buyers check out as guests — no accounts, no cards on our
servers, ever. The full contract lives in `AGENTS.md`; this file is the
operator's handbook.

## Run it locally

```sh
cp .env.example .env            # then fill the money addresses at least
pip install -r requirements.txt # or: python -m venv .venv && .venv/bin/pip install -r requirements.txt
uvicorn app.main:app --reload
```

The wall hangs at `http://localhost:8000`. There are no accounts:
knock three times on the £UVR€ wordmark, then three times on the
revealed entry (or open `http://localhost:8000/#atelier` straight
away) to reach the desk. Tests: `make test` (or
`python -m pytest tests/ -q`).

## Free staging on Render

`render.yaml` is the staging road — free, and honestly labeled: the
service sleeps when idle, the free database is time-limited, and
uploads vanish on redeploy (no persistent disk). Good for showing the
room around; not for selling.

Render dashboard → New → Blueprint → point at this repo, then set
`INTERAC_TRANSFER_EMAIL` (and any sandbox money keys) in the
dashboard. `PUBLIC_BASE_URL` and `DATABASE_URL` wire themselves.
When the first piece sells: stand up `deploy/` on the VPS and point
DNS there.

## Configure money

| Key | Meaning |
|---|---|
| `INTERAC_TRANSFER_EMAIL` | The e-Transfer deposit address quoted in checkout instructions |
| `CRYPTO_ETH_ADDRESS` / `CRYPTO_BTC_ADDRESS` / `CRYPTO_USDC_ADDRESS` | Your wallets; buyers pick a coin, send, paste the tx hash — you verify on-chain, then mark paid |
| `PAYPAL_ENV` (`sandbox`→`live`), `PAYPAL_CLIENT_ID/SECRET/WEBHOOK_ID` | PayPal road; register a sandbox webhook for `PAYMENT.CAPTURE.COMPLETED` first |
| `CRYPTO_PROVIDER` (`coinbase`\|`btpay`), `COINBASE_API_KEY/WEBHOOK_SECRET`, `BTPAY_URL/API_KEY/STORE_ID/WEBHOOK_SECRET` | Crypto road; only `confirmed`/`InvoiceSettled` settles |

Without keys the corresponding road answers 503 — never a half-made
commission. Webhooks are the source of truth; signatures are verified
and replays are no-ops.

## Deploy (M6)

A Montreal-region VPS keeps latency low and residency sane (OVH BHS is
the standing recommendation). Point DNS at the box, then on the host:

```sh
git clone <repo> luvre && cd luvre
DOMAIN=luvre.ca SECRET_KEY=$(openssl rand -hex 32) \
  POSTGRES_PASSWORD=$(openssl rand -hex 24) \
  INTERAC_TRANSFER_EMAIL=transfers@luvre.ca \
  docker compose -f deploy/docker-compose.yml up -d --build
```

Caddy terminates HTTPS automatically. The container runs
`alembic upgrade head` on boot; schema changes ship as revisions under
`alembic/versions/` (`alembic revision --autogenerate -m "…"`, review,
commit). Secrets stay in the host environment — nothing secret is ever
committed (`.env` is git-ignored).

## Backups

Nightly, encrypted, off-box:

```sh
# host crontab — 3:40 AM Montreal time
40 3 * * * OFFBOX="backup@example:/srv/luvre-backups" /srv/luvre/deploy/backup.sh
```

`deploy/backup.sh` dumps Postgres (`pg_dump -Fc`), gzips, keeps 14
nights locally, and rsyncs off-box when `OFFBOX` is set. Restore with
`pg_restore` into a fresh `db` service, then `docker compose up app`.
