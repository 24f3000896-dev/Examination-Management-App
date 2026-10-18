"""SQLite access + programmatic schema creation (no manual DB creation needed)."""
import sqlite3
from flask import g, current_app
from werkzeug.security import generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','examiner','student')),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','pending','inactive')),
  phone TEXT, department TEXT, roll_no TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS courses(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  credits INTEGER DEFAULT 4,
  status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Inactive'))
);
CREATE TABLE IF NOT EXISTS exams(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  course_id INTEGER NOT NULL REFERENCES courses(id),
  name TEXT NOT NULL,
  exam_type TEXT NOT NULL CHECK(exam_type IN ('Viva','Practical','Project Demo','Assessment')),
  duration INTEGER NOT NULL CHECK(duration > 0),
  max_marks INTEGER NOT NULL CHECK(max_marks > 0),
  slot_start TEXT, slot_end TEXT, book_start TEXT, book_end TEXT,
  status TEXT NOT NULL DEFAULT 'Draft'
    CHECK(status IN ('Draft','Slot Creation','Booking Open','Closed','Completed')),
  venue TEXT, instructions TEXT,
  results_published INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS exam_examiners(
  exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  examiner_id INTEGER NOT NULL REFERENCES users(id),
  PRIMARY KEY(exam_id, examiner_id)
);
CREATE TABLE IF NOT EXISTS rubrics(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  criterion TEXT NOT NULL,
  max_marks REAL NOT NULL CHECK(max_marks > 0),
  weightage REAL NOT NULL DEFAULT 0,
  description TEXT
);
CREATE TABLE IF NOT EXISTS slots(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exam_id INTEGER NOT NULL REFERENCES exams(id),
  examiner_id INTEGER NOT NULL REFERENCES users(id),
  slot_date TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
  capacity INTEGER NOT NULL CHECK(capacity > 0),
  available INTEGER NOT NULL CHECK(available >= 0),
  status TEXT NOT NULL DEFAULT 'Available'
    CHECK(status IN ('Available','Full','Cancelled','Completed')),
  location TEXT
);
CREATE TABLE IF NOT EXISTS bookings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES users(id),
  slot_id INTEGER NOT NULL REFERENCES slots(id),
  booking_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'Booked' CHECK(status IN ('Booked','Cancelled','Completed')),
  cancelled_at TEXT
);
CREATE TABLE IF NOT EXISTS results(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  booking_id INTEGER NOT NULL UNIQUE REFERENCES bookings(id),
  total REAL NOT NULL,
  remarks TEXT,
  evaluated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rubric_scores(
  booking_id INTEGER NOT NULL REFERENCES bookings(id),
  rubric_id INTEGER NOT NULL REFERENCES rubrics(id) ON DELETE CASCADE,
  marks REAL NOT NULL,
  PRIMARY KEY(booking_id, rubric_id)
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def q(sql, args=(), one=False):
    rows = get_db().execute(sql, args).fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def run(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    # Admin is a pre-existing superuser (no admin registration in the UI)
    if not q("SELECT 1 FROM users WHERE role='admin'"):
        db.execute(
            "INSERT INTO users(name,email,password,role,status) VALUES(?,?,?,?,?)",
            ("Administrator", "admin@emp.com", generate_password_hash("admin123"), "admin", "active"),
        )
    db.commit()
