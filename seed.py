"""Optional demo data:  python seed.py   (admin@emp.com / admin123 already exists after first run)"""
from datetime import date, timedelta
from werkzeug.security import generate_password_hash
from app import app
from db import run, q

with app.app_context():
    if q("SELECT 1 FROM courses LIMIT 1"):
        raise SystemExit("Data already present - delete instance/emp.db to re-seed.")
    pw = generate_password_hash("password123")
    for n, e, d in [("Dr. Rao", "rao@emp.com", "Computer Science"), ("Dr. Iyer", "iyer@emp.com", "Mathematics")]:
        run("INSERT INTO users(name,email,password,role,status,department) VALUES(?,?,?,?,?,?)", (n, e, pw, "examiner", "active", d))
    run("INSERT INTO users(name,email,password,role,status,department) VALUES(?,?,?,?,?,?)",
        ("Dr. Pending", "pending@emp.com", pw, "examiner", "pending", "Physics"))
    for n, e, r in [("Asha", "asha@emp.com", "S001"), ("Ben", "ben@emp.com", "S002"), ("Chitra", "chitra@emp.com", "S003")]:
        run("INSERT INTO users(name,email,password,role,roll_no) VALUES(?,?,?,?,?)", (n, e, pw, "student", r))
    cid = run("INSERT INTO courses(code,name,description,credits) VALUES('CS101','Intro to Programming','Basics of Python',4)")
    t = date.today()
    eid = run("""INSERT INTO exams(course_id,name,exam_type,duration,max_marks,slot_start,slot_end,book_start,book_end,status,venue)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (cid, "CS101 Final Viva", "Viva", 15, 50, t.isoformat(),
             (t + timedelta(days=10)).isoformat(), t.isoformat(), (t + timedelta(days=20)).isoformat(), "Slot Creation", "Lab 2"))
    for c, m in [("Concept clarity", 20), ("Code walkthrough", 20), ("Communication", 10)]:
        run("INSERT INTO rubrics(exam_id,criterion,max_marks,weightage) VALUES(?,?,?,?)", (eid, c, m, m))
    run("INSERT INTO exam_examiners VALUES(?,2)", (eid,))
    print("Seeded. Logins -> admin@emp.com/admin123 ; rao@emp.com, asha@emp.com ... /password123")
