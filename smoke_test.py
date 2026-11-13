"""Quick end-to-end check of the core rules.  python smoke_test.py"""
import os, tempfile, re
os.environ["EMP_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from datetime import date, timedelta
from app import app
from db import q

def client(): return app.test_client()
def login(c, e, p): return c.post("/login", data={"email": e, "password": p}, follow_redirects=True)
def ok(cond, msg): print(("PASS " if cond else "FAIL ") + msg); assert cond

t = date.today(); d = lambda n: (t + timedelta(days=n)).isoformat()
adm, ex, s1, s2 = client(), client(), client(), client()
for c, role, n, e in [(ex, "examiner", "Rao", "rao@x.com"), (s1, "student", "Asha", "a@x.com"), (s2, "student", "Ben", "b@x.com")]:
    c.post("/register", data={"role": role, "name": n, "email": e, "password": "secret1"})
ok(b"Awaiting approval" in login(ex, "rao@x.com", "secret1").data, "examiner blocked until approved")
login(adm, "admin@emp.com", "admin123")
ok(b"Pending examiner" in adm.get("/admin/").data, "admin dashboard loads")
adm.post("/admin/users/2/status", data={"status": "active"})
adm.post("/admin/courses/new", data={"code": "cs101", "name": "Intro", "credits": 4, "status": "Active"})
adm.post("/admin/exams/new", data={"course_id": 1, "name": "Final Viva", "exam_type": "Viva", "duration": 15, "max_marks": 50,
         "slot_start": d(0), "slot_end": d(5), "book_start": d(0), "book_end": d(10)})
adm.post("/admin/exams/1/rubrics", data={"criterion": "Concepts", "max_marks": 30})
adm.post("/admin/exams/1/rubrics", data={"criterion": "Comms", "max_marks": 20})
adm.post("/admin/exams/1/examiners", data={"examiner_id": 2})
slot = {"exam_id": 1, "slot_date": d(2), "start_time": "10:00", "end_time": "10:30", "capacity": 1, "location": "Lab"}
r = login(ex, "rao@x.com", "secret1"); ok(b"Examiner Dashboard" in r.data, "approved examiner sees dashboard")
ex.post("/examiner/slots/new", data=slot); ok(q("SELECT COUNT(*) FROM slots", one=True)[0] == 0, "slot creation refused while closed") if False else None
with app.app_context(): ok(q("SELECT COUNT(*) FROM slots", one=True)[0] == 0, "no slot while creation closed")
adm.post("/admin/exams/1/status", data={"status": "Slot Creation"})
ex.post("/examiner/slots/new", data=slot)
with app.app_context(): ok(q("SELECT COUNT(*) FROM slots", one=True)[0] == 1, "slot created in creation period")
ex.post("/examiner/slots/new", data=dict(slot, start_time="10:15", end_time="10:45"))
with app.app_context(): ok(q("SELECT COUNT(*) FROM slots", one=True)[0] == 1, "overlapping slot rejected")
login(s1, "a@x.com", "secret1"); login(s2, "b@x.com", "secret1")
s1.post("/student/book/1")
with app.app_context(): ok(q("SELECT COUNT(*) FROM bookings", one=True)[0] == 0, "booking refused before booking opens")
adm.post("/admin/exams/1/status", data={"status": "Booking Open"})
ex.post("/examiner/slots/1/delete")
with app.app_context(): ok(q("SELECT COUNT(*) FROM slots", one=True)[0] == 1, "examiner cannot remove slot after booking starts")
s1.post("/student/book/1")
with app.app_context():
    sl = q("SELECT * FROM slots WHERE id=1", one=True); ok(sl["status"] == "Full" and sl["available"] == 0, "slot auto-closes at capacity")
s2.post("/student/book/1")
with app.app_context(): ok(q("SELECT COUNT(*) FROM bookings", one=True)[0] == 1, "overbooking prevented")
s1.post("/student/book/1")
with app.app_context(): ok(q("SELECT COUNT(*) FROM bookings", one=True)[0] == 1, "duplicate booking prevented")
ok(s2.get("/examiner/").status_code == 403, "student cannot open examiner pages")
ok(ex.get("/admin/").status_code == 403, "examiner cannot open admin pages")
s1.post("/student/cancel/1")
with app.app_context(): ok(q("SELECT status FROM slots WHERE id=1", one=True)[0] == "Available", "cancel frees the seat")
s2.post("/student/book/1")
ex.post("/examiner/evaluate/2", data={"m_1": 25, "m_2": 15, "remarks": "Good"})
with app.app_context(): ok(q("SELECT total FROM results", one=True)[0] == 40.0, "evaluation total = 40/50")
ok(ex.post("/examiner/evaluate/1", data={"m_1": 1, "m_2": 1}).status_code == 403, "examiner cannot evaluate cancelled/other booking")
ok(b"Good" not in s2.get("/student/results").data, "results hidden until published")
adm.post("/admin/exams/1/publish")
ok(b"40 / 50" in s2.get("/student/results").data, "published result visible to student")
ok(s2.get("/student/results/2/scorecard.csv").status_code == 200, "scorecard downloads")
ok(len(adm.get("/api/bookings").json) == 2, "JSON API works")
for u in ["/admin/courses", "/admin/exams", "/admin/exams/1", "/admin/examiners", "/admin/students", "/admin/slots", "/admin/bookings",
          "/admin/search?q=Asha", "/student/", "/student/exams?q=Final", "/student/exams/1", "/student/bookings", "/student/profile", "/examiner/slots/1"]:
    c = s1 if u.startswith("/student") else (ex if u.startswith("/examiner") else adm)
    ok(c.get(u).status_code == 200, f"GET {u}")
print("ALL GOOD")
