# CLAUDE.md — Habitual

Habitual is a gamified **habit teacher** web app. Users track habits, earn points and streaks,
and compete with friends in **habit rooms** with leaderboards. Web (desktop) only for now.
Hosted on **Vercel**, built in **Python (Flask)**.

The developer is a 2nd-year CSE (AI/ML) student learning as they build. Explain non-obvious
decisions briefly in chat, keep code readable, and prefer clarity over cleverness.

---

## How to work in this repo

- Build **one phase at a time** (see Roadmap). Don't start the next phase until the current one runs
  locally and the developer confirms.
- Before a big change, state the plan in a few lines and which files you'll touch.
- **Ask before adding any new dependency** not listed in the Tech Stack.
- All points/streak/freeze/crown logic lives in `habitual/points.py` and **must have pytest tests**.
  Run `pytest` after changing it.
- Never commit `.env` or secrets. Never hardcode `SECRET_KEY` or `DATABASE_URL`.
- Enforce every rule **on the server**. Frontend validation is for UX only.
- After finishing a phase, update the phase checkboxes at the bottom of this file.
- When unsure about current Vercel/Flask/Neon behaviour, check the official docs rather than guessing.

---

## Tech stack (final — don't swap without asking)

**Backend**
- Python 3.12, Flask
- Flask-SQLAlchemy + Flask-Migrate (Alembic)
- PostgreSQL on **Neon** (driver: `psycopg` v3). Separate Neon branches: `dev` (local) and `main` (prod)
- Flask-Login (sessions), Werkzeug password hashing, Flask-WTF (forms + CSRF)
- `zoneinfo` (stdlib) for per-user timezones
- pytest

**Frontend** (server-rendered, minimal JS)
- Jinja2 templates
- Tailwind CSS via the **standalone CLI** (no Node). Commit the built CSS file.
- HTMX for partial updates (check-in, delete, vouch, freeze) without page reloads
- Alpine.js for small UI state (modals, confirm dialogs, password meter, dropdowns)
- GSAP + ScrollTrigger (animations), Lenis (landing page smooth scroll)
- View Transitions API for page-to-page transitions (progressive enhancement)
- Chart.js (completion ring, weekly bars); calendar heatmap is a custom Jinja grid
- canvas-confetti (celebrations), Lucide icons, Google Fonts
- Load JS libraries from pinned CDN versions

**Hosting**
- Vercel Python runtime, zero-config where possible. Entrypoint: `app.py` exposing `app`.
  Only add `vercel.json` if actually needed.
- Env vars: `SECRET_KEY`, `DATABASE_URL`
- Serverless means **no persistent disk** → no SQLite in prod, no file uploads to disk.
- Use Neon's **pooled** connection string; set SQLAlchemy `pool_pre_ping=True` and a small pool.

---

## Folder structure

```
habitual/
├── app.py                  # Vercel entrypoint: from habitual import create_app; app = create_app()
├── habitual/
│   ├── __init__.py         # app factory, extensions, blueprints
│   ├── config.py
│   ├── models.py
│   ├── auth.py             # blueprint: signup, login, logout, username check
│   ├── habits.py           # blueprint: dashboard, create, check-in, delete, freeze
│   ├── rooms.py            # blueprint: create, join, leave, leaderboard, vouch
│   ├── analytics.py        # blueprint + stats/insights helpers
│   ├── points.py           # ALL scoring/streak rules (pure functions, tested)
│   ├── utils/time.py       # "today" for a user in their timezone
│   ├── templates/          # base.html, partials/, pages
│   └── static/             # css/, js/, img/
├── tailwind/input.css
├── migrations/
├── tests/
├── requirements.txt
├── .env.example
└── CLAUDE.md
```

---

## Core architecture decisions

1. **No cron / background jobs.** Streaks, misses, room streaks and room health are **computed on read**
   from check-ins and freezes. Crowns are awarded at check-in time.
2. **Points ledger.** Every point change is a row in `point_transactions`
   (`reason`: `daily`, `milestone`, `crown`, `freeze_purchase`).
   - **Earned points** = sum of positive amounts. Never decreases (except when a habit is deleted).
     Used for **all rankings**. Shown as the main number in the header.
   - **Balance** = earned − spent. Used to buy streak freezes.
   - **Habit points** = earned points for that habit.
3. **Room habits are normal habits** with a `room_id`. Joining a room creates a habit for that
   member. Check-ins, streaks, points and analytics are shared code for solo and room habits.
4. **"Today" is always the user's local date** (`users.timezone`, detected at signup).
   Never use server time for habit dates.

---

## Data model

