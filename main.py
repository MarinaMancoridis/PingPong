import csv
import io
import sqlite3
import random
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Optional
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")
DB = "pingpong.db"

EMOJIS = [
    # animals
    "🦊", "🐻", "🦁", "🐯", "🐺", "🦝", "🐨", "🦔", "🦦", "🦥",
    "🐸", "🦋", "🐙", "🦜", "🐬", "🦭", "🐲", "🦩", "🐝", "🦀",
    "🐧", "🦆", "🦉", "🦅", "🐦", "🦚", "🦤", "🐢", "🦎", "🐠",
    "🐡", "🦑", "🦞", "🐊", "🦏", "🦛", "🦒", "🦘", "🐘", "🦓",
    "🐿️", "🦫", "🦡", "🐇", "🐾",
    # nature & celestial
    "🌙", "⭐", "🌸", "🍀", "🌊", "🌋", "🌵", "🌴", "🍄", "🌺",
    "🌻", "🌹", "🍁", "❄️", "☄️", "🌪️", "🌈", "🔥", "💧", "🌿",
    # objects & symbols
    "🎯", "🎸", "🚀", "🔮", "🎪", "🍕", "🎩", "🎭", "🎨", "🎲",
    "🧩", "🎻", "🥁", "🎺", "🪗", "🎮", "🕹️", "🧸", "🪆", "🎠",
    "🏆", "🥇", "🔭", "🧪", "💡", "🔑", "🪄", "⚗️", "🧲",
    "🪁", "🛸", "🧊", "🪬", "🫧",
]

THREAD_COLORS = [
    "#4a90e2", "#e2844a", "#50b86c", "#9b6be2",
    "#e24a7a", "#4ab8e2", "#d4a23a", "#7a6be2",
]


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS people (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                emoji      TEXT NOT NULL DEFAULT '👤',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS group_threads (
                group_id  INTEGER NOT NULL REFERENCES groups(id),
                thread_id INTEGER NOT NULL REFERENCES threads(id),
                PRIMARY KEY (group_id, thread_id)
            )
        """)

        g_cols = {r[1] for r in conn.execute("PRAGMA table_info(groups)").fetchall()}
        if "icon" not in g_cols:
            conn.execute("ALTER TABLE groups ADD COLUMN icon TEXT DEFAULT ''")
            existing_groups = conn.execute("SELECT id FROM groups ORDER BY created_at").fetchall()
            used_icons: set = set()
            for grp in existing_groups:
                avail = [e for e in EMOJIS if e not in used_icons]
                icon = random.choice(avail if avail else EMOJIS)
                used_icons.add(icon)
                conn.execute("UPDATE groups SET icon=? WHERE id=?", (icon, grp["id"]))

        t_cols = {r[1] for r in conn.execute("PRAGMA table_info(threads)").fetchall()}
        if "sort_order" not in t_cols:
            conn.execute("ALTER TABLE threads ADD COLUMN sort_order INTEGER DEFAULT 0")
            for idx, t in enumerate(
                conn.execute("SELECT id FROM threads ORDER BY created_at ASC").fetchall()
            ):
                conn.execute("UPDATE threads SET sort_order=? WHERE id=?", (idx, t["id"]))
        if "is_active" not in t_cols:
            conn.execute("ALTER TABLE threads ADD COLUMN is_active INTEGER DEFAULT 1")

        col_info = conn.execute("PRAGMA table_info(tasks)").fetchall()
        cols = {r[1]: r for r in col_info}

        if not cols:
            _create_tasks_table(conn)
        else:
            person_col = cols.get("person_id")
            needs_rebuild = person_col and person_col[3] == 1

            if needs_rebuild:
                conn.execute("ALTER TABLE tasks RENAME TO tasks_bak")
                _create_tasks_table(conn)
                kept = [c for c in cols if c != "rowid"]
                cs = ", ".join(kept)
                conn.execute(f"INSERT INTO tasks ({cs}) SELECT {cs} FROM tasks_bak")
                conn.execute("DROP TABLE tasks_bak")
            else:
                if "notes" not in cols:
                    conn.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")
                if "closed_at" not in cols:
                    conn.execute("ALTER TABLE tasks ADD COLUMN closed_at TIMESTAMP")
                if "effort" not in cols:
                    conn.execute("ALTER TABLE tasks ADD COLUMN effort TEXT")
                if "est_hours" not in cols:
                    conn.execute("ALTER TABLE tasks ADD COLUMN est_hours REAL")
                if "sort_order" not in cols:
                    conn.execute("ALTER TABLE tasks ADD COLUMN sort_order INTEGER DEFAULT 0")
                    rows = conn.execute(
                        "SELECT id FROM tasks ORDER BY thread_id, "
                        "CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, due_date ASC, created_at DESC"
                    ).fetchall()
                    for i, row in enumerate(rows):
                        conn.execute("UPDATE tasks SET sort_order=? WHERE id=?", (i, row["id"]))
                if "thread_id" not in cols:
                    conn.execute("ALTER TABLE tasks ADD COLUMN thread_id INTEGER REFERENCES threads(id)")
                    conn.execute("INSERT OR IGNORE INTO threads (id, name) VALUES (1, 'General')")
                    conn.execute("UPDATE tasks SET thread_id = 1 WHERE thread_id IS NULL")
                if "due_date" not in cols:
                    conn.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT")
                if "is_deadline" not in cols:
                    conn.execute("ALTER TABLE tasks ADD COLUMN is_deadline INTEGER DEFAULT 0")

        # Grandfather all NULL due_dates as ANYTIME and NULL effort as standard (me only)
        conn.execute("UPDATE tasks SET due_date = 'ANYTIME' WHERE due_date IS NULL")
        me_row = conn.execute("SELECT id FROM people WHERE LOWER(name)='me' LIMIT 1").fetchone()
        me_id = me_row["id"] if me_row else None
        if me_id:
            conn.execute(
                "UPDATE tasks SET effort = 'standard' WHERE effort IS NULL AND person_id = ?",
                (me_id,)
            )
        # Clear effort from any tasks not assigned to me
        conn.execute(
            "UPDATE tasks SET effort = NULL WHERE person_id IS NULL OR person_id != ?",
            (me_id,) if me_id else (0,)
        )


def _create_tasks_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id          INTEGER REFERENCES threads(id),
            description        TEXT NOT NULL,
            person_id          INTEGER REFERENCES people(id),
            due_date           TEXT,
            notes              TEXT,
            closed_at          TIMESTAMP,
            effort             TEXT,
            est_hours          REAL,
            sort_order         INTEGER DEFAULT 0,
            is_deadline        INTEGER DEFAULT 0,
            status             TEXT NOT NULL DEFAULT 'open',
            created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            blocked_by_task_id INTEGER REFERENCES tasks(id)
        )
    """)


