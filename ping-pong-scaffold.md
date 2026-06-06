# Ping Pong — Build Week Scaffold

## Concept

Ping Pong is a tracker for the things you're *waiting on*. Not a to-do list of what you have to do next, but a list of who or what owes you the next move before you can proceed. A task here is really a blocked task: "renew my license" is waiting on *the DMV*; "ship the proposal" is waiting on *Dana's feedback*; "rent the car" is waiting on *the license being renewed*. Each entry names the thing you're trying to get done and the party holding the ball — a person, an organization, or another one of your own tasks.

The whole point is that the ball is in someone else's court, and right now the only place that's tracked is your head. Ping Pong is a simple web app: an input form to add a blocked item (the task, plus who/what has the ball), and a list of everything currently waiting. You glance at it and instantly see "these five things are stalled, and here's whose move it is on each." When the ball comes back to you — feedback arrives, the license clears — you act on it or close it out.

## Origin / Why It Matters

Multi-step decisions and projects stall on dependencies, and the burden of remembering "I can't start B until A comes back" falls entirely on you. Things fall through the cracks not because you forgot to do them, but because you forgot you were waiting on someone — and they forgot too, so it sits forever. Ordinary to-do apps model *your* next action; they're bad at modeling "blocked, pending external input," which is exactly the state these items live in. You likely care about this because the cost isn't doing the work — it's the silent dropped handoff, the renewal that lapses, the email you never followed up on. A list that surfaces "whose move is it?" turns invisible waiting into something you can see and nudge.

## Form

You explicitly asked for a **simple web app with an input form that lists the tasks** — that's the form, and this scaffold builds on it rather than substituting something else. It's a good call: a web app is glanceable, lives at a URL you can open from any device, and gives you an obvious surface to grow later. One concern worth naming, not as grounds to change the plan but to keep in view: a web app needs to be *running* and *reachable* to be useful, where a CLI or a native app is always there. For build week, running it locally is completely fine; if you later want it on your phone from anywhere, you'll need to deploy it somewhere (a note for Key Challenges, not a reason to pick a different form now).

**Recommended primary form: FastAPI + SQLite, with a small server-rendered HTML front end.** This is the durable default and it fits exactly. FastAPI gives you a real HTTP API (`POST /tasks`, `GET /tasks`, `POST /tasks/{id}/close`), SQLite is a single file with no separate database server to run, and a server-rendered template (Jinja2) gives you the form-and-list UI you described without dragging in a separate JavaScript front-end build. Because the API is real underneath the HTML, you can later add a phone-friendly page, a Slack reminder, or a second client without a rewrite — the list-rendering page is just the first client of the API, not the whole app.

**Worth deciding consciously — one real design axis here:** *is a "who/what" a free-text string, or a thing the app knows about?* The minimal reading of your description is free text — you type "Dana" or "DMV" and it's just a label. That's the simplest thing that works and it's where the MVP starts. But the most interesting line in your idea is the dependency one: "I can't proceed on renting a car until I renew my license." That's a task waiting on *another task*, not on an outside party. If "who/what" can optionally point at another row in your own list, Ping Pong stops being a flat list and starts modeling chains — and when you close "renew license," the app can light up "rent car" as newly unblocked. That's the difference between a tool that's mostly plumbing and one genuinely worth keeping. **Recommendation:** start with free-text who/what for the MVP (it tests the core glance-value fast), but design the schema so a blocker can *optionally* be a foreign key to another task. Add the task-on-task linking as the very next step after the MVP works. Don't build the linking UI on day one, but don't paint yourself into a schema that can't express it.

A native mobile app would be the "right" answer if scope weren't a constraint and you wanted this in your pocket with push reminders — note that you're deferring that, and the API-first web shape is what keeps that door open.

## Minimum Viable Product

The thinnest real end-to-end slice, built on the stack you'll keep:

A FastAPI app backed by a SQLite file with one table, `tasks` (columns: `id`, `description`, `waiting_on` text, `status` defaulting to `open`, `created_at`, and a nullable `blocked_by_task_id` foreign key reserved for the next step but not yet used by the UI). Three pieces wired together:

1. `POST /tasks` accepts a description and a `waiting_on` string, inserts a row, returns it.
2. `GET /` renders an HTML page (Jinja2 template) that lists all `open` tasks — each showing the description and "waiting on: X" — with the add-task form at the top.
3. `POST /tasks/{id}/close` marks a task closed so it drops off the list.

You open `localhost:8000`, type in three real things you're actually waiting on right now, see them listed, and close one. That's the MVP: a keeper slice through the real architecture, not a throwaway. The moment you can look at your own real blocked items in one place — and the count isn't living only in your head anymore — is the moment the core idea is experienced for real.

## Key Assumption to Validate

