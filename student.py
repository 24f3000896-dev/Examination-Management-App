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


@bp.route("/book/<int:sid>", methods=["POST"])
@student_only
def book(sid):
    slot = q(SLOT_SQL + " WHERE sl.id=?", (sid,), one=True) or abort(404)
    exam = q("SELECT * FROM exams WHERE id=?", (slot["exam_id"],), one=True)
    uid = g.user["id"]
    if not can_book(exam):
        flash("Booking is not open for this examination.", "danger")
    elif has_active_booking(uid, exam["id"]):
        flash("You already have a booking for this examination.", "warning")
    else:
        db = get_db()
        # Atomic guard: succeeds only while seats remain -> no overbooking
        cur = db.execute("UPDATE slots SET available=available-1 WHERE id=? AND available>0 AND status='Available'", (sid,))
        if cur.rowcount == 0:
            db.rollback()
            flash("Sorry, that slot is full or unavailable.", "danger")
        else:
            db.execute("INSERT INTO bookings(student_id,slot_id,booking_date) VALUES(?,?,?)",
                       (uid, sid, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.execute("UPDATE slots SET status='Full' WHERE id=? AND available=0", (sid,))   # auto-close at capacity
            db.commit()
            flash("Slot booked successfully!", "success")
    return redirect(url_for("student.bookings"))


@bp.route("/cancel/<int:bid>", methods=["POST"])
@student_only
def cancel(bid):
    b = q(BOOKING_SQL + " WHERE b.id=? AND b.student_id=?", (bid, g.user["id"]), one=True) or abort(404)
    exam = q("SELECT * FROM exams WHERE id=?", (b["exam_id"],), one=True)
    if b["status"] != "Booked":
        flash("Only active bookings can be cancelled.", "warning")
    elif not (exam["status"] == "Booking Open" and in_window(exam["book_start"], exam["book_end"])):
        flash("The booking deadline has passed; cancellation is no longer possible.", "danger")
    else:
        db = get_db()
        db.execute("UPDATE bookings SET status='Cancelled', cancelled_at=? WHERE id=?", (datetime.now().strftime("%Y-%m-%d %H:%M"), bid))
        db.execute("UPDATE slots SET available=available+1, status='Available' WHERE id=? AND status IN ('Full','Available')", (b["slot_id"],))
        db.commit()
        flash("Booking cancelled.", "success")
    return redirect(url_for("student.bookings"))


@bp.route("/bookings")
@student_only
def bookings():
    rows = q(BOOKING_SQL + " WHERE b.student_id=? ORDER BY b.id DESC", (g.user["id"],))
    return render_template("student/bookings.html", bookings=rows, today=today())


def _results(uid, bid=None):
    sql = """SELECT b.id AS booking_id, e.id AS exam_id, e.name AS exam, e.max_marks, e.exam_type, c.code AS course_code,
             sl.slot_date, x.name AS examiner, r.total, r.remarks
             FROM results r JOIN bookings b ON b.id=r.booking_id JOIN slots sl ON sl.id=b.slot_id
             JOIN exams e ON e.id=sl.exam_id JOIN courses c ON c.id=e.course_id JOIN users x ON x.id=sl.examiner_id
             WHERE b.student_id=? AND e.results_published=1"""
    args = [uid]
    if bid:
        sql += " AND b.id=?"
        args.append(bid)
    return q(sql, args)


@bp.route("/results")
@student_only
def results():
    rows = _results(g.user["id"])
    detail = {r["booking_id"]: q("""SELECT ru.criterion, ru.max_marks, rs.marks FROM rubric_scores rs
                                    JOIN rubrics ru ON ru.id=rs.rubric_id WHERE rs.booking_id=?""", (r["booking_id"],)) for r in rows}
    return render_template("student/results.html", rows=rows, detail=detail)


@bp.route("/results/<int:bid>/scorecard.csv")
@student_only
def scorecard(bid):
    r = (_results(g.user["id"], bid) or abort(404))[0]
    lines = ["Student,Roll No,Course,Examination,Type,Examiner,Date,Total,Max Marks,Remarks",
             ",".join('"%s"' % str(v).replace('"', "'") for v in (g.user["name"], g.user["roll_no"] or "", r["course_code"],
                      r["exam"], r["exam_type"], r["examiner"], r["slot_date"], r["total"], r["max_marks"], r["remarks"] or ""))]
    return Response("\n".join(lines), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=scorecard_{bid}.csv"})


@bp.route("/profile", methods=["GET", "POST"])
@student_only
def profile():
    if request.method == "POST":
        f = request.form
        if not f.get("name", "").strip():
            flash("Name is required.", "danger")
        else:
            run("UPDATE users SET name=?, phone=?, department=?, roll_no=? WHERE id=?",
                (f["name"].strip(), f.get("phone", "").strip(), f.get("department", "").strip(), f.get("roll_no", "").strip(), g.user["id"]))
            flash("Profile updated.", "success")
            return redirect(url_for("student.profile"))
    return render_template("student/profile.html")
