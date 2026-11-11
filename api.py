"""Read-only JSON API (login required, role-scoped)."""
from flask import Blueprint, jsonify, g
from db import q
from helpers import BOOKING_SQL, SLOT_SQL

bp = Blueprint("api", __name__, url_prefix="/api")


def _auth(*roles):
    if not g.user:
        return jsonify(error="login required"), 401
    if roles and g.user["role"] not in roles:
        return jsonify(error="forbidden"), 403
    return None


def rows(r):
    return jsonify([dict(x) for x in r])


@bp.route("/exams")
def exams():
    return _auth() or rows(q("""SELECT e.id, e.name, e.exam_type, e.duration, e.max_marks, e.status, c.code AS course_code
                               FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.status!='Draft' OR ?='admin'""", (g.user["role"],)))


@bp.route("/slots")
def slots():
    err = _auth()
    if err:
        return err
    if g.user["role"] == "examiner":
        return rows(q(SLOT_SQL + " WHERE sl.examiner_id=?", (g.user["id"],)))
    return rows(q(SLOT_SQL + " WHERE sl.status IN ('Available','Full') OR ?='admin'", (g.user["role"],)))


@bp.route("/bookings")
def bookings():
    err = _auth()
    if err:
        return err
    role, uid = g.user["role"], g.user["id"]
    if role == "admin":
        return rows(q(BOOKING_SQL))
    col = "b.student_id" if role == "student" else "sl.examiner_id"
    return rows(q(BOOKING_SQL + f" WHERE {col}=?", (uid,)))


@bp.route("/examiners")
def examiners():
    return _auth("admin") or rows(q("SELECT id,name,email,department,status FROM users WHERE role='examiner'"))


@bp.route("/students")
def students():
    return _auth("admin") or rows(q("SELECT id,name,email,roll_no,department,status FROM users WHERE role='student'"))
