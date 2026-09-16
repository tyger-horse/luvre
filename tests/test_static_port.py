"""The served gallery is the ported demo: frozen tokens, no open registration."""

RETIRED = (
    "Create access",      # demo's registration tab
    "Cut a key",          # demo's registration submit
    "auth/register",      # demo's local-transport route
    "Any house may hold a key",
    "House handle",
    "Enter the studio",   # retired login form
    "Studio contact",
    "studioForm",
    "deskHandle",
    "signOut",
    "savedToken",
)

REQUIRED = (
    "£UVR€",              # laser wordmark
    "laserFx",            # wordmark filter
    "dossier",            # FLIP dossier
    "veil",               # veil component
    "sheet",              # sheet component
    "toasts",             # toast component
    "/static/app.js",
    "/static/studio.js",
    "/static/app.css",
    "A commission",        # guest checkout sheet
    "acMethods",            # road choice: interac / paypal / crypto / handover
    "acLookCode",           # ask-after-it lookup
    'value="crypto"',       # M4 road open
    'value="usdc"',         # coin choice: eth / btc / usdc
    'id="acCoins"',         # ...shown only on the crypto road
    'unlisted route" hidden',  # the door starts unlisted — Raph's knock only
)


def test_gallery_serves_ported_demo(client):
    res = client.get("/")
    assert res.status_code == 200, res.text
    html = res.text
    for needle in REQUIRED:
        assert needle in html, f"ported gallery lost {needle!r}"
    for needle in RETIRED:
        assert needle not in html, f"open-registration relic survived: {needle!r}"
    # Non-negotiable §2.3: no card form may ever be built.
    assert "card" not in html.lower(), "card data must never touch our walls"

REQUIRED_JS = (
    "LUVRE_API",          # fetch transport, demo method names kept
    "fixtureParams",      # plate-pending pieces keep the frame truthful
    "renderGarment",      # generative renderer as dev fixture
    "fromProjection",     # wire-to-wall field mapping
    "Acquired",           # M5 sold plaque
)


def test_gallery_serves_ported_demo(client):
    res = client.get("/")
    assert res.status_code == 200, res.text
    html = res.text
    for needle in REQUIRED:
        assert needle in html, f"ported gallery lost {needle!r}"
    for needle in RETIRED:
        assert needle not in html, f"open-registration relic survived: {needle!r}"
    js = client.get("/static/app.js").text
    for needle in REQUIRED_JS:
        assert needle in js, f"ported gallery script lost {needle!r}"


def test_studio_scripts_carry_no_open_registration(client):
    for path in ("/static/app.js", "/static/studio.js"):
        res = client.get(path)
        assert res.status_code == 200, path
        for needle in ("auth/register", "Create access", "Cut a key", "Any house may hold a key"):
            assert needle not in res.text, f"{path} still offers {needle!r}"


def test_door_is_unlisted(client):
    js = client.get("/static/studio.js").text
    for needle in ("#atelier", "revealDoor", "luvre.door"):
        assert needle in js, f"the secret knock lost {needle!r}"


def test_frozen_tokens_survive(client):
    css = client.get("/static/app.css").text
    assert "#cac4ce" in css
    assert "Cinzel" in css
    assert "Cormorant Garamond" in css
    assert "Josefin Sans" in css


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}