def _seed_defaults():
    with get_conn() as conn:
        conn.execute("UPDATE people SET emoji = '🐒' WHERE LOWER(name) = 'me'")


def _pick_emoji(conn):
    used = {row[0] for row in conn.execute("SELECT emoji FROM people").fetchall()}
    available = [e for e in EMOJIS if e not in used]
    return random.choice(available if available else EMOJIS)


def _pick_group_emoji(conn):
    used = {row[0] for row in conn.execute("SELECT icon FROM groups WHERE icon != ''").fetchall()}
    available = [e for e in EMOJIS if e not in used]
    return random.choice(available if available else EMOJIS)


init_db()
_seed_defaults()


# ── Jinja2 filters ────────────────────────────────────────────────────────────

def fmt_date(s):
    if not s:
        return ""
    if s == 'ASAP':
        return "ASAP"
    if s == 'ANYTIME':
        return "Anytime"
    try:
        d = date.fromisoformat(s)
        today = date.today()
        if d == today:
            return "Today"
        if d == today + timedelta(days=1):
            return "Tomorrow"
        return d.strftime("%b %-d")
    except Exception:
        return s


def date_cls(s):
    if not s:
        return ""
    if s == 'ASAP':
        return "soon"
    if s == 'ANYTIME':
        return ""
    try:
        d = date.fromisoformat(s)
        today = date.today()
        if d < today:
            return "overdue"
        if d <= today + timedelta(days=2):
            return "soon"
        return "future"
    except Exception:
        return ""


def fmt_ts(s):
    if not s:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(s)
        return dt.strftime("%-m/%-d/%y %-I:%M %p").replace("AM","am").replace("PM","pm")
    except Exception:
        return s


templates.env.filters["fmt_date"] = fmt_date
templates.env.filters["date_cls"] = date_cls
templates.env.filters["fmt_ts"]   = fmt_ts


