from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in as admin to access this page.", "danger")
            return redirect(url_for("admin.admin_login"))
        return f(*args, **kwargs)
    return wrapper
