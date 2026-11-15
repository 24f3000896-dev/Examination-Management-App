# Examination Management Portal (EMP)

Flask + Jinja2 + Bootstrap 5 + SQLite (plain `sqlite3`, schema created in code by `db.init_db()`).
Core features use no JavaScript (only Bootstrap's navbar toggle and delete-confirm prompts).

## Run locally
```
pip install -r requirements.txt
python app.py              # creates instance/emp.db automatically -> http://127.0.0.1:5000
python seed.py             # OPTIONAL demo data
python smoke_test.py       # OPTIONAL automated check of the core rules
```
Admin (pre-seeded in the DB, no registration): **admin@emp.com / admin123**
Demo data logins (after seed.py): rao@emp.com, asha@emp.com ... / password123 (pending@emp.com is an unapproved examiner)

## Exam phases (admin buttons on the exam page)
Draft -> Slot Creation -> (close = Draft) -> Booking Open -> Closed -> Completed.
Examiner slot creation needs status "Slot Creation" AND today inside the slot-creation dates;
student booking needs "Booking Open" AND today inside the booking dates.

## Files
app.py (factory) | db.py (schema) | helpers.py (rules, decorators) | auth.py | admin.py | examiner.py | student.py | api.py (JSON) | templates/ | static/

## JSON API (login required, role-scoped)
GET /api/exams, /api/slots, /api/bookings, /api/examiners (admin), /api/students (admin)
