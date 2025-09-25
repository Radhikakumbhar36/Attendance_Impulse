# Attendance Impulse System

A comprehensive attendance management system with GPS photo verification, face recognition, and automated reporting.

## Features

### Employee Features
- **GPS Photo Attendance**: Employees mark attendance by uploading photos with GPS coordinates
- **Face Recognition**: Automatic face verification against stored employee photos
- **Location Validation**: Attendance is only accepted if within 1km of assigned site
- **Real-time Status**: View current attendance status, working hours, and pending approvals
- **Profile Management**: Update personal information and view attendance history

### Admin Features
- **Attendance Approval**: Review and approve attendance requests from employees outside site range
- **Comprehensive Reports**: Date-wise attendance reports with detailed analytics
- **Employee Management**: Add, edit, and manage employee records with photos
- **Branch & Site Management**: Manage branches and their associated sites
- **Excel Export**: Export attendance reports to Excel format
- **Real-time Dashboard**: View daily attendance summary and pending approvals

### System Features
- **Automatic Status Calculation**: 
  - Full Day: IN between 7:45 AM - 8:15 AM, OUT after 6:00 PM
  - Half Day: IN after 8:15 AM or OUT before 6:00 PM
  - Absent: No attendance marked
- **Working Hours Calculation**: Automatic calculation of total working hours
- **Location-based Validation**: GPS coordinates must be within 1km of assigned site
- **Pending Approval System**: Admin approval required for location mismatches

## Installation

### Prerequisites
- Python 3.8+
- PostgreSQL database
- Camera with GPS capabilities (for employees)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Attendance_Impulse
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   Create a `.env` file in the root directory:
   ```env
   DATABASE_URL=postgresql://username:password@localhost/attendance_db
   SECRET_KEY=your-secret-key-here
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-app-password
   ```

5. **Run database migration**
   ```bash
   python migrate_database.py
   ```

6. **Run in production**
   ```bash
   # Windows (Waitress)
   python -m waitress --listen=0.0.0.0:5000 app:app
   # Linux (Gunicorn)
   gunicorn -w 3 -b 0.0.0.0:5000 app:app
   ```

Logs: see `logs/app.log` (rotating).

## Usage

### Employee Login
1. Navigate to the employee login page
2. Use Employee ID or Email to login
3. Upload GPS photo for IN/OUT attendance
4. System will verify face and location automatically

### Admin Login
1. Navigate to the admin login page
2. Use Admin ID or Email to login
3. Access dashboard to view attendance summary
4. Approve/reject pending attendance requests
5. Generate and export attendance reports

### GPS Photo Requirements
- Enable location services on your device
- Grant camera location permissions
- Take a NEW photo (don't use gallery photos)
- Ensure GPS icon appears when taking photo
- Don't edit or process the photo before uploading

## Database Schema

### Key Tables

#### Attendance
- `id`: Primary key
- `employee_id`: Foreign key to Employee
- `date`: Attendance date
- `in_time`, `out_time`: Timestamps
- `in_photo`, `out_photo`: Photo filenames
- `in_latitude`, `in_longitude`: GPS coordinates for IN
- `out_latitude`, `out_longitude`: GPS coordinates for OUT
- `in_address`, `out_address`: Reverse geocoded addresses
- `site_id`: Foreign key to Site
- `status`: Full Day, Half Day, or Absent
- `working_hours`: Calculated working hours
- `pending_approval`: Boolean for approval status

#### AttendanceApproval
- `id`: Primary key
- `employee_id`: Foreign key to Employee
- `attendance_id`: Foreign key to Attendance
- `date`: Attendance date
- `attendance_type`: "in" or "out"
- `photo`: Photo filename
- `latitude`, `longitude`: GPS coordinates
- `address`: Reverse geocoded address
- `time`: Attendance timestamp
- `status`: Pending, Approved, or Rejected
- `remarks`: Admin remarks
- `created_at`, `approved_at`: Timestamps
- `approved_by`: Foreign key to Admin

#### Site
- `id`: Primary key
- `name`: Site name
- `address`: Site address
- `latitude`, `longitude`: GPS coordinates
- `branch_id`: Foreign key to Branch

## API Endpoints

### Employee Routes
- `GET /` - Employee login page
- `POST /` - Employee login
- `GET /employee/dashboard` - Employee dashboard
- `POST /attendance/in` - Mark IN attendance
- `POST /attendance/out` - Mark OUT attendance
- `GET /employee/profile` - Employee profile
- `POST /employee/profile` - Update profile
- `GET /api/attendance/status` - Get attendance status (JSON)

### Admin Routes
- `GET /admin/login` - Admin login page
- `POST /admin/login` - Admin login
- `GET /admin/dashboard` - Admin dashboard
- `GET /admin/employees` - Employee management
- `GET /admin/branches` - Branch management
- `GET /admin/reports/attendance` - Attendance reports
- `GET /admin/reports/attendance/export` - Export reports
- `POST /admin/attendance/approve/<id>` - Approve attendance
- `POST /admin/attendance/reject/<id>` - Reject attendance

## Configuration

### File Upload Settings
- Maximum file size: 16MB
- Allowed extensions: PNG, JPG, JPEG, GIF
- Upload folder: `static/uploads/`

### GPS Settings
- Site proximity radius: 1km
- GPS coordinate validation: -90 to 90 (lat), -180 to 180 (lon)

### Attendance Rules
- Valid IN time: 7:45 AM to 8:15 AM
- Valid OUT time: After 6:00 PM
- Full Day: Valid IN + Valid OUT
- Half Day: Either IN or OUT (but not both valid)
- Absent: No attendance marked

## Troubleshooting

### Common Issues

1. **GPS not detected in photos**
   - Ensure location services are enabled
   - Grant camera location permissions
   - Take a new photo (don't use gallery)
   - Check if GPS icon appears when taking photo

2. **Face recognition fails**
   - Ensure employee has a clear photo in database
   - Take photo with good lighting
   - Ensure single face is visible
   - Check if photo is not too blurry

3. **Location mismatch**
   - Verify site coordinates are correct
   - Check if employee is within 1km of site
   - Contact admin for approval if location is valid

4. **Database connection issues**
   - Check DATABASE_URL in .env file
   - Ensure PostgreSQL is running
   - Verify database credentials

### Debug Tools
- `/debug/gps` - Test GPS extraction from photos
- `/debug/gps-detailed` - Comprehensive GPS analysis

## Security Features

- Password hashing with bcrypt
- Session management
- File upload validation
- SQL injection protection
- XSS protection
- CSRF protection

## Performance Considerations

- Face recognition processing time: ~2-3 seconds
- GPS extraction time: ~1-2 seconds
- Photo storage: Local filesystem
- Database indexing on frequently queried fields

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For support and questions, please contact the development team or create an issue in the repository.