import os

from flask import Flask
from sqlalchemy import inspect

from models import db


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


def init_database():
    with app.app_context():
        db.create_all()

        inspector = inspect(db.engine)

        print("Database connected successfully!")
        print("Database:", db.engine.url.database)

        print("\nTables:")
        for table in inspector.get_table_names():
            print(f"- {table}")


if __name__ == "__main__":
    init_database()
    