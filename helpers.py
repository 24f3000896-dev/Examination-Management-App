from datetime import date
from functools import wraps
from flask import g, redirect, url_for, abort, render_template

BOOKING_SQL = """
SELECT b.id, b.status, b.booking_date, b.student_id, s.name AS student, s.email AS student_email,
       s.roll_no, e.id AS exam_id, e.name AS exam, e.status AS exam_status, e.max_marks,
       sl.id AS slot_id, sl.slot_date, sl.start_time, sl.end_time, sl.location,
       sl.examiner_id, x.name AS examiner
FROM bookings b
JOIN users s ON s.id = b.student_id
JOIN slots sl ON sl.id = b.slot_id
JOIN exams e ON e.id = sl.exam_id
JOIN users x ON x.id = sl.examiner_id
"""

SLOT_SQL = """
SELECT sl.*, e.name AS exam, e.status AS exam_status, x.name AS examiner
FROM slots sl
JOIN exams e ON e.id = sl.exam_id
JOIN users x ON x.id = sl.examiner_id
"""


def today():
    return date.today().isoformat()


def valid_date(s):
    try:
        date.fromisoformat(s)
        return s
    except (TypeError, ValueError):
        return None


def to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def to_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def in_window(start, end):
    t = today()
    return (not start or start <= t) and (not end or t <= end)


def can_create_slots(e):
    """Examiners may create slots only while Admin has opened slot creation AND today is in the window."""
    return e["status"] == "Slot Creation" and in_window(e["slot_start"], e["slot_end"])


def can_book(e):
    return e["status"] == "Booking Open" and in_window(e["book_start"], e["book_end"])


def slots_locked(e):
    """Slots can be updated/removed only before booking starts."""
    return e["status"] in ("Booking Open", "Closed", "Completed")


def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **k):
            if not g.user:
                return redirect(url_for("auth.login"))
            if role and g.user["role"] != role:
                abort(403)
            if role == "examiner" and g.user["status"] != "active":
                return render_template("pending.html")
            return f(*a, **k)
        return wrapper
    return deco
