from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, HiddenField
from wtforms.validators import DataRequired

from ..models import db, Task, Comment, User, PROJECT_STATUSES

tasks_bp = Blueprint("tasks", __name__, url_prefix="/tasks")


class TaskForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    description = TextAreaField("Description")
    status = SelectField("Status", choices=[(s, s.replace("_", " ").title()) for s in ["todo", "in_progress", "review", "done"]])
    priority = SelectField("Priority", choices=[(p, p.title()) for p in ["low", "medium", "high", "critical"]])
    assignee_id = SelectField("Assignee", coerce=lambda x: int(x) if x else None)
    project_id = HiddenField("Project ID")


class CommentForm(FlaskForm):
    content = TextAreaField("Comment", validators=[DataRequired()])


def _assignee_choices(project_id):
    from ..models import ProjectPermission, GroupMembership
    user_ids = set()
    for perm in ProjectPermission.query.filter_by(project_id=project_id).all():
        if perm.user_id:
            user_ids.add(perm.user_id)
        if perm.group_id:
            for m in GroupMembership.query.filter_by(group_id=perm.group_id).all():
                user_ids.add(m.user_id)
    if not user_ids:
        user_ids = {u.id for u in User.query.filter_by(is_active_user=True).all()}
    users = User.query.filter(User.id.in_(user_ids)).order_by(User.username).all()
    return [(None, "-- Unassigned --")] + [(u.id, u.username) for u in users]


@tasks_bp.route("/<int:task_id>")
@login_required
def detail_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    if not current_user.has_project_permission(task.project_id, "viewer"):
        flash("Access denied.", "danger")
        return redirect(url_for("projects.list_projects"))
    form = CommentForm()
    comments = task.comments.order_by(Comment.created_at).all()
    return render_template(
        "tasks/detail.html", task=task, form=form, comments=comments
    )


@tasks_bp.route("/project/<int:project_id>/create", methods=["GET", "POST"])
@login_required
def create_task(project_id):
    if not current_user.has_project_permission(project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("projects.list_projects"))
    from ..models import Project
    project = db.session.get(Project, project_id)
    if not project:
        flash("Project not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    form = TaskForm()
    form.assignee_id.choices = _assignee_choices(project_id)
    form.project_id.data = str(project_id)
    if form.validate_on_submit():
        max_pos = db.session.query(db.func.max(Task.position)).filter_by(
            project_id=project_id
        ).scalar() or 0
        task = Task(
            project_id=project_id,
            title=form.title.data,
            description=form.description.data,
            status=form.status.data,
            priority=form.priority.data,
            assignee_id=form.assignee_id.data,
            created_by=current_user.id,
            position=max_pos + 1,
        )
        db.session.add(task)
        db.session.commit()
        flash(f"Task '{task.title}' created.", "success")
        return redirect(url_for("tasks.detail_task", task_id=task.id))
    return render_template(
        "tasks/form.html", form=form, title="Create Task", project=project
    )


@tasks_bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    if not current_user.has_project_permission(task.project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("tasks.detail_task", task_id=task_id))
    form = TaskForm(obj=task)
    form.assignee_id.choices = _assignee_choices(task.project_id)
    form.project_id.data = str(task.project_id)
    if form.validate_on_submit():
        task.title = form.title.data
        task.description = form.description.data
        task.status = form.status.data
        task.priority = form.priority.data
        task.assignee_id = form.assignee_id.data
        db.session.commit()
        flash(f"Task '{task.title}' updated.", "success")
        return redirect(url_for("tasks.detail_task", task_id=task.id))
    return render_template(
        "tasks/form.html", form=form, title="Edit Task", project=task.project
    )


@tasks_bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    if not current_user.has_project_permission(task.project_id, "admin"):
        flash("Access denied.", "danger")
        return redirect(url_for("tasks.detail_task", task_id=task_id))
    project_id = task.project_id
    db.session.delete(task)
    db.session.commit()
    flash("Task deleted.", "success")
    return redirect(url_for("projects.detail_project", project_id=project_id))


@tasks_bp.route("/<int:task_id>/comment", methods=["POST"])
@login_required
def add_comment(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    if not current_user.has_project_permission(task.project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("tasks.detail_task", task_id=task_id))
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(
            task_id=task_id, user_id=current_user.id, content=form.content.data
        )
        db.session.add(comment)
        db.session.commit()
        flash("Comment added.", "success")
    return redirect(url_for("tasks.detail_task", task_id=task_id))


@tasks_bp.route("/<int:task_id>/status", methods=["POST"])
@login_required
def update_status(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return {"error": "not found"}, 404
    if not current_user.has_project_permission(task.project_id, "editor"):
        return {"error": "forbidden"}, 403
    new_status = request.form.get("status") or request.json.get("status")
    if new_status not in ["todo", "in_progress", "review", "done"]:
        return {"error": "invalid status"}, 400
    task.status = new_status
    db.session.commit()
    if request.content_type and "json" in request.content_type:
        return {"ok": True, "status": new_status}
    return redirect(url_for("tasks.detail_task", task_id=task_id))
