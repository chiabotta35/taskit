import os
from pathlib import Path
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate

from .config import Config
from .models import db, User

_version_file = Path(__file__).resolve().parent.parent.joinpath("VERSION")
VERSION = os.environ.get("THEYARD_VERSION") or (
    _version_file.read_text().strip() if _version_file.exists() else "dev"
)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    from .auth import auth_bp
    from .projects import projects_bp
    from .tasks import tasks_bp
    from .kanban import kanban_bp
    from .webhooks_ui import webhooks_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(kanban_bp)
    app.register_blueprint(webhooks_bp)

    @app.context_processor
    def inject_globals():
        from .models import TASK_STATUSES, TASK_PRIORITIES, PROJECT_STATUSES

        return {
            "task_statuses": TASK_STATUSES,
            "task_priorities": TASK_PRIORITIES,
            "project_statuses": PROJECT_STATUSES,
            "app_version": VERSION,
        }

    with app.app_context():
        os.makedirs("data", exist_ok=True)
        db.create_all()

    return app
