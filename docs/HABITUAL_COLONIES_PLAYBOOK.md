# Habitual: Colonies — Rebuild Playbook

Copy-paste prompts for Claude Code, one phase at a time. Look is LOCKED (section 1). Game rules come from the "Colonies — Game Plan" doc.


## Where you are
| Phase | Status |
|---|---|
| 0 Secret scan + perf cleanup | DONE |
| 1a Plan | DONE |
| 1b Tokens, fonts, style guide | DONE |
| 1c groups 1-6 (shell, auth, dashboard, detail, fleet, account/errors/modals) | DONE |
| Extras: My fleets page (/rooms), check-in from fleet cards, stale sidebar stats fix, badge popup/outline fixes, freeze numbers templated from points.py | DONE |
| Phase 1 merge + deploy | DONE: live on `main` at 9f68a1c (526 tests); verify live site |
| Phase 2 Sprite pipeline | DONE: live on `main` at 24da759 (80 imported + 12 drawn; shield dome density to tune in Phase 5) |
| Phase 3 Archive fix (schema) | DONE and verified live at dd36716 (includes Leave from My fleets + ended-fleet check-in fix). Phase 4 NEXT |
| Phases 4-11 | Not started |
(Update this table as you go.)

## Golden rules (read every time)
1. `/clear` between phases. Start each with the **Session start** prompt (section 4).
2. **Migrate prod BEFORE pushing** any change that touches the schema: dev branch first, then `./scripts/migrate-prod.sh`, then push.
3. Never commit `_perf.py`, `.env`, `.env.prod`. Never paste secrets into chat.
4. One phase = one branch (`colonies-p1`, ...). Merge to `main` only when tests pass and you have clicked through it locally on desktop AND phone width.
5. Redeploy on Vercel after env var changes.
6. Game rules live in ONE tested file, `habitual/game.py` (pure functions, pytest). No game rules inside routes or templates.
7. Points ledger stays the single source of truth. Spending Energy = a negative row in `point_transactions`.
8. No background jobs: anything "while you were away" is computed on next load.

## EXACT-MATCH RULE (applies to every phase)
The UI must match the approved canvas exactly. Everything is exported in **colonies-reference.zip** (32 screens as HTML with inline styles, 80 real pixel-art sprites, art manifest).

One-time setup, before Phase 1:
1. Unzip so you get `docs/reference/colonies/` in the repo: `screens/`, `art/`, `canvas.json`, `README.md`.
2. Commit it (`git add docs/reference/colonies && git commit -m "Add Colonies UI reference"`).
3. Add this line to CLAUDE.md: `UI source of truth: docs/reference/colonies/ (read README.md there). Match screens exactly; never restyle.`

Add this to the end of EVERY phase prompt that touches UI:
```
Match docs/reference/colonies/screens/<ScreenName>.dc.html exactly (sizes, colours, fonts, spacing, borders, copy formatting, sprite usage). Port its inline styles 1:1. Use only art from docs/reference/colonies/art/ (copy to static/art/ with readable names via the manifest). When done, give me a side-by-side checklist: for each screen, what matches and any deviation with the reason. Do not make design decisions of your own; if the mock and the real data disagree, ask me.
```

Screen to page map (use in the prompts):
| App page | Phone mock | Web mock |
|---|---|---|
| Landing | PhoneLanding | WebLanding |
| Colony home | PhoneHome | WebHome |
| Check-in moment | PhoneCheckIn | (WebHome) |
| Habits | PhoneHabits | WebHabits |
| Build menu | PhoneBuild | (WebHome) |
| Storm and repair | PhoneStorm | (WebHome) |
| Fleet | PhoneFleet | WebFleet |
| Sector rankings | PhoneSector | WebSector |
| Galaxy | PhoneGalaxy | WebGalaxy |
| Visit a planet | PhoneVisit | (WebGalaxy) |
| Shop | PhoneShop | WebShop |
| Commander profile | PhoneProfile | WebProfile |
| Create commander | PhoneAvatar | WebAvatar |
| Customize planet | PhonePlanet | WebPlanet |
| Shared parts | PhoneHud, PhoneNav | Sidebar |
Not for production (planning only): Main (style direction), Globe/Isometric/SideView (planet alternatives; the Globe was chosen), CustomizeFlow.

