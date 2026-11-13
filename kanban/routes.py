"""Page route and JSON API for cards."""
from datetime import date

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from .db import COLUMNS, PRIORITIES, get_db

bp = Blueprint("kanban", __name__)

EDITABLE = ("title", "description", "priority", "assignee", "points", "due_date")


def card_to_dict(row):
    return dict(row)


def get_card_or_404(card_id):
    row = get_db().execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    if row is None:
        abort(404, description="Card not found")
    return row


def validate(data, partial=False):
    """Return a cleaned dict of fields, or raise a 400 with a clear message."""
    clean = {}
    if not partial or "title" in data:
        title = str(data.get("title", "")).strip()
        if not title:
            abort(400, description="Title is required")
        if len(title) > 120:
            abort(400, description="Title must be 120 characters or fewer")
        clean["title"] = title
    if "description" in data:
        clean["description"] = str(data["description"] or "").strip()
    if "assignee" in data:
        clean["assignee"] = str(data["assignee"] or "").strip()
    if "priority" in data:
        if data["priority"] not in PRIORITIES:
            abort(400, description=f"Priority must be one of {PRIORITIES}")
        clean["priority"] = data["priority"]
    if "points" in data:
        pts = data["points"]
        if pts in (None, ""):
            clean["points"] = None
        else:
            try:
                pts = int(pts)
            except (TypeError, ValueError):
                abort(400, description="Story points must be a whole number")
            if pts < 0:
                abort(400, description="Story points cannot be negative")
            clean["points"] = pts
    if "due_date" in data:
        due = data["due_date"] or None
        if due:
            try:
                date.fromisoformat(due)
            except ValueError:
                abort(400, description="Due date must be YYYY-MM-DD")
        clean["due_date"] = due
    if "status" in data:
        if data["status"] not in COLUMNS:
            abort(400, description=f"Status must be one of {COLUMNS}")
        clean["status"] = data["status"]
    return clean


def check_wip(status, moving_card_id=None):
    """Enforce the work-in-progress limit on the In Progress column."""
    if status != "in_progress":
        return
    limit = current_app.config["WIP_LIMIT"]
    count = get_db().execute(
        "SELECT COUNT(*) FROM cards WHERE status = 'in_progress' AND id != ?",
        (moving_card_id or -1,),
    ).fetchone()[0]
    if count >= limit:
        abort(409, description=f"WIP limit reached: only {limit} cards allowed in progress")


@bp.errorhandler(400)
@bp.errorhandler(404)
@bp.errorhandler(409)
def json_error(err):
    return jsonify(error=err.description), err.code


@bp.get("/")
def index():
    return render_template("index.html", wip_limit=current_app.config["WIP_LIMIT"])


@bp.get("/api/cards")
def list_cards():
    rows = get_db().execute("SELECT * FROM cards ORDER BY status, position, id").fetchall()
    return jsonify([card_to_dict(r) for r in rows])


@bp.post("/api/cards")
def create_card():
    data = validate(request.get_json(silent=True) or {})
    status = data.pop("status", "backlog")
    check_wip(status)
    db = get_db()
    position = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM cards WHERE status = ?", (status,)
    ).fetchone()[0]
    fields = {"status": status, "position": position, **data}
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cur = db.execute(f"INSERT INTO cards ({cols}) VALUES ({marks})", tuple(fields.values()))
    db.commit()
    return jsonify(card_to_dict(get_card_or_404(cur.lastrowid))), 201


@bp.patch("/api/cards/<int:card_id>")
def update_card(card_id):
    get_card_or_404(card_id)
    data = validate(request.get_json(silent=True) or {}, partial=True)
    data = {k: v for k, v in data.items() if k in EDITABLE}
    if not data:
        abort(400, description="No editable fields supplied")
    sets = ", ".join(f"{k} = ?" for k in data)
    db = get_db()
    db.execute(
        f"UPDATE cards SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (*data.values(), card_id),
    )
    db.commit()
    return jsonify(card_to_dict(get_card_or_404(card_id)))


@bp.post("/api/cards/<int:card_id>/move")
def move_card(card_id):
    """Move a card to a column and position, re-numbering the cards around it."""
    card = get_card_or_404(card_id)
    body = request.get_json(silent=True) or {}
    status = body.get("status", card["status"])
    if status not in COLUMNS:
        abort(400, description=f"Status must be one of {COLUMNS}")
    if status != card["status"]:
        check_wip(status, card_id)

    db = get_db()
    ids = [
        r["id"]
        for r in db.execute(
            "SELECT id FROM cards WHERE status = ? AND id != ? ORDER BY position, id",
            (status, card_id),
        )
    ]
    try:
        position = int(body.get("position", len(ids)))
    except (TypeError, ValueError):
        abort(400, description="Position must be a whole number")
    position = max(0, min(position, len(ids)))
    ids.insert(position, card_id)

    db.execute(
        "UPDATE cards SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, card_id),
    )
    db.executemany("UPDATE cards SET position = ? WHERE id = ?", [(i, cid) for i, cid in enumerate(ids)])
    db.commit()
    return jsonify(card_to_dict(get_card_or_404(card_id)))


@bp.delete("/api/cards/<int:card_id>")
def delete_card(card_id):
    get_card_or_404(card_id)
    db = get_db()
    db.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    db.commit()
    return "", 204


@bp.get("/api/stats")
def stats():
    """Simple sprint metrics: card counts and story points per column."""
    rows = get_db().execute(
        "SELECT status, COUNT(*) AS cards, COALESCE(SUM(points), 0) AS points "
        "FROM cards GROUP BY status"
    ).fetchall()
    by_status = {c: {"cards": 0, "points": 0} for c in COLUMNS}
    for r in rows:
        by_status[r["status"]] = {"cards": r["cards"], "points": r["points"]}
    total_points = sum(v["points"] for v in by_status.values())
    done_points = by_status["done"]["points"]
    return jsonify(
        columns=by_status,
        total_points=total_points,
        done_points=done_points,
        percent_complete=round(100 * done_points / total_points) if total_points else 0,
    )
