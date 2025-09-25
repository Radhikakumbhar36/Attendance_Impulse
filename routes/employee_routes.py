import os
import re
import tempfile
import requests
from datetime import datetime, time, timedelta
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    current_app,
    jsonify
)
import face_recognition
from geopy.distance import geodesic
from flask_mail import Mail, Message
from extensions import db
from models.employee import Employee
from models.site import Site
from models.attendance import Attendance, AttendanceApproval
from models.admin import Admin

employee_bp = Blueprint("employee", __name__)
EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

# ----------------- Helper Functions -----------------

def login_required(func):
    """Decorator to ensure employee is logged in"""
    def wrapper(*args, **kwargs):
        if session.get("user_type") != "employee" or not session.get("user_id"):
            flash("Please log in first.", "danger")
            return redirect(url_for("employee.employee_login"))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

def verify_face_match(uploaded_path, stored_path):
    """Verify face match with detailed logging"""
    try:
        current_app.logger.info(f"Starting face verification: uploaded={uploaded_path}, stored={stored_path}")
        
        # Load uploaded image
        uploaded_image = face_recognition.load_image_file(uploaded_path)
        uploaded_encodings = face_recognition.face_encodings(uploaded_image)
        
        if not uploaded_encodings:
            current_app.logger.warning("No face found in uploaded image")
            return False, "No face detected in uploaded photo"

        if len(uploaded_encodings) > 1:
            current_app.logger.warning("Multiple faces found in uploaded image")
            return False, "Multiple faces detected. Please upload photo with single face"

        # Load stored image
        if not stored_path or not os.path.exists(stored_path):
            current_app.logger.error(f"Stored face image not found: {stored_path}")
            return False, "Employee face not found in database"

        stored_image = face_recognition.load_image_file(stored_path)
        stored_encodings = face_recognition.face_encodings(stored_image)
        
        if not stored_encodings:
            current_app.logger.error("No face found in stored image")
            return False, "Database face image is invalid"

        # Compare faces with tolerance
        matches = face_recognition.compare_faces([stored_encodings[0]], uploaded_encodings[0], tolerance=0.6)
        face_distance = face_recognition.face_distance([stored_encodings[0]], uploaded_encodings[0])
        
        current_app.logger.info(f"Face match result: {matches[0]}, distance: {face_distance[0]}")
        
        if matches[0]:
            return True, "Face verified successfully"
        else:
            return False, "Face verification failed - faces do not match"
            
    except Exception as e:
        current_app.logger.exception("Face verification error: %s", e)
        return False, f"Face verification error: {str(e)}"

def extract_gps_from_photo(photo_path):
    """Enhanced GPS extraction from both EXIF metadata and visual text overlays"""
    try:
        current_app.logger.info(f"Starting enhanced GPS extraction for: {photo_path}")
        
        # Import the enhanced GPS extractor
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        from utils.gps_extractor import extract_gps_and_datetime
        
        # Use the enhanced extraction method
        lat, lon, dt, address, method = extract_gps_and_datetime(photo_path)
        
        if lat is not None and lon is not None:
            current_app.logger.info(f"GPS extraction successful: {lat:.6f}, {lon:.6f} (Method: {method})")
            return lat, lon
        else:
            current_app.logger.error("GPS extraction failed with all methods")
            return None, None
            
    except Exception as e:
        current_app.logger.error(f"Enhanced GPS extraction error: {e}")
        import traceback
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return None, None

def get_address_from_coordinates(lat, lon):
    """Get address from GPS coordinates using reverse geocoding"""
    try:
        # Using OpenStreetMap Nominatim (free service)
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&addressdetails=1"
        headers = {'User-Agent': 'AttendanceSystem/1.0'}
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'display_name' in data:
                return data['display_name']
        
        return f"Location: {lat:.6f}, {lon:.6f}"
    except:
        return f"Location: {lat:.6f}, {lon:.6f}"

def is_within_site_range(emp_lat, emp_lon, sites, radius_km=2.0):
    """Check if employee location is within range of any assigned site"""
    closest_distance = float('inf')
    
    for site in sites:
        try:
            distance = geodesic((emp_lat, emp_lon), (site.latitude, site.longitude)).kilometers
            current_app.logger.info(f"Proximity check: site={getattr(site, 'name', 'N/A')} lat={site.latitude} lon={site.longitude} distance_km={distance:.4f} radius_km={radius_km}")
            if distance < closest_distance:
                closest_distance = distance
            if distance <= radius_km:
                return True, site, distance
        except:
            continue
    return False, None, closest_distance

def format_time_12hour(dt):
    """Format datetime to 12-hour format like '9:01 AM'"""
    if not dt:
        return None
    return dt.strftime("%I:%M %p").lstrip('0')

