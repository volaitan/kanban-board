"""Kanban board: a small Flask + SQLite app for running agile work."""
import os

from flask import Flask


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "kanban.sqlite"),
        WIP_LIMIT=3,  # max cards allowed in "In Progress"
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from . import db, routes

    db.init_app(app)
    app.register_blueprint(routes.bp)
    return app