## Decisions I assumed (change any before Phase 3)
| Question from the game plan | Assumed default |
|---|---|
| Existing users | Start with a free colony (Rust world, no buildings) and keep their current balance as Energy. XP = their earned points. |
| Who sees the galaxy map | Friends and fleet-mates first. Public toggle later. |
| Storms on planned breaks | Add "Vacation mode" (up to 14 days, once per 60 days) that pauses storm damage. |
| Building costs | Use the table in the game plan as starting values, tune after friend testing. |

## Order
| Phase | What | Schema change? |
|---|---|---|
| 0 | Secret scan + remove perf code | no |
| 1 | Colonies theme: tokens, fonts, style guide, restyle existing pages | no |
| 2 | Pixel sprite pipeline (generated art) | no |
| 3 | Archive fix (archive habits instead of deleting) | YES |
| 4 | Colony core: categories, planet, buildings, Energy spending, check-in beam | YES |
| 5 | Storms, repairs, shields, supply drop, comeback | YES |
| 6 | Fleets: rooms become fleets (station, boss, nudges, trophies) | YES |
| 7 | Sectors: weekly score, leagues, galaxy map, visit a planet | YES |
| 8 | Shop + commander avatar + planet customizer | YES |
| 9 | Landing page, phone-first pass + PWA | no |
| 10 | Reminders (story-style) | YES |
| 11 | Friend testing, balance pass, README, v1.0 | no |

---

## What each phase does (plain language)

| Phase | What it does | What you can do/see afterwards | Needs prod migration? |
|---|---|---|---|
| 0 | Safety cleanup. Scans the public repo's history for leaked passwords/keys and deletes the temporary speed-test code. | Nothing visible. You know the repo is clean. | No |
| 1 | Re-skins the whole existing app to the Colonies look: new colours, Silkscreen/Plex fonts, square HUD panels, sidebar (web) and bottom tab bar (phone). Same features as today. Starts with a style-guide page so you approve the look before the full re-skin. | Habitual looks like your mockups; everything still works as before. | No |
| 2 | Art. Imports your 80 approved pixel sprites into the app and draws only the missing ones (building levels 2-3, damaged/under-construction versions, supply crate, etc.), shown on a contact sheet for your approval. | A complete sprite library the game can use. | No |
| 3 | Fixes the one thing that would break the game: deleting a habit or leaving a room currently erases points. Habits get archived instead, so spent Energy can never go negative. | Deleting a habit hides it but your points stay. | Yes |
| 4 | The core game. Habits get categories; every user gets a planet; Energy (your current points balance) buys buildings that take hours to finish; XP and ranks; check-ins fire an Energy beam into the planet. Also adds signup onboarding: create your commander, then customize your planet. | A real colony home screen: planet, buildings, build menu, today's habits, commander and planet customization. | Yes |
| 5 | Consequences and surprises. Missed days cause storm damage to a building (repaired by the next completed day or with Energy), shields protect you, a daily supply crate, comeback bonus after a break, vacation mode. | Reasons to open the app daily; a missed day stings but never wipes progress. | Yes |
| 6 | Rooms become fleets. A shared space station grows with every member's check-in, a weekly boss takes damage from check-ins, one-tap nudges for fleetmates, finished missions become trophies. Existing room features (leaderboard, crown, vouches, join link) stay. | Team play with friends: station, boss fight, nudges. | Yes |
| 7 | Competition. Weekly Score, six sector leagues of ~30 commanders (top 5 move up, bottom 5 move down), the galaxy map of everyone's planets, and visiting another planet. | Weekly ranking with promotion, galaxy map, planet visits. | Yes |
| 8 | Shop and unlocks. Buy cosmetics and shields with Energy; earned-only parts (Admiral suit, mirror visor, ice world, etc.) unlock from achievements; other people's looks show on the galaxy, sector, fleet and profile screens. | Collecting and showing off cosmetics. | Yes |
| 9 | Public face and mobile. A landing page that explains the game, a polished phone layout, and an installable app (PWA) with an install prompt. | Visitors understand the app in 10 seconds; your friends can install it to their home screen. | No |
| 10 | Reminders. Story-style messages ("Commander, the Biodome is running dry") by email and push, with quiet hours and a per-user toggle. | Gentle nudges that bring people back. | Yes |
| 11 | Launch. Friend testing with a feedback link and a balance log (are costs and rewards fair?), tuning, README with screenshots, v1.0 tag. | A tested, documented v1.0 you can put on your resume. | No |