| Table | Key fields |
|---|---|
| `users` | id, name, username (unique, case-insensitive), password_hash, timezone, theme (unused — reserved, dark-only v1), created_at |
| `habits` | id, user_id, room_id (nullable), title, emoji, tiny_version (text), created_on (date) |
| `checkins` | id, habit_id, date, created_at (timestamp), proof_note (nullable) — **UNIQUE(habit_id, date)** |
| `freezes` | id, user_id, habit_id (nullable until used), purchased_at, used_on (date, nullable) |
| `point_transactions` | id, user_id, habit_id (nullable), amount, reason, date, created_at |
| `rooms` | id, title, emoji, creator_id, duration_days, start_date, invite_token (unique) |
| `room_members` | id, room_id, user_id, joined_on — UNIQUE(room_id, user_id) |
| `vouches` | id, checkin_id, user_id, emoji (✅ or 🔥) — UNIQUE(checkin_id, user_id) |
| `badges` | id, user_id, type, earned_on — UNIQUE(user_id, type) |

Deleting a habit cascades to its check-ins, vouches and point transactions (its points leave the total).

---

## Business rules (source of truth)

### Accounts
- Username: 3–20 chars, `a-z 0-9 _`, stored lowercase, unique. Live availability check via HTMX while typing.
- Password: ≥ 8 chars, at least one uppercase, one lowercase, one digit, one special character.
  Show a live checklist/strength meter; re-validate on the server.
- After signup or login → redirect to `/dashboard`. Logged-in users visiting `/` go to the dashboard.
- Basic brute-force protection: after 5 failed logins for a username, block for 10 minutes (store in DB).

### Check-ins
- At most **one check-in per habit per local day** (DB unique constraint + server check).
- Only **today** can be checked in. No backdating, no future dates.
- Optional proof note (max 280 chars).

