from flask import Flask, session, redirect, url_for, flash
import logging
from logging.handlers import RotatingFileHandler
from config import (
    SQLALCHEMY_DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS,
    SECRET_KEY,
    UPLOAD_FOLDER,
    ALLOWED_EXTENSIONS,
    MAX_CONTENT_LENGTH
)
from extensions import db, bcrypt
from routes.employee_routes import employee_bp
from routes.admin_routes import admin_bp
import os
import pytesseract


def create_app():
    app = Flask(__name__)

    # Load Database Config
    app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS
    app.config["SECRET_KEY"] = SECRET_KEY

    # Load File Upload Config
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["ALLOWED_EXTENSIONS"] = ALLOWED_EXTENSIONS
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

    # Ensure upload folder exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Init Extensions
    db.init_app(app)
    bcrypt.init_app(app)

    # Configure Tesseract path early if provided
    try:
        tess_env = os.environ.get('TESSERACT_CMD') or os.environ.get('TESSERACT_EXE')
        if tess_env and os.path.isfile(tess_env):
            pytesseract.pytesseract.tesseract_cmd = tess_env
        else:
            # Fall back to common Windows install path
            common = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
            common86 = r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe"
            if os.path.isfile(common):
                pytesseract.pytesseract.tesseract_cmd = common
            elif os.path.isfile(common86):
                pytesseract.pytesseract.tesseract_cmd = common86
    except Exception:
        pass

    # Register Blueprints
    app.register_blueprint(employee_bp)
    app.register_blueprint(admin_bp)

    # Logout Route
    @app.route("/logout")
    def logout():
        session.clear()
        flash("Logged out.", "info")
        return redirect(url_for("employee.employee_login"))

    # Create Tables if not exists
    with app.app_context():
        db.create_all()

    # Production logging (rotating file)
    try:
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(os.path.join(log_dir, 'app.log'), maxBytes=2_000_000, backupCount=5)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s'))
        app.logger.addHandler(handler)
    except Exception:
        pass

    return app


app = create_app()

if __name__ == "__main__":
    # For local runs; in production use waitress or gunicorn
    app.run(host="0.0.0.0", port=5000, debug=False)