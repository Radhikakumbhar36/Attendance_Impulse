# models/attendance.py
from extensions import db
from datetime import datetime

class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    
    # In attendance fields
    in_time = db.Column(db.DateTime, nullable=True)
    in_photo = db.Column(db.String(255), nullable=True)
    in_latitude = db.Column(db.Float, nullable=True)
    in_longitude = db.Column(db.Float, nullable=True)
    in_address = db.Column(db.Text, nullable=True)
    
    # Out attendance fields
    out_time = db.Column(db.DateTime, nullable=True)
    out_photo = db.Column(db.String(255), nullable=True)
    out_latitude = db.Column(db.Float, nullable=True)
    out_longitude = db.Column(db.Float, nullable=True)
    out_address = db.Column(db.Text, nullable=True)
    
    # Site and status fields
    site_id = db.Column(db.Integer, db.ForeignKey("site.id"), nullable=True)
    status = db.Column(db.String(30), default="Absent")  # Full Day, Half Day, Absent
    working_hours = db.Column(db.String(10), nullable=True)  # Format: "8:30"
    
    # Pending approval fields
    pending_approval = db.Column(db.Boolean, default=False)
    pending_type = db.Column(db.String(10), nullable=True)  # "in" or "out"
    pending_latitude = db.Column(db.Float, nullable=True)
    pending_longitude = db.Column(db.Float, nullable=True)
    pending_address = db.Column(db.Text, nullable=True)
    pending_time = db.Column(db.DateTime, nullable=True)
    pending_photo = db.Column(db.String(255), nullable=True)
    
    # Relationships
    employee = db.relationship("Employee", backref="attendances")
    site = db.relationship("Site", backref="attendances")


class AttendanceApproval(db.Model):
    __tablename__ = "attendance_approval"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    attendance_id = db.Column(db.Integer, db.ForeignKey("attendance.id"), nullable=True)
    date = db.Column(db.Date, nullable=False)
    attendance_type = db.Column(db.String(10), nullable=False)  # "in" or "out"
    photo = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    address = db.Column(db.Text, nullable=True)
    time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="Pending")  # Pending / Approved / Rejected
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=True)
    
    # Relationships
    employee = db.relationship("Employee", backref="attendance_approvals")
    attendance = db.relationship("Attendance", backref="approvals")
    approver = db.relationship("Admin", backref="approved_attendances")