**Suggested pacing:** Phases 0-2 are one sitting each. Phase 3 is short but risky (database), so do it carefully. Phases 4-8 are the big ones: expect one or more sessions per phase, and use them yourself for a few days before the next. Phase 9 can happen anytime after 4 if you want friends on phones earlier. Do not start Phase 5+ until Phase 4 feels fun to use daily.

**Stop points** (good moments to invite friends to test): after Phase 4 (solo colony), after Phase 6 (fleets), after Phase 7 (full competition).

---

## 1. The locked design brief (paste this into CLAUDE.md in Phase 1)

**Name / tagline:** Habitual — "Your habits build a world."
**Style:** Mission control, pixel worlds. Clean HUD panels in warm amber on near-black, wrapped around hand-made pixel planets. Arcade feel from the pixel type and sprites, not from neon.

**Colors (CSS variables, dark only)**
| Token | Name | Hex | Use |
|---|---|---|---|
| `--void` | Void | #0C0F14 | page ground |
| `--hull` | Hull | #141922 | panels, cards |
| `--bulkhead` | Bulkhead | #2A3140 | 1px lines, tracks |
| `--bone` | Bone | #ECE6D8 | main text |
| `--dust` | Dust | #9A9384 | quiet text (check contrast: only on void/hull, 12px+) |
| `--phosphor` | Phosphor | #FFB238 | Energy, primary actions, active state |
| `--phosphor-hi` | | #FFD27A | hover |
| `--rust` | Rust | #E2603A | planets, alerts, boss HP, damage |
| `--signal` | Signal | #8BD7A0 | done, healthy, shield up |
| `--steel` | Steel | #3E5A7A | sky, shields |
| `--regolith` | Regolith | #C9A27A | ground tones in art |

