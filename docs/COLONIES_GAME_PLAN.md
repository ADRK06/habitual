# Habitual: Colonies — Game Plan

 · 

## The big idea

Every user gets their own planet in space, and doing real habits is the only way to build a colony on it. Points stop being a number in the header and become the fuel for something you can see grow.

Right now points feel useless because they do only one job: buying streak freezes. Colonies gives them three jobs:
- **Build:** points (shown as Energy) pay for buildings, upgrades and repairs on your planet.
- **Show off:** your planet, your commander avatar and your rank are visible to every other user on a shared galaxy map.
- **Compete:** every week you are ranked against about 30 other commanders, and the best move up to a higher sector of space.

The one rule behind everything: **the game can never be won without doing real habits.** Nothing in the game can be bought, farmed or rushed any other way.

## How it works for the user

You do your habits, they give you Energy, and Energy builds your colony. That is the whole loop.

### A normal day
- You open Habitual and see your planet. Something has changed since last time: a building finished, a supply drop landed, or a storm is coming.
- You check in a habit. An energy beam flies from the habit card into your planet.
- You spend Energy to start a new building or upgrade one.
- The building takes a few hours to finish, so you come back later to see it done.

### The two numbers

Your app already tracks these two numbers. Colonies just gives them space names.

| Today in Habitual | In Colonies | What it does |
|---|---|---|
| Earned points (never goes down) | **Commander XP** | Sets your commander rank and colony level |
| Balance (earned minus spent) | **Energy** | Spent on buildings, repairs, freezes and cosmetics |

Spending Energy never lowers your XP, so building never feels like losing progress.

### Habits become buildings

Each habit gets a category. The category decides which kind of building it powers, so your planet ends up looking like your real life.

| Habit category | Building | Building's job in the game |
|---|---|---|
| Fitness | Defense Tower | Protects your colony from storm damage |
| Study and reading | Research Lab | Unlocks new building designs |
| Sleep | Power Reactor | Small bonus on Energy from every check-in |
| Water and food | Biodome | Grows your colony's population |
| Mind (meditation, journaling) | Observatory | Reveals rare events and new planets |
| Anything else | Custom Module | User picks the look |

A building of a category unlocks once you have done enough check-ins in that category. For example, the first Research Lab needs 10 study check-ins.

### Your commander avatar
- **Rank** rises with XP: Cadet, Pilot, Captain, Commander, Admiral.
- **Class** comes from your strongest category: Guardian (fitness), Scientist (study), Engineer (sleep), Botanist (water and food) or Explorer (mind).
- **Suit, helmet and ship** are cosmetics bought with Energy.

## Competing with everyone

You are ranked two ways: your **Colony Level** shows long-term effort, and your **Weekly Score** decides who wins each week. Splitting them means a new user can win a week even against someone who has played for a year.

### Colony Level (all-time)

Colony Level comes straight from Commander XP, so it only ever goes up. It is shown on your planet and on the galaxy map.

### Weekly Score (resets every Monday)

The Weekly Score is mostly about consistency, not volume. Completing 5 out of 5 habits beats completing 20 out of 40.
- **Check-ins scheduled** counts only the habits you had when the week started, using each habit's frequency (daily, specific days, or X times a week).
- **Perfect days** are days where every scheduled habit was done (up to 7).
- **Vouched check-ins** are capped at 20 a week.

### Sectors (weekly leagues)
- Each week you are placed in a sector of about 30 commanders at your tier.
- On Monday, the top 5 warp up a tier and the bottom 5 drop down.
- Tiers, lowest to highest: Asteroid Belt, Moon Orbit, Nebula, Star Cluster, Core Systems, Deep Space.
- Rewards for the top 3: Energy, a rare cosmetic, and a trophy on their planet.

### The galaxy map

All colonies float on one shared map. Anyone can tap a planet to see its buildings, commander, rank and current streak. Inactive colonies slowly dim, which quietly shows when someone has stopped.

### Fleets (your existing rooms)

Every habit room becomes a fleet that builds a shared station and fights a weekly boss together. The next section explains how.

