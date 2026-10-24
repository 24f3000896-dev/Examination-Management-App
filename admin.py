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


