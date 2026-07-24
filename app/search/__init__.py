from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from ..models import db, Task, Project, User, Label, ProjectPermission, GroupMembership

search_bp = Blueprint("search", __name__, url_prefix="/search")


def _accessible_project_ids(user):
    if user.can_manage_all_projects():
        return None
    project_ids = set()
    for perm in ProjectPermission.query.filter_by(user_id=user.id).all():
        project_ids.add(perm.project_id)
    for m in user.group_memberships:
        for perm in ProjectPermission.query.filter_by(group_id=m.group_id).all():
            project_ids.add(perm.project_id)
    return project_ids


@search_bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    label_id = request.args.get("label_id", "")
    project_id = request.args.get("project_id", "")
    assignee_id = request.args.get("assignee_id", "")

    results = []
    if q:
        query = db.session.query(Task).join(Project)

        accessible = _accessible_project_ids(current_user)
        if accessible is not None:
            query = query.filter(Project.id.in_(accessible))

        from sqlalchemy import or_, func
        task_num = None
        if q.isdigit():
            task_num = int(q)
        if task_num is not None:
            query = query.filter(or_(
                Task.title.ilike(f"%{q.replace('%', '%%').replace('_', '\\_')}%"),
                Task.description.ilike(f"%{q.replace('%', '%%').replace('_', '\\_')}%"),
                Task.task_number == task_num,
            ))
        else:
            escaped = q.replace("%", "%%").replace("_", "\\_")
            query = query.filter(or_(
                Task.title.ilike(f"%{escaped}%"),
                Task.description.ilike(f"%{escaped}%"),
            ))

        if status:
            query = query.filter(Task.status == status)
        if priority:
            query = query.filter(Task.priority == priority)
        if assignee_id and assignee_id.isdigit():
            query = query.filter(Task.assignee_id == int(assignee_id))
        if project_id and project_id.isdigit():
            query = query.filter(Task.project_id == int(project_id))
        if label_id and label_id.isdigit():
            query = query.join(Task.task_labels).filter(Label.id == int(label_id))

        results = query.order_by(Task.updated_at.desc()).all()

    all_projects = Project.query.order_by(Project.name).all()
    all_users = User.query.filter_by(is_active_user=True).order_by(User.username).all()

    return render_template(
        "search/index.html",
        q=q, status=status, priority=priority, label_id=label_id,
        project_id=project_id, assignee_id=assignee_id,
        results=results, all_projects=all_projects, all_users=all_users,
    )
