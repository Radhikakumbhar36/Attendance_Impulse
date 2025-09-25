from app import app, db, bcrypt
from models.admin import Admin
from models.employee import Employee

with app.app_context():
    print("Creating DB tables...")
    db.create_all()

    if not Admin.query.filter_by(admin_id="ADM001").first():
        admin_pw = bcrypt.generate_password_hash("AdminPass123").decode("utf-8")
        admin = Admin(name="Radhika Kumbhar", email="radhikakumbhar2978@gmail.com", admin_id="ADM001", keyword="admin-Impulse", password_hash=admin_pw)
        db.session.add(admin)
        print("Sample admin: ADM001 / AdminPass123")

    if not Employee.query.filter_by(employee_id="EMP001").first():
        emp_pw = bcrypt.generate_password_hash("EmpPass123").decode("utf-8")
        emp = Employee(employee_id="EMP001", name="Onkar Mane", email="onkarmane@gmail.com", password_hash=emp_pw)
        db.session.add(emp)
        print("Sample employee: EMP001 / EmpPass123")

    db.session.commit()
    print("Done.")