This idea works only if: **seeing your waiting-on items in one external list actually changes behavior — you nudge the held ball or close the loop instead of letting it sit.** If that's not true, Ping Pong is just a second inbox you stop checking, and items fall through the cracks of the tracker the same way they fell through the cracks of your memory. The MVP tests this directly: put your *real* pending items in, live with it, and see whether glancing at the list makes you act. The risk isn't technical — it's whether the list earns a glance. If it doesn't, that's a real and useful finding (see What Success Looks Like).

## Existing Products and Prior Art

- **Todoist / Things / TickTick / Microsoft To Do** — general task managers. They model *your* next action and treat dependencies as an afterthought (Todoist has no first-class "blocked by"; Things has none). They don't make "whose move is it?" the primary view, which is the entire point here.
- **Asana / Jira / Linear / Monday** — project tools that *do* support task dependencies and "blocked" states. But they're heavyweight, team-oriented, and built around your own work queue, not a personal "things other people owe me" glance. Overkill for a personal waiting-on list, and the waiting-on framing is buried.
- **"Waiting For" lists in GTD apps** — David Allen's *Getting Things Done* has an explicit "Waiting For" list, and many setups (OmniFocus, plain text) implement it as a tag or context. This is the closest conceptual prior art and validates the need. What's missing in most implementations is the task-on-task dependency chain and a UI that's *only* about waiting, not a mode buried inside a bigger app.
- **Follow-up reminders in email (Boomerang, Superhuman, Gmail nudges)** — these track "you're waiting on a reply to this email." Narrower (email only) and they don't model non-email waits like a license renewal or another task.

The space isn't empty, but the specific shape — a dead-simple personal list whose first-class concept is "who/what has the ball," including other tasks — is underserved. Most tools either bury it or are too heavy.

## Failed Predecessors

No single famous graveyard here, but a pattern to learn from: countless personal-tracker apps die because they demand more upkeep than the problem they solve. A waiting-on list only works if adding an item is nearly frictionless — if logging a blocked task takes more effort than just remembering it, you'll stop. The GTD "Waiting For" list itself frequently fails in practice for the same reason: people set it up and abandon it. Lesson: keep capture brutally fast (one form, two fields) and make the list worth opening, or it becomes the abandoned tool the original problem was already living without.

## Relevant Background or Research

The premise leans lightly on *Getting Things Done* (David Allen) — specifically the "Waiting For" list as a distinct category from next-actions; it's the clearest articulation of why "blocked, pending someone else" deserves its own surface. On the build side, the FastAPI docs' tutorial on request bodies, form data, and Jinja2 templates (`fastapi.tiangolo.com`) covers essentially everything the MVP needs; no novel technique is involved. This is a straightforward CRUD app — don't over-research it.

## Key Challenges

