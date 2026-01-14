from flask import Flask
from app.db import db

def create_app_for_db():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///planner.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app

if __name__ == "__main__":
    app = create_app_for_db()
    with app.app_context():
        db.create_all()
        print("✅ planner.db created / tables ensured")