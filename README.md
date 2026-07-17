# Taskit

Lightweight project board for homelab use. Docker-based, multi-user, with RBAC, webhooks, and a clean dark UI.

## Features

### Core
- **Projects** — create, edit, archive with status tracking, color-coded, task prefixes
- **Tasks** — assignees, priority levels, status workflow (To Do → In Progress → Review → Done)
- **Task Labels** — color-coded labels per project for categorization
- **Due Dates** — set deadlines with overdue warnings
- **Task Dependencies** — link blocking/blocked-by relationships
- **Task Numbering** — display IDs like `TSK-001`
- **Recurring Tasks** — schedule tasks to repeat on intervals
- **Bulk Actions** — select multiple tasks and change status/priority/delete

### Views
- **Kanban Board** — drag-and-drop columns by status
- **Gantt Timeline** — visual timeline of tasks with dependencies
- **Dashboard** — overview of your tasks, recent activity, and project stats
- **Search** — full-text search with filters (status, priority, assignee, project)

### Collaboration
- **Comments** — threaded discussion on tasks
- **File Attachments** — attach files to tasks
- **Activity Log** — audit trail for all project changes
- **Notifications** — in-app notification panel with read/unread tracking

### Access Control
- **Auth & RBAC** — login/register, global roles (Admin/Owner), per-project roles (Admin/Editor/Viewer)
- **Groups** — assign permissions to groups instead of individual users
- **Per-project Permissions** — user or group based, project-level access control

### Integrations
- **Webhooks** — fire JSON events to Discord, Slack, or any endpoint on task/comment/project changes

### UI
- **Dark Theme** — 8 accent color themes (green, blue, purple, orange, pink, cyan, amber, light)
- **Collapsible Sidebar** — clean navigation with project list, settings panel, and user profile
- **Settings Panel** — theme switcher, webhooks, user/group management in the sidebar
- **Responsive** — works on desktop and tablet

## Quick Start

```bash
git clone https://github.com/chiabotta35/taskit.git
cd taskit
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
| `DATABASE_URL` | `sqlite:///data/taskit.db` | Database URI |
| `ADMIN_USERNAME` | `admin` | Initial admin username |
| `ADMIN_EMAIL` | `admin@example.com` | Initial admin email |
| `ADMIN_PASSWORD` | `changeme` | Initial admin password |

## Tech Stack

- Python 3.12 / Flask / SQLAlchemy
- SQLite (file-based, mounted as Docker volume)
- Jinja2 templates
- Docker / Gunicorn
- GitHub Actions CI/CD → GHCR

## License

MIT
