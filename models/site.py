from extensions import db

class Site(db.Model):
    __tablename__ = "site"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"), nullable=False)
    branch = db.relationship("Branch", back_populates="sites")
    
    def __repr__(self):
        return f"<Site {self.name}>"
