from datetime import date, timedelta
from collections import Counter

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from ..models import db, Task, User, Project, ProjectPermission, ActivityLog

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


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


@reports_bp.route("/")
@login_required
def index():
    project_ids = _visible_project_ids(current_user)
    is_admin = current_user.can_manage_all_projects()

    target_user_id = request.args.get("user_id", type=int)
    if is_admin and target_user_id:
        user_filter = db.session.get(User, target_user_id)
    elif is_admin:
        user_filter = None
    else:
        user_filter = current_user
        target_user_id = current_user.id

    query = Task.query.filter(Task.project_id.in_(project_ids))
    if user_filter:
        query = query.filter(Task.assignee_id == user_filter.id)

    all_tasks = query.all()
    total = len(all_tasks)
    status_counts = Counter(t.status for t in all_tasks)
    priority_counts = Counter(t.priority for t in all_tasks)
    done_tasks = [t for t in all_tasks if t.status == "done"]
    active_tasks = [t for t in all_tasks if t.status != "done"]
    overdue = [t for t in active_tasks if t.due_date and t.due_date < date.today()]

    # Tasks per project
    project_task_counts = Counter(t.project.name for t in all_tasks)

    # Activity last 14 days
    week_ago = date.today() - timedelta(days=13)
    activity_days = []
    for i in range(14):
        d = week_ago + timedelta(days=i)
        count = ActivityLog.query.filter(
            ActivityLog.project_id.in_(project_ids),
            db.func.date(ActivityLog.created_at) == d,
        ).count()
        activity_days.append({"label": d.strftime("%d"), "day_name": d.strftime("%a"), "count": count})
    max_activity = max((d["count"] for d in activity_days), default=1) or 1

    all_users = User.query.filter_by(is_active_user=True).order_by(User.username).all() if is_admin else []

    return render_template(
        "reports/index.html",
        total=total,
        status_counts=status_counts,
        priority_counts=priority_counts,
        overdue_count=len(overdue),
        done_count=len(done_tasks),
        active_count=len(active_tasks),
        project_task_counts=project_task_counts,
        activity_days=activity_days,
        max_activity=max_activity,
        is_admin=is_admin,
        all_users=all_users,
        target_user=user_filter,
        target_user_id=target_user_id,
    )


@reports_bp.route("/user/<int:user_id>")
@login_required
def user_report(user_id):
    is_admin = current_user.can_manage_all_projects()
    if not is_admin and user_id != current_user.id:
        flash("Access denied.", "danger")
        return redirect(url_for("reports.index"))

    project_ids = _visible_project_ids(current_user)
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("reports.index"))

    tasks = Task.query.filter(
        Task.project_id.in_(project_ids),
        Task.assignee_id == user_id,
    ).all()

    total = len(tasks)
    status_counts = Counter(t.status for t in tasks)
    priority_counts = Counter(t.priority for t in tasks)
    overdue = [t for t in tasks if t.status != "done" and t.due_date and t.due_date < date.today()]

    return render_template(
        "reports/user.html",
        user=user,
        total=total,
        status_counts=status_counts,
        priority_counts=priority_counts,
        overdue_count=len(overdue),
    )
