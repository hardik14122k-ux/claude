"""Convenience runner so you can `python -m server.run` from the repo root."""
from server import db
from server.app import app
from server.hrms import schema as hrms_db


if __name__ == "__main__":
    db.init_db()
    hrms_db.init_hrms_db()
    app.run(debug=True, host="127.0.0.1", port=5000)
