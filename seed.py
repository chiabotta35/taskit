import os
from app import create_app, db
from app.models import User


def seed():
    app = create_app()
    with app.app_context():
        admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        admin_password = os.environ.get("ADMIN_PASSWORD", "changeme")

        existing = User.query.filter_by(username=admin_username).first()
        if not existing:
            admin = User(
                username=admin_username,
                email=admin_email,
                is_admin=True,
                is_owner=True,
                is_active_user=True,
            )
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            print(f"[seed] Admin user '{admin_username}' created.")
        else:
            print(f"[seed] Admin user '{admin_username}' already exists, skipping.")


if __name__ == "__main__":
    seed()
