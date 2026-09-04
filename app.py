from flask import Flask, render_template, session, redirect, url_for
from dotenv import load_dotenv
import os

load_dotenv()

from routes.auth      import auth_bp
from routes.cases     import cases_bp
from routes.ai_routes import ai_bp
from routes.documents import docs_bp
from routes.deadlines import deadlines_bp
from models.database  import init_db


def create_app():
    app = Flask(__name__)

    # ── SECRET KEY ──────────────────────────────────────
    app.secret_key = os.getenv("SECRET_KEY", "legalmind-secret-key-2024")

    # ── CONFIG ──────────────────────────────────────────
    app.config["UPLOAD_FOLDER"]      = os.getenv("UPLOAD_FOLDER", "uploads")
    app.config["GENERATED_FOLDER"]   = os.getenv("GENERATED_FOLDER", "generated")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    # ── ENSURE FOLDERS EXIST ────────────────────────────
    os.makedirs(app.config["UPLOAD_FOLDER"],    exist_ok=True)
    os.makedirs(app.config["GENERATED_FOLDER"], exist_ok=True)
    os.makedirs("vector_store/faiss_index",     exist_ok=True)
    os.makedirs("data",                         exist_ok=True)

    # ── REGISTER BLUEPRINTS ─────────────────────────────
    app.register_blueprint(auth_bp,       url_prefix="/auth")
    app.register_blueprint(cases_bp,      url_prefix="/cases")
    app.register_blueprint(ai_bp,         url_prefix="/ai")
    app.register_blueprint(docs_bp,       url_prefix="/documents")
    app.register_blueprint(deadlines_bp,  url_prefix="/deadlines")

    # ── ROOT ROUTE ──────────────────────────────────────
    @app.route("/")
    def index():
        if "lawyer_id" in session:
            return redirect(url_for("cases.dashboard"))
        return redirect(url_for("auth.login"))

    # ── ERROR HANDLERS ──────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return render_template("login.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("login.html"), 500

    # ── INIT DATABASE ───────────────────────────────────
    with app.app_context():
        init_db()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        debug=os.getenv("FLASK_DEBUG", "True") == "True",
        host="0.0.0.0",
        port=5000
    )