Text on Phosphor buttons is Void (#0C0F14). Never put Dust text on Bulkhead.

**Type**
- Silkscreen (400/700): titles, labels, buttons, ranks. UPPERCASE for labels and buttons.
- IBM Plex Sans (400/500/600): body, habit names.
- IBM Plex Mono (400/500): every number (points, streaks, timers, ranks).
- Self-host the fonts (no Google Fonts request at runtime) if licence allows; otherwise Google Fonts link with `display=swap`.

**Shape:** square corners everywhere (0 radius), 1px Bulkhead borders, no gradients, no blur shadows, no glow washes. Active/selected = 1px Phosphor border. Dashed Phosphor border = "in progress".
**Buttons:** primary = Phosphor fill, Void text, Silkscreen 12-15px, 44px min height. Secondary = transparent, Bone text, 1px Bulkhead border. Tertiary = Phosphor text + 1px Phosphor border.
**Chips/badges:** 28px high, Hull fill, 1px Bulkhead border, Plex Mono number; status chips outline-only in Signal/Rust/Phosphor.
**Progress bars:** 4-6px tall, Bulkhead track, Phosphor fill (Rust for boss HP).
**Motion (themed, all respects prefers-reduced-motion):**
- Check-in: an Energy beam (pixel line) travels from the habit card to the planet, planet pulses once, "+5" floats up in Plex Mono.
- Building: construction scaffold sprite, 2-frame blink; completion = brief flash + pop.
- Storm: screen-edge rust flicker, 600ms, only once per visit.
- Streak/level up: pixel confetti (square particles in Phosphor/Signal/Rust).
- Page transitions: 120ms fade. Stepped (steps(4)) easing for bars filling, to feel retro.
- Keep GSAP/Lenis only where they serve these; remove anything that is just decoration.
**Layout:** Web: left sidebar 240px (Colony, Habits, Fleets, Sector, Galaxy, Shop, Profile) + content. Phone: top commander bar (Energy, XP/level) + bottom tab bar, 44px targets, 16px gutters.
**Tone of copy:** short, "Commander" voice, plain. "Observatory under construction", "Storm hit the Biodome", never cutesy walls of text.
**Accessibility:** 4.5:1 text contrast, visible focus ring (2px Phosphor outline, offset 2px), real buttons/links, alt text on art (decorative = empty alt), reduced-motion respected, don't rely on color alone for status.

**Screens to exist when done:** Landing, Login/Signup/Forgot/Reset, Colony home, Habits (list + detail + analytics), Build menu, Check-in moment, Storm/repair, Fleet (station + boss + members), Sector rankings, Galaxy map, Visit a planet, Shop, Commander profile, Avatar locker, Planet customizer, Account security.

---

## 2. Phase prompts

### Phase 0 — Secret scan + remove perf code
```
Do two things, nothing else.

1) Scan the whole git history of this PUBLIC repo for leaked secrets: database URLs (postgres://, postgresql+psycopg://), SMTP passwords, SECRET_KEY values, API keys, .env/.env.prod contents. Use `git log -p` with grep/ripgrep, and also check every file ever added (git log --all --diff-filter=A --name-only) for .env* files. REPORT ONLY. Mask every secret in your output (show first 4 chars + ***). Say CLEAN or FOUND, and if FOUND list commit hash + file + what kind of secret. Do NOT rewrite history or change anything.

2) Remove the temporary perf code: delete habitual/_perf.py and the HABITUAL_PERF hook in habitual/__init__.py. Confirm no other file imports it. Run pytest. Show me the diff before committing.
```

### Phase 1 — Colonies theme (no features, no schema)
Work on branch `colonies-p1`. Do NOT push to `main` until all six groups are approved (see "Merge and deploy Phase 1" below). Review each step in the browser at 1440px and 390px before saying "go" for the next.

**Status:** 1a done · 1b done · 1c group 1 committed (needs your visual check) · groups 2-6 to do.

#### Decisions already made (these apply to every Phase 1 prompt)
- Planet view: **Globe** is the chosen one; ignore Isometric and SideView. Main.dc.html is the token/style source.
- Nav follows the mocks (Colony, Habits, Fleet, Ranks, Galaxy; Shop opens from the Energy pill) but only shows items whose feature exists, via `Config.NAV_FEATURES`. In Phase 1 only Habits, Fleet and Profile/Account are on. Each later phase flips its flag.
- No XP/Level/Rank in Phase 1. The Energy pill shows the current points balance. Repeal CLAUDE.md's "no fake levels or XP" line in Phase 4, not now.
- Dashboard in Phase 1 = the WebHabits/PhoneHabits screen restyled. The planet home (WebHome/PhoneHome) comes in Phase 4.
- Screens with no mock (auth, errors, empty states, create/join modals, habit detail analytics, account security, toasts): extrapolate strictly from Main.dc.html and existing components. Re-skin only, no layout changes.
- User-facing "Rooms" becomes "Fleet"; routes and DB names stay.
- Silkscreen only for system labels/titles/buttons/nav. All user-entered text (habit names, fleet names, usernames) uses IBM Plex Sans, truncating with ellipsis.
- Lenis removed. Emails stay plain.
- Every group: zero `rounded-`, `shadow-`, `backdrop-blur` in touched files (show the grep), pixel-match at 390 and 1440, keep all behaviour (HTMX OOB swaps, x-teleport/htmx:afterSettle logic), run pytest, commit, list URLs to click through, then stop and wait.

#### 1a — Plan only (DONE; kept for reference)
```
Read CLAUDE.md, tailwind/input.css, templates/, static/, and docs/reference/colonies/README.md plus every file in docs/reference/colonies/screens/. DO NOT write code yet.

I am rebuilding Habitual as "Habitual: Colonies". The approved screens in docs/reference/colonies/ are the EXACT target. Where anything below and a screen file disagree, the screen file wins. Apply the look to the existing app first (same features, new look). The game features come in later phases.

[PASTE SECTION 1 OF THIS FILE HERE: the locked design brief]

First, list the files in docs/reference/colonies/screens/ and tell me whether the count matches the 32 screens exported.

Produce a plan only: (a) Tailwind v4 @theme tokens; (b) a mapping of every current template/partial to the nearest mock screen, and what has no mock yet; (c) how to self-host the three fonts; (d) which JS libs to keep or remove; (e) risks (HTMX OOB swaps, calendar/heatmap alignment, chart re-colouring, the fixed dashboard card layout); (f) a /dev/styleguide route (404 unless HABITUAL_DEV=1); (g) the commit grouping for the restyle. Wait for my OK.
```

#### 1b — Tokens, fonts, style guide only (DONE)
```
Build only the foundations: Tailwind tokens, self-hosted fonts, base/reset styles, and the /dev/styleguide page (404 unless HABITUAL_DEV=1). Rebuild tailwind output. Do not restyle real pages yet. Add the design brief to CLAUDE.md under "Design system". Run pytest. Commit. Tell me the command to view the style guide.
```
View it with: `HABITUAL_DEV=1 flask --app app run --debug --port 5001` then open `http://127.0.0.1:5001/dev/styleguide` (port 5001 because macOS AirPlay uses 5000 and answers 403; no trailing period in the URL).

#### Branch setup (DONE)
```
Move the Colonies work onto a branch without losing anything: git switch -c colonies-p1, verify the commits are on it, then git branch -f main origin/main. Stay on colonies-p1. Do not push anything.
```

#### 1c — Apply, one commit per group
For each group: `/clear`, paste the prompt, review in the browser, send me screenshots (desktop 1440 and phone 390), then say "go" for the next. Compare each page against the canvas screen named in the prompt.

**Group 1 — Shell: sidebar, top bar, tab bar (DONE, review pending)**
```
Branch colonies-p1, Phase 1c group 1: shell only. Rebuild base.html and app_base.html to match Sidebar.dc.html (web, 240px) and PhoneHud.dc.html + PhoneNav.dc.html (phone), driven by Config.NAV_FEATURES (only Habits, Fleet, Profile/Account on). Keep base.html's x-teleport/htmx:afterSettle logic exactly. Match the mock pixel values; no new design decisions. Rounded/shadow/blur grep for every touched file. pytest, commit, list screens to click through. Stop and wait.
```
What to check: desktop sidebar (width, icons, active item in Phosphor, logo) vs Sidebar.dc.html; phone top bar (Energy and streak pills) vs PhoneHud.dc.html; phone bottom tabs vs PhoneNav.dc.html; a check-in popover is not hidden behind the bars.

**Group 2 — Auth pages**
```
Branch colonies-p1, Phase 1c group 2: auth pages only (login, signup, forgot password, reset password, check email, verify email). Read CLAUDE.md and docs/reference/colonies/README.md first.

There is no mock for these, so extrapolate strictly from docs/reference/colonies/screens/Main.dc.html and the components used in the other screens (Hull panels, 1px Bulkhead borders, square corners, Silkscreen uppercase for titles/labels/buttons, IBM Plex Sans for body and all user-entered text, Phosphor primary button with Void text at 44px min height, Rust for errors, Signal for success). Layout: centred single column, max ~420px, logo-mark and wordmark on top as in WebLanding's header. No sidebar on these pages. Keep every form field, validation message, CSRF token, rate-limit message, HTMX behaviour (username availability check) and route exactly as they are; this is a re-skin only.

Do the rounded-/shadow-/backdrop-blur grep for every file you touch (must be zero) and remove the deprecated --color-navy bridge token usage from these templates. Check each page at 390px and 1440px. Run pytest, commit, and list the exact URLs I should click through (including an error state for each form). Stop and wait for my review before group 3.
```

**Group 3 — Dashboard / habits list, habit cards, check-in popover**
```
Branch colonies-p1, Phase 1c group 3: the dashboard/habits list page, habit cards, check-in popover and empty state. Read CLAUDE.md and docs/reference/colonies/README.md first.

Target: docs/reference/colonies/screens/WebHabits.dc.html (web) and PhoneHabits.dc.html (phone). Match them exactly: card structure, sizes, filters, check-in button, status text, spacing. Keep today's data and behaviour: HTMX check-in/undo/freeze with all OOB swaps, header stats, day status, badges row, 30-day overview, create-habit modal, and the CLAUDE.md fixed card layout rules. Do NOT build the planet/colony home (WebHome) here. If a mock element has no data yet (building icons, XP, category icon), omit it and tell me. The create-habit modal and create/join-fleet modals have no mock: extrapolate from Main.dc.html components. Remove deprecated navy bridge token usage from these templates. rounded-/shadow-/backdrop-blur grep must be zero in touched files. Check at 390 and 1440. Run pytest, commit, list URLs to click through, then give me a deviation checklist versus the two mock screens. Stop and wait.
```

**Group 4 — Habit detail and analytics**
```
Branch colonies-p1, Phase 1c group 4: habit detail page (ring card, month calendar, weekly bar chart, 5-week heatmap, streak tiles, insight, check-in/undo/freeze controls). No mock exists for this page: keep today's layout and only re-skin with tokens and components from Main.dc.html. Re-colour Chart.js and the rings (explicit font-family strings and hex values in the Chart.js config, Plex Mono for numbers, Phosphor/Signal/Steel/Rust per the style guide). Month calendar status legend: Signal done, Steel shielded, Rust outline missed, Bulkhead outline future/off-day. Do not touch calendar/heatmap alignment logic. Keep all live HTMX updates working (the heatmap must still update on check-in). Square corners, no shadow/blur, grep zero in touched files. Check at 390 and 1440. pytest, commit, list URLs to click through. Stop and wait.
```

**Group 5 — Rooms and leaderboard (shown as "Fleet")**
```
Branch colonies-p1, Phase 1c group 5: rooms pages, shown to users as "Fleet". Targets: WebFleet.dc.html and PhoneFleet.dc.html. Rename user-facing text from Rooms/Room to Fleet (nav, titles, buttons, empty states); routes and DB names stay. Match the mocks for: header, shield badge for the room streak, leaderboard rows with vouch buttons, members list, join code/link block. OMIT: station image, boss HP, modules, flagship of the day, nudges (later phases); tell me what you omitted. Keep every existing room feature working (leaderboard ranking, crown, feed, vouch, health meter, streak, join code, leave/delete). Remove --color-rooms (pink) and the navy bridge tokens, and delete those deprecated tokens from tailwind/input.css once nothing references them (grep to prove). Grep for rounded-/shadow-/backdrop-blur zero in touched files. 390 and 1440. pytest, commit, URLs to click through, deviation checklist vs the two mocks. Stop and wait.
```

**Group 6 — Account, modals, toasts, errors, empty states**
```
Branch colonies-p1, Phase 1c group 6: account security page, toasts/flash messages, the badge modal, all remaining modals, error pages (404/500/403/429), and any remaining empty states. Mapping: WebProfile/PhoneProfile SETTINGS rows where they overlap; everything else extrapolated from Main.dc.html. Keep all behaviour (password change, email add/verify, sessions, delete account/Danger Zone). Finally: grep the whole templates tree for rounded-, shadow-, backdrop-blur, old navy/rooms tokens, Google Fonts, and any hex colour not in the Colonies palette; fix every hit. Make sure /dev/styleguide still renders. Run the full pytest suite, commit, and give me a final checklist of every page to click through at 390 and 1440. Stop and wait. Do not push or merge.
```

#### Merge and deploy Phase 1 (after all six groups are approved)
Phase 1 has no schema change, so no `migrate-prod.sh`.
1. On `colonies-p1`: run the full test suite, then click through every page at 1440 and 390 once more (logged out and logged in).
2. Push the branch only: `git push -u origin colonies-p1`. Vercel builds a preview URL; open it and re-check key pages (login, habits, a fleet, habit detail) on your phone.
3. If good: `git switch main`, `git merge --ff-only colonies-p1` (or `--no-ff` if you want a merge commit), `git push`. Vercel deploys production.
4. After deploy, open https://habituall.vercel.app and sanity check login, check-in, undo, and fleet pages.
5. Delete the old branch later if you like. Rollback: in Vercel, promote the previous deployment.

### Phase 2 — Art: import the real sprites, draw only what is missing
The 80 approved sprites already exist in `docs/reference/colonies/art/`. Do NOT redraw them.
```
1) Copy every PNG from docs/reference/colonies/art/ to static/art/ with readable names taken from docs/reference/colonies/README.md (ART_MANIFEST), e.g. building-defense-tower.png, avatar-hel-round.png, planet-kepler9.png. Write static/art/manifest.json mapping the new name to the original id. Do not modify pixels.

2) Audit: list every sprite the game plan needs that is NOT in the art folder (for example buildings at level 2 and 3, scaffold/under-construction frame, damaged variants, supply crate open/closed, shield dome, energy beam particle, boss variants, station levels 2-3, trophies, remaining planet worlds/atmospheres/rings/moons). Output the list with proposed pixel size, matching the size/style of the existing sprites.

3) scripts/make_sprites.py: for ONLY the missing sprites, define each as a small text grid mapped to the exact palette hex values already used in the existing art (sample the colours from the existing PNGs), render crisp PNGs (nearest-neighbour) into static/art/. Idempotent. Match outline weight, light direction and density of the existing sprites.

4) Build static/art/_sheet.png (contact sheet of ALL sprites, existing + new, labelled, new ones marked) and show it at 4x on /dev/styleguide.
Show me the contact sheet and wait for approval before using any NEW sprite in a page.
```

### Phase 3 — Archive fix (schema)
```
Plan then implement (plan first, wait for OK): replace hard-delete of habits with archiving.
- habits.archived_on (nullable date). Deleting a habit or leaving a room archives instead; past point_transactions stay in the ledger.
- Archived habits vanish from dashboard, streaks, scores, rankings, room leaderboards; a member's contribution to a room remains visible after they leave.
- Creator handover when leaving a room stays as-is.
- Unarchive is NOT needed. Account deletion still hard-deletes everything.
- Migration with Flask-Migrate. Tests: spending then leaving never produces a negative balance; archived habit excluded from every aggregate; delete-and-recreate gives no extra points.
Before pushing: run migration on dev, then ./scripts/migrate-prod.sh (back up the prod branch in Neon first), then push.
```

### Phase 4 — Colony core
```
Implement Colonies phase 1 per the Game Plan. Plan first (list files, tables, routes, tests), wait for OK, then build in commits.
- habits.category (fitness, study, sleep, water_food, mind, other); category picker on habit create/edit; existing habits default to other.
- Tables: colonies (one per user, auto-created on first visit with the free Rust world), buildings (type, level, slot, started_at, finishes_at, damaged_on).
- habitual/game.py: pure functions for costs, build times, unlock rules (10 check-ins in the category), Energy = balance, XP = earned, commander rank thresholds, colony level, daily Energy cap of 100 from check-ins. The cap MUST be computed from the points ledger for the user's local day (it counts archived/deleted habits too), so creating and deleting habits can never reset or bypass it. Add a test for that. Full pytest coverage.
- Routes: GET /colony, POST /colony/build, POST /colony/upgrade/<id>. Spending writes a negative point_transactions row (reason build/upgrade). Buildings store finishes_at; "done" is decided on read.
- Colony home page per the Colonies mockups: planet scene with building slots, today's habits list with check-in, Energy/XP in the header, build menu (phone: bottom sheet).
- Check-in response returns Energy gained; frontend plays the Energy beam to the planet (reduced-motion safe).
Do not touch rooms/fleets, sectors, shop yet. Run migrations on dev, then prod BEFORE pushing.

ALSO IN THIS PHASE (onboarding customization, per the mocks): new users go signup -> "Create your commander" (PhoneAvatar/WebAvatar, step 1 of 3) -> "Customize your planet" (PhonePlanet/WebPlanet, step 2) -> first habit (step 3) -> colony home. Existing users see the same two screens once on next login (skippable, defaults applied).
- Commander = 7 layered slots (helmet, visor, skin, hair, suit, gear, badge), rendered by stacking transparent PNGs from docs/reference/colonies/art/ in the same z-order the mock's script uses. Planet = world, atmosphere, ring, moons, building layout, name.
- Store as users.avatar (JSON, one key per slot) and colonies.look (JSON). Starter kit = only the parts marked FREE in the mocks (README/CustomizeFlow). Locked parts are visible and can be tried on, but Save is blocked until the user owns every equipped part (mock: "USE FREE PARTS" button).
- Server validates on save: every equipped part must be a starter part or in owned_items; reject otherwise. Tests for valid save, locked-part rejection, and tampered payload.
- Render the user's commander and planet everywhere the mocks show them (header, profile, colony home). Others' looks appear on galaxy/sector/fleet in the later phases.
- Changing parts you already own is free and unlimited, via the locker in Profile.
```

### Phase 5 — Storms, repairs, shields, daily crate, comeback
```
Implement per Game Plan, in game.py with tests:
- On app open compare today with users.last_seen_on. Each missed scheduled day with no shield damages one building (oldest first; undefended before Defense Towers; Defense Tower level absorbs hits per week). Damage is repaired free by the next completed day's check-in (oldest damaged first) or paid early (60 Energy).
- Shield = existing streak freeze, now sold at 80 Energy, hold max 3.
- Daily supply crate: first visit each day, 5-35 Energy growing over 7 consecutive days, unique (user_id, date).
- Comeback: away 3+ days gives double Energy for 3 days.
- Vacation mode: up to 14 days, once per 60 days, pauses storms.
- Storm UI per the brief (rust edge flicker once per visit, damaged sprite, repair button).
Idempotency: refreshing the page must not apply damage twice. Add tests for that.
```

### Phase 6 — Fleets (rooms become fleets)
```
Rooms become fleets. Keep every room feature (leaderboard, crown -> flagship of the day, vouches, health meter -> station power bar, streak -> station shield, join code/link). Rename user-facing text to Fleet.
Add: fleet_stations (level, progress, boss_hp, boss_week), nudges (one per pair per day), trophies (mission end).
- Each member check-in on a room habit adds station progress and deals 1 damage to the weekly boss. Boss HP scales with member count so small and big fleets are equally hard. Beating it gives members Energy + the VX-3 hull skin.
- Station damaged if room streak breaks; repaired by next all-member day. No progress loss.
- Nudge: one-tap ping to a fleetmate who hasn't checked in by evening.
- Mission end: station becomes a trophy on every member's planet.
Plan first, wait for OK, tests in game.py. Migrate dev, then prod, then push.
```

### Phase 7 — Sectors + galaxy
```
Weekly sectors per Game Plan:
- Weekly Score computed (consistency over volume, perfect days, vouched capped at 20/week; habits lock on Monday). Tiers: Asteroid Belt, Moon Orbit, Nebula, Star Cluster, Core Systems, Deep Space. Groups of ~30, top 5 up, bottom 5 down, new accounts start in the lowest tier.
- Settlement happens on first load after Monday inside one DB transaction (idempotent). Tables sector_weeks, sector_members.
- Pages: /sector (rankings), /galaxy (shared map; default visibility friends + fleet-mates), /colony/<username> (visit, read-only, shows buildings, rank, streak; dim inactive colonies).
- Rewards for top 3: Energy + trophy.
Tests for settlement idempotency, ties, and fresh-account placement. Plan first.
```

### Phase 8 — Shop + unlockable parts (customization already exists from Phase 4)
```
The commander/planet editors and starter kit shipped in Phase 4. Now add the unlock side, per the Inventory tables in the Game Plan and docs/reference/colonies/screens (PhoneShop/WebShop, PhoneProfile/WebProfile, CustomizeFlow rules).
- owned_items table (user_id, item_key, bought_at). Shop buys cosmetics and shields with Energy (negative point_transactions row, reason cosmetic/shield), blocks if balance is too low.
- Earned-only parts unlock automatically from their conditions (Crest = Captain rank, Mirror visor = 30-day streak, Admiral suit = top 3 sector, Scarf = beat a fleet boss, Planet badge = Colony LV 10, Ice world = 30-day streak, Ring = Colony LV 10, Second moon = Observatory LV 2, Signal atmosphere = Observatory LV 1). Add an unlock check run on check-in and on week settlement; show "how close you are" text exactly as in the locker mocks.
- Locker (in Profile) shows every part, locked ones previewable, "how to get it" under each. Save validation unchanged (starter or owned only).
- Show other users' commanders/planets on galaxy, sector table, fleet crew, visit page and the shareable profile card.
- Sprites for any part not in the art folder: add via scripts/make_sprites.py, show contact sheet first.
Plan first.
```

### Phase 9 — Landing + phone-first + PWA
```
1) Landing page (logged-out) with: hero (planet), How it works (3 steps), the 6 buildings, Fleets, Sectors, Storms-and-repair, FAQ, final CTA. Copy in the Commander voice, no invented stats.
2) Phone-first pass at 390px for every screen: bottom tab bar, 44px targets, no horizontal scroll, bottom sheets for menus.
3) PWA: manifest, icons from the sprite pipeline, service worker caching static assets only (never authenticated HTML or API), install prompt, iOS "Add to Home Screen" hint.
Lighthouse mobile >= 90 for Performance and Accessibility on landing and colony home.
```

### Phase 10 — Reminders
```
Plan only first: story-style reminders ("Commander, the Biodome is running dry") by email and web push; per-user quiet hours and timezone; Vercel cron; idempotent reminder_log; opt-in toggles in settings. Web push needs the PWA from Phase 9. Wait for OK, then build in stages. Migrate prod before pushing.
```

### Phase 11 — Friend testing, balance, v1.0
```
Prepare for friend testing: a /feedback link, a seed/demo account script (dev only), and a balance log I can read: average Energy/day, buildings per week, storm hits per active user, boss win rate. Then update README with screenshots in docs/screenshots/, tech stack, rules, and tag v1.0.
```

---

## 3. Fixes you may need mid-phase
**Bug:** `Bug: <what I did> -> <what happened> -> <what I expected>. Find the root cause first, show it, then fix with a test.`
**Live 500:** `Live site returns 500 on <route>. Here is the Vercel log: <paste, secrets masked>. Check first whether prod is missing a migration (compare alembic heads dev vs prod) before changing code.`

## 4. Utility prompts
**Session start**
```
Read CLAUDE.md and docs/ first. We are on Phase <N> of the Colonies rebuild (HABITUAL_COLONIES_PLAYBOOK). Summarise in 5 lines what exists, what this phase changes, and any schema impact. Do not write code until I say go.
```
**Session end**
```
Update CLAUDE.md with what changed this phase (new tables, routes, game rules, design tokens). List migrations created and whether each is applied to dev and prod. Run pytest and show the result. Give me the exact commit list and the push checklist.
```
