from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash

class Employee(db.Model):
    __tablename__ = "employee"
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    contact_no = db.Column(db.String(20), nullable=True)
    photo = db.Column(db.String(255), nullable=True)  # New column for storing photo filename

    password_hash = db.Column(db.String(255), nullable=False)
    password_changed = db.Column(db.Boolean, default=False, nullable=False)
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # For soft delete

    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"), nullable=True)
    branch = db.relationship("Branch", back_populates="employees")

    # Methods for password handling
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)