- **Capture friction (serious, and the real make-or-break).** If adding a blocked item is even slightly annoying, you won't do it and the tool dies. The form must be trivially fast — two fields, one button, no required category dropdowns or date pickers. This is an interaction risk, not a technical one, and it's the most important thing to get right.
- **Whether the list earns a glance (serious).** Tied to the Key Assumption. A list you never open is worthless. Watch whether you actually return to it; if you don't, the framing or the surfacing is wrong, not the code.
- **The free-text vs. linked-blocker decision (moderate).** Getting the schema right so a blocker can later point at another task is easy *if you reserve the column now* and painful to retrofit if you don't. Low effort to get right early; annoying to fix late.
- **Deployment / always-on (minor for build week, real later).** A locally-run web app is only useful while it's running. For the demo and your own dogfooding, `localhost` is fine. If you want it reachable from your phone, you'll need to deploy it (a small host, or a machine that's always up) — defer this, but know it's the cost of the web-app form you chose.
- **Evaluation ambiguity (moderate).** "Did it work?" isn't a unit test — it's behavioral. Decide up front how you'll judge it: did you put real items in, did you return to the list unprompted, did anything get unstuck *because* you saw it? Without that, you can't tell success from a tool you politely abandoned.

## Setup Checklist (Do This Before Starting)

- **Python 3.12+** — the runtime for the whole app. Create a per-project virtual environment (`python3 -m venv venv`) and work inside it.
- **FastAPI + Uvicorn** — `pip install fastapi "uvicorn[standard]"`. FastAPI is the web framework; Uvicorn is the ASGI server that actually runs it.
- **Jinja2** — `pip install jinja2`. Template engine for server-rendering the form-and-list HTML page.
- **python-multipart** — `pip install python-multipart`. Required for FastAPI to parse HTML `<form>` submissions (a `POST` from a form); easy to forget and it fails with an unhelpful error without it.
- **SQLite** — no install needed; it ships with Python via the `sqlite3` module, and the database is just a file in the project folder. (Optional: `pip install sqlalchemy` if you'd rather use an ORM than raw SQL — your call; raw `sqlite3` is enough for the MVP.)
- **No API keys, accounts, OAuth, or external data.** This idea needs none of that — there's nothing to fund, authorize, or wait on. Setup is genuinely just the pip installs above.

## Plan of Attack

1. **First commit target.** Project skeleton: a venv, `requirements.txt` (fastapi, uvicorn, jinja2, python-multipart), an empty `main.py` with a FastAPI app and one `GET /` route returning "Ping Pong", and a `.gitignore` that excludes `venv/` and the SQLite file. Confirm `uvicorn main:app --reload` serves the page.
2. **Core skeleton.** Create the SQLite `tasks` table on startup (including the reserved nullable `blocked_by_task_id` column you won't use yet). Add `POST /tasks` that inserts a row and `GET /tasks` (JSON) that returns all open rows. Verify with `curl` or the auto-generated `/docs` page — the API works before any HTML exists.
3. **First testable artifact.** Wire up the Jinja2 template: `GET /` renders the add-task form plus the list of open tasks, and `POST /tasks/{id}/close` marks one closed. Now you can open the browser, add real waiting-on items, see them listed, and close one. This is the MVP — start dogfooding it with your actual pending items.
4. **Next step (the interesting one): task-on-task dependencies.** Let the "who/what" field optionally be another task instead of free text — populate `blocked_by_task_id`, and when a task is closed, surface any tasks that were blocked by it as newly unblocked. This is what makes Ping Pong more than a flat list.
5. **Decisions to make early — name them now:**
   - *Free-text blocker vs. linked task* for the MVP. Recommendation: free text for the MVP, schema reserved for linking. Decide before you write the table so the column exists.
   - *Raw `sqlite3` vs. SQLAlchemy.* Either is fine; pick before step 2 so you're not switching mid-stream. Raw SQL is less to learn for a one-table app.
   - *How you'll judge success* (behavioral, not a test) — decide before you start dogfooding so you're actually watching for it.

## What Success Looks Like

**The artifact:** a running FastAPI + SQLite web app with a working add-form, a live list of what you're waiting on, and the ability to close items — plus, ideally, task-on-task dependency linking.

**The demo, in order:** (1) open the app showing a list of *your own real* pending items, each with whose move it is; (2) add a new blocked item live via the form and watch it appear; (3) close an item and watch it drop off; (4) if you reached the dependency step, close a task that another task was waiting on and show the dependent task surfacing as unblocked.

**Audience and takeaway:** fellow builders. They should leave understanding that this isn't another to-do app — it's a tracker for the *waiting* state specifically, and that "whose move is it?" is a genuinely different and useful lens.

**The one question the demo answers:** *Does putting your waiting-on items in one external list actually surface things that would otherwise fall through the cracks?* "Works" operationally means: over real use, you returned to the list unprompted and at least one stuck thing got nudged or closed *because* you saw it. If instead you stopped opening it and items still slipped, that's a clear, legitimate negative result — you'd have learned that a passive list isn't enough and the missing ingredient is active reminding (a nudge, a notification), which is exactly what the next version would test.

**Why it's worth continuing:** the API-first shape means the HTML list is just the first client. A clean `POST /tasks` / `GET /tasks` boundary and real SQLite storage mean you can later add a phone-friendly page, a daily Slack/email nudge of stale items, or "ping the person who has the ball" — without rewriting the core. The reserved `blocked_by_task_id` column means the dependency-chain feature grows in naturally instead of forcing a migration.

## Jargon & Libraries Referenced

- **FastAPI** — a modern Python web framework for building HTTP APIs with automatic request validation and an auto-generated interactive docs page at `/docs`. The backend of this app.
- **Uvicorn** — the ASGI server that actually runs a FastAPI app (`uvicorn main:app --reload`); FastAPI defines the app, Uvicorn serves it.
- **Jinja2** — Python's standard HTML templating engine; lets you render the task list and form as server-side HTML pages rather than building a separate JavaScript front end.
- **python-multipart** — a small dependency FastAPI needs specifically to read submitted HTML `<form>` data; without it, form `POST`s fail with an unhelpful error.
- **ASGI** — the async server interface FastAPI is built on (the modern successor to WSGI); you don't interact with it directly, but it's why Uvicorn rather than a plain Flask-style server runs the app.
- **SQLAlchemy** — an optional Python ORM that maps database rows to Python objects; an alternative to writing raw SQL against `sqlite3`. Overkill-but-fine for a one-table app.
- **GTD "Waiting For" list** — from David Allen's *Getting Things Done*: a dedicated list of items you've handed off and are awaiting a response on, kept separate from your own next-actions. The conceptual ancestor of this whole idea.
- **Foreign key** — a database column whose value points at the primary key of another row (here, `blocked_by_task_id` pointing at another task's `id`); the mechanism that turns the flat list into dependency chains.
