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


def _slot_error(f, exam, sid=None):
    d, st, en, cap = valid_date(f.get("slot_date")), f.get("start_time"), f.get("end_time"), to_int(f.get("capacity"))
    if not d or not st or not en:
        return "Date, start time and end time are required."
    if d < today():
        return "Slot date cannot be in the past."
    if st >= en:
        return "End time must be after start time."
    if not cap or cap < 1:
        return "Capacity must be at least 1."
    if q("""SELECT 1 FROM slots WHERE examiner_id=? AND slot_date=? AND status!='Cancelled' AND id!=?
            AND start_time < ? AND end_time > ?""", (g.user["id"], d, sid or -1, en, st), one=True):
        return "You already have an overlapping slot at that time."
    return None


@bp.route("/slots/new", methods=["GET", "POST"])
@examiner_only
def slot_new():
    options = [e for e in assigned_exams() if can_create_slots(e)]
    if request.method == "POST":
        f = request.form
        exam = next((e for e in options if e["id"] == to_int(f.get("exam_id"))), None)
        if not exam:
            flash("Slot creation is not open for that examination (or it is not assigned to you).", "danger")
        else:
            err = _slot_error(f, exam)
            if err:
                flash(err, "danger")
            else:
                cap = to_int(f["capacity"])
                run("""INSERT INTO slots(exam_id,examiner_id,slot_date,start_time,end_time,capacity,available,location)
                       VALUES(?,?,?,?,?,?,?,?)""", (exam["id"], g.user["id"], f["slot_date"], f["start_time"],
                                                  f["end_time"], cap, cap, f.get("location", "").strip() or exam["venue"]))
                flash("Slot created.", "success")
                return redirect(url_for("examiner.dashboard"))
    return render_template("examiner/slot_form.html", slot=None, exams=options)


def _own_slot(sid):
    return q(SLOT_SQL + " WHERE sl.id=? AND sl.examiner_id=?", (sid, g.user["id"]), one=True) or abort(404)


@bp.route("/slots/<int:sid>/edit", methods=["GET", "POST"])
@examiner_only
def slot_edit(sid):
    slot = _own_slot(sid)
    exam = q("SELECT * FROM exams WHERE id=?", (slot["exam_id"],), one=True)
    if slots_locked(exam):
        flash("Booking has started for this examination, so the slot can no longer be changed.", "warning")
        return redirect(url_for("examiner.dashboard"))
    if request.method == "POST":
        f = request.form
        err = _slot_error(f, exam, sid)
        booked = q("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND status='Booked'", (sid,), one=True)[0]
        cap = to_int(f.get("capacity"), 0)
        if not err and cap < booked:
            err = f"Capacity cannot be below the {booked} students already booked."
        if err:
            flash(err, "danger")
        else:
            avail = cap - booked
            run("""UPDATE slots SET slot_date=?,start_time=?,end_time=?,capacity=?,available=?,location=?,
                   status=? WHERE id=?""", (f["slot_date"], f["start_time"], f["end_time"], cap, avail,
                                           f.get("location", "").strip(), "Full" if avail == 0 else "Available", sid))
            flash("Slot updated.", "success")
            return redirect(url_for("examiner.dashboard"))
    return render_template("examiner/slot_form.html", slot=slot, exams=[])


@bp.route("/slots/<int:sid>/delete", methods=["POST"])
@examiner_only
def slot_delete(sid):
    slot = _own_slot(sid)
    exam = q("SELECT * FROM exams WHERE id=?", (slot["exam_id"],), one=True)
    if slots_locked(exam):
        flash("Booking has started; the slot cannot be removed now. Ask the Admin.", "warning")
    else:
        try:
            run("DELETE FROM slots WHERE id=?", (sid,))
        except sqlite3.IntegrityError:         # has booking history -> keep the record, mark cancelled
            run("UPDATE slots SET status='Cancelled', available=0 WHERE id=?", (sid,))
        flash("Slot removed.", "success")
    return redirect(url_for("examiner.dashboard"))


@bp.route("/slots/<int:sid>")
@examiner_only
def slot_bookings(sid):
    slot = _own_slot(sid)
    rows = q("""SELECT b.id, b.status, b.booking_date, s.name AS student, s.email, s.roll_no, r.total, r.remarks
                FROM bookings b JOIN users s ON s.id=b.student_id LEFT JOIN results r ON r.booking_id=b.id
                WHERE b.slot_id=? ORDER BY b.status, s.name""", (sid,))
    return render_template("examiner/slot_bookings.html", slot=slot, rows=rows)


@bp.route("/evaluate/<int:bid>", methods=["GET", "POST"])
@examiner_only
def evaluate(bid):
    # Only bookings that belong to THIS examiner's slots can be evaluated
    b = q(BOOKING_SQL + " WHERE b.id=? AND sl.examiner_id=?", (bid, g.user["id"]), one=True)
    if not b or b["status"] == "Cancelled":
        abort(403)
    rubrics = q("SELECT * FROM rubrics WHERE exam_id=? ORDER BY id", (b["exam_id"],))
    if not rubrics:
        flash("No rubric has been defined for this examination yet. Ask the Admin.", "warning")
        return redirect(url_for("examiner.slot_bookings", sid=b["slot_id"]))
    scores = {r["rubric_id"]: r["marks"] for r in q("SELECT * FROM rubric_scores WHERE booking_id=?", (bid,))}
    result = q("SELECT * FROM results WHERE booking_id=?", (bid,), one=True)
    if request.method == "POST":
        got, err = {}, None
        for r in rubrics:
            m = to_float(request.form.get(f"m_{r['id']}"))
            if m is None or m < 0 or m > r["max_marks"]:
                err = f"Marks for '{r['criterion']}' must be between 0 and {r['max_marks']:g}."
                break
            got[r["id"]] = m
        if err:
            flash(err, "danger")
            scores = {k: request.form.get(f"m_{k}") for k in [r["id"] for r in rubrics]}
        else:
            wsum = sum(r["weightage"] for r in rubrics)
            if wsum > 0:
                frac = sum(got[r["id"]] / r["max_marks"] * r["weightage"] for r in rubrics) / wsum
            else:
                frac = sum(got.values()) / sum(r["max_marks"] for r in rubrics)
            total = round(frac * b["max_marks"], 2)
            db = get_db()
            for rid, m in got.items():
                db.execute("""INSERT INTO rubric_scores(booking_id,rubric_id,marks) VALUES(?,?,?)
                              ON CONFLICT(booking_id,rubric_id) DO UPDATE SET marks=excluded.marks""", (bid, rid, m))
            db.execute("""INSERT INTO results(booking_id,total,remarks) VALUES(?,?,?)
                          ON CONFLICT(booking_id) DO UPDATE SET total=excluded.total, remarks=excluded.remarks,
                          evaluated_at=CURRENT_TIMESTAMP""", (bid, total, request.form.get("remarks", "").strip()))
            db.execute("UPDATE bookings SET status='Completed' WHERE id=?", (bid,))
            db.execute("""UPDATE slots SET status='Completed' WHERE id=? AND NOT EXISTS
                          (SELECT 1 FROM bookings WHERE slot_id=? AND status='Booked')""", (b["slot_id"], b["slot_id"]))
            db.commit()
            flash(f"Evaluation saved. Total: {total:g} / {b['max_marks']}.", "success")
            return redirect(url_for("examiner.slot_bookings", sid=b["slot_id"]))
    return render_template("examiner/evaluate.html", b=b, rubrics=rubrics, scores=scores, result=result)
