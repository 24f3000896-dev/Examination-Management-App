import os
from flask import Flask, g, session, render_template, redirect, url_for
from db import close_db, init_db, q


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    os.makedirs(app.instance_path, exist_ok=True)
    app.config["DATABASE"] = os.environ.get("EMP_DB", os.path.join(app.instance_path, "emp.db"))
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()

    from auth import bp as auth_bp
    from admin import bp as admin_bp
    from examiner import bp as examiner_bp
    from student import bp as student_bp
    from api import bp as api_bp
    for b in (auth_bp, admin_bp, examiner_bp, student_bp, api_bp):
        app.register_blueprint(b)

    @app.before_request
    def load_user():
        uid = session.get("uid")
        g.user = q("SELECT * FROM users WHERE id=?", (uid,), one=True) if uid else None
        if g.user and g.user["status"] == "inactive":
            session.clear()
            g.user = None

    @app.route("/")
    def index():
        if g.user:
            return redirect(url_for(g.user["role"] + ".dashboard"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, msg="You are not allowed to view this page."), 403

    @app.errorhandler(404)
    def missing(e):
        return render_template("error.html", code=404, msg="Page not found."), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