## Habit rooms as fleets

Rooms become fleets: you build your own planet solo, and your fleet is the team you build a space station with. Every room feature you already have carries over, so fleets are mostly a new look plus a few team goals.

### What carries over

| Room feature today | In Colonies |
|---|---|
| Room | Fleet |
| Room habit (a normal habit with a room_id) | Still powers your own planet, so every room check-in also gives you Energy |
| Room leaderboard | The fleet's internal ranking, unchanged |
| Daily crown (first to check in) | Flagship of the day: your ship leads the fleet on the station screen |
| Vouches | Bonus Energy and Weekly Score, as before |
| Health meter (who checked in today) | The station's power bar for today |
| Room streak | The station's shield, which stays up while the room streak is alive |
| Invite link and join code | "Join my fleet" |

### What's new
- **Shared space station.** Every member's check-in adds progress, and the station levels up with new modules such as a docking bay or comms tower. It orbits above every member's planet, so you see your team's work each time you open the app.
- **Repair, not reset, for the team.** If the room streak breaks, the station takes damage instead of losing progress. The next day everyone checks in repairs it.
- **Weekly boss.** An alien mothership attacks each fleet every Monday, and every member check-in deals 1 damage. Beating it gives every member Energy and a cosmetic.
- **Nudges.** If a fleetmate hasn't checked in by evening, tap their ship to send a one-tap ping.
- **Mission complete.** When a room's duration ends, the station becomes a trophy on every member's planet, sized by how much the fleet built.
- **Fleet vs fleet (later).** Fleets are ranked on the galaxy map by the average Weekly Score of their members, so big rooms don't win just by being big.

The boss's health scales with the fleet, so a 3-person room and a 10-person room face an equally hard fight:

### The archive fix (do this first)

Today, leaving a room deletes your room habit and its points, and deleting any habit does the same. Once points become spendable Energy, that breaks: someone could spend 300 Energy, leave a room, and end up with a negative balance.

The fix is to **archive habits instead of deleting them.** An archived habit disappears from the dashboard and stops counting toward streaks, scores and rankings, but its past points stay in the ledger. A member's contributions to a fleet station also stay after they leave. Creator handover when leaving works exactly as it does now.

### Backend for fleets

| What | Stored or computed |
|---|---|
| Station level, progress, boss HP and boss week | Stored in fleet_stations |
| Station shield | Computed from the existing room streak |
| Station power bar | Computed from the existing health meter |
| Boss damage and station progress | Added inside the existing check-in route when the habit has a room_id |
| Nudges | New nudges table: from_user, to_user, room_id, date, unique per pair per day |
| Mission trophies | New trophies table: user_id, room_id, station_level, earned_on |
| Archived habits | New habits.archived_on column, replacing the hard delete |

## Keeping users coming back

Most people quit habit trackers because logging is boring, one bad day kills their motivation, and nobody notices when they leave. Each mechanic below fixes one of those, and several build on features Habitual already has.

| Why people quit | What Colonies does | Builds on |
|---|---|---|
| Opening the app feels like a chore | Something new waits every visit: a finished building, a supply drop, an incoming storm | New |
| Opening the app feels like a chore | Check-ins play an energy beam into the planet, with sound | Existing check-in animation |
| One missed day ruins everything | A missed day damages one building instead of resetting progress; your next completed day repairs it | New |
| One missed day ruins everything | Do the tiny version of a habit to keep the streak alive at lower Energy | Existing tiny_version on habits |
| One missed day ruins everything | Shields protect your colony and streak for a day | Existing streak freezes |
| Coming back after a break feels bad | Comeback bonus: double Energy for 3 days after 3+ days away | New |
| Nobody notices if you stop | Your fleet's station and boss depend on you; friends can send a one-tap nudge | Existing rooms |
| Nobody notices if you stop | Your planet dims on the galaxy map | New |
| No reason to keep going after week one | Goals at three timescales: today's habits, this week's sector rank, long-term wonders and new planets | New |
| Reminders get ignored | Story-style reminders: "Commander, the Biodome is running dry" | Planned reminders feature |