def calculate_working_hours(in_time, out_time):
    """Calculate working hours between in and out time"""
    if not in_time or not out_time:
        return "0:00"
    
    duration = out_time - in_time
    hours = int(duration.total_seconds() // 3600)
    minutes = int((duration.total_seconds() % 3600) // 60)
    return f"{hours}:{minutes:02d}"

def cleanup_incomplete_attendance(employee_id):
    """Clean up incomplete attendance records from previous days"""
    today = datetime.now().date()
    
    # Find all attendance records for this employee that are not from today
    old_attendances = Attendance.query.filter(
        Attendance.employee_id == employee_id,
        Attendance.date < today
    ).all()
    
    for attendance in old_attendances:
        # If attendance has IN time but no OUT time, mark as Half Day
        if attendance.in_time and not attendance.out_time:
            attendance.status = "Half Day"
            attendance.working_hours = "0:00"  # No out time means no working hours
            current_app.logger.info(f"Finalized incomplete attendance for employee {employee_id} on {attendance.date}")
        
        # If attendance has OUT time but no IN time, mark as Half Day
        elif attendance.out_time and not attendance.in_time:
            attendance.status = "Half Day"
            attendance.working_hours = "0:00"
            current_app.logger.info(f"Finalized incomplete attendance for employee {employee_id} on {attendance.date}")
        
        # If no times at all, mark as Absent
        elif not attendance.in_time and not attendance.out_time:
            attendance.status = "Absent"
            attendance.working_hours = "0:00"
    
    # Also check if there's an incomplete record for today that should be cleared
    # This handles cases where the system might have created a record but it's incomplete
    today_attendance = Attendance.query.filter_by(employee_id=employee_id, date=today).first()
    if today_attendance and not today_attendance.in_time and not today_attendance.out_time:
        # If today's record has no times, delete it to start fresh
        db.session.delete(today_attendance)
        current_app.logger.info(f"Deleted empty attendance record for employee {employee_id} on {today}")
    
    # CRITICAL FIX: If there's a record for today with IN time but no OUT time from previous day,
    # we need to check if this is actually from a previous day that got created with today's date
    # This can happen if the system creates a record with current date but the IN time is from previous day
    if today_attendance and today_attendance.in_time:
        # Check if the IN time is from a previous day (before midnight)
        if today_attendance.in_time.date() < today:
            # This is a stale record - delete it
            db.session.delete(today_attendance)
            current_app.logger.info(f"Deleted stale attendance record for employee {employee_id} - IN time was from {today_attendance.in_time.date()}")
    
    db.session.commit()

def cleanup_all_incomplete_attendance():
    """Clean up incomplete attendance records for all employees"""
    today = datetime.now().date()
    
    # Find all attendance records that are not from today and have incomplete data
    incomplete_attendances = Attendance.query.filter(
        Attendance.date < today,
        db.or_(
            db.and_(Attendance.in_time.isnot(None), Attendance.out_time.is_(None)),
            db.and_(Attendance.out_time.isnot(None), Attendance.in_time.is_(None)),
            db.and_(Attendance.in_time.is_(None), Attendance.out_time.is_(None))
        )
    ).all()
    
    for attendance in incomplete_attendances:
        # If attendance has IN time but no OUT time, mark as Half Day
        if attendance.in_time and not attendance.out_time:
            attendance.status = "Half Day"
            attendance.working_hours = "0:00"
            current_app.logger.info(f"Finalized incomplete attendance for employee {attendance.employee_id} on {attendance.date}")
        
        # If attendance has OUT time but no IN time, mark as Half Day
        elif attendance.out_time and not attendance.in_time:
            attendance.status = "Half Day"
            attendance.working_hours = "0:00"
            current_app.logger.info(f"Finalized incomplete attendance for employee {attendance.employee_id} on {attendance.date}")
        
        # If no times at all, mark as Absent
        elif not attendance.in_time and not attendance.out_time:
            attendance.status = "Absent"
            attendance.working_hours = "0:00"
    
    # Also clean up any empty records for today
    empty_today_records = Attendance.query.filter(
        Attendance.date == today,
        Attendance.in_time.is_(None),
        Attendance.out_time.is_(None)
    ).all()
    
    for record in empty_today_records:
        db.session.delete(record)
        current_app.logger.info(f"Deleted empty attendance record for employee {record.employee_id} on {today}")
    
    db.session.commit()
    current_app.logger.info(f"Daily cleanup completed. Processed {len(incomplete_attendances)} incomplete attendance records and deleted {len(empty_today_records)} empty records.")

def determine_attendance_status(in_time, out_time):
    """Determine attendance status based on in/out times"""
    if not in_time and not out_time:
        return "Absent"
    
    # Valid in time: 7:45 AM to 8:15 AM
    valid_in = in_time and time(7, 45) <= in_time.time() <= time(8, 15)
    
    # Valid out time: after 6:00 PM
    valid_out = out_time and out_time.time() >= time(18, 0)
    
    if valid_in and valid_out:
        return "Full Day"
    elif in_time or out_time:
        return "Half Day"
    else:
        return "Absent"

def send_admin_approval_email(employee, attendance_type, lat, lon, address, reason):
    """Send email to admin for attendance approval"""
    try:
        mail = Mail(current_app)
        
        # Get admin emails
        admins = Admin.query.filter_by(is_active=True).all()
        admin_emails = [admin.email for admin in admins]
        
        if not admin_emails:
            current_app.logger.error("No active admin emails found")
            return False
        
        # Create approval link
        approval_link = url_for('admin.approve_attendance', 
                               employee_id=employee.id,
                               attendance_type=attendance_type,
                               date=datetime.now().strftime('%Y-%m-%d'),
                               _external=True)
        
        subject = f"Attendance Approval Required - {employee.name}"
        
        body = f"""
        Attendance approval required for employee outside site range.
        
        Employee: {employee.name} (ID: {employee.employee_id})
        Type: {attendance_type.title()} Attendance
        Date: {datetime.now().strftime('%d-%m-%Y')}
        Time: {format_time_12hour(datetime.now())}
        
        Location Details:
        - Coordinates: {lat:.6f}, {lon:.6f}
        - Address: {address}
        - Reason: {reason}
        
        Google Maps: https://maps.google.com/?q={lat},{lon}
        
        To approve this attendance, click: {approval_link}
        
        This is an automated message from the Attendance System.
        """
        
        msg = Message(subject=subject, recipients=admin_emails, body=body)
        mail.send(msg)
        
        current_app.logger.info(f"Approval email sent for {employee.name}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"Failed to send approval email: {e}")
        return False

def validate_gps_photo(photo_file):
    """Pre-validate if uploaded file contains GPS data before processing"""
    if not photo_file:
        return False, "No photo uploaded"
    
    if not photo_file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        return False, "Invalid file type. Only JPG, JPEG, or PNG allowed"
    
    # Create temporary file to check GPS
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
        photo_file.save(tmp_file.name)
        temp_path = tmp_file.name
    
    try:
        lat, lon = extract_gps_from_photo(temp_path)
        if lat is None or lon is None:
            return False, "Photo does not contain GPS location data"
        
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return False, "Invalid GPS coordinates in photo"
            
        return True, "GPS photo validated successfully"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ----------------- Route Functions -----------------

def process_attendance_with_coordinates(emp, photo_file, attendance_type, lat, lon):
    """Process attendance with provided GPS coordinates (for GPS overlay photos)"""
    
    # Step 1: Validate photo upload
    if not photo_file:
        return False, "Please upload a photo."
    
    if not photo_file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        return False, "Please upload a valid image file (JPG, JPEG, or PNG)."
    
    # Save photo temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
        photo_file.save(tmp_file.name)
        temp_path = tmp_file.name
    
    try:
        # Step 2: Face Recognition (FIRST PRIORITY)
        stored_face_path = os.path.join(current_app.config["UPLOAD_FOLDER"], emp.photo) if emp.photo else None
        face_match, face_message = verify_face_match(temp_path, stored_face_path)
        
        if not face_match:
            current_app.logger.warning(f"Face verification failed for {emp.name}: {face_message}")
            return False, f"Face verification failed: {face_message}"
        
        current_app.logger.info(f"Face verified successfully for {emp.name}")
        
        # Step 3: Use provided GPS coordinates
        current_app.logger.info(f"Using provided GPS coordinates: {lat:.6f}, {lon:.6f}")
        
        # Step 4: Get address from coordinates
        address = get_address_from_coordinates(lat, lon)
        
        # Extract datetime from photo overlay to prevent reusing old photos
        from utils.gps_extractor import extract_datetime_from_text_overlay, validate_photo_time
        extracted_datetime, ok = extract_datetime_from_text_overlay(temp_path)
        if not ok or extracted_datetime is None:
            return False, (
                "Failed to read date/time from the GPS photo. Please upload a GPS Map Camera photo with a visible date and time."
            )
        
        # Enforce that the photo date must be today's date (accepts dd/mm or mm/dd at OCR stage)
        if extracted_datetime.date() != datetime.now().date():
            return False, (
                "Photo date does not match today's date. Please use a fresh GPS photo taken today."
            )
        
        # Validate photo time is within 10 minutes of upload time
        upload_time = datetime.now()  # Time when photo was uploaded
        time_diff_minutes = abs((extracted_datetime - upload_time).total_seconds() / 60)
        current_app.logger.info(f"Photo time: {extracted_datetime.strftime('%d/%m/%Y %I:%M:%S %p')}")
        current_app.logger.info(f"Upload time: {upload_time.strftime('%d/%m/%Y %I:%M:%S %p')}")
        current_app.logger.info(f"Time difference: {time_diff_minutes:.1f} minutes")
        
        if time_diff_minutes > 10:
            current_app.logger.warning(f"Time validation failed: Photo time differs from upload time by {time_diff_minutes:.1f} minutes (max allowed: 10 min)")
            return False, f"Time validation failed: Photo time differs from upload time by {time_diff_minutes:.1f} minutes (max allowed: 10 min)"
        
        current_app.logger.info(f"Time validation passed: Photo time valid (diff: {time_diff_minutes:.1f} min)")
        
        # ALWAYS use photo time, never upload time
        current_time = extracted_datetime
        formatted_time = format_time_12hour(current_time)
        
        current_app.logger.info(f"GPS provided - Lat: {lat}, Lon: {lon}, Address: {address}, Time: {formatted_time}")
        
        # Step 5: Check if location is within site range
        employee_sites = Site.query.filter_by(branch_id=emp.branch_id).all()
        within_range, matched_site, distance = is_within_site_range(lat, lon, employee_sites)
        
        today = current_time.date()
        
        # Clean up any incomplete attendance from previous days first
        cleanup_incomplete_attendance(emp.id)
        
        # Get or create today's attendance record
        attendance = Attendance.query.filter_by(employee_id=emp.id, date=today).first()
        
        if not attendance:
            attendance = Attendance(employee_id=emp.id, date=today)
            db.session.add(attendance)
        
        # Note: Photos are not saved permanently to save storage space
        # Only GPS coordinates, datetime, and attendance data are stored
        
        # Step 6: Process attendance based on location
        if within_range:
            # Location is within range - process immediately
            if attendance_type == "in":
                attendance.in_time = current_time
                attendance.in_latitude = lat
                attendance.in_longitude = lon
                attendance.in_address = address
                # Photo not saved to conserve storage
                attendance.site_id = matched_site.id
                
            else:  # out
                attendance.out_time = current_time
                attendance.out_latitude = lat
                attendance.out_longitude = lon
                attendance.out_address = address
                # Photo not saved to conserve storage
            
            # Update status and working hours
            attendance.status = determine_attendance_status(attendance.in_time, attendance.out_time)
            attendance.working_hours = calculate_working_hours(attendance.in_time, attendance.out_time)
            
            db.session.commit()
            
            success_msg = f"{attendance_type.title()} attendance marked successfully!\n"
            success_msg += f"Location: {address[:100]}...\n"
            success_msg += f"Photo Time: {formatted_time} (extracted from photo)\n"
            success_msg += f"Site: {matched_site.name} (Distance: {distance:.2f}km)"
            
            return True, success_msg
            
        else:
            # Location is outside range - send for admin approval
            reason = f"Employee location is outside the 2km range of assigned sites. Closest site distance: {distance:.2f}km"
            
            # Create attendance approval record
            approval = AttendanceApproval(
                employee_id=emp.id,
                attendance_id=attendance.id,
                date=today,
                attendance_type=attendance_type,
                photo=None,  # Photos not saved to conserve storage
                latitude=lat,
                longitude=lon,
                address=address,
                time=current_time,
                status="Pending"
            )
            db.session.add(approval)
            
            # Update attendance with pending info
            attendance.pending_approval = True
            attendance.pending_type = attendance_type
            attendance.pending_latitude = lat
            attendance.pending_longitude = lon
            attendance.pending_address = address
            attendance.pending_time = current_time
            attendance.pending_photo = None  # Photos not saved to conserve storage
            
            db.session.commit()
            
            # Send email to admin
            email_sent = send_admin_approval_email(emp, attendance_type, lat, lon, address, reason)
            
            if email_sent:
                pending_msg = f"Attendance request sent for admin approval.\n"
                pending_msg += f"Your location: {address[:100]}...\n"
                pending_msg += f"Time: {formatted_time}\n"
                pending_msg += f"Reason: Outside site range ({distance:.2f}km from nearest site)\n"
                pending_msg += "Admin will review and approve if valid."
                return True, pending_msg
            else:
                return False, "Failed to send approval request to admin. Please contact support."
    
    finally:
        # Clean up temporary file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

def process_attendance(emp, photo_file, attendance_type):
    """Complete attendance processing with face recognition and GPS validation"""
    
    # Step 1: Validate photo upload
    if not photo_file:
        return False, "Please upload a photo."
    
    if not photo_file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        return False, "Please upload a valid image file (JPG, JPEG, or PNG)."
    
    # Save photo temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
        photo_file.save(tmp_file.name)
        temp_path = tmp_file.name
    
    try:
        # Step 2: Face Recognition (FIRST PRIORITY)
        stored_face_path = os.path.join(current_app.config["UPLOAD_FOLDER"], emp.photo) if emp.photo else None
        face_match, face_message = verify_face_match(temp_path, stored_face_path)
        
        if not face_match:
            current_app.logger.warning(f"Face verification failed for {emp.name}: {face_message}")
            return False, f"Face verification failed: {face_message}"
        
        current_app.logger.info(f"Face verified successfully for {emp.name}")
        
        # Step 3: Extract GPS coordinates and datetime using OCR (after face recognition)
        from utils.gps_extractor import extract_gps_and_datetime
        lat, lon, extracted_datetime, address, method = extract_gps_and_datetime(temp_path)
        
        if lat is None or lon is None:
            return False, "Failed to extract GPS information from photo. Please ensure your GPS photo has clear, visible coordinates and date/time overlay. Try taking a new photo with better lighting or clearer text."
        
        current_app.logger.info(f"GPS extracted via {method} - Lat: {lat}, Lon: {lon}")
        
        # Step 4: Get address from coordinates
        address = get_address_from_coordinates(lat, lon)
        
        # Require datetime to be extracted from the photo (reject reused/old photos)
        if extracted_datetime is None:
            return False, (
                "Failed to extract date/time from photo. Please ensure the GPS photo shows a clear date and time overlay."
            )
        
        current_time = extracted_datetime
        
        # Enforce that the photo date must be today's date
        if current_time.date() != datetime.now().date():
            return False, (
                "Photo date does not match today's date. Please use a fresh GPS photo taken today."
            )
        
        # Validate photo time is within 10 minutes of upload time
        upload_time = datetime.now()  # Time when photo was uploaded
        time_diff_minutes = abs((extracted_datetime - upload_time).total_seconds() / 60)
        current_app.logger.info(f"Photo time: {extracted_datetime.strftime('%d/%m/%Y %I:%M:%S %p')}")
        current_app.logger.info(f"Upload time: {upload_time.strftime('%d/%m/%Y %I:%M:%S %p')}")
        current_app.logger.info(f"Time difference: {time_diff_minutes:.1f} minutes")
        
        if time_diff_minutes > 10:
            current_app.logger.warning(f"Time validation failed: Photo time differs from upload time by {time_diff_minutes:.1f} minutes (max allowed: 10 min)")
            return False, f"Time validation failed: Photo time differs from upload time by {time_diff_minutes:.1f} minutes (max allowed: 10 min)"
        
        current_app.logger.info(f"Time validation passed: Photo time valid (diff: {time_diff_minutes:.1f} min)")
        
        formatted_time = format_time_12hour(current_time)
        
        current_app.logger.info(f"GPS extracted - Lat: {lat}, Lon: {lon}, Address: {address}, Time: {formatted_time}")
        
        # Step 5: Check if location is within site range
        employee_sites = Site.query.filter_by(branch_id=emp.branch_id).all()
        within_range, matched_site, distance = is_within_site_range(lat, lon, employee_sites)
        
        today = current_time.date()
        
        # Clean up any incomplete attendance from previous days first
        cleanup_incomplete_attendance(emp.id)
        
        # Get or create today's attendance record
        attendance = Attendance.query.filter_by(employee_id=emp.id, date=today).first()
        
        if not attendance:
            attendance = Attendance(employee_id=emp.id, date=today)
            db.session.add(attendance)
        
        # Note: Photos are not saved permanently to save storage space
        # Only GPS coordinates, datetime, and attendance data are stored
        
        # Step 6: Process attendance based on location
        if within_range:
            # Location is within range - process immediately
            if attendance_type == "in":
                attendance.in_time = current_time
                attendance.in_latitude = lat
                attendance.in_longitude = lon
                attendance.in_address = address
                # Photo not saved to conserve storage
                attendance.site_id = matched_site.id
                
            else:  # out
                attendance.out_time = current_time
                attendance.out_latitude = lat
                attendance.out_longitude = lon
                attendance.out_address = address
                # Photo not saved to conserve storage
            
            # Update status and working hours
            attendance.status = determine_attendance_status(attendance.in_time, attendance.out_time)
            attendance.working_hours = calculate_working_hours(attendance.in_time, attendance.out_time)
            
            db.session.commit()
            
            success_msg = f"{attendance_type.title()} attendance marked successfully!\n"
            success_msg += f"Location: {address[:100]}...\n"
            success_msg += f"Photo Time: {formatted_time} (extracted from photo)\n"
            success_msg += f"Site: {matched_site.name} (Distance: {distance:.2f}km)"
            
            return True, success_msg
            
        else:
            # Location is outside range - send for admin approval
            reason = f"Employee location is outside the 2km range of assigned sites. Closest site distance: {distance:.2f}km"
            
            # Create attendance approval record
            approval = AttendanceApproval(
                employee_id=emp.id,
                attendance_id=attendance.id,
                date=today,
                attendance_type=attendance_type,
                photo=None,  # Photos not saved to conserve storage
                latitude=lat,
                longitude=lon,
                address=address,
                time=current_time,
                status="Pending"
            )
            db.session.add(approval)
            
            # Update attendance with pending info
            attendance.pending_approval = True
            attendance.pending_type = attendance_type
            attendance.pending_latitude = lat
            attendance.pending_longitude = lon
            attendance.pending_address = address
            attendance.pending_time = current_time
            attendance.pending_photo = None  # Photos not saved to conserve storage
            
            db.session.commit()
            
            # Send email to admin
            email_sent = send_admin_approval_email(emp, attendance_type, lat, lon, address, reason)
            
            if email_sent:
                pending_msg = f"Attendance request sent for admin approval.\n"
                pending_msg += f"Your location: {address[:100]}...\n"
                pending_msg += f"Time: {formatted_time}\n"
                pending_msg += f"Reason: Outside site range ({distance:.2f}km from nearest site)\n"
                pending_msg += "Admin will review and approve if valid."
                return True, pending_msg
            else:
                return False, "Failed to send approval request to admin. Please contact support."
    
    finally:
        # Clean up temporary file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

# ----------------- Route Handlers -----------------

@employee_bp.route("/", methods=["GET", "POST"])
def employee_login():
    """Employee login route"""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        if EMAIL_RE.match(identifier):
            employee = Employee.query.filter_by(email=identifier, is_active=True).first()
        else:
            employee = Employee.query.filter_by(employee_id=identifier, is_active=True).first()

        if not employee or not employee.check_password(password):
            flash("Invalid credentials or account deactivated.", "danger")
            return redirect(url_for("employee.employee_login"))

        session.clear()
        session["user_type"] = "employee"
        session["user_id"] = employee.id
        session["user_name"] = employee.name
        
        # Check if password needs to be updated
        if not employee.password_changed:
            flash("Please update your password for security reasons.", "warning")
            return redirect(url_for("employee.update_password"))
        
        flash("Logged in successfully.", "success")
        return redirect(url_for("employee.employee_dashboard"))

    return render_template("employee_login.html")

# ---------------- Employee Password Update ----------------
@employee_bp.route("/update-password", methods=["GET", "POST"])
@login_required
def update_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        employee = Employee.query.get(session["user_id"])
        
        if not employee.check_password(current_password):
            flash("Current password is incorrect!", "danger")
            return redirect(url_for("employee.update_password"))
        
        if new_password != confirm_password:
            flash("New passwords do not match!", "danger")
            return redirect(url_for("employee.update_password"))
        
        if len(new_password) < 8:
            flash("Password must be at least 8 characters long!", "danger")
            return redirect(url_for("employee.update_password"))
        
        employee.set_password(new_password)
        employee.password_changed = True
        db.session.commit()
        
        flash("Password updated successfully!", "success")
        return redirect(url_for("employee.employee_dashboard"))
    
    return render_template("update_password.html")

# ---------------- Employee Forgot Password ----------------
@employee_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        user_type = request.form.get("user_type", "employee")
        
        if user_type == "employee":
            employee = Employee.query.filter_by(email=email).first()
            if employee:
                # Generate reset token (simplified - in production use proper token generation)
                import secrets
                import datetime
                employee.reset_token = secrets.token_urlsafe(32)
                employee.reset_token_expires = datetime.datetime.now() + datetime.timedelta(hours=1)
                db.session.commit()
                
                # In production, send email here
                flash(f"Reset link sent to {email}. Token: {employee.reset_token}", "success")
            else:
                flash("Email not found!", "danger")
        else:
            flash("Invalid user type!", "danger")
        
        return redirect(url_for("employee.forgot_password"))
    
    return render_template("forgot_password.html")

@employee_bp.route("/employee/dashboard")
@login_required
def employee_dashboard():
    """Employee dashboard showing today's attendance status"""
    emp = Employee.query.get(session["user_id"])
    today = datetime.now().date()
    
    # Clean up any incomplete attendance from previous days
    cleanup_incomplete_attendance(emp.id)
    
    # Get today's attendance
    attendance = Attendance.query.filter_by(employee_id=emp.id, date=today).first()
    
    # Get branch name
    branch_name = emp.branch.name if emp.branch else "No Branch Assigned"
    
    return render_template(
        "dashboard_employee.html",
        employee=emp,
        attendance=attendance,
        today=today,
        branch_name=branch_name,
        format_time=format_time_12hour
    )

@employee_bp.route("/attendance/in", methods=["POST"])
@login_required
def attendance_in():
    """Mark IN attendance"""
    emp = Employee.query.get(session["user_id"])
    photo_file = request.files.get("photo")
    
    # Process attendance with automatic GPS extraction only
    success, message = process_attendance(emp, photo_file, "in")
    
    if success:
        flash(message, "success")
    else:
        flash(message, "danger")
    
    return redirect(url_for("employee.employee_dashboard"))

@employee_bp.route("/attendance/out", methods=["POST"])
@login_required
def attendance_out():
    """Mark OUT attendance"""
    emp = Employee.query.get(session["user_id"])
    photo_file = request.files.get("photo")
    
    # Check if employee has in-attendance for today
    today = datetime.now().date()
    attendance = Attendance.query.filter_by(employee_id=emp.id, date=today).first()
    
    if not attendance or not attendance.in_time:
        flash("You must mark IN attendance before marking OUT attendance.", "danger")
        return redirect(url_for("employee.employee_dashboard"))
    
    # Process attendance with automatic GPS extraction only
    success, message = process_attendance(emp, photo_file, "out")
    
    if success:
        flash(message, "success")
    else:
        flash(message, "danger")
    
    return redirect(url_for("employee.employee_dashboard"))

@employee_bp.route("/logout")
@login_required
def logout():
    """Employee logout"""
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("employee.employee_login"))

@employee_bp.route("/employee/profile", methods=["GET", "POST"])
@login_required
def employee_profile():
    """Employee profile management"""
    emp = Employee.query.get(session["user_id"])
    if not emp:
        flash("Employee not found.", "danger")
        return redirect(url_for("employee.employee_login"))

    if request.method == "POST":
        emp.name = request.form.get("name") or emp.name
        emp.email = request.form.get("email") or emp.email
        emp.contact_no = request.form.get("contact_no") or emp.contact_no
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("employee.employee_profile"))

    return render_template("employee_profile.html", employee=emp)

# ----------------- API Routes -----------------

@employee_bp.route("/api/attendance/status")
@login_required
def get_attendance_status():
    """API endpoint to get current attendance status"""
    emp = Employee.query.get(session["user_id"])
    today = datetime.now().date()
    attendance = Attendance.query.filter_by(employee_id=emp.id, date=today).first()
    
    if attendance:
        return jsonify({
            "has_in": bool(attendance.in_time),
            "has_out": bool(attendance.out_time),
            "status": attendance.status,
            "in_time": format_time_12hour(attendance.in_time) if attendance.in_time else None,
            "out_time": format_time_12hour(attendance.out_time) if attendance.out_time else None,
            "working_hours": attendance.working_hours,
            "pending_approval": attendance.pending_approval
        })
    else:
        return jsonify({
            "has_in": False,
            "has_out": False,
            "status": "Not marked",
            "pending_approval": False
        })

# ----------------- Debug Routes -----------------

@employee_bp.route("/debug/gps", methods=["GET", "POST"])
@login_required
def debug_gps():
    """Debug route for GPS testing"""
    if request.method == "POST":
        photo_file = request.files.get("photo")
        if not photo_file:
            return "No photo uploaded"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
            photo_file.save(tmp_file.name)
            temp_path = tmp_file.name
        
        try:
            lat, lon = extract_gps_from_photo(temp_path)
            if lat is not None and lon is not None:
                address = get_address_from_coordinates(lat, lon)
                return f"""
                <h2>GPS Debug Results</h2>
                <p><strong>Coordinates:</strong> {lat:.8f}, {lon:.8f}</p>
                <p><strong>Address:</strong> {address}</p>
                <p><strong>Google Maps:</strong> <a href='https://maps.google.com/?q={lat},{lon}' target='_blank'>View Location</a></p>
                <p><strong>Time:</strong> {format_time_12hour(datetime.now())}</p>
                """
            else:
                return "<p style='color:red'>No GPS data found in photo</p>"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    return '''
    <h2>GPS Debug Tool</h2>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="photo" accept="image/*" required>
        <button type="submit">Test GPS Extraction</button>
    </form>
    '''

@employee_bp.route("/debug/time-validation", methods=["GET", "POST"])
@login_required
def debug_time_validation():
    """Debug route for time validation testing"""
    if request.method == "POST":
        photo_file = request.files.get("photo")
        if not photo_file:
            return "No photo uploaded"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
            photo_file.save(tmp_file.name)
            temp_path = tmp_file.name
        
        try:
            from utils.gps_extractor import extract_datetime_from_text_overlay, validate_photo_time
            
            # Extract datetime from photo
            extracted_datetime, ok = extract_datetime_from_text_overlay(temp_path)
            
            result = f"<h2>Time Validation Debug Results</h2>"
            result += f"<p><strong>Photo:</strong> {photo_file.filename}</p>"
            
            if extracted_datetime:
                upload_time = datetime.now()  # Simulate upload time
                time_diff = abs((extracted_datetime - upload_time).total_seconds() / 60)
                
                result += f"<p><strong>Photo Time (from GPS overlay):</strong> {extracted_datetime.strftime('%d/%m/%Y %I:%M:%S %p')}</p>"
                result += f"<p><strong>Upload Time (current system time):</strong> {upload_time.strftime('%d/%m/%Y %I:%M:%S %p')}</p>"
                result += f"<p><strong>Time Difference:</strong> {time_diff:.1f} minutes</p>"
                
                # Test validation
                time_valid, time_message = validate_photo_time(extracted_datetime, upload_time, max_minutes_diff=10)
                result += f"<p><strong>Validation Result:</strong> {time_message}</p>"
                
                if time_valid:
                    result += "<p style='color:green'><strong>✅ TIME VALID</strong></p>"
                else:
                    result += "<p style='color:red'><strong>❌ TIME INVALID</strong></p>"
            else:
                result += "<p style='color:red'><strong>❌ NO TIME EXTRACTED FROM PHOTO</strong></p>"
            
            return result
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    return '''
    <h2>Time Validation Debug Tool</h2>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="photo" accept="image/*" required>
        <button type="submit">Test Time Validation</button>
    </form>
    '''

@employee_bp.route("/debug/gps-detailed", methods=["GET", "POST"])
@login_required
def debug_gps_detailed():
    """Comprehensive GPS debugging tool"""
    if request.method == "POST":
        photo_file = request.files.get("photo")
        if not photo_file:
            return "No photo uploaded"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
            photo_file.save(tmp_file.name)
            temp_path = tmp_file.name
        
        try:
            # Detailed analysis
            image = Image.open(temp_path)
            result = f"<h2>Photo Analysis Report</h2>"
            result += f"<p><strong>File:</strong> {photo_file.filename}</p>"
            result += f"<p><strong>Format:</strong> {image.format}</p>"
            result += f"<p><strong>Size:</strong> {image.size}</p>"
            
            # Check EXIF data
            exif_data = None
            if hasattr(image, '_getexif'):
                exif_data = image._getexif()
            elif hasattr(image, 'getexif'):
                exif_data = image.getexif()
            
            if not exif_data:
                result += "<p><strong style='color:red'>NO EXIF DATA FOUND</strong></p>"
                result += "<p>This photo does not contain any metadata. Possible reasons:</p>"
                result += "<ul><li>Photo was edited/processed and metadata was stripped</li>"
                result += "<li>Photo was downloaded from internet</li>"
                result += "<li>Camera app doesn't save metadata</li>"
                result += "<li><strong>GPS overlay apps only add visual text, not EXIF data</strong></li></ul>"
            else:
                result += f"<p><strong style='color:green'>EXIF data found:</strong> {len(exif_data)} tags</p>"
                
                # List all EXIF tags
                result += "<h3>All EXIF Tags:</h3><ul>"
                gps_found = False
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, f"Tag_{tag_id}")
                    if tag_name == "GPSInfo":
                        gps_found = True
                        result += f"<li><strong style='color:blue'>{tag_name}</strong>: {value}</li>"
                    else:
                        result += f"<li>{tag_name}: {str(value)[:100]}{'...' if len(str(value)) > 100 else ''}</li>"
                result += "</ul>"
                
                if not gps_found:
                    result += "<p><strong style='color:red'>NO GPS INFO FOUND</strong></p>"
                    result += "<p>EXIF data exists but no GPS information. Possible reasons:</p>"
                    result += "<ul><li>Location services were disabled when photo was taken</li>"
                    result += "<li>Camera app doesn't have location permission</li>"
                    result += "<li>Photo was taken with GPS disabled</li>"
                    result += "<li><strong>GPS overlay apps only add visual text, not EXIF data</strong></li></ul>"
                else:
                    # Try to extract GPS
                    lat, lon = extract_gps_from_photo(temp_path)
                    if lat is not None and lon is not None:
                        result += f"<p><strong style='color:green'>GPS EXTRACTION SUCCESSFUL</strong></p>"
                        result += f"<p><strong>Coordinates:</strong> {lat:.8f}, {lon:.8f}</p>"
                        result += f"<p><strong>Google Maps:</strong> <a href='https://maps.google.com/?q={lat},{lon}' target='_blank'>View Location</a></p>"
                        
                        # Get address
                        address = get_address_from_coordinates(lat, lon)
                        result += f"<p><strong>Address:</strong> {address}</p>"
                        
                        # Check site proximity
                        emp = Employee.query.get(session["user_id"])
                        employee_sites = Site.query.filter_by(branch_id=emp.branch_id).all()
                        within_range, matched_site, distance = is_within_site_range(lat, lon, employee_sites)
                        
                        if within_range:
                            result += f"<p><strong style='color:green'>SITE PROXIMITY:</strong> Within range of {matched_site.name} ({distance:.2f}km)</p>"
                        else:
                            result += f"<p><strong style='color:orange'>SITE PROXIMITY:</strong> Outside range (closest: {distance:.2f}km)</p>"
                        
                    else:
                        result += "<p><strong style='color:red'>GPS EXTRACTION FAILED</strong></p>"
                        result += "<p>GPS data exists but couldn't be parsed. Check application logs for details.</p>"
            
            return result
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    return '''
    <h2>GPS Photo Debugger</h2>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="photo" accept="image/*" required>
        <button type="submit">Analyze Photo</button>
    </form>
    <h3>How to ensure GPS photos:</h3>
    <ol>
        <li>Enable Location Services on your device</li>
        <li>Grant location permission to your camera app</li>
        <li>Take a NEW photo (don't use gallery photos)</li>
        <li>Ensure GPS/location icon appears when taking photo</li>
        <li>Don't edit or process the photo before uploading</li>
        <li><strong>Don't use GPS overlay apps - they only add visual text, not EXIF data</strong></li>
    </ol>
    <h3>Important Note:</h3>
    <p style="color:red; font-weight:bold;">
    GPS overlay apps (like "GPS Map Camera") only add visual text/watermarks to photos. 
    They do NOT embed GPS coordinates in the photo's EXIF metadata, which is what our system reads.
    You need to use your device's native camera app with location services enabled.
    </p>
    '''

