import os
from dotenv import load_dotenv

load_dotenv()

# Database Config
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:yourpassword@localhost/attendance"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Secret Key
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-this")

# File Upload Config
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB limit

# Mail Config
MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
MAIL_DEFAULT_SENDER = MAIL_USERNAME
