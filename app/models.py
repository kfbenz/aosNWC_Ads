from app.extensions import db


class Ad(db.Model):
    __tablename__ = "ads"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    customer = db.Column(db.String(150), nullable=False)
    ad_type = db.Column(db.String(50), nullable=False)
    run_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<Ad {self.id} - {self.title}>"
