from extensions import db

class Branch(db.Model):
    __tablename__ = "branch"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    code = db.Column(db.String(50), nullable=False, default="N/A")      # default ensures no null
    city = db.Column(db.String(50), nullable=False, default="Unknown")  # safe default

    # Relationships
    employees = db.relationship(
        "Employee",
        back_populates="branch",
        cascade="all, delete-orphan"
    )
    sites = db.relationship(
        "Site",
        back_populates="branch",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Branch {self.name}>"
