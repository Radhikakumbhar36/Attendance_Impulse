from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, current_app
)
from extensions import db
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from models import Branch, Employee, Site, Admin
from models.attendance import Attendance, AttendanceApproval
from routes.employee_routes import cleanup_all_incomplete_attendance
from utils.auth import login_required 


# ---------------- Blueprint ----------------
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# ---------------- Config ----------------
ADMIN_KEYWORD = "admin_Impulse"


# ---------------- Helper ----------------
def login_required(func):
    """Decorator to check admin login"""
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in first.", "danger")
            return redirect(url_for("admin.login"))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


# ---------------- Admin Register ----------------
@admin_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        admin_id = request.form.get("admin_id")
        keyword = request.form.get("keyword")
        password = request.form.get("password")

        if not all([name, email, admin_id, keyword, password]):
            flash("All fields are required!", "danger")
            return redirect(url_for("admin.register"))

        if keyword != ADMIN_KEYWORD:
            flash("Invalid keyword. Registration denied.", "danger")
            return redirect(url_for("admin.register"))

        existing_admin = Admin.query.filter(
            (Admin.email == email) | (Admin.admin_id == admin_id)
        ).first()
        if existing_admin:
            flash("Admin with given Email or ID already exists!", "danger")
            return redirect(url_for("admin.register"))

        new_admin = Admin(admin_id=admin_id, name=name, email=email, keyword=keyword)
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()
        flash("Admin registered successfully!", "success")
        return redirect(url_for("admin.login"))

    return render_template("admin_register.html")