# ── helpers ───────────────────────────────────────────────────────────────────

def _people_with_counts(conn):
    return conn.execute("""
        SELECT p.*,
               COUNT(CASE WHEN t.status='open' THEN 1 END) AS open_count
        FROM people p
        LEFT JOIN tasks t ON t.person_id = p.id
        GROUP BY p.id
        ORDER BY CASE WHEN LOWER(p.name) = 'me' THEN 0 ELSE 1 END, p.name COLLATE NOCASE
    """).fetchall()


def _threads_with_tasks(conn):
    threads = conn.execute(
        "SELECT * FROM threads WHERE is_active = 1 ORDER BY sort_order ASC, created_at ASC"
    ).fetchall()
    result = []
    for i, thread in enumerate(threads):
        tasks = conn.execute("""
            SELECT t.*, p.name AS person_name, p.emoji AS person_emoji
            FROM tasks t
            LEFT JOIN people p ON t.person_id = p.id
            WHERE t.thread_id = ? AND t.status = 'open'
            ORDER BY t.sort_order ASC, t.created_at DESC
        """, (thread["id"],)).fetchall()

        now_tasks = [t for t in tasks if not t["person_id"]]
        person_order, person_map = [], {}
        for t in tasks:
            if t["person_id"]:
                pid = t["person_id"]
                if pid not in person_map:
                    person_map[pid] = {
                        "label": f"{t['person_emoji']} {t['person_name']}",
                        "tasks": [],
                    }
                    person_order.append(pid)
                person_map[pid]["tasks"].append(t)

        groups = []
        if now_tasks:
            groups.append({"label": "Now", "is_now": True, "tasks": now_tasks})
        for pid in person_order:
            groups.append({"label": person_map[pid]["label"], "is_now": False,
                           "tasks": person_map[pid]["tasks"]})

        open_count = len(tasks)
        total_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE thread_id=?", (thread["id"],)
        ).fetchone()[0]
        closed_tasks = conn.execute("""
            SELECT t.*, p.name AS person_name, p.emoji AS person_emoji
            FROM tasks t
            LEFT JOIN people p ON t.person_id = p.id
            WHERE t.thread_id = ? AND t.status = 'closed'
            ORDER BY t.created_at DESC
        """, (thread["id"],)).fetchall()

        thread_people = conn.execute("""
            SELECT p.*,
                   COUNT(t.id) AS thread_count
            FROM people p
            LEFT JOIN tasks t ON t.person_id = p.id AND t.thread_id = ?
            GROUP BY p.id
            ORDER BY
                CASE WHEN LOWER(p.name) = 'me' THEN 0 ELSE 1 END,
                COUNT(t.id) DESC,
                p.name COLLATE NOCASE
        """, (thread["id"],)).fetchall()

        result.append({
            "thread":       thread,
            "tasks":        tasks,
            "groups":       groups,
            "open_count":   open_count,
            "total_count":  total_count,
            "closed_tasks": closed_tasks,
            "color":        THREAD_COLORS[i % len(THREAD_COLORS)],
            "people":       thread_people,
        })
    return result


def _groups_with_threads(conn):
    groups = conn.execute("SELECT * FROM groups ORDER BY sort_order, created_at").fetchall()
    result = []
    for g in groups:
        thread_ids = [r["thread_id"] for r in
                      conn.execute("""SELECT gt.thread_id FROM group_threads gt
                                      JOIN threads th ON th.id = gt.thread_id
                                      WHERE gt.group_id = ? AND th.is_active = 1""",
                                   (g["id"],)).fetchall()]
        result.append({"group": g, "thread_ids": thread_ids})
    return result


def _due_sidebar(conn, color_map, today):
    me_row = conn.execute(
        "SELECT id FROM people WHERE LOWER(name) = 'me' LIMIT 1"
    ).fetchone()
    me_id = me_row["id"] if me_row else None

    rows = conn.execute("""
        SELECT t.*, p.name AS person_name, p.emoji AS person_emoji,
               th.name AS thread_name
        FROM tasks t
        LEFT JOIN people p   ON t.person_id  = p.id
        LEFT JOIN threads th ON t.thread_id  = th.id
        WHERE t.status = 'open' AND (th.is_active = 1 OR th.id IS NULL)
        ORDER BY
            CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END,
            t.due_date ASC,
            t.created_at ASC
    """).fetchall()

    overdue_tasks, asap_tasks, dated_tasks, anytime_tasks = [], [], [], []
    for row in rows:
        task = dict(row)
        task["thread_color"] = color_map.get(task["thread_id"], "#aaa")
        task["is_me"] = bool(me_id and task["person_id"] == me_id)
        d = task["due_date"]
        if not d or d == 'ANYTIME':
            anytime_tasks.append(task)
        elif d == 'ASAP':
            asap_tasks.append(task)
        else:
            try:
                if date.fromisoformat(d) < today:
                    overdue_tasks.append(task)
                else:
                    dated_tasks.append(task)
            except ValueError:
                anytime_tasks.append(task)

    upper_groups = []

    if overdue_tasks:
        upper_groups.append({
            "label": "Overdue", "cls": "overdue", "is_now": False, "is_anytime": False,
            "person_groups": [], "tasks": overdue_tasks,
        })

    if asap_tasks:
        upper_groups.append({
            "label": "ASAP", "cls": "asap", "is_now": False, "is_anytime": False,
            "person_groups": [], "tasks": asap_tasks,
        })

    dated_map, dated_order = {}, []
    for task in dated_tasks:
        d = date.fromisoformat(task["due_date"])
        if d == today:
            key, label, cls = "__today", "Today", "today"
        elif d == today + timedelta(days=1):
            key, label, cls = "__tomorrow", "Tomorrow", "tomorrow"
        else:
            key, label, cls = d.isoformat(), d.strftime("%a, %b %-d"), "future"
        if key not in dated_map:
            dated_map[key] = {"label": label, "cls": cls, "is_now": False, "is_anytime": False,
                              "person_groups": [], "tasks": []}
            dated_order.append(key)
        dated_map[key]["tasks"].append(task)
    upper_groups.extend(dated_map[k] for k in dated_order)

    anytime_group = None
    if anytime_tasks:
        anytime_group = {
            "label": "Anytime", "cls": "anytime", "is_now": False, "is_anytime": True,
            "person_groups": [], "tasks": anytime_tasks,
        }

    return upper_groups, anytime_group


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, tab: str = "home"):
    today = date.today()
    with get_conn() as conn:
        threads_data = _threads_with_tasks(conn)
        people       = _people_with_counts(conn)
        color_map    = {td["thread"]["id"]: td["color"] for td in threads_data}
        due_upper, due_anytime = _due_sidebar(conn, color_map, today)
        me_row       = conn.execute("SELECT id FROM people WHERE LOWER(name)='me' LIMIT 1").fetchone()
        me_id        = me_row["id"] if me_row else None
        groups_data     = _groups_with_threads(conn)
        inactive_threads = conn.execute(
            "SELECT * FROM threads WHERE is_active = 0 ORDER BY sort_order ASC, created_at ASC"
        ).fetchall()
    return templates.TemplateResponse("index.html", {
        "request":          request,
        "threads_data":     threads_data,
        "people":           people,
        "due_upper":        due_upper,
        "due_anytime":      due_anytime,
        "tab":              tab,
        "today":            today.isoformat(),
        "me_id":            me_id,
        "all_emojis":       EMOJIS,
        "groups_data":      groups_data,
        "inactive_threads": inactive_threads,
    })


# Tasks

@app.post("/tasks/reorder")
async def reorder_tasks(request: Request):
    data = await request.json()
    with get_conn() as conn:
        for i, tid in enumerate(data.get("ids", [])):
            conn.execute("UPDATE tasks SET sort_order=? WHERE id=?", (i, int(tid)))
    return JSONResponse({"ok": True})


@app.post("/tasks")
async def create_task(
    description:  str           = Form(...),
    thread_id:    int           = Form(...),
    person_id:    Optional[int] = Form(None),
    due_date:     str           = Form(""),
    effort:       str           = Form(""),
    is_deadline:  str           = Form("0"),
):
    with get_conn() as conn:
        me_row = conn.execute("SELECT id FROM people WHERE LOWER(name)='me' LIMIT 1").fetchone()
        me_id = me_row["id"] if me_row else None
        is_me = me_id and person_id == me_id
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM tasks WHERE thread_id=?", (thread_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO tasks (thread_id, description, person_id, due_date, effort, sort_order, is_deadline) "
            "VALUES (?,?,?,?,?,?,?)",
            (thread_id, description.strip(), person_id or None, due_date or None,
             effort.strip() or None if is_me else None, max_order + 1,
             1 if is_deadline == "1" else 0),
        )
    return RedirectResponse("/", status_code=303)


