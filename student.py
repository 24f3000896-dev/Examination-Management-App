from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, g, Response
from db import q, run, get_db
from helpers import login_required, today, in_window, can_book, BOOKING_SQL, SLOT_SQL

bp = Blueprint("student", __name__, url_prefix="/student")
student_only = login_required("student")


def has_active_booking(uid, exam_id):
    return q("""SELECT 1 FROM bookings b JOIN slots sl ON sl.id=b.slot_id
                WHERE b.student_id=? AND sl.exam_id=? AND b.status IN ('Booked','Completed')""", (uid, exam_id), one=True)


@bp.route("/")
@student_only
def dashboard():
    uid = g.user["id"]
    exams = q("""SELECT e.*, c.code AS course_code FROM exams e JOIN courses c ON c.id=e.course_id
                 WHERE e.status='Booking Open' ORDER BY e.book_end""")
    slots = q(SLOT_SQL + """ WHERE e.status='Booking Open' AND sl.status='Available' AND sl.available>0
              AND sl.exam_id NOT IN (SELECT sl2.exam_id FROM bookings b2 JOIN slots sl2 ON sl2.id=b2.slot_id
                                     WHERE b2.student_id=? AND b2.status IN ('Booked','Completed'))
              ORDER BY sl.slot_date, sl.start_time""", (uid,))
    mine = q(BOOKING_SQL + " WHERE b.student_id=? ORDER BY sl.slot_date, sl.start_time", (uid,))
    upcoming = [b for b in mine if b["status"] == "Booked" and b["slot_date"] >= today()]
    booked = [b for b in mine if b["status"] == "Booked"]
    results = q("""SELECT r.*, e.name AS exam, e.max_marks FROM results r JOIN bookings b ON b.id=r.booking_id
                   JOIN slots sl ON sl.id=b.slot_id JOIN exams e ON e.id=sl.exam_id
                   WHERE b.student_id=? AND e.results_published=1""", (uid,))
    return render_template("student/dashboard.html", exams=exams, slots=slots, upcoming=upcoming,
                           booked=booked, results=results)


@bp.route("/exams")
@student_only
def exams():
    term, etype, course = request.args.get("q", "").strip(), request.args.get("type", ""), request.args.get("course", "")
    sql = """SELECT e.*, c.code AS course_code, c.name AS course_name FROM exams e
             JOIN courses c ON c.id=e.course_id WHERE e.status!='Draft'"""
    args = []
    if term:
        sql += " AND (e.name LIKE ? OR c.name LIKE ? OR c.code LIKE ?)"
        args += [f"%{term}%"] * 3
    if etype:
        sql += " AND e.exam_type=?"
        args.append(etype)
    if course:
        sql += " AND c.id=?"
        args.append(course)
    return render_template("student/exams.html", exams=q(sql + " ORDER BY e.book_start", args),
                           courses=q("SELECT * FROM courses ORDER BY code"),
                           types=["Viva", "Practical", "Project Demo", "Assessment"], term=term, etype=etype, course=course)


@bp.route("/exams/<int:eid>")
@student_only
def exam_detail(eid):
    exam = q("SELECT e.*, c.code AS course_code, c.name AS course_name FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.id=? AND e.status!='Draft'",
             (eid,), one=True) or abort(404)
    rubrics = q("SELECT * FROM rubrics WHERE exam_id=?", (eid,))
    slots = q(SLOT_SQL + " WHERE sl.exam_id=? AND sl.status IN ('Available','Full') ORDER BY sl.slot_date, sl.start_time", (eid,))
    return render_template("student/exam_detail.html", exam=exam, rubrics=rubrics, slots=slots,
                           booked=has_active_booking(g.user["id"], eid), open=can_book(exam))

