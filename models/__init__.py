from extensions import db

# Import all models here
from .admin import Admin
from .branch import Branch
from .employee import Employee
from .site import Site

# Export them for easy import
__all__ = ["Admin", "Branch", "Employee", "Site", "db","Attendance","AttendanceApproval"]
