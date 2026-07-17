# TheYard

Lightweight project board for homelab use. Docker-based, multi-user, with RBAC and per-project permissions.

## Features

- **Projects** — create, edit, archive with status tracking
- **Tasks** — assignees, priority levels, status workflow (To Do → In Progress → Review → Done)
- **Kanban Board** — drag-and-drop task management
- **Comments** — thread discussion on tasks
- **Auth & RBAC** — admin, owner, editor, viewer roles
- **Groups** — assign permissions to groups instead of individual users
- **Per-project permissions** — user or group based, project-level access control

## Quick Start

```bash
git clone https://github.com/chiabotta35/theyard.git
cd theyard
cp .env.example .env   # edit with your values
docker compose up --build
```

Access at `http://localhost:5000`.

The admin account is created automatically from your `.env` values on first boot.

## Versioning

The app reads its version from the `VERSION` file, displayed in the nav bar. To release:

```bash
echo "1.0.0" > VERSION
git add VERSION
git commit -m "bump to v1.0.0"
git tag v1.0.0
git push origin main --tags
```

This triggers the CI workflow to build and push a Docker image tagged with the version to GHCR.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change-me-in-production` | Flask secret key |
| `DATABASE_URL` | `sqlite:///data/theyard.db` | Database URI |
| `ADMIN_USERNAME` | `admin` | Initial admin username |
| `ADMIN_EMAIL` | `admin@example.com` | Initial admin email |
| `ADMIN_PASSWORD` | `changeme` | Initial admin password |

## Tech Stack

- Python 3.12 / Flask
- SQLite (via SQLAlchemy)
- Jinja2 templates
- Docker / Gunicorn

## License

MIT