### Daily supply drop

The first visit each day opens a supply crate with a small random Energy reward. Consecutive days make the crate bigger, up to day 7.

### Wonders and new planets

Wonders are huge end-game buildings, such as a Dyson Sphere or a Space Elevator, that take months of consistency to finish. A 30-day streak on any habit unlocks a second planet type, such as an ice world or a lava world. These give long-term players something to chase.

## How it plugs into the current backend

Colonies sits on top of what you already have: Flask, Neon Postgres, the points ledger and the check-in route. Nothing existing gets replaced; the game reads from the ledger and check-ins, and adds a few new tables.

### Three rules that keep it simple
- **The points ledger stays the single source of truth.** Spending Energy is just a new negative transaction in point_transactions, exactly like buying a freeze today.
- **No background jobs, same as now.** Anything that "happens while you're away" is worked out when you next load the page. A building stores the time it will finish; when you open the app after that time, it shows as done. Storm damage is calculated by looking at the days since your last visit.
- **Game rules live in one tested file.** A new game.py holds the pure rules (costs, Weekly Score, damage, tiers) with pytest tests, the same way points.py holds the streak and points rules.

### What changes in existing tables

| Table | Change |
|---|---|
| habits | Add category (fitness, study, sleep, water_food, mind, other) and archived_on (nullable date) |
| users | Add last_seen_on (date), commander_class, equipped_suit, equipped_ship, current_tier |
| point_transactions | No change to columns; new reason values: build, upgrade, repair, cosmetic, supply_drop, comeback, sector_reward, boss_reward |
| rooms | No change; a room is now shown as a fleet |

### New tables

| Table | Key fields | What it stores |
|---|---|---|
| colonies | id, user_id (unique), name, planet_type, created_on | One planet per user, plus extra unlocked planets later |
| buildings | id, colony_id, type, level, slot, started_at, finishes_at, damaged_on (nullable) | Every building, when it finishes, and whether it is damaged |
| owned_items | id, user_id, item_key, bought_at | Cosmetics a user has bought |
| sector_weeks | id, week_start, tier, group_number | One row per sector group per week |
| sector_members | id, sector_week_id, user_id, weekly_score, final_rank, result (up / stay / down) | Who is in which sector and how they finished |
| fleet_stations | id, room_id (unique), level, progress, boss_hp, boss_week | Each fleet's shared station and weekly boss |
| supply_drops | id, user_id, date, amount — unique (user_id, date) | One crate per user per day |

The shop's item list, building costs and planet types live in code as constants, not in the database. They change rarely and are easier to edit there.

### What happens when someone checks in
- The existing check-in route runs as it does now: saves the check-in, adds daily and milestone points, and awards the crown.
- **New:** if a building is damaged, the oldest one is repaired for free.
- **New:** if the habit is in a fleet, its station gains progress and the boss loses HP.
- **New:** the page returns the Energy gained so the frontend can play the energy-beam animation.

### What happens when someone opens the app
- Compare today with last_seen_on. For each missed scheduled day with no freeze, mark one building damaged, oldest first. Undefended buildings are hit before Defense Towers.
- If they were away 3 or more days, start the comeback bonus.
- If no supply drop exists for today, offer the crate.
- If a new week has started and last week's sector is unsettled, settle it: rank everyone, write final_rank and result, pay rewards, and build the new week's groups.
- Update last_seen_on to today.

Step 4 runs only once because the first visitor of the week settles it inside a database transaction; everyone after sees it already done. If that ever proves slow, Vercel's built-in cron can call the same function at Monday 00:05 instead.

### New routes

| Route | Does |
|---|---|
| GET /colony | Your planet view |
| POST /colony/build | Spend Energy to start a building |
| POST /colony/upgrade/ | Upgrade a building |
| POST /colony/repair/ | Pay Energy to repair a building early |
| GET /shop, POST /shop/buy | Cosmetics and shields |
| GET /galaxy | The shared map |
| GET /colony/ | Visit someone else's planet |
| GET /sector | This week's sector ranking |
| POST /supply-drop | Open today's crate |

