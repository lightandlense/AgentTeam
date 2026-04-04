# Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a client list home page and per-client management dashboard (schedule, info, docs, OAuth, test tools) for the voice-agent admin UI.

**Architecture:** Three new FastAPI routes in `admin.py`, two new Jinja2 templates, and a minor nav addition to `documents.html`. All rendering is server-side; only one small inline `<script>` block for the test-calendar fetch. Tests extend `tests/test_admin.py`.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy async (AsyncSession), httpx + pytest-asyncio for tests, plain HTML/CSS (no JS framework).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/routers/admin.py` | Modify | Add 3 new routes: `GET /`, `GET /client/{id}`, `POST /client/{id}/settings` |
| `admin/templates/client_list.html` | Create | Renders all-client cards |
| `admin/templates/client_dashboard.html` | Create | Per-client scrollable dashboard |
| `admin/templates/documents.html` | Modify | Add `← Back to dashboard` nav link |
| `tests/test_admin.py` | Modify | Add tests for all three new routes |

---

## Task 1: Tests for GET /admin/ (client list)

**Files:**
- Modify: `tests/test_admin.py`

- [ ] **Step 1: Add failing tests to `tests/test_admin.py`**

Add after the existing imports and `_make_mock_db` helper:

```python
# ---------------------------------------------------------------------------
# Helpers for dashboard tests
# ---------------------------------------------------------------------------

def _mock_client(
    client_id="test-id",
    business_name="Test Business",
    timezone="America/Denver",
    working_days=None,
    business_hours=None,
    slot_duration_minutes=60,
    buffer_minutes=0,
    lead_time_minutes=60,
    business_address="123 Main St",
    owner_email="owner@test.com",
):
    from unittest.mock import MagicMock
    c = MagicMock()
    c.client_id = client_id
    c.business_name = business_name
    c.timezone = timezone
    c.working_days = working_days if working_days is not None else [1, 2, 3, 4, 5]
    c.business_hours = business_hours if business_hours is not None else {"start": "09:00", "end": "17:00"}
    c.slot_duration_minutes = slot_duration_minutes
    c.buffer_minutes = buffer_minutes
    c.lead_time_minutes = lead_time_minutes
    c.business_address = business_address
    c.owner_email = owner_email
    return c


def _make_scalars_db(scalar_items: list):
    """Mock db where execute().scalars().all() returns scalar_items."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = scalar_items
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def _override():
        yield mock_session

    return _override


# ---------------------------------------------------------------------------
# GET /admin/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_list_returns_200():
    """GET /admin/ should return 200 and list client business names."""
    from app.database import get_db

    clients = [_mock_client(client_id="c1", business_name="HVAC Co")]
    app.dependency_overrides[get_db] = _make_scalars_db(clients)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/admin/")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert "HVAC Co" in response.text


@pytest.mark.asyncio
async def test_client_list_empty():
    """GET /admin/ with no clients should still return 200."""
    from app.database import get_db

    app.dependency_overrides[get_db] = _make_scalars_db([])
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/admin/")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd E:/Antigravity/AgentTeam/voice-agent
python -m pytest tests/test_admin.py::test_client_list_returns_200 tests/test_admin.py::test_client_list_empty -v
```

Expected: FAIL — `404 Not Found` (route doesn't exist yet)

---

## Task 2: Implement GET /admin/ + client_list.html

**Files:**
- Modify: `app/routers/admin.py`
- Create: `admin/templates/client_list.html`

- [ ] **Step 1: Add route to `app/routers/admin.py`**

Add this import at the top (after existing imports):
```python
from app.models.client import Client, Embedding, OAuthToken
```

Then add the route before the existing `GET /admin/documents` route:

```python
@router.get("/")
async def client_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Render a list of all clients."""
    result = await db.execute(select(Client).order_by(Client.business_name))
    clients = result.scalars().all()
    return templates.TemplateResponse(
        "client_list.html",
        {"request": request, "clients": clients},
    )
