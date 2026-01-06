import os
import re
import pandas as pd
import numpy as np
from flask import (
    Flask, render_template, redirect, url_for, flash, request,
    session, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, login_required,
    logout_user, current_user
)
from flask_mail import Mail
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import joblib
import pymysql

from config import Config
from models import db, User, PredictionHistory
from utils import send_reset_email, verify_reset_token


# ------------------------- helpers -------------------------
def clean_salary(s):
    """Convert salary string to numeric representative value."""
    if pd.isna(s) or str(s).strip() == "":
        return 0.0
    s = str(s)
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d+(?:,\d+)?", s)]
    if len(nums) == 0:
        return 0.0
    elif len(nums) == 1:
        return float(nums[0])
    else:
        return float(sum(nums) / len(nums))


# -----------------------------------------------------
# APP FACTORY
# -----------------------------------------------------
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    ensure_mysql_db_exists(app)
    db.init_app(app)

    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.init_app(app)

    # Flask-Mail setup
    mail = Mail(app)

    # ML Model paths
    app.ml = {
        "pipeline": None,
        "model": None,
        "vectorizer": None,
        "pipeline_path": os.path.join(app.root_path, "models", "pipeline.pkl"),
        "model_path": os.path.join(app.root_path, "models", "model.pkl"),
        "vec_path": os.path.join(app.root_path, "models", "vectorizer.pkl"),
    }

    # ---------------------------
    # User Loader
    # ---------------------------
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except Exception:
            return None

    # -----------------------------------------------------
    # AUTH ROUTES
    # -----------------------------------------------------
    @app.route("/")
    def index():
        return render_template("main_index.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not username or not email or not password:
                flash("Please fill all fields", "danger")
                return redirect(url_for("signup"))

            if User.query.filter(
                (User.username == username) | (User.email == email)
            ).first():
                flash("Username or email already exists", "warning")
                return redirect(url_for("signup"))

            hashed = generate_password_hash(password)
            user = User(username=username, email=email, password=hashed)
            db.session.add(user)
            db.session.commit()
            flash("Account created. Please login.", "success")
            return redirect(url_for("login"))

        return render_template("auth_signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            email_or_username = request.form.get("email_or_username", "").strip()
            password = request.form.get("password", "")

            user = User.query.filter(
                (User.email == email_or_username.lower())
                | (User.username == email_or_username)
            ).first()

            if user and check_password_hash(user.password, password):
                login_user(user)
                session["login_message"] = f"Welcome back, {user.username}! 👋"
                return redirect(url_for("dashboard"))

            flash("Invalid credentials", "danger")
            return redirect(url_for("login"))

        return render_template("auth_login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Logged out successfully", "info")
        return redirect(url_for("index"))

    # -----------------------------------------------------
    # PASSWORD RESET (Fixed)
    # -----------------------------------------------------
    @app.route("/reset_request", methods=["GET", "POST"])
    def reset_request():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = User.query.filter_by(email=email).first()

            if user:
                send_reset_email(user, mail, app)
                flash("Password reset link sent to your email (check spam).", "info")
            else:
                flash("If an account exists for that email, an email was sent.", "info")

            return redirect(url_for("login"))

        return render_template("auth_reset_request.html")

    @app.route("/reset/<token>", methods=["GET", "POST"])
    def reset_token(token):
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        email = verify_reset_token(token, app)
        if not email:
            flash("That is an invalid or expired token", "warning")
            return redirect(url_for("reset_request"))

        user = User.query.filter_by(email=email).first()
        if request.method == "POST":
            pw = request.form.get("password", "")
            if not pw:
                flash("Password required", "danger")
                return redirect(url_for("reset_token", token=token))

            user.password = generate_password_hash(pw)
            db.session.commit()
            flash("Your password has been updated.", "success")
            return redirect(url_for("login"))

        return render_template("auth_reset_token.html", token=token)

    # -----------------------------------------------------
    # DASHBOARD & PREDICTION
    # -----------------------------------------------------
    @app.route("/dashboard")
    @login_required
    def dashboard():
        items = (
            PredictionHistory.query.filter_by(user_id=current_user.id)
            .order_by(PredictionHistory.timestamp.desc())
            .limit(50)
            .all()
        )
        login_message = session.pop("login_message", None)
        return render_template("main_dashboard.html", items=items, login_message=login_message)

    def load_ml(app):
        """Load model and vectorizer."""
        if app.ml.get("model") and app.ml.get("vectorizer"):
            return

        try:
            if os.path.exists(app.ml["vec_path"]):
                app.ml["vectorizer"] = joblib.load(app.ml["vec_path"])
            if os.path.exists(app.ml["model_path"]):
                app.ml["model"] = joblib.load(app.ml["model_path"])
            app.logger.info("✅ Loaded ML model and vectorizer.")
        except Exception as e:
            app.logger.warning("❌ Failed to load ML model/vectorizer: %s", e)

    @app.route("/predict", methods=["POST"])
    @login_required
    def predict():
        """Make prediction using trained model."""
        text = request.form.get("text", "").strip()
        job_title = request.form.get("job_title", "").strip()
        salary_range_raw = request.form.get("salary_range", "").strip()
        company_profile = request.form.get("company_profile", "").strip()
        requirements = request.form.get("requirements", "").strip()

        if not text and (job_title or salary_range_raw or company_profile or requirements):
            text = " ".join([job_title, salary_range_raw, company_profile, requirements]).strip()

        if not text:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Please provide job details."}), 400
            flash("Please fill all fields before predicting.", "warning")
            return redirect(url_for("dashboard"))

        load_ml(app)

        try:
            if app.ml["vectorizer"] is None or app.ml["model"] is None:
                msg = "Model files missing. Please run train.py first."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 500
                flash(msg, "danger")
                return redirect(url_for("dashboard"))

            salary_numeric = clean_salary(salary_range_raw)
            df = pd.DataFrame({"text": [text], "salary_range": [salary_numeric]})

            pred_raw = app.ml["model"].predict(df)
            pred = int(pred_raw[0])

            label = "Fake Job Posting" if pred == 1 else "Real Job Posting"

            rec = PredictionHistory(text=text, prediction=label, user_id=current_user.id)
            db.session.add(rec)
            db.session.commit()

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"prediction": label})

            flash(f"✅ Prediction: {label}" if "Real" in label else f"⚠️ Prediction: {label}",
                  "success" if "Real" in label else "danger")
            return redirect(url_for("dashboard"))

        except Exception as e:
            app.logger.exception("Prediction failed")
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": str(e)}), 500
            flash(f"Prediction failed: {e}", "danger")
            return redirect(url_for("dashboard"))

    # -----------------------------------------------------
    # HISTORY API
    # -----------------------------------------------------
    @app.route("/history")
    @login_required
    def history():
        items = (
            PredictionHistory.query.filter_by(user_id=current_user.id)
            .order_by(PredictionHistory.timestamp.desc())
            .all()
        )
        data = [
            {"text": i.text, "prediction": i.prediction, "timestamp": i.timestamp.isoformat()}
            for i in items
        ]
        return jsonify(data)

    with app.app_context():
        db.create_all()

    return app


# -----------------------------------------------------
# MYSQL DATABASE SETUP
# -----------------------------------------------------
def ensure_mysql_db_exists(app):
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", 3306))
    dbname = os.getenv("MYSQL_DB", "fakejobdb")

    try:
        conn = pymysql.connect(
            host=host, user=user, password=password, port=port,
            cursorclass=pymysql.cursors.DictCursor,
        )
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS {dbname} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print("Could not create DB automatically:", e)


# -----------------------------------------------------
# RUN APP
# -----------------------------------------------------
if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True)
