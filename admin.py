import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from db import q, run, get_db
from helpers import login_required, valid_date, to_int, to_float, BOOKING_SQL, SLOT_SQL

bp = Blueprint("admin", __name__, url_prefix="/admin")
admin_only = login_required("admin")

EXAM_TYPES = ["Viva", "Practical", "Project Demo", "Assessment"]
EXAM_STATUSES = ["Draft", "Slot Creation", "Booking Open", "Closed", "Completed"]


@bp.route("/")
@admin_only
def dashboard():
    def count(sql):
        return q(sql, one=True)[0]
    stats = [
        ("Courses", count("SELECT COUNT(*) FROM courses"), "admin.courses"),
        ("Examinations", count("SELECT COUNT(*) FROM exams"), "admin.exams"),
        ("Examiners", count("SELECT COUNT(*) FROM users WHERE role='examiner'"), "admin.examiners"),
        ("Students", count("SELECT COUNT(*) FROM users WHERE role='student'"), "admin.students"),
        ("Exam Slots", count("SELECT COUNT(*) FROM slots"), "admin.slots"),
        ("Bookings", count("SELECT COUNT(*) FROM bookings"), "admin.bookings"),
    ]
    pending = q("SELECT * FROM users WHERE role='examiner' AND status='pending'")
    return render_template("admin/dashboard.html", stats=stats, pending=pending)


# ---------------- Courses ----------------
@bp.route("/courses")
@admin_only
def courses():
    return render_template("admin/courses.html", courses=q("SELECT * FROM courses ORDER BY code"))


@bp.route("/courses/new", methods=["GET", "POST"])
@bp.route("/courses/<int:cid>/edit", methods=["GET", "POST"])
@admin_only
def course_form(cid=None):
    course = q("SELECT * FROM courses WHERE id=?", (cid,), one=True) if cid else None
    if cid and not course:
        abort(404)
    if request.method == "POST":
        f = request.form
        code, name = f.get("code", "").strip().upper(), f.get("name", "").strip()
        vals = (code, name, f.get("description", "").strip(), to_int(f.get("credits"), 0), f.get("status", "Active"))
        if not code or not name:
            flash("Course code and name are required.", "danger")
        else:
            try:
                if cid:
                    run("UPDATE courses SET code=?,name=?,description=?,credits=?,status=? WHERE id=?", vals + (cid,))
                else:
                    run("INSERT INTO courses(code,name,description,credits,status) VALUES(?,?,?,?,?)", vals)
                flash("Course saved.", "success")
                return redirect(url_for("admin.courses"))
            except sqlite3.IntegrityError:
                flash("A course with that code already exists.", "danger")
        course = {"id": cid, "code": code, "name": name, "description": f.get("description"),
                  "credits": f.get("credits"), "status": f.get("status")}
    return render_template("admin/course_form.html", course=course)


@bp.route("/courses/<int:cid>/delete", methods=["POST"])
@admin_only
def course_delete(cid):
    try:
        run("DELETE FROM courses WHERE id=?", (cid,))
        flash("Course deleted.", "success")
    except sqlite3.IntegrityError:
        flash("Course has examinations and cannot be deleted. Mark it Inactive instead.", "warning")
    return redirect(url_for("admin.courses"))


# ---------------- Examinations ----------------
@bp.route("/exams")
@admin_only
def exams():
    rows = q("""SELECT e.*, c.code AS course_code, c.name AS course_name FROM exams e
                JOIN courses c ON c.id=e.course_id ORDER BY e.id DESC""")
    return render_template("admin/exams.html", exams=rows)


@bp.route("/exams/new", methods=["GET", "POST"])
@bp.route("/exams/<int:eid>/edit", methods=["GET", "POST"])
@admin_only
def exam_form(eid=None):
    exam = q("SELECT * FROM exams WHERE id=?", (eid,), one=True) if eid else None
    if eid and not exam:
        abort(404)
    if request.method == "POST":
        f = request.form
        dates = [valid_date(f.get(k)) for k in ("slot_start", "slot_end", "book_start", "book_end")]
        duration, max_marks, course_id = to_int(f.get("duration")), to_int(f.get("max_marks")), to_int(f.get("course_id"))
        err = None
        if not f.get("name", "").strip() or not course_id:
            err = "Name and course are required."
        elif f.get("exam_type") not in EXAM_TYPES:
            err = "Invalid examination type."
        elif not duration or duration <= 0 or not max_marks or max_marks <= 0:
            err = "Duration and maximum marks must be positive numbers."
        elif None in dates:
            err = "All four timeline dates are required."
        elif dates[0] > dates[1] or dates[2] > dates[3]:
            err = "End dates cannot be before start dates."
        elif dates[1] > dates[3]:
            err = "Slot creation must end on or before the booking end date."
        if err:
            flash(err, "danger")
            exam = dict(f)
            exam["id"] = eid
        else:
            vals = (course_id, f["name"].strip(), f["exam_type"], duration, max_marks, *dates,
                    f.get("venue", "").strip(), f.get("instructions", "").strip())
            if eid:
                run("""UPDATE exams SET course_id=?,name=?,exam_type=?,duration=?,max_marks=?,slot_start=?,slot_end=?,
                       book_start=?,book_end=?,venue=?,instructions=? WHERE id=?""", vals + (eid,))
            else:
                eid = run("""INSERT INTO exams(course_id,name,exam_type,duration,max_marks,slot_start,slot_end,
                             book_start,book_end,venue,instructions) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", vals)
            flash("Examination saved.", "success")
            return redirect(url_for("admin.exam_detail", eid=eid))
    courses = q("SELECT * FROM courses WHERE status='Active' ORDER BY code")
    return render_template("admin/exam_form.html", exam=exam, courses=courses, types=EXAM_TYPES)


@bp.route("/exams/<int:eid>")
@admin_only
def exam_detail(eid):
    exam = q("SELECT e.*, c.code AS course_code, c.name AS course_name FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.id=?",
             (eid,), one=True)
    if not exam:
        abort(404)
    rubrics = q("SELECT * FROM rubrics WHERE exam_id=?", (eid,))
    assigned = q("SELECT u.* FROM users u JOIN exam_examiners ee ON ee.examiner_id=u.id WHERE ee.exam_id=?", (eid,))
    candidates = q("""SELECT * FROM users WHERE role='examiner' AND status='active'
                      AND id NOT IN (SELECT examiner_id FROM exam_examiners WHERE exam_id=?)""", (eid,))
    slots = q(SLOT_SQL + " WHERE sl.exam_id=? ORDER BY sl.slot_date, sl.start_time", (eid,))
    return render_template("admin/exam_detail.html", exam=exam, rubrics=rubrics, assigned=assigned,
                           candidates=candidates, slots=slots, statuses=EXAM_STATUSES,
                           rubric_total=sum(r["max_marks"] for r in rubrics))


@bp.route("/exams/<int:eid>/delete", methods=["POST"])
@admin_only
def exam_delete(eid):
    try:
        run("DELETE FROM exams WHERE id=?", (eid,))
        flash("Examination deleted.", "success")
    except sqlite3.IntegrityError:
        flash("This examination already has slots/bookings. Set its status to Closed instead.", "warning")
        return redirect(url_for("admin.exam_detail", eid=eid))
    return redirect(url_for("admin.exams"))


@bp.route("/exams/<int:eid>/status", methods=["POST"])
@admin_only
def exam_status(eid):
    """Covers: open/close slot creation, open/close student booking, mark completed."""
    status = request.form.get("status")
    if status not in EXAM_STATUSES:
        abort(400)
    run("UPDATE exams SET status=? WHERE id=?", (status, eid))
    flash(f"Examination status set to '{status}'.", "success")
    return redirect(url_for("admin.exam_detail", eid=eid))


@bp.route("/exams/<int:eid>/publish", methods=["POST"])
@admin_only
def exam_publish(eid):
    run("UPDATE exams SET results_published = 1 - results_published WHERE id=?", (eid,))
    flash("Result publication toggled.", "success")
    return redirect(url_for("admin.exam_detail", eid=eid))


@bp.route("/exams/<int:eid>/examiners", methods=["POST"])
@admin_only
def exam_assign(eid):
    xid = to_int(request.form.get("examiner_id"))
    if q("SELECT 1 FROM users WHERE id=? AND role='examiner' AND status='active'", (xid,), one=True):
        run("INSERT OR IGNORE INTO exam_examiners(exam_id,examiner_id) VALUES(?,?)", (eid, xid))
        flash("Examiner assigned.", "success")
    else:
        flash("Only approved, active examiners can be assigned.", "danger")
    return redirect(url_for("admin.exam_detail", eid=eid))


@bp.route("/exams/<int:eid>/examiners/<int:xid>/remove", methods=["POST"])
@admin_only
def exam_unassign(eid, xid):
    run("DELETE FROM exam_examiners WHERE exam_id=? AND examiner_id=?", (eid, xid))
    flash("Examiner removed from examination.", "success")
    return redirect(url_for("admin.exam_detail", eid=eid))


# ---------------- Rubrics ----------------
def _rubric_vals(f):
    crit, mx, wt = f.get("criterion", "").strip(), to_float(f.get("max_marks")), to_float(f.get("weightage"), None)
    if not crit or not mx or mx <= 0:
        return None
    return crit, mx, (mx if wt is None else wt), f.get("description", "").strip()


@bp.route("/exams/<int:eid>/rubrics", methods=["POST"])
@admin_only
def rubric_add(eid):
    v = _rubric_vals(request.form)
    if not v:
        flash("Criterion name and positive max marks are required.", "danger")
    else:
        run("INSERT INTO rubrics(exam_id,criterion,max_marks,weightage,description) VALUES(?,?,?,?,?)", (eid,) + v)
        flash("Rubric criterion added.", "success")
    return redirect(url_for("admin.exam_detail", eid=eid))


@bp.route("/rubrics/<int:rid>/edit", methods=["GET", "POST"])
@admin_only
def rubric_edit(rid):
    r = q("SELECT * FROM rubrics WHERE id=?", (rid,), one=True) or abort(404)
    if request.method == "POST":
        v = _rubric_vals(request.form)
        if v:
            run("UPDATE rubrics SET criterion=?,max_marks=?,weightage=?,description=? WHERE id=?", v + (rid,))
            flash("Rubric updated.", "success")
            return redirect(url_for("admin.exam_detail", eid=r["exam_id"]))
        flash("Criterion name and positive max marks are required.", "danger")
    return render_template("admin/rubric_form.html", r=r)


@bp.route("/rubrics/<int:rid>/delete", methods=["POST"])
@admin_only
def rubric_delete(rid):
    r = q("SELECT * FROM rubrics WHERE id=?", (rid,), one=True) or abort(404)
    if q("SELECT 1 FROM rubric_scores WHERE rubric_id=? LIMIT 1", (rid,), one=True):
        flash("This criterion has already been used in evaluations and cannot be removed.", "warning")
    else:
        run("DELETE FROM rubrics WHERE id=?", (rid,))
        flash("Rubric criterion removed.", "success")
    return redirect(url_for("admin.exam_detail", eid=r["exam_id"]))


# ---------------- Users ----------------
@bp.route("/examiners")
@admin_only
def examiners():
    rows = q("""SELECT u.*, (SELECT COUNT(*) FROM slots WHERE examiner_id=u.id) AS slot_count
                FROM users u WHERE role='examiner' ORDER BY (status='pending') DESC, name""")
    return render_template("admin/users.html", users=rows, kind="Examiners")


@bp.route("/students")
@admin_only
def students():
    rows = q("""SELECT u.*, (SELECT COUNT(*) FROM bookings WHERE student_id=u.id) AS booking_count
                FROM users u WHERE role='student' ORDER BY name""")
    return render_template("admin/users.html", users=rows, kind="Students")


@bp.route("/users/<int:uid>/status", methods=["POST"])
@admin_only
def user_status(uid):
    status = request.form.get("status")
    u = q("SELECT * FROM users WHERE id=? AND role IN ('examiner','student')", (uid,), one=True) or abort(404)
    if status not in ("active", "inactive"):
        abort(400)
    run("UPDATE users SET status=? WHERE id=?", (status, uid))
    flash(f"{u['name']} is now {status}.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