```

- [ ] **Step 2: Create `admin/templates/client_list.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voice Agent Admin</title>
    <style>
        body { font-family: sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
        h1 { margin-bottom: 1.5rem; }
        .clients { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
        .card { border: 1px solid #ddd; border-radius: 6px; padding: 1.2rem; text-decoration: none; color: inherit; display: block; }
        .card:hover { background: #f8f8f8; border-color: #aaa; }
        .card h2 { margin: 0 0 0.4rem; font-size: 1.1rem; }
        .card p { margin: 0; color: #666; font-size: 0.9rem; }
        .no-clients { color: #888; }
    </style>
</head>
<body>
    <h1>Voice Agent Admin</h1>

    {% if clients %}
    <div class="clients">
        {% for c in clients %}
        <a class="card" href="/admin/client/{{ c.client_id }}">
            <h2>{{ c.business_name }}</h2>
            <p>{{ c.timezone }} &mdash; {{ c.working_days | length }} working day{{ 's' if c.working_days | length != 1 else '' }}</p>
            <p>{{ c.owner_email }}</p>
        </a>
        {% endfor %}
    </div>
    {% else %}
    <p class="no-clients">No clients found.</p>
    {% endif %}
</body>
</html>
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd E:/Antigravity/AgentTeam/voice-agent
python -m pytest tests/test_admin.py::test_client_list_returns_200 tests/test_admin.py::test_client_list_empty -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/routers/admin.py admin/templates/client_list.html tests/test_admin.py
git commit -m "feat(admin): add client list page at /admin/"
```

---

## Task 3: Tests for GET /admin/client/{client_id}

**Files:**
- Modify: `tests/test_admin.py`

- [ ] **Step 1: Add failing tests**

Add to `tests/test_admin.py`:

```python
# ---------------------------------------------------------------------------
# GET /admin/client/{client_id}
# ---------------------------------------------------------------------------


def _make_dashboard_db(client, token=None, doc_count=0):
    """Mock db for dashboard: handles 3 sequential execute() calls."""
    mock_session = AsyncMock()

    # Result 1: scalar_one_or_none() → client
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = client

    # Result 2: scalar_one_or_none() → token
    token_result = MagicMock()
    token_result.scalar_one_or_none.return_value = token

    # Result 3: scalar() → doc_count
    doc_result = MagicMock()
    doc_result.scalar.return_value = doc_count

    mock_session.execute = AsyncMock(
        side_effect=[client_result, token_result, doc_result]
    )

    async def _override():
        yield mock_session

    return _override


@pytest.mark.asyncio
async def test_client_dashboard_returns_200():
    """GET /admin/client/{id} should return 200 and show client name."""
    from app.database import get_db

    c = _mock_client(client_id="c1", business_name="HVAC Co", timezone="America/Denver")
    app.dependency_overrides[get_db] = _make_dashboard_db(c, token=None, doc_count=2)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/admin/client/c1")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert "HVAC Co" in response.text
    assert "America/Denver" in response.text


@pytest.mark.asyncio
async def test_client_dashboard_returns_404_for_unknown_client():
    """GET /admin/client/{id} should return 404 when client not found."""
    from app.database import get_db

    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=client_result)

    async def _override():
        yield mock_session

    app.dependency_overrides[get_db] = _override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/admin/client/unknown")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd E:/Antigravity/AgentTeam/voice-agent
python -m pytest tests/test_admin.py::test_client_dashboard_returns_200 tests/test_admin.py::test_client_dashboard_returns_404_for_unknown_client -v
```

Expected: FAIL — 404 (route not found)

---

## Task 4: Implement GET /admin/client/{client_id} + client_dashboard.html

**Files:**
- Modify: `app/routers/admin.py`
- Create: `admin/templates/client_dashboard.html`

- [ ] **Step 1: Add required imports to `app/routers/admin.py`**

Ensure these imports are present at the top:
```python
from fastapi.responses import Response
from sqlalchemy.sql import func
from app.models.client import Client, Embedding, OAuthToken
```

- [ ] **Step 2: Add dashboard GET route to `app/routers/admin.py`**

Add after the `client_list` route:

```python
_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@router.get("/client/{client_id}")
async def client_dashboard(
    client_id: str,
    request: Request,
    message: str = "",
    error: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Render the per-client management dashboard."""
    result = await db.execute(select(Client).where(Client.client_id == client_id))
    client = result.scalar_one_or_none()
    if client is None:
        return Response("Client not found", status_code=404)

    token_result = await db.execute(
        select(OAuthToken)
        .where(OAuthToken.client_id == client_id)
        .order_by(OAuthToken.id.desc())
        .limit(1)
    )
    token = token_result.scalar_one_or_none()

    doc_result = await db.execute(
        select(func.count(func.distinct(Embedding.doc_name))).where(
            Embedding.client_id == client_id
        )
    )
    doc_count = doc_result.scalar() or 0

    return templates.TemplateResponse(
        "client_dashboard.html",
        {
            "request": request,
            "client": client,
            "token": token,
            "doc_count": doc_count,
            "day_labels": _DAY_LABELS,
            "message": message,
            "error": error,
        },
    )
```

- [ ] **Step 3: Create `admin/templates/client_dashboard.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ client.business_name }} &mdash; Admin</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
        nav { margin-bottom: 1.5rem; }
        nav a { color: #555; text-decoration: none; font-size: 0.9rem; }
        nav a:hover { text-decoration: underline; }
        h1 { margin-bottom: 0.25rem; }
        .subtitle { color: #666; margin-bottom: 2rem; font-size: 0.9rem; }
        section { border: 1px solid #ddd; border-radius: 6px; padding: 1.2rem; margin-bottom: 1.5rem; }
        section h2 { margin: 0 0 1rem; font-size: 1rem; text-transform: uppercase; letter-spacing: 0.05em; color: #444; }
        label { display: block; margin-bottom: 0.8rem; font-size: 0.9rem; }
        label span { display: block; margin-bottom: 0.2rem; font-weight: bold; }
        input[type="text"], input[type="email"], input[type="time"], input[type="number"] {
            width: 100%; max-width: 360px; padding: 0.4rem 0.5rem; border: 1px solid #ccc; border-radius: 3px; font-size: 0.9rem; box-sizing: border-box;
        }
        .days { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .days label { margin: 0; }
        .days input[type="checkbox"] { margin-right: 0.2rem; }
        .row { display: flex; gap: 1rem; flex-wrap: wrap; }
        .row label { flex: 1; min-width: 140px; }
        button[type="submit"] { padding: 0.4rem 1rem; background: #333; color: #fff; border: none; border-radius: 3px; cursor: pointer; font-size: 0.9rem; margin-top: 0.5rem; }
        button[type="submit"]:hover { background: #555; }
        .message-ok  { color: green; margin-bottom: 1rem; }
        .message-err { color: red;   margin-bottom: 1rem; }
        .oauth-ok   { color: green; }
        .oauth-exp  { color: #c00; }
        .tool-result { margin-top: 0.8rem; font-size: 0.85rem; font-family: monospace; white-space: pre-wrap; background: #f4f4f4; padding: 0.6rem; border-radius: 3px; display: none; }
        a.doc-link { color: #333; font-size: 0.9rem; }
    </style>
</head>
<body>
    <nav><a href="/admin/">← All clients</a></nav>

    <h1>{{ client.business_name }}</h1>
    <p class="subtitle">{{ client.client_id }}</p>

    {% if message %}
    <p class="{{ 'message-err' if error else 'message-ok' }}">{{ message }}</p>
    {% endif %}

    <form method="post" action="/admin/client/{{ client.client_id }}/settings">
        <input type="hidden" name="section" value="info">

        <!-- ── 1. Client Info ───────────────────────────────────── -->
        <section>
            <h2>Client Info</h2>
            <label><span>Business name</span>
                <input type="text" name="business_name" value="{{ client.business_name }}" required>
            </label>
            <label><span>Address</span>
                <input type="text" name="business_address" value="{{ client.business_address or '' }}">
            </label>
            <label><span>Owner email</span>
                <input type="email" name="owner_email" value="{{ client.owner_email }}" required>
            </label>
        </section>

        <!-- ── 2. Schedule ─────────────────────────────────────── -->
        <section>
            <h2>Schedule</h2>
            <label><span>Timezone (IANA)</span>
                <input type="text" name="timezone" value="{{ client.timezone }}" required placeholder="America/Denver">
            </label>
            <label><span>Working days</span></label>
            <div class="days">
                {% for i in range(1, 8) %}
                <label>
                    <input type="checkbox" name="working_days" value="{{ i }}"
                        {% if i in client.working_days %}checked{% endif %}>
                    {{ day_labels[i - 1] }}
                </label>
                {% endfor %}
            </div>
            <br>
            <div class="row">
                <label><span>Hours start</span>
                    <input type="time" name="bh_start" value="{{ client.business_hours.start }}">
                </label>
                <label><span>Hours end</span>
                    <input type="time" name="bh_end" value="{{ client.business_hours.end }}">
                </label>
            </div>
            <div class="row">
                <label><span>Slot duration (min)</span>
                    <input type="number" name="slot_duration_minutes" value="{{ client.slot_duration_minutes }}" min="15" max="480">
                </label>
                <label><span>Buffer (min)</span>
                    <input type="number" name="buffer_minutes" value="{{ client.buffer_minutes }}" min="0">
                </label>
                <label><span>Lead time (min)</span>
                    <input type="number" name="lead_time_minutes" value="{{ client.lead_time_minutes }}" min="0">
                </label>
            </div>
        </section>

        <button type="submit">Save changes</button>
    </form>

    <!-- ── 3. Knowledge Base ───────────────────────────────────── -->
    <section>
        <h2>Knowledge Base</h2>
        <p>{{ doc_count }} document{{ 's' if doc_count != 1 else '' }} ingested.
           <a class="doc-link" href="/admin/documents?client_id={{ client.client_id }}">Manage documents →</a>
        </p>
    </section>

    <!-- ── 4. OAuth ────────────────────────────────────────────── -->
    <section>
        <h2>OAuth / Google Calendar</h2>
        {% if token %}
            {% if token.token_expiry %}
            <p class="{{ 'oauth-exp' if token.token_expiry.replace(tzinfo=none) < now else 'oauth-ok' }}">
                Token expires: {{ token.token_expiry.strftime('%Y-%m-%d %H:%M UTC') }}
            </p>
            {% else %}
            <p class="oauth-ok">Token stored (no expiry recorded)</p>
            {% endif %}
        {% else %}
            <p class="oauth-exp">No token — calendar not connected.</p>
        {% endif %}
        <p><a href="/oauth/start?client_id={{ client.client_id }}">Re-authorize Google Calendar →</a></p>
    </section>

    <!-- ── 5. Tools ────────────────────────────────────────────── -->
    <section>
        <h2>Tools</h2>
        <button type="button" id="test-cal-btn">Test Calendar</button>
        <div class="tool-result" id="test-cal-result"></div>
    </section>

    <script>
    document.getElementById('test-cal-btn').addEventListener('click', async function () {
        const btn = this;
        const out = document.getElementById('test-cal-result');
        btn.disabled = true;
        btn.textContent = 'Testing…';
        out.style.display = 'none';
        try {
            const res = await fetch('/admin/test-calendar/{{ client.client_id }}');
            const data = await res.json();
            out.textContent = JSON.stringify(data, null, 2);
        } catch (e) {
            out.textContent = 'Request failed: ' + e.message;
        } finally {
            out.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Test Calendar';
        }
    });
    </script>
</body>
</html>
```

**Note:** The template references `token.token_expiry.replace(tzinfo=none)` and `now` — Jinja2 doesn't have a built-in `now` variable. Pass `now=datetime.utcnow()` from the route instead (fixed in next step).

- [ ] **Step 4: Fix `now` variable — update dashboard route in `admin.py`**

Add `from datetime import datetime` at the top of `admin.py`, then update the `client_dashboard` route's `TemplateResponse` call to include `now`:

```python
return templates.TemplateResponse(
    "client_dashboard.html",
    {
        "request": request,
        "client": client,
        "token": token,
        "doc_count": doc_count,
        "day_labels": _DAY_LABELS,
        "message": message,
        "error": error,
        "now": datetime.utcnow(),
    },
)
```

Also update the template's OAuth section to use simpler expiry comparison (Jinja2 can't call `.replace()`). Replace the token expiry check block with:

```html
{% if token %}
    {% if token.token_expiry %}
    <p>Token expires: {{ token.token_expiry.strftime('%Y-%m-%d %H:%M UTC') }}
       {% if token.token_expiry < now %}<strong class="oauth-exp">(EXPIRED)</strong>{% else %}<span class="oauth-ok">(valid)</span>{% endif %}
    </p>
    {% else %}
    <p class="oauth-ok">Token stored (no expiry recorded)</p>
    {% endif %}
{% else %}
    <p class="oauth-exp">No token — calendar not connected.</p>
{% endif %}
```

But `token.token_expiry` is timezone-aware and `now` is naive — this will raise a TypeError. Make `now` timezone-aware:

```python
from datetime import datetime, timezone
# ...
"now": datetime.now(timezone.utc),
```

And ensure the template comparison works. If `token.token_expiry` is timezone-aware, the comparison `token.token_expiry < now` works when both have tzinfo.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd E:/Antigravity/AgentTeam/voice-agent
python -m pytest tests/test_admin.py::test_client_dashboard_returns_200 tests/test_admin.py::test_client_dashboard_returns_404_for_unknown_client -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/admin.py admin/templates/client_dashboard.html tests/test_admin.py
git commit -m "feat(admin): add per-client dashboard at /admin/client/{id}"
```

---

## Task 5: Tests for POST /admin/client/{client_id}/settings

**Files:**
- Modify: `tests/test_admin.py`

- [ ] **Step 1: Add failing tests**

```python
# ---------------------------------------------------------------------------
# POST /admin/client/{client_id}/settings
# ---------------------------------------------------------------------------


def _make_update_db(client):
    """Mock db for settings POST: execute returns client, commit is a no-op."""
    mock_session = AsyncMock()
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = client
    mock_session.execute = AsyncMock(return_value=client_result)
    mock_session.commit = AsyncMock()

    async def _override():
        yield mock_session

    return _override


@pytest.mark.asyncio
async def test_settings_post_redirects_on_success():
    """POST /admin/client/{id}/settings should save and redirect to dashboard."""
    from app.database import get_db

    c = _mock_client(client_id="c1")
    app.dependency_overrides[get_db] = _make_update_db(c)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            response = await client.post(
                "/admin/client/c1/settings",
                data={
                    "business_name": "New Name",
                    "owner_email": "new@test.com",
                    "timezone": "America/Chicago",
                    "working_days": ["1", "2", "3", "4", "5", "6", "7"],
                    "bh_start": "08:00",
                    "bh_end": "18:00",
                    "slot_duration_minutes": "90",
                    "buffer_minutes": "15",
                    "lead_time_minutes": "120",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code in (302, 303)
    assert "/admin/client/c1" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_settings_post_404_for_unknown_client():
    """POST to unknown client_id should return 404."""
    from app.database import get_db

    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=client_result)

    async def _override():
        yield mock_session

    app.dependency_overrides[get_db] = _override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/admin/client/unknown/settings",
                data={"business_name": "X", "owner_email": "x@x.com", "timezone": "UTC"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd E:/Antigravity/AgentTeam/voice-agent
python -m pytest tests/test_admin.py::test_settings_post_redirects_on_success tests/test_admin.py::test_settings_post_404_for_unknown_client -v
```

Expected: FAIL — 404 (route not found)

---

## Task 6: Implement POST /admin/client/{client_id}/settings

**Files:**
- Modify: `app/routers/admin.py`

- [ ] **Step 1: Add settings POST route to `app/routers/admin.py`**

Add after the `client_dashboard` route:

```python
@router.post("/client/{client_id}/settings")
async def update_client_settings(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Save client info and schedule changes."""
    form = await request.form()

    result = await db.execute(select(Client).where(Client.client_id == client_id))
    client = result.scalar_one_or_none()
    if client is None:
        return Response("Client not found", status_code=404)

    # Client info
    name = (form.get("business_name") or "").strip()
    if name:
        client.business_name = name

    addr = (form.get("business_address") or "").strip()
    client.business_address = addr or None

    email = (form.get("owner_email") or "").strip()
    if email:
        client.owner_email = email

    # Schedule
    tz = (form.get("timezone") or "").strip()
    if tz:
        client.timezone = tz

    raw_days = form.getlist("working_days")
    if raw_days:
        try:
            client.working_days = sorted(
                {int(d) for d in raw_days if d.isdigit() and 1 <= int(d) <= 7}
            )
        except (ValueError, TypeError):
            pass  # keep existing value

    bh_start = (form.get("bh_start") or "").strip()
    bh_end = (form.get("bh_end") or "").strip()
    if bh_start and bh_end:
        client.business_hours = {"start": bh_start, "end": bh_end}

    for field in ("slot_duration_minutes", "buffer_minutes", "lead_time_minutes"):
        val = (form.get(field) or "").strip()
        if val.isdigit():
            setattr(client, field, int(val))

    await db.commit()
    return RedirectResponse(
        url=f"/admin/client/{client_id}?message=Settings+saved",
        status_code=303,
    )
```

Add `RedirectResponse` to the existing FastAPI import at the top of `admin.py`:
```python
from fastapi.responses import RedirectResponse, Response
```

- [ ] **Step 2: Run all new tests to verify they pass**

```bash
cd E:/Antigravity/AgentTeam/voice-agent
python -m pytest tests/test_admin.py::test_settings_post_redirects_on_success tests/test_admin.py::test_settings_post_404_for_unknown_client -v
```

Expected: PASS

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
cd E:/Antigravity/AgentTeam/voice-agent
python -m pytest tests/test_admin.py -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add app/routers/admin.py tests/test_admin.py
git commit -m "feat(admin): add settings POST /admin/client/{id}/settings"
```

---

## Task 7: Add back-nav to documents.html

**Files:**
- Modify: `admin/templates/documents.html`

- [ ] **Step 1: Add nav link to `documents.html`**

Replace the opening `<body>` tag and `<h1>` with:

```html
<body>
    <nav style="margin-bottom:1rem;">
        <a href="/admin/client/{{ client_id }}" style="color:#555;text-decoration:none;font-size:0.9rem;">← Back to {{ client_id }}</a>
    </nav>
    <h1>Knowledge Base &mdash; {{ client_id }}</h1>
```

The `client_id` variable is already in the template context (it's passed by `list_documents`).

- [ ] **Step 2: Run documents test to make sure nothing broke**

```bash
cd E:/Antigravity/AgentTeam/voice-agent
python -m pytest tests/test_admin.py::test_get_documents_returns_200 -v
```

Expected: PASS

- [ ] **Step 3: Commit and push**

```bash
git add admin/templates/documents.html
git commit -m "feat(admin): add back-to-dashboard nav on documents page"
git push origin master
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Client list ✓, dashboard GET ✓, settings POST ✓, OAuth status ✓, test calendar button ✓, back nav on documents ✓, knowledge base doc count ✓
- [x] **No placeholders:** All steps contain actual code
- [x] **Type consistency:** `client.working_days` is `list[int]` throughout; form values parsed to `int`; `_DAY_LABELS` indexing uses `i - 1` to match 1-based isoweekday; `now` is timezone-aware `datetime`
- [x] **Route prefix:** All routes are under `/admin` prefix (set by `router = APIRouter(prefix="/admin")`), so `@router.get("/")` → `/admin/`, `@router.get("/client/{id}")` → `/admin/client/{id}`
