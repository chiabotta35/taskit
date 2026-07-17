from datetime import date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from ..models import db, Project, Task

gantt_bp = Blueprint("gantt", __name__, url_prefix="/gantt")


@gantt_bp.route("/<int:project_id>")
@login_required
def view(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        flash("Project not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    if not current_user.has_project_permission(project_id, "viewer"):
        flash("Access denied.", "danger")
        return redirect(url_for("projects.list_projects"))
    tasks = Task.query.filter_by(project_id=project_id).filter(
        Task.due_date.isnot(None)
    ).order_by(Task.position, Task.created_at).all()

    today = date.today()
    all_dates = [t.due_date for t in tasks if t.due_date]
    if all_dates:
        min_date = min(all_dates) - timedelta(days=1)
        max_date = max(all_dates) + timedelta(days=3)
    else:
        min_date = today - timedelta(days=7)
        max_date = today + timedelta(days=14)

    days = []
    d = min_date
    while d <= max_date:
        days.append(d)
        d += timedelta(days=1)

    task_bars = []
    for t in tasks:
        if not t.due_date:
            continue
        start = t.due_date - timedelta(days=max(1, t.priority == "critical" and 3 or t.priority == "high" and 2 or 1))
        end = t.due_date
        if start < min_date:
            start = min_date
        bar_left = (start - min_date).days * (600 / max(len(days), 1))
        bar_width = max((end - start).days + 1, 1) * (600 / max(len(days), 1))
        status_colors = {
            "todo": "var(--text-muted)",
            "in_progress": "var(--accent)",
            "review": "var(--warning)",
            "done": "var(--success)",
        }
        color = status_colors.get(t.status, "var(--accent)")
        task_bars.append({
            "task": t,
            "left": bar_left,
            "width": max(bar_width, 20),
            "color": color,
        })

    today_offset = (today - min_date).days * (600 / max(len(days), 1))

    return render_template(
        "gantt/view.html", project=project, tasks=tasks,
        days=days, task_bars=task_bars, today=today, today_offset=today_offset,
        min_date=min_date, max_date=max_date,
    )