@app.post("/tasks/{task_id}/notes")
async def update_task_notes(task_id: int, notes: str = Form("")):
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET notes=? WHERE id=?", (notes, task_id))
    return JSONResponse({"ok": True})


@app.post("/tasks/{task_id}/update")
async def update_task(
    task_id:      int,
    description:  str           = Form(...),
    person_id:    Optional[int] = Form(None),
    due_date:     str           = Form(""),
    effort:       str           = Form(""),
    is_deadline:  str           = Form("0"),
):
    with get_conn() as conn:
        me_row = conn.execute("SELECT id FROM people WHERE LOWER(name)='me' LIMIT 1").fetchone()
        me_id  = me_row["id"] if me_row else None
        is_me  = me_id and person_id == me_id
        conn.execute(
            "UPDATE tasks SET description=?, person_id=?, due_date=?, effort=?, is_deadline=? WHERE id=?",
            (
                description.strip(),
                person_id or None,
                due_date or "ANYTIME",
                effort.strip() or None if is_me else None,
                1 if is_deadline == "1" else 0,
                task_id,
            ),
        )
    return RedirectResponse("/", status_code=303)


@app.post("/tasks/{task_id}/close")
async def close_task(task_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET status='closed', closed_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
    return RedirectResponse("/", status_code=303)


@app.post("/tasks/{task_id}/reopen")
async def reopen_task(task_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET status='open' WHERE id=?", (task_id,))
    return RedirectResponse("/", status_code=303)


# Threads

@app.post("/threads")
async def create_thread(name: str = Form(...)):
    with get_conn() as conn:
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) FROM threads").fetchone()[0]
        conn.execute("INSERT INTO threads (name, sort_order) VALUES (?,?)", (name.strip(), max_order + 1))
    return RedirectResponse("/", status_code=303)


@app.post("/threads/reorder")
async def reorder_threads(request: Request):
    data = await request.json()
    with get_conn() as conn:
        for i, tid in enumerate(data.get("ids", [])):
            conn.execute("UPDATE threads SET sort_order=? WHERE id=?", (i, int(tid)))
    return JSONResponse({"ok": True})


@app.post("/threads/{thread_id}/update")
async def update_thread(thread_id: int, name: str = Form(...)):
    with get_conn() as conn:
        conn.execute("UPDATE threads SET name=? WHERE id=?", (name.strip(), thread_id))
    return RedirectResponse("/?tab=manage", status_code=303)


@app.post("/threads/{thread_id}/delete")
async def delete_thread(thread_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE threads SET is_active = 0 WHERE id=?", (thread_id,))
    return RedirectResponse("/?tab=manage", status_code=303)


@app.post("/threads/{thread_id}/activate")
async def activate_thread(thread_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE threads SET is_active = 1 WHERE id=?", (thread_id,))
    return RedirectResponse("/?tab=manage", status_code=303)


# Groups

@app.post("/groups")
async def create_group(name: str = Form(...)):
    with get_conn() as conn:
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) FROM groups").fetchone()[0]
        icon = _pick_group_emoji(conn)
        conn.execute("INSERT INTO groups (name, sort_order, icon) VALUES (?,?,?)", (name.strip(), max_order + 1, icon))
    return RedirectResponse("/?tab=manage", status_code=303)


@app.post("/groups/{group_id}/update")
async def update_group(group_id: int, name: str = Form(...)):
    with get_conn() as conn:
        conn.execute("UPDATE groups SET name=? WHERE id=?", (name.strip(), group_id))
    return RedirectResponse("/?tab=manage", status_code=303)


@app.post("/groups/{group_id}/delete")
async def delete_group(group_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM group_threads WHERE group_id=?", (group_id,))
        conn.execute("DELETE FROM groups WHERE id=?", (group_id,))
    return RedirectResponse("/?tab=manage", status_code=303)


@app.post("/groups/{group_id}/threads/add")
async def add_thread_to_group(group_id: int, thread_id: int = Form(...)):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO group_threads (group_id, thread_id) VALUES (?,?)",
                     (group_id, thread_id))
    return JSONResponse({"ok": True})


@app.post("/groups/{group_id}/threads/{thread_id}/remove")
async def remove_thread_from_group(group_id: int, thread_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM group_threads WHERE group_id=? AND thread_id=?",
                     (group_id, thread_id))
    return JSONResponse({"ok": True})


# People

@app.post("/people/quick")
async def create_person_quick(name: str = Form(...)):
    with get_conn() as conn:
        emoji = _pick_emoji(conn)
        cur = conn.execute(
            "INSERT INTO people (name, emoji) VALUES (?,?)",
            (name.strip(), emoji),
        )
        person_id = cur.lastrowid
    _seed_defaults()
    return JSONResponse({"id": person_id, "name": name.strip(), "emoji": emoji})


@app.post("/people")
async def create_person(name: str = Form(...)):
    with get_conn() as conn:
        emoji = _pick_emoji(conn)
        conn.execute("INSERT INTO people (name, emoji) VALUES (?,?)", (name.strip(), emoji))
    return RedirectResponse("/?tab=manage", status_code=303)


@app.post("/people/{person_id}/update")
async def update_person(person_id: int, name: str = Form(...), emoji: str = Form(...)):
    with get_conn() as conn:
        conn.execute(
            "UPDATE people SET name=?, emoji=? WHERE id=?",
            (name.strip(), emoji.strip(), person_id),
        )
    return RedirectResponse("/?tab=manage", status_code=303)


@app.post("/people/{person_id}/delete")
async def delete_person(person_id: int):
    with get_conn() as conn:
        person = conn.execute("SELECT name FROM people WHERE id=?", (person_id,)).fetchone()
        if person and person["name"].lower() == "me":
            return RedirectResponse("/?tab=manage", status_code=303)
        open_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE person_id=? AND status='open'", (person_id,)
        ).fetchone()[0]
        if open_count == 0:
            conn.execute("DELETE FROM people WHERE id=?", (person_id,))
    return RedirectResponse("/?tab=manage", status_code=303)


# Export

@app.get("/export/csv")
async def export_csv():
    today = date.today()
    with get_conn() as conn:
        people  = conn.execute("SELECT emoji, name FROM people ORDER BY id").fetchall()
        threads = conn.execute("SELECT name FROM threads ORDER BY sort_order, created_at").fetchall()
        groups  = conn.execute("SELECT g.name, g.icon, GROUP_CONCAT(th.name, '|') AS thread_names "
                               "FROM groups g "
                               "LEFT JOIN group_threads gt ON gt.group_id = g.id "
                               "LEFT JOIN threads th ON th.id = gt.thread_id "
                               "GROUP BY g.id ORDER BY g.sort_order, g.created_at").fetchall()
        tasks   = conn.execute("""
            SELECT th.name AS thread_name, t.description, t.status,
                   p.name AS person_name, p.emoji AS person_emoji,
                   t.due_date, t.effort, t.is_deadline,
                   t.notes, t.closed_at
            FROM tasks t
            LEFT JOIN people p   ON t.person_id  = p.id
            LEFT JOIN threads th ON t.thread_id  = th.id
            ORDER BY th.sort_order, t.sort_order
        """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["## PEOPLE"])
    writer.writerow(["Emoji", "Name"])
    for p in people:
        writer.writerow([p["emoji"], p["name"]])

    writer.writerow([])
    writer.writerow(["## THREADS"])
    writer.writerow(["Name"])
    for t in threads:
        writer.writerow([t["name"]])

    writer.writerow([])
    writer.writerow(["## GROUPS"])
    writer.writerow(["Name", "Icon", "Threads (pipe-separated)"])
    for g in groups:
        writer.writerow([g["name"], g["icon"] or "", g["thread_names"] or ""])

    writer.writerow([])
    writer.writerow(["## TASKS"])
    writer.writerow(["Thread", "Description", "Person Emoji", "Person Name",
                     "Due Date", "Effort", "Is Deadline", "Status", "Closed At", "Notes"])
    for row in tasks:
        writer.writerow([
            row["thread_name"] or "",
            row["description"],
            row["person_emoji"] or "",
            row["person_name"] or "",
            row["due_date"] or "",
            row["effort"] or "",
            "1" if row["is_deadline"] else "0",
            row["status"],
            row["closed_at"] or "",
            row["notes"] or "",
        ])

    filename = f"pingpong_{today.isoformat()}.csv"
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