@employee_bp.route("/cleanup-attendance")
def cleanup_attendance():
    """Manual cleanup route for incomplete attendance records"""
    try:
        cleanup_all_incomplete_attendance()
        return "Daily attendance cleanup completed successfully!"
    except Exception as e:
        current_app.logger.error(f"Cleanup failed: {e}")
        return f"Cleanup failed: {str(e)}", 500

@employee_bp.route("/clear-today-attendance")
@login_required
def clear_today_attendance():
    """Clear today's attendance record for current employee (for testing)"""
    try:
        emp = Employee.query.get(session["user_id"])
        today = datetime.now().date()
        
        # Find and delete today's attendance record
        today_attendance = Attendance.query.filter_by(employee_id=emp.id, date=today).first()
        if today_attendance:
            db.session.delete(today_attendance)
            db.session.commit()
            current_app.logger.info(f"Cleared today's attendance for employee {emp.name}")
            flash("Today's attendance cleared successfully!", "success")
        else:
            flash("No attendance record found for today.", "info")
        
        return redirect(url_for("employee.employee_dashboard"))
    except Exception as e:
        current_app.logger.error(f"Failed to clear today's attendance: {e}")
        flash(f"Failed to clear attendance: {str(e)}", "danger")
        return redirect(url_for("employee.employee_dashboard"))