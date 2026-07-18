from datetime import date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from ..models import db, Project, Task, ProjectPermission, GroupMembership

global_gantt_bp = Blueprint("global_gantt", __name__, url_prefix="/timeline")


def _visible_project_ids(user):
    if user.can_manage_all_projects():
        return [p.id for p in Project.query.all()]
    ids = set()
    for perm in ProjectPermission.query.filter(ProjectPermission.user_id == user.id).all():
        ids.add(perm.project_id)
    for m in user.group_memberships:
        for perm in ProjectPermission.query.filter(ProjectPermission.group_id == m.group_id).all():
            ids.add(perm.project_id)
    return list(ids)


@global_gantt_bp.route("/")
@login_required
def view():
    project_ids = _visible_project_ids(current_user)
    tasks = (
        Task.query
        .filter(Task.project_id.in_(project_ids), Task.due_date.isnot(None))
        .order_by(Task.position, Task.created_at)
        .all()
    )

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

    status_colors = {
        "todo": "var(--text-muted)",
        "in_progress": "var(--primary)",
        "review": "var(--warning)",
        "done": "var(--success)",
    }

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
        color = status_colors.get(t.status, "var(--primary)")
        task_bars.append({
            "task": t,
            "left": bar_left,
            "width": max(bar_width, 20),
            "color": color,
        })

    today_offset = (today - min_date).days * (600 / max(len(days), 1))

    return render_template(
        "gantt/global.html",
        tasks=tasks, days=days, task_bars=task_bars,
        today=today, today_offset=today_offset,
        min_date=min_date, max_date=max_date,
    )