### Frontend

The planet stays inside your current stack: Jinja for the page, HTMX for build and buy buttons, Alpine.js for menus, and GSAP for the energy beam, construction and storm animations. Draw the first planet as layered SVG with building sprites placed on fixed slots. Move to PixiJS only if the galaxy map later needs hundreds of moving planets.

### Safety

Every new table ships with a Flask-Migrate migration. Run it on the dev branch first, then on production with scripts/migrate-prod.sh **before** pushing the code, so the earlier 500-error incident can't happen again.

## Fairness rules

Once strangers compete, someone will try to cheat, usually by adding lots of tiny habits. These rules make cheating pointless.
- **Consistency beats volume.** The Weekly Score uses the share of habits done, so more habits never helps by itself.
- **Habits lock on Monday.** Habits added mid-week count from next week's score, not this one.
- **Daily Energy cap.** At most 100 Energy a day from check-ins, so 40 habits can't flood the shop.
- **Vouched check-ins count extra,** but only up to 20 a week.
- **Only today can be checked in.** This rule already exists and stays.
- **New accounts start in the lowest tier,** so a fresh account can't skip ahead.
- **Delet****ed habits are archived, not erased:** past points stay but the habit stops counting, so delete-and-recreate tricks gain nothing.

## Inventory

Every item a player can own falls into one of five groups: currencies, buildings, consumables, cosmetics and collectibles. Costs and timings match the UI mockups and are starting values to tune after testing.

### Currencies

| Item | How you get it | What it's for | Can it go down? |
|---|---|---|---|
| Commander XP | Every point earned (check-ins, milestones, crowns, vouches) | Commander rank and colony level | No |
| Energy | Same earnings as XP, plus supply drops, boss and sector rewards | Buildings, upgrades, repairs, shields, cosmetics | Yes, when spent |
| Weekly Score | Worked out from the week's consistency, perfect days and vouches | Sector ranking; resets every Monday | Resets weekly |

### Buildings

| Building | Habit category | Unlocks at | Cost (LV 1 → next) | Build time | Effect |
|---|---|---|---|---|---|
| Defense Tower | Fitness | 10 fitness check-ins | 120 → +60 per level | 4h | Blocks 1 storm hit a week per level |
| Research Lab | Study | 10 study check-ins | 100 → 200 at LV 3 | 6h | Unlocks new building designs and Wonders |
| Power Reactor | Sleep | 10 sleep check-ins | 150 → +75 per level | 3h | +1 Energy per check-in per level |
| Biodome | Water and food | 10 water/food check-ins | 100 → +50 per level | 2h | +2 population per level |
| Observatory | Mind | 10 mind check-ins | 140 → +70 per level | 5h | Reveals rare events and uncharted regions |
| Custom Module | Other | Any 10 check-ins | 80 → +40 per level | 1h | Looks only; user picks the design |
| Wonder: Dyson Sphere | All | Colony LV 20 | 2,000 | 7 days | End-game status piece; +10% Energy |
| Wonder: Space Elevator | All | Colony LV 25 | 3,000 | 10 days | End-game status piece; free repairs |

Population comes from Biodomes and adds to colony level, along with building count.

### Consumables

| Item | How you get it | Cost | Effect | Limit |
|---|---|---|---|---|
| Shield (1 day) | Shop, sector rewards | 80 Energy | Covers one missed day: streak and colony both protected | Hold up to 3 |
| Paid repair | From a damaged building | 60 Energy | Fixes a building now instead of waiting for a free repair | — |
| Daily supply crate | First visit each day | Free | 5–35 Energy, growing over 7 days in a row | 1 per day |
| Comeback boost | Returning after 3+ days away | Free | Double Energy for 3 days | Once per break |

### Cosmetics (looks only, never affect score)