### Streaks
- **Current streak** = number of consecutive completed days ending today (or yesterday, if today isn't done yet).
- A day with a used **freeze** keeps the chain unbroken but does **not** add to the count.
- **Longest streak** = max ever, same definition.
- A missed day with no freeze resets the current streak to 0.

### Points (per habit)
For a completed day that is day **n** of the current streak:
- Base: **5**
- Bonus: **+10** if n = 7, **+20** if n = 14, **+30** if n = 30, then **+30** at every further multiple of 30 (60, 90, 120…)
- Milestones are based on the **consecutive** streak. If the streak breaks, milestones restart (hitting day 7 again pays again).

| Streak day | Points that day |
|---|---|
| Normal day | 5 |
| 7 | 15 |
| 14 | 25 |
| 30, 60, 90… | 35 |

### Streak freezes
- Cost **50 balance**. A user can hold at most **2** unused freezes.
- Used manually: if **yesterday** was missed on a habit with a streak ≥ 1, the card shows
  "Save your streak 🧊" until end of today. Only yesterday can be frozen.
- A frozen day earns no points and doesn't count as a completion (success rate unaffected in its favour).

### Success rate
- Completed days ÷ days since the habit was created (or since joining, for room habits), including today
  only if today is completed. Show as a percentage.

### Rooms
- Creator sets title, emoji and duration (7–90 days). The room starts on its creation date and ends after
  `duration_days`. After it ends it becomes read-only with final standings, and the winner gets a badge.
- **Join link**: `/join/<invite_token>` (token from `secrets.token_urlsafe`). The creator can regenerate it.
  People can join any time before the room ends; days before they joined aren't counted as misses.
- Room members earn the same points as solo habits, plus the **daily crown**:
  the **first member to check in each day with a non-empty proof note** gets **+2** (`reason = crown`).
- **Leaderboard order**: room habit points (desc) → fewest missed days → earliest average check-in time.
- **Room health meter**: % of members who have checked in today.
- **Room streak**: consecutive days on which every member (as of that day) checked in. Freezes don't count.
- Members can **vouch** (✅ / 🔥) on each other's check-ins, one per check-in per person.
- **Leave room** (with confirmation) deletes that member's room habit and its points.
  If the creator leaves, ownership passes to the top-ranked member. If the last member leaves, delete the room.

### Badges (v1)
`first_checkin`, `first_week` (7-day streak), `fortnight` (14), `perfect_month` (30), `crown_collector` (10 crowns),
`room_champion` (won a finished room), `freeze_saver` (used a freeze and reached 7 afterwards).

### Smart insights (per habit, simple statistics — no ML in v1)
- Best and worst weekday by completion rate
- Usual check-in time (median)
- This month vs last month completion rate change
- Show only after ≥ 14 days of data. Otherwise show "Keep going — insights unlock after 14 days".

---

## Pages & UI spec

**Landing `/`**: app-intro style, immersive. Animated hero (Habitual wordmark, tagline about building habits
that stick), scroll-driven feature sections (streaks, points, rooms, insights), animated streak/flame visuals,
clear **Log in** and **Create account** CTAs.

**Auth `/signup`, `/login`**: split or centered card layout with subtle animated background, live validation,
password checklist, show/hide password.

**Dashboard `/dashboard`**
- Header: **name**, `@username` below it, **earned points** (animated count-up), balance and freezes held.
- Actions: **Create habit** (modal with templates and a "make it tiny" teacher tip) and **Create room**.
- Grid of cards, staggered entrance animation.
  - **Solo card**: title and emoji, current streak 🔥, longest streak, habit points, success rate,
    check-in button, **✕ top-right delete** → confirm modal ("Are you sure? This removes X points").
  - **Room card** (subtle "Room" badge): habit name, current leader 👑, days remaining, your points,
    health meter, check-in button, **Leave room** → confirm modal.
- Check-in: satisfying animation, confetti on milestones and badges, toast with points earned.
- Empty state with a friendly prompt to create a first habit.

**Habit page `/habits/<id>`**
- Back button. Completion % ring (Chart.js), calendar heatmap (month view, navigable),
  past-7-days bar chart, streak and point stats, recent check-in log with proof notes, insights panel.
- ⚠️ The developer has a **reference image** for this layout. Ask for it before building Phase 3.

**Room page `/rooms/<id>`**
- Back button. Room header (title, days left, room streak, health meter, invite link with copy button).
- Leaderboard: rank, name, points, streak, crowns, with the top 3 visually distinguished and animated reordering.
- Today's check-in feed with proof notes and vouch buttons.
- The current user's personal stats panel (same components as the habit page).

**Join `/join/<token>`**: shows room info plus a Join button. If logged out, send to login/signup, then back here.

---

## Design direction

- **Mood**: gamified but professional - esports/game-UI energy, not a toy. Bold color, confident type,
  genuine motion - never cutesy or juvenile.
- **Slogan**: "Play your habits." - hero tagline, page title, meta description.
- **Theme**: dark-only for v1 (no light mode - see Roadmap). Deep void-black background with navy-tinted
  glassy surfaces and three neon accents used as accents/glows, never as large flat areas.

  | Token | Hex | Role |
  |---|---|---|
  | `--color-void` | `#121212` | Page background (`bg`) |
  | `--color-black` | `#000000` | Deepest layer - gradient endpoints, backdrops (`bg-deep`) |
  | `--color-navy` | `#000080` | Surfaces and glows **only** - never text (too low contrast). Cards use navy blended into void (`surface`, `border`) |
  | `--color-yellow` | `#ffff00` | Primary accent - CTAs, focus rings, points, success states, milestone fills (`accent`, `success`) |
  | `--color-crimson` | `#dc143c` | Streak/flame color and danger/error states (`streak`, `danger`). Large text/graphics only - fails AA at small sizes |
  | `--color-pink` | `#ff00ff` | Rooms/social accent (`rooms`) |

  All tokens live in `tailwind/input.css`'s `@theme` block as both raw (`--color-yellow`) and semantic
  (`--color-accent`) names - use the semantic name in templates.
- **Type**: three-tier system, loaded via Google Fonts, all pinned.
  - **Orbitron** (`font-display`) - wordmark and hero display numbers on the landing page only. Its zero
    has a slash through it, which reads as a 🚫 "prohibited" icon at small sizes - never use it for a stat
    that can show "0" (streaks, counters, tiles). Don't use it for long copy either - it strains at small
    sizes/long phrases.
  - **Exo 2** (`font-heading`) - section headings (h1-h4 by default via the base layer) **and all stat
    numbers in tiles/cards** (streak counts, habit strength %, header point totals) - bold with
    `tabular-nums` so digits don't shift width as they animate.
  - **Inter** (`font-body`) - everything else.
- **Logo**: no icon mark yet - the developer is drafting one to slot in later. Until then, use the text
  wordmark "Habitual" in `font-display` (nav, footer). Favicon is a placeholder flat yellow/void teardrop
  (`habitual/static/img/favicon.svg`) - swap it when the real mark lands.
- **Gamified elements, kept honest**: points, milestones (day 7/14/30...), the daily crown, streaks. No
  fake "levels" or "XP" framing - the app doesn't have a level system, so don't imply one. Progress toward
  a milestone is shown as a plain countdown ("Day 23 of 30 to next milestone"), not a leveling/XP bar.
- **Surfaces**: soft glassy cards (navy-tinted surface over void), subtle borders, generous spacing,
  rounded-2xl.
- **Motion**:
  - Purposeful and fast (150-400ms UI, longer only on landing/scroll reveals).
  - **Scroll-triggered reveals replay every time a section re-enters the viewport, in both scroll
    directions** (GSAP ScrollTrigger `toggleActions: "play reverse play reverse"`, or `scrub: true` for
    anything tied directly to scroll position like the landing page's connecting line).
  - List reordering (e.g. a leaderboard) uses GSAP's **Flip** plugin, not manual position math - it's the
    only way to keep gaps even regardless of row height or animation progress.
  - Animate `transform` (scaleX/scaleY/translate), never a layout-affecting property like `height` on a
    flex child - percentage heights inside flex containers visibly overshoot mid-animation. Use
    `transform-origin` + `scaleY`/`scaleX` for bars/fills, and clip the container with `overflow-hidden`.
  - **Never hide content by default in CSS or inline style.** Every animated element must be fully visible
    in the raw server-rendered HTML with no JS; GSAP only ever animates *from* that visible state
    (`gsap.from()`/`gsap.fromTo()`), gated behind a `window.gsap` check. This is a hard rule, not a
    suggestion - verify it by blocking the GSAP CDN script and confirming the page is still fully legible.
  - **Respect `prefers-reduced-motion`**: skip scroll-driven/looping animation entirely (`gsap.set()` to
    the final state instead), and don't initialize Lenis smooth-scroll.
- **Desktop-first** (≥ 1024px) but don't break on smaller widths.
- Accessible: visible focus states, labels, sufficient contrast (crimson text must be large/bold - see
  palette table), keyboard-usable modals.
- Use design tokens as CSS variables (in `tailwind/input.css`) so colors are consistent everywhere.

---

## Security checklist
- CSRF on all POST requests (Flask-WTF; send the token in HTMX requests via headers).
- Every habit, room or check-in route verifies ownership or membership (no access by guessing IDs).
- Secure session cookies in prod (`Secure`, `HttpOnly`, `SameSite=Lax`).
- Escape all user content (Jinja autoescape stays on). Validate lengths server-side.

---

## Commands

```bash
# setup (Windows: .venv\Scripts\activate  |  macOS/Linux: source .venv/bin/activate)
python -m venv .venv
pip install -r requirements.txt

# run locally
flask --app app run --debug

# database migrations (against the Neon dev branch, via .env)
flask --app app db migrate -m "message"
flask --app app db upgrade

# database migrations against prod (Neon main branch)
# put the prod pooled DATABASE_URL in .env.prod (gitignored, see .env.prod.example)
./scripts/migrate-prod.sh

# tests
pytest

# tailwind (standalone CLI binary in project root, gitignored - fetch it first)
./scripts/get-tailwind.sh
./tailwindcss -i tailwind/input.css -o habitual/static/css/app.css --watch
./tailwindcss -i tailwind/input.css -o habitual/static/css/app.css --minify   # before committing
```

Deploy: push to GitHub `main` → Vercel auto-deploys. Run `./scripts/migrate-prod.sh` against the Neon
`main` branch before or with deploys that change the schema.

---

## Roadmap

- [ ] **Phase 0 — Setup**: repo, venv, hello-world Flask, Neon dev/main branches, first Vercel deploy live
- [x] **Phase 1 — Accounts + landing**: models for users, signup/login/logout, validation, username check, timezone detection, animated landing page, base layout and design tokens
- [x] **Phase 2 — Solo habits + dashboard**: habit CRUD with templates and tiny tips, check-in with notes, `points.py` (points, streaks, milestones) with tests, freezes, header stats, delete confirmation, check-in animations
- [x] **Phase 3 — Habit analytics page**: ring, heatmap, weekly chart, log, insights (**get the reference image first**)
- [x] **Phase 4 — Rooms**: create, join link + join code, room cards, leaderboard with tiebreakers, crown, health meter, room streak, vouches, leave/ownership transfer, room end and results
- [x] **Phase 5 — Polish**: badges, confetti, empty/loading/error states, full animation pass
- [ ] **Phase 6 — Launch**: security checklist, rate limits, real test with friends, bug fixes, final deploy

**v2 (not now)**: photo proof (Vercel Blob), email/web-push reminders, ML "at-risk day" prediction, mobile,
design and implement the Habitual logo (SVG, nav/footer/favicon) - reference image at
`docs/reference/logo-reference.png`, keep its stacked-capsules + checkmark concept, simplified to our
palette and fonts (see "Logo" under Design direction).