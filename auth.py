import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from db import q, run

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = q("SELECT * FROM users WHERE email=?", (email,), one=True)
        if not user or not check_password_hash(user["password"], request.form.get("password", "")):
            flash("Invalid email or password.", "danger")
        elif user["status"] == "inactive":
            flash("Your account has been deactivated. Contact the Admin.", "danger")
        else:
            session.clear()
            session["uid"] = user["id"]
            return redirect(url_for(user["role"] + ".dashboard"))
    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        role = f.get("role")
        name, email, pw = f.get("name", "").strip(), f.get("email", "").strip().lower(), f.get("password", "")
        if role not in ("student", "examiner"):       # Admin cannot be registered
            flash("Invalid role.", "danger")
        elif not name or "@" not in email:
            flash("Enter a valid name and email.", "danger")
        elif len(pw) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            status = "pending" if role == "examiner" else "active"   # examiners need Admin approval
            try:
                run("INSERT INTO users(name,email,password,role,status,phone,department,roll_no) VALUES(?,?,?,?,?,?,?,?)",
                    (name, email, generate_password_hash(pw), role, status,
                     f.get("phone", "").strip(), f.get("department", "").strip(), f.get("roll_no", "").strip()))
                flash("Registered! " + ("Wait for Admin approval before accessing the dashboard."
                                         if role == "examiner" else "You can log in now."), "success")
                return redirect(url_for("auth.login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "danger")
    return render_template("register.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