# ---------------- Admin Login ----------------
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier")
        password = request.form.get("password")

        if not all([identifier, password]):
            flash("Both fields are required!", "danger")
            return redirect(url_for("admin.login"))

        admin = Admin.query.filter(
            (Admin.email == identifier) | (Admin.admin_id == identifier)
        ).first()

        if admin and admin.check_password(password):
            session["admin_id"] = admin.id
            
            # Check if password needs to be updated
            if not admin.password_changed:
                flash("Please update your password for security reasons.", "warning")
                return redirect(url_for("admin.update_password"))
            
            flash("Login successful!", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Invalid credentials", "danger")
            return redirect(url_for("admin.login"))

    return render_template("admin_login.html")


# ---------------- Admin Password Update ----------------
@admin_bp.route("/update-password", methods=["GET", "POST"])
@login_required
def update_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        admin = Admin.query.get(session["admin_id"])
        
        if not admin.check_password(current_password):
            flash("Current password is incorrect!", "danger")
            return redirect(url_for("admin.update_password"))
        
        if new_password != confirm_password:
            flash("New passwords do not match!", "danger")
            return redirect(url_for("admin.update_password"))
        
        if len(new_password) < 8:
            flash("Password must be at least 8 characters long!", "danger")
            return redirect(url_for("admin.update_password"))
        
        admin.set_password(new_password)
        admin.password_changed = True
        db.session.commit()
        
        flash("Password updated successfully!", "success")
        return redirect(url_for("admin.dashboard"))
    
    return render_template("update_password.html")


# ---------------- Admin Forgot Password ----------------
@admin_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        user_type = request.form.get("user_type", "admin")
        
        if user_type == "admin":
            admin = Admin.query.filter_by(email=email).first()
            if admin:
                # Generate reset token (simplified - in production use proper token generation)
                import secrets
                import datetime
                admin.reset_token = secrets.token_urlsafe(32)
                admin.reset_token_expires = datetime.datetime.now() + datetime.timedelta(hours=1)
                db.session.commit()
                
                # In production, send email here
                flash(f"Reset link sent to {email}. Token: {admin.reset_token}", "success")
            else:
                flash("Email not found!", "danger")
        else:
            flash("Invalid user type!", "danger")
        
        return redirect(url_for("admin.forgot_password"))
    
    return render_template("forgot_password.html")


# ---------------- Admin Dashboard ----------------
@admin_bp.route("/dashboard")
@login_required
def dashboard():
    admin = Admin.query.get(session["admin_id"])
    
    # Run daily cleanup for all employees
    cleanup_all_incomplete_attendance()
    
    pending_approvals = AttendanceApproval.query.filter_by(status="Pending").all()
    
    # Get today's attendance summary
    today = datetime.now().date()
    today_attendances = Attendance.query.filter_by(date=today).all()
    
    # Calculate summary statistics
    total_employees = Employee.query.count()
    present_today = len([a for a in today_attendances if a.status in ["Full Day", "Half Day"]])
    full_day = len([a for a in today_attendances if a.status == "Full Day"])
    half_day = len([a for a in today_attendances if a.status == "Half Day"])
    absent = total_employees - present_today
    
    return render_template("dashboard_admin.html", 
                         admin=admin, 
                         pending_approvals=pending_approvals,
                         total_employees=total_employees,
                         present_today=present_today,
                         full_day=full_day,
                         half_day=half_day,
                         absent=absent,
                         today=today)


# ---------------- Admin Logout ----------------
@admin_bp.route("/logout")
@login_required
def logout():
    session.pop("admin_id", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("admin.login"))


# ---------------- Branches (CRUD) ----------------
@admin_bp.route("/branches")
@login_required
def branches():
    branches = Branch.query.all()
    return render_template("branches.html", branches=branches)


@admin_bp.route("/branch/add", methods=["POST"])
@login_required
def add_branch():
    name = request.form.get("name")
    code = request.form.get("code") or "N/A"
    city = request.form.get("city") or "Unknown"

    if not name:
        flash("Branch name is required!", "danger")
        return redirect(url_for("admin.branches"))

    new_branch = Branch(name=name, code=code, city=city)
    db.session.add(new_branch)
    db.session.commit()
    flash("Branch added successfully!", "success")
    return redirect(url_for("admin.branches"))


@admin_bp.route("/branch/edit/<int:id>", methods=["POST"])
@login_required
def edit_branch(id):
    branch = Branch.query.get_or_404(id)
    branch.name = request.form.get("name") or branch.name
    branch.code = request.form.get("code") or branch.code
    branch.city = request.form.get("city") or branch.city
    db.session.commit()
    flash("Branch updated successfully!", "success")
    return redirect(url_for("admin.branches"))


@admin_bp.route("/branch/delete/<int:id>", methods=["POST", "GET"])
@login_required
def delete_branch(id):
    branch = Branch.query.get_or_404(id)
    db.session.delete(branch)
    db.session.commit()
    flash("Branch deleted!", "danger")
    return redirect(url_for("admin.branches"))


# ---------------- Employees (CRUD) ----------------
@admin_bp.route("/employees")
@login_required
def employees():
    # Show only active employees by default
    employees = Employee.query.filter_by(is_active=True).all()
    branches = Branch.query.all()
    return render_template("employees.html", employees=employees, branches=branches)


@admin_bp.route("/employee/add", methods=["POST"])
@login_required
def add_employee():
    name = request.form.get("name")
    email = request.form.get("email")
    employee_id = request.form.get("employee_id")
    password = request.form.get("password")
    contact_no = request.form.get("contact_no")
    branch_id = request.form.get("branch_id")
    photo_file = request.files.get("photo")

    if not all([name, email, employee_id, password]):
        flash("Please fill in all required fields!", "danger")
        return redirect(url_for("admin.employees"))

    existing_emp = Employee.query.filter(
        (Employee.employee_id == employee_id) | (Employee.email == email)
    ).first()
    if existing_emp:
        flash("Employee with this ID or email already exists!", "danger")
        return redirect(url_for("admin.employees"))

    filename = None
    if photo_file and allowed_file(photo_file.filename):
        filename = secure_filename(photo_file.filename)
        upload_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        photo_file.save(upload_path)

    new_emp = Employee(
        employee_id=employee_id,
        name=name,
        email=email,
        contact_no=contact_no,
        branch_id=(int(branch_id) if branch_id else None),
        photo=filename
    )
    new_emp.set_password(password)

    db.session.add(new_emp)
    db.session.commit()
    flash("Employee added successfully!", "success")
    return redirect(url_for("admin.employees"))



@admin_bp.route("/employee/edit/<int:employee_id>", methods=["GET", "POST"])
@login_required
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    branches = Branch.query.all()

    if request.method == "POST":
        try:
            # Update fields
            employee.name = request.form.get("name", employee.name)
            employee.email = request.form.get("email", employee.email)
            employee.contact_no = request.form.get("contact_no", employee.contact_no)

            # Branch (cast to int if provided)
            branch_id = request.form.get("branch_id")
            if branch_id:
                employee.branch_id = int(branch_id)

            # Handle photo upload
            if "photo" in request.files and request.files["photo"].filename.strip() != "":
                photo = request.files["photo"]
                filename = secure_filename(photo.filename)
                upload_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
                photo.save(upload_path)
                employee.photo = filename

            db.session.commit()
            flash("✅ Employee updated successfully!", "success")
            return redirect(url_for("admin.edit_employee", employee_id=employee.id))

        except Exception as e:
            db.session.rollback()
            flash(f"❌ Error updating employee: {e}", "danger")

    # GET request → render edit form
    return render_template(
        "edit_employee.html",
        employee=employee,
        branches=branches
    )


@admin_bp.route("/employee/delete/<int:id>", methods=["POST", "GET"])
@login_required
def delete_employee(id):
    emp = Employee.query.get_or_404(id)
    
    # Create a special "deleted employee" record if it doesn't exist
    deleted_emp = Employee.query.filter_by(employee_id="DELETED_EMPLOYEE").first()
    if not deleted_emp:
        deleted_emp = Employee(
            employee_id="DELETED_EMPLOYEE",
            name="[Deleted Employee]",
            email="deleted@system.local",
            contact_no="",
            is_active=False
        )
        deleted_emp.set_password("deleted")
        db.session.add(deleted_emp)
        db.session.flush()  # Get the ID
    
    # Update all attendance records to point to the deleted employee record
    from models.attendance import Attendance, AttendanceApproval
    Attendance.query.filter_by(employee_id=emp.id).update({"employee_id": deleted_emp.id})
    AttendanceApproval.query.filter_by(employee_id=emp.id).update({"employee_id": deleted_emp.id})
    
    # Delete employee photo file if exists
    if emp.photo:
        try:
            photo_path = os.path.join(current_app.config["UPLOAD_FOLDER"], emp.photo)
            if os.path.exists(photo_path):
                os.remove(photo_path)
        except Exception as e:
            current_app.logger.warning(f"Could not delete employee photo: {e}")
    
    # Now safely delete the employee
    db.session.delete(emp)
    db.session.commit()
    
    flash(f"Employee {emp.name} has been deleted. All attendance records are preserved under '[Deleted Employee]'.", "success")
    return redirect(url_for("admin.employees"))


@admin_bp.route("/employees/inactive")
@login_required
def inactive_employees():
    """View inactive employees"""
    inactive_employees = Employee.query.filter_by(is_active=False).all()
    return render_template("inactive_employees.html", employees=inactive_employees)


@admin_bp.route("/employee/reactivate/<int:id>", methods=["POST"])
@login_required
def reactivate_employee(id):
    """Reactivate a deactivated employee"""
    emp = Employee.query.get_or_404(id)
    emp.is_active = True
    db.session.commit()
    flash(f"Employee {emp.name} has been reactivated successfully!", "success")
    return redirect(url_for("admin.inactive_employees"))


@admin_bp.route("/employee/force-delete/<int:id>", methods=["POST"])
@login_required
def force_delete_employee(id):
    """Force delete employee and all related records (use with caution - data loss!)"""
    emp = Employee.query.get_or_404(id)
    
    try:
        # Delete all attendance records (THIS WILL CAUSE DATA LOSS!)
        from models.attendance import Attendance, AttendanceApproval
        attendance_count = Attendance.query.filter_by(employee_id=emp.id).count()
        approval_count = AttendanceApproval.query.filter_by(employee_id=emp.id).count()
        
        Attendance.query.filter_by(employee_id=emp.id).delete()
        AttendanceApproval.query.filter_by(employee_id=emp.id).delete()
        
        # Delete employee photo file if exists
        if emp.photo:
            try:
                photo_path = os.path.join(current_app.config["UPLOAD_FOLDER"], emp.photo)
                if os.path.exists(photo_path):
                    os.remove(photo_path)
            except Exception as e:
                current_app.logger.warning(f"Could not delete employee photo: {e}")
        
        # Delete employee
        db.session.delete(emp)
        db.session.commit()
        flash(f"Employee {emp.name} and ALL DATA deleted! ({attendance_count} attendance + {approval_count} approval records lost)", "danger")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error force deleting employee: {str(e)}", "danger")
    
    return redirect(url_for("admin.employees"))


# ---------------- Sites (CRUD) ----------------
@admin_bp.route("/branch/<int:branch_id>/sites", methods=["GET"])
@login_required
def sites(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    sites = Site.query.filter_by(branch_id=branch_id).all()
    return render_template("sites.html", branch=branch, sites=sites)


@admin_bp.route("/branch/<int:branch_id>/site/add", methods=["POST"])
@login_required
def add_site(branch_id):
    name = request.form.get("name")
    address = request.form.get("address")
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")

    if not all([name, address, latitude, longitude]):
        flash("All fields are required!", "danger")
        return redirect(url_for("admin.sites", branch_id=branch_id))

    new_site = Site(name=name, address=address, latitude=latitude, longitude=longitude, branch_id=branch_id)
    db.session.add(new_site)
    db.session.commit()
    flash("Site added successfully!", "success")
    return redirect(url_for("admin.sites", branch_id=branch_id))


@admin_bp.route("/site/edit/<int:id>", methods=["POST"])
@login_required
def edit_site(id):
    site = Site.query.get_or_404(id)
    site.name = request.form.get("name")
    site.address = request.form.get("address")
    site.latitude = request.form.get("latitude")
    site.longitude = request.form.get("longitude")
    db.session.commit()
    flash("Site updated successfully!", "success")
    return redirect(url_for("admin.sites", branch_id=site.branch_id))


@admin_bp.route("/site/delete/<int:id>", methods=["POST", "GET"])
@login_required
def delete_site(id):
    site = Site.query.get_or_404(id)
    branch_id = site.branch_id
    db.session.delete(site)
    db.session.commit()
    flash("Site deleted!", "danger")
    return redirect(url_for("admin.sites", branch_id=branch_id))


# ---------------- Attendance Approval ----------------
@admin_bp.route("/attendance/approve/<int:approval_id>", methods=["POST"])
@login_required
def approve_attendance(approval_id):
    approval = AttendanceApproval.query.get_or_404(approval_id)
    admin = Admin.query.get(session["admin_id"])
    
    # Update approval status
    approval.status = "Approved"
    approval.approved_at = datetime.utcnow()
    approval.approved_by = admin.id
    approval.remarks = request.form.get("remarks", "")

    # Get or create attendance record
    attendance = Attendance.query.filter_by(employee_id=approval.employee_id, date=approval.date).first()
    if not attendance:
        attendance = Attendance(employee_id=approval.employee_id, date=approval.date)
        db.session.add(attendance)

    # Update attendance based on type
    if approval.attendance_type == "in":
        attendance.in_time = approval.time
        attendance.in_photo = approval.photo
        attendance.in_latitude = approval.latitude
        attendance.in_longitude = approval.longitude
        attendance.in_address = approval.address
    else:  # out
        attendance.out_time = approval.time
        attendance.out_photo = approval.photo
        attendance.out_latitude = approval.latitude
        attendance.out_longitude = approval.longitude
        attendance.out_address = approval.address

    # Clear pending approval status
    attendance.pending_approval = False
    attendance.pending_type = None
    attendance.pending_latitude = None
    attendance.pending_longitude = None
    attendance.pending_address = None
    attendance.pending_time = None
    attendance.pending_photo = None

    # Update status and working hours
    from routes.employee_routes import determine_attendance_status, calculate_working_hours
    attendance.status = determine_attendance_status(attendance.in_time, attendance.out_time)
    attendance.working_hours = calculate_working_hours(attendance.in_time, attendance.out_time)

    db.session.commit()
    flash("Attendance approved successfully!", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/attendance/reject/<int:approval_id>", methods=["POST"])
@login_required
def reject_attendance(approval_id):
    approval = AttendanceApproval.query.get_or_404(approval_id)
    admin = Admin.query.get(session["admin_id"])
    
    approval.status = "Rejected"
    approval.approved_at = datetime.utcnow()
    approval.approved_by = admin.id
    approval.remarks = request.form.get("remarks", "Rejected by admin")

    # Clear pending approval status from attendance
    attendance = Attendance.query.filter_by(employee_id=approval.employee_id, date=approval.date).first()
    if attendance:
        attendance.pending_approval = False
        attendance.pending_type = None
        attendance.pending_latitude = None
        attendance.pending_longitude = None
        attendance.pending_address = None
        attendance.pending_time = None
        attendance.pending_photo = None

    db.session.commit()
    flash("Attendance rejected successfully!", "success")
    return redirect(url_for("admin.dashboard"))


# ---------------- Attendance Reports ----------------
@admin_bp.route("/reports/attendance")
@login_required
def attendance_reports():
    """Comprehensive attendance reporting"""
    # Get date range from request
    start_date = request.args.get('start_date', datetime.now().date().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().date().strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except:
        start_date = datetime.now().date()
        end_date = datetime.now().date()
    
    # Get all employees with their attendance for the date range
    employees = Employee.query.all()
    attendance_data = []
    
    for emp in employees:
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).order_by(Attendance.date.desc()).all()
        
        attendance_data.append({
            'employee': emp,
            'attendances': attendances
        })
    
    return render_template("attendance_reports.html", 
                         attendance_data=attendance_data,
                         start_date=start_date,
                         end_date=end_date)


@admin_bp.route("/reports/attendance/export")
@login_required
def export_attendance_reports():
    """Export attendance reports to Excel"""
    import pandas as pd
    from io import BytesIO
    
    # Get date range from request
    start_date = request.args.get('start_date', datetime.now().date().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().date().strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except:
        start_date = datetime.now().date()
        end_date = datetime.now().date()
    
    # Get attendance data
    attendances = db.session.query(Attendance, Employee, Branch, Site).join(
        Employee, Attendance.employee_id == Employee.id
    ).outerjoin(
        Branch, Employee.branch_id == Branch.id
    ).outerjoin(
        Site, Attendance.site_id == Site.id
    ).filter(
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).order_by(Attendance.date.desc(), Employee.name).all()
    
    # Prepare data for Excel
    data = []
    for attendance, employee, branch, site in attendances:
        data.append({
            'Date': attendance.date.strftime('%Y-%m-%d'),
            'Employee ID': employee.employee_id,
            'Employee Name': employee.name,
            'Branch': branch.name if branch else 'No Branch',
            'Site': site.name if site else 'No Site',
            'In Time': attendance.in_time.strftime('%I:%M %p') if attendance.in_time else 'Not Marked',
            'Out Time': attendance.out_time.strftime('%I:%M %p') if attendance.out_time else 'Not Marked',
            'Working Hours': attendance.working_hours or '0:00',
            'Status': attendance.status,
            'In Address': attendance.in_address or 'N/A',
            'Out Address': attendance.out_address or 'N/A'
        })
    
    # Create Excel file
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Attendance Report', index=False)
    
    output.seek(0)
    
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename=attendance_report_{start_date}_to_{end_date}.xlsx'}
    )