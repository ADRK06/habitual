# Habitual — Play your habits.

**[habituall.vercel.app](https://habituall.vercel.app)**

![Python](https://img.shields.io/badge/python-3.12-blue)
![Flask](https://img.shields.io/badge/flask-3.1-black)
![PostgreSQL](https://img.shields.io/badge/postgresql-neon-336791)
![Deployed on Vercel](https://img.shields.io/badge/deployed-vercel-black)
![Tests](https://img.shields.io/badge/tests-381%20passing-brightgreen)

---

<!--
  Screenshots section: commented out until the real image files exist in
  docs/screenshots/ (landing.png, dashboard.png, habit-analytics.png,
  room-leaderboard.png), so GitHub doesn't render broken-image icons.
  Add the captures, then delete the HTML comment markers wrapping this
  section (the one that opens right above "## Screenshots" and the one
  that closes just after the "---" below it) to turn it back on.

## Screenshots

> Placeholders — drop the real captures into `docs/screenshots/` using these exact filenames
> and they'll render here automatically.

| Dashboard | Habit analytics |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Habit analytics](docs/screenshots/habit-analytics.png) |

| Landing page | Room leaderboard |
|---|---|
| ![Landing page](docs/screenshots/landing.png) | ![Room leaderboard](docs/screenshots/room-leaderboard.png) |

**Screens to capture:**
- `landing.png` — the animated landing page hero/scroll sections
- `dashboard.png` — the dashboard with a few habit cards (solo + at least one room card) and the
  header stats visible
- `habit-analytics.png` — a habit detail page showing the completion ring, heatmap, and an
  unlocked insight
- `room-leaderboard.png` — a room page with the leaderboard podium, a visible crown, and the
  check-in feed

---
-->

## What it is

Habitual is a gamified habit tracker built with a server-rendered Flask stack: track habits
solo or in head-to-head "rooms" with friends, earn points for consistency rather than vanity
streaks, and see the math behind every number. It's a solo full-stack project built to go deep
on Flask, PostgreSQL, and interactive server-rendered UI (HTMX + Alpine) without reaching for a
JS framework.

---

## Features

### Habits & streaks
- Three frequency modes per habit: **Daily**, **Specific Days** (e.g. Mon/Wed/Fri), or
  **X times a week**
- One check-in per habit per local day, with an optional proof note
- Streak freezes — spend balance to protect yesterday's streak after a miss (max 2 held)
- Milestone bonuses at day 7 / 14 / 30, then every 30 days after
- Undo today's check-in, which cleanly reprices that day's ledger entries

### Points economy
- **Earned points** — sum of every positive ledger entry, never decreases, used for all rankings
- **Balance** — earned minus spent, the currency for buying streak freezes
- Full point history is a ledger, not a counter — every change is its own row

### Analytics
- Completion ring (week + month) and a per-habit **habit strength** score
- Calendar heatmap, navigable by month
- Smart insights (best/worst weekday, usual check-in time, month-over-month change) — unlock
  after 14 days of data
- A 30-day overview grid + line chart across every active habit on the dashboard

### Rooms
- Invite via a shareable link **or** a short, human-typeable join code
- Leaderboard with a podium view: ranked by points → fewest missed days → earliest average
  check-in time
- **Timezone-fair daily crown** 👑 — first member to check in with a proof note each day, decided
  only once every member's own local day has actually closed
- Vouch on teammates' check-ins (✅ / 🔥), one per person per check-in
- Room streak (every member checked in that day) and a live room health meter
- Ownership transfers to the top-ranked member if the creator leaves; the room closes if the
  last member does

### Badges
- One-time, permanent badges: first check-in, 7/14/30-day streaks, a freeze save that reaches a
  week, 10 room crowns collected, and winning a room outright

### Accessibility & motion
- Visible focus states, labeled inputs, keyboard-usable modals
- `prefers-reduced-motion` respected — scroll-driven/looping animation is skipped entirely
- Every animated element is fully visible in the raw server-rendered HTML with JS disabled;
  animation only ever runs *from* that visible state, never *to* it

---

## Tech stack

| Layer | Choice |
|---|---|
| Language / framework | Python 3.12, Flask |
| ORM / migrations | Flask-SQLAlchemy, Flask-Migrate (Alembic) |
| Database | PostgreSQL on [Neon](https://neon.tech/), via `psycopg` v3 |
| Auth / forms | Flask-Login, Werkzeug password hashing, Flask-WTF (CSRF) |
| Templates | Jinja2, server-rendered |
| Interactivity | [HTMX](https://htmx.org/) (partial updates), [Alpine.js](https://alpinejs.dev/) (UI state) |
| Styling | Tailwind CSS (standalone CLI, no Node toolchain) |
| Animation | GSAP + ScrollTrigger + Flip, Lenis (smooth scroll), View Transitions API |
| Charts | Chart.js (rings, weekly bars); calendar heatmap is a custom Jinja grid |
| Extras | canvas-confetti, Lucide icons, Google Fonts (Orbitron / Exo 2 / Inter) |
| Testing | pytest (381 tests) |
| Hosting | Vercel (Python runtime), zero-config |

---

## Architecture highlights

- **Points ledger, not a running total.** Every point change (`daily`, `milestone`, `crown`,
  `freeze_purchase`) is its own row in `point_transactions`. Earned points and balance are both
  derived by summing the ledger, so every number in the UI is reconstructable from history —
  nothing to keep in sync, nothing that can drift.
- **Compute-on-read streaks.** There's no cron and no background worker — the app runs on
  Vercel's serverless runtime, which rules both out. Streaks, misses, room health, and room
  streaks are pure functions of check-ins and freezes, recomputed fresh on every request from
  [`habitual/points.py`](habitual/points.py).
- **Room habits reuse habit code.** Joining a room doesn't create a separate data model — it
  creates a normal `Habit` row with `room_id` set. Check-in, undo, freeze, and the entire
  analytics page are the *same code path* for solo and room habits; only a few room-specific
  gates (e.g. blocking actions after a member's own day has passed the room's end) branch at all.
- **Race-proof daily crown.** `RoomCrown` carries a `UNIQUE(room_id, date)` constraint, and
  `finalize_due_crowns()` lazily decides a day's winner the first time anyone loads a page after
  that day has closed for *every* member — safe to call on every request; a concurrent
  double-finalize just hits the constraint and no-ops instead of double-awarding.
- **Timezone handling.** "Today" is always a user's own local date (`users.timezone`, detected
  at signup) — never the server's. A room has no single shared "today": each member's
  participation, crown eligibility, and streak are judged against their own local clock.
- **Exploit-resistant frequency edits.** Editing a habit's frequency sets a
  `frequency_changed_on` floor; every live-computed stat (streak, success rate, heatmap) restarts
  counting from that date instead of the habit's original creation date, so a broken streak can't
  be resurrected by switching frequency modes — while past history still renders unchanged.
- **HTMX out-of-band updates.** A check-in, undo, or freeze returns one response that
  `hx-swap-oob`-updates every affected fragment at once (header stats, the habit card, the
  dashboard overview, badges) — no full-page reload, no client-side state to reconcile.
- **Pure-function business rules.** All scoring/streak/freeze/crown math
  ([`points.py`](habitual/points.py)) and all analytics aggregation
  ([`analytics.py`](habitual/analytics.py)) are plain functions with no database access —
  independently pytest-able, and the same functions back the UI and the dev seeding CLI.

---

## Scoring rules

For a completed day that is day **n** of the current streak:

| Streak day | Points that day |
|---|---|
| Normal day | 5 |
| 7 | 15 _(5 base + 10 milestone)_ |
| 14 | 25 _(5 base + 20 milestone)_ |
| 30, 60, 90 … | 35 _(5 base + 30 milestone)_ |

- Milestones are based on the **consecutive** streak — breaking it restarts the countdown, so
  reaching day 7 again later pays again.
- **Freezes** cost 50 balance, cap at 2 held at once, and only ever cover *yesterday* if it was
  missed on a habit with an active streak. A frozen day earns no points and isn't counted as a
  completion for success rate.
- Room members earn the same points as a solo habit, plus **+2** for the daily crown 👑 (first
  member to check in with a non-empty proof note).

---

## Project structure

```
habitual/
├── app.py                  # Vercel entrypoint: from habitual import create_app; app = create_app()
├── habitual/
│   ├── __init__.py          # app factory, extensions, blueprints
│   ├── config.py
│   ├── models.py
│   ├── auth.py               # signup, login, logout, username availability
│   ├── habits.py             # dashboard, habit CRUD, check-in, freeze
│   ├── rooms.py               # create/join, leaderboard, vouching, crowns
│   ├── analytics.py          # ring/heatmap/insight aggregation (pure functions)
│   ├── points.py              # all scoring/streak/freeze/crown rules (pure, tested)
│   ├── badges.py
│   ├── frequency.py           # Daily / Specific Days / Weekly scheduling helpers
│   ├── cli.py                 # dev-only seeding command
│   ├── templates/
│   └── static/
├── tailwind/input.css
├── migrations/
├── tests/
└── requirements.txt
```

---

## Local setup

**Prerequisites:** Python 3.12, a [Neon](https://neon.tech/) Postgres database (a free dev
branch is enough).

```bash
# Clone and enter the project
git clone https://github.com/ADRK06/habitual.git
cd habitual

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# then edit .env and fill in DATABASE_URL (your Neon dev branch) and SECRET_KEY (any long random string)

# Fetch the Tailwind standalone CLI and build the CSS
./scripts/get-tailwind.sh
./tailwindcss -i tailwind/input.css -o habitual/static/css/app.css

# Run database migrations
flask --app app db upgrade

# Run the app
flask --app app run --debug
```

The app runs at `http://127.0.0.1:5000`.

While working on styles, run Tailwind in watch mode in a second terminal:

```bash
./tailwindcss -i tailwind/input.css -o habitual/static/css/app.css --watch
```

**Seeding test data:** rather than waiting real days to see milestones and freezes, backdate
check-ins for a habit you've already created:

```bash
flask --app app dev-backdate --habit <habit_id> --days 10
flask --app app dev-backdate --habit <habit_id> --days 10 --skip-yesterday   # leaves a gap to test the freeze prompt
flask --app app dev-backdate --habit <habit_id> --days 30 --include-today   # see a 30-day milestone
```

This command refuses to run against production (it checks for the `VERCEL` env var and for a
`DATABASE_URL` matching `.env.prod`).

> Never commit `.env` or any real `DATABASE_URL`/`SECRET_KEY` — both are gitignored;
> `.env.example` shows the shape only.

---

## Testing

```bash
pytest
```

381 tests currently pass, covering every scoring/streak/freeze rule
([`tests/test_points.py`](tests/test_points.py)) plus auth, habits, rooms, badges, analytics,
and frequency behavior — see [`tests/`](tests/).

---

## Deployment

- **Hosting:** [Vercel](https://vercel.com/), Python runtime, zero-config — `app.py` exposes
  `app` directly, no `vercel.json` needed. Pushing to `main` on GitHub auto-deploys.
- **Database:** [Neon](https://neon.tech/) Postgres, split into a `dev` branch (used locally)
  and a `main` branch (production), each with its own pooled connection string.
- **Environment variables:** `SECRET_KEY` and `DATABASE_URL`, set in Vercel's project settings —
  never committed.
- **Schema changes against production:** put the prod pooled `DATABASE_URL` in a local,
  gitignored `.env.prod` (see `.env.prod.example`), then run:

  ```bash
  ./scripts/migrate-prod.sh
  ```

  before or alongside any deploy that changes the schema.

---

## Roadmap

**v2 (not started):**
- Photo proof on check-ins (via Vercel Blob)
- Email / web-push reminders
- An "at-risk day" prediction model
- Mobile layout
- A real Habitual logo (SVG, nav/footer/favicon) — concept exploration lives on the
  `logo-exploration` branch

---

## Author

**Aadhira K**
[LinkedIn](https://www.linkedin.com/in/aadhira-kamal-341340372/) · [GitHub](https://github.com/ADRK06)