| Type | Item | How you get it | Cost |
|---|---|---|---|
| Suit | Phosphor | Starter | Free |
| Suit | Steel | Shop | 150 |
| Suit | Signal | Shop | 150 |
| Suit | Rust | Shop | 150 |
| Suit | Bone | Shop | 220 |
| Suit | Admiral | Top 3 finish in any sector | Not for sale |
| Ship | Scout | Starter | Free |
| Ship | Hauler | Shop; shown when sending Energy | 180 |
| Ship | Lancer | Shop; leads boss raids | 260 |
| Hull skin | VX-3 | Beat the weekly boss with your fleet | Not for sale |
| Planet skin | Rust world | Starter | Free |
| Planet skin | Ice world | 30-day streak on any habit | Not for sale |
| Planet skin | Lava world | Shop | 400 |
| Planet skin | Ringed giant | Season 1 reward | Not for sale |

### Avatar parts and planet looks

Commanders are built from 7 swappable slots and planets from 6 settings. Locked parts can be tried on in the locker but only saved once owned.

| Slot | Free at start | Bought with Energy | Earned only |
|---|---|---|---|
| Helmet | Round, Boxy | — | Crest (Captain rank) |
| Visor | Open (shows face), Amber, Steel, Rust | Signal 60 | Mirror (30-day streak) |
| Skin tone | All 5 | — | — |
| Hair | Covered, Dark, Brown, Silver | — | — |
| Suit | Phosphor | Steel 150, Signal 150, Bone 220 | Admiral (top 3 sector finish) |
| Gear | None, Antenna | Lights 90, Jetpack 200 | Scarf (beat a fleet boss) |
| Badge | None, Star, Bolt | — | Planet (Colony LV 10) |
| Planet world | Rust, Dust, Verdant | Lava 400 | Ice (30-day streak), Ringed giant (Season 1) |
| Atmosphere | Steel | Amber 100 | Signal (Observatory LV 1) |
| Ring | None | — | Ring (Colony LV 10) |
| Moons | None, One | — | Two moons (Observatory LV 2) |
| Building layout | Rearrange freely | — | More slots with colony level |

Stored as two small JSON settings: users.avatar (one key per slot) and colonies.look (world, atmosphere, ring, moons, slot order). Saving checks every equipped part is starter or in owned_items.

### Collectibles

| Item | How you get it | Where it shows |
|---|---|---|
| Sector trophy | Top 3 finish in a week | On your planet and profile |
| Station trophy | Fleet mission ends; size = final station level | Orbiting your planet |
| Title: Night Reader | 30 study check-ins after 9 PM | Profile, galaxy card |
| Title: 30-Day Crew | 30-day streak on any habit | Profile, galaxy card |
| Title: Storm Survivor | Repair a storm-damaged building | Profile |
| Title: Boss Slayer | Beat a weekly boss (counts up) | Profile |
| Title: First Light | Flagship of the day (counts up) | Profile |
| Title: 100-Day Monk | 100-day streak on any habit | Profile, galaxy card |
| Title: Wonder Builder | Finish any Wonder | Profile, galaxy card |

### Where each group is stored
- **Currencies:** XP and Energy come from the existing point_transactions ledger; Weekly Score is computed, with final results saved in sector_members.
- **Buildings:** the buildings table.
- **Consumables:** shields use the existing freezes table; crates use supply_drops.
- **Cosmetics:** owned_items, plus the equipped ones on users.
- **Collectibles:** titles use the existing badges table; trophies use the trophies table.
- **Item list, costs and effects:** constants in game.py, so tuning a price is a one-line change.

## Build roadmap

Phase 1 alone already fixes the "points are useless" problem, so ship it first and add competition only once the planet feels good.

Each phase is one Claude Code session in your usual flow: /clear, add the phase to CLAUDE.md, run migrations on dev, then on production, then push.

## Open questions
- Did the backend changes from the other chat touch check-ins, points or rooms? If so, update the "How it plugs in" section.
- Should existing users start with a free colony and buildings matching their current points, or start fresh with bonus Energy?
- Is the galaxy map public to all users, or only to friends and fleet members at first?
- What are the exact Energy costs per building and level? To be tuned after testing with real users.
- Should storms damage buildings at all for users on a break they planned, like exams?
