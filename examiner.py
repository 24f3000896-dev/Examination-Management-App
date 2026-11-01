import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, g
from db import q, run, get_db
from helpers import (login_required, valid_date, to_int, to_float, today, can_create_slots, slots_locked,
                     BOOKING_SQL, SLOT_SQL)

bp = Blueprint("examiner", __name__, url_prefix="/examiner")
examiner_only = login_required("examiner")


def assigned_exams():
    return q("""SELECT e.*, c.code AS course_code, c.name AS course_name FROM exams e
                JOIN courses c ON c.id=e.course_id
                JOIN exam_examiners ee ON ee.exam_id=e.id WHERE ee.examiner_id=? ORDER BY e.id DESC""", (g.user["id"],))


@bp.route("/")
@examiner_only
def dashboard():
    uid = g.user["id"]
    exams = assigned_exams()
    slots = q("""SELECT sl.*, e.name AS exam, e.status AS exam_status,
                 (SELECT COUNT(*) FROM bookings b WHERE b.slot_id=sl.id AND b.status!='Cancelled') AS booked
                 FROM slots sl JOIN exams e ON e.id=sl.exam_id WHERE sl.examiner_id=?
                 ORDER BY sl.slot_date, sl.start_time""", (uid,))
    booked = sum(s["booked"] for s in slots)
    pending = q(BOOKING_SQL + """ WHERE sl.examiner_id=? AND b.status='Booked'
                AND NOT EXISTS (SELECT 1 FROM results r WHERE r.booking_id=b.id) ORDER BY sl.slot_date""", (uid,))
    return render_template("examiner/dashboard.html", exams=exams, slots=slots, booked=booked,
                           pending=pending, can_create=can_create_slots, locked=slots_locked)

