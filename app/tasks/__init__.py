import os
import uuid
from datetime import date
from pathlib import Path

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_from_directory, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, HiddenField
from wtforms.validators import DataRequired, Optional

from ..models import (
    db, Task, Comment, User, Label, TaskLabel, TaskDependency,
    Attachment, PROJECT_STATUSES, log_activity, notify,
)
from ..webhooks import fire_webhook, build_task_payload, build_comment_payload

tasks_bp = Blueprint("tasks", __name__, url_prefix="/tasks")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "txt", "log", "csv", "json", "zip", "tar", "gz"}


class TaskForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    description = TextAreaField("Description")
    status = SelectField("Status", choices=[(s, s.replace("_", " ").title()) for s in ["todo", "in_progress", "review", "done"]])
    priority = SelectField("Priority", choices=[(p, p.title()) for p in ["low", "medium", "high", "critical"]])
    assignee_id = SelectField("Assignee", coerce=lambda x: int(x) if x and str(x).strip() else None)
    due_date = StringField("Due Date", validators=[Optional()])
    project_id = HiddenField("Project ID")
    labels = HiddenField("Labels")
    blocked_by = HiddenField("Blocked By")


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


def _next_task_number(project_id):
    max_num = db.session.query(db.func.max(Task.task_number)).filter_by(project_id=project_id).scalar()
    return (max_num or 0) + 1


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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
    task_labels = [tl.label for tl in task.task_labels]
    blocked_by_tasks = [d.blocked_by for d in task.blocking]
    blocking_tasks = [d.task for d in task.blocks]
    attachments = task.attachments
    from ..models import Subtask, TimeEntry
    subtasks = Subtask.query.filter_by(task_id=task_id).order_by(Subtask.position).all()
    time_entries = TimeEntry.query.filter_by(task_id=task_id).order_by(TimeEntry.started_at.desc()).all()
    return render_template(
        "tasks/detail.html", task=task, form=form, comments=comments,
        task_labels=task_labels, blocked_by_tasks=blocked_by_tasks,
        blocking_tasks=blocking_tasks, attachments=attachments,
        subtasks=subtasks, time_entries=time_entries,
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
    labels = Label.query.filter_by(project_id=project_id).order_by(Label.name).all()
    existing_tasks = Task.query.filter_by(project_id=project_id).order_by(Task.task_number).all()
    if form.validate_on_submit():
        max_pos = db.session.query(db.func.max(Task.position)).filter_by(
            project_id=project_id
        ).scalar() or 0
        due = None
        if form.due_date.data:
            try:
                due = date.fromisoformat(form.due_date.data)
            except (ValueError, TypeError):
                pass
        task = Task(
            project_id=project_id,
            task_number=_next_task_number(project_id),
            title=form.title.data,
            description=form.description.data,
            status=form.status.data,
            priority=form.priority.data,
            assignee_id=form.assignee_id.data,
            created_by=current_user.id,
            position=max_pos + 1,
            due_date=due,
        )
        db.session.add(task)
        db.session.flush()
        selected = form.labels.data or ""
        for lid in selected.split(","):
            lid = lid.strip()
            if lid.isdigit():
                db.session.add(TaskLabel(task_id=task.id, label_id=int(lid)))
        blocked = form.blocked_by.data or ""
        for bid in blocked.split(","):
            bid = bid.strip()
            if bid.isdigit() and int(bid) != task.id:
                db.session.add(TaskDependency(task_id=task.id, blocked_by_id=int(bid)))
        log_activity(project_id, current_user.id, "created", "task", task.id, task.title)
        if task.assignee_id and task.assignee_id != current_user.id:
            notify(task.assignee_id, f"Assigned to {task.display_id}: {task.title}", url=f"/tasks/{task.id}")
        db.session.commit()
        fire_webhook("task.created", build_task_payload(task, "created"))
        flash(f"Task '{task.title}' created.", "success")
        return redirect(url_for("tasks.detail_task", task_id=task.id))
    return render_template(
        "tasks/form.html", form=form, title="Create Task", project=project,
        labels=labels, existing_tasks=existing_tasks,
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
    labels = Label.query.filter_by(project_id=task.project_id).order_by(Label.name).all()
    existing_label_ids = [str(tl.label_id) for tl in task.task_labels]
    existing_dep_ids = [str(d.blocked_by_id) for d in task.blocking]
    existing_tasks = Task.query.filter(Task.project_id == task.project_id, Task.id != task.id).order_by(Task.task_number).all()
    if form.validate_on_submit():
        old_status = task.status
        old_assignee = task.assignee_id
        task.title = form.title.data
        task.description = form.description.data
        task.status = form.status.data
        task.priority = form.priority.data
        task.assignee_id = form.assignee_id.data
        task.due_date = None
        if form.due_date.data:
            try:
                task.due_date = date.fromisoformat(form.due_date.data)
            except (ValueError, TypeError):
                pass
        TaskLabel.query.filter_by(task_id=task.id).delete()
        selected = form.labels.data or ""
        for lid in selected.split(","):
            lid = lid.strip()
            if lid.isdigit():
                db.session.add(TaskLabel(task_id=task.id, label_id=int(lid)))
        TaskDependency.query.filter_by(task_id=task.id).delete()
        blocked = form.blocked_by.data or ""
        for bid in blocked.split(","):
            bid = bid.strip()
            if bid.isdigit() and int(bid) != task.id:
                db.session.add(TaskDependency(task_id=task.id, blocked_by_id=int(bid)))
        db.session.commit()
        fire_webhook("task.updated", build_task_payload(task, "updated"))
        if task.status != old_status:
            fire_webhook("task.status_changed", build_task_payload(task, "status_changed"))
        if task.assignee_id and task.assignee_id != old_assignee and task.assignee_id != current_user.id:
            notify(task.assignee_id, f"Assigned to {task.display_id}: {task.title}", url=f"/tasks/{task.id}")
        flash(f"Task '{task.title}' updated.", "success")
        return redirect(url_for("tasks.detail_task", task_id=task.id))
    if task.due_date:
        form.due_date.data = task.due_date.isoformat()
    form.blocked_by.data = ",".join(existing_dep_ids)
    return render_template(
        "tasks/form.html", form=form, title="Edit Task", project=task.project,
        labels=labels, existing_label_ids=existing_label_ids,
        existing_tasks=existing_tasks, existing_dep_ids=existing_dep_ids,
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
    log_activity(project_id, current_user.id, "deleted", "task", task.id, task.title)
    payload = build_task_payload(task, "deleted")
    db.session.delete(task)
    db.session.commit()
    fire_webhook("task.deleted", payload)
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
        log_activity(task.project_id, current_user.id, "commented", "task", task.id, task.title, detail=form.content.data[:200])
        if task.assignee_id and task.assignee_id != current_user.id:
            notify(task.assignee_id, f"Comment on {task.display_id}: {task.title}", body=form.content.data[:200], url=f"/tasks/{task.id}")
        db.session.commit()
        fire_webhook("comment.created", build_comment_payload(comment, "created"))
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
    new_status = request.form.get("status") if request.form else None
    if not new_status and request.is_json:
        new_status = request.json.get("status")
    if new_status not in ["todo", "in_progress", "review", "done"]:
        return {"error": "invalid status"}, 400
    old_status = task.status
    task.status = new_status
    log_activity(task.project_id, current_user.id, "moved", "task", task.id, task.title, detail=f"{old_status} → {new_status}")
    db.session.commit()
    fire_webhook("task.updated", build_task_payload(task, "updated"))
    if task.status != old_status:
        fire_webhook("task.status_changed", build_task_payload(task, "status_changed"))
    if request.content_type and "json" in request.content_type:
        return {"ok": True, "status": new_status}
    return redirect(url_for("tasks.detail_task", task_id=task_id))


@tasks_bp.route("/<int:task_id>/upload", methods=["POST"])
@login_required
def upload_attachment(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    if not current_user.has_project_permission(task.project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("tasks.detail_task", task_id=task_id))
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "warning")
        return redirect(url_for("tasks.detail_task", task_id=task_id))
    if not _allowed(file.filename):
        flash("File type not allowed.", "warning")
        return redirect(url_for("tasks.detail_task", task_id=task_id))
    upload_dir = Path(current_app.instance_path).parent / "data" / "attachments" / str(task.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[1].lower()
    stored = f"{uuid.uuid4().hex}.{ext}"
    file.save(upload_dir / stored)
    att = Attachment(
        task_id=task.id,
        user_id=current_user.id,
        filename=file.filename,
        stored_name=stored,
        size=os.path.getsize(upload_dir / stored),
        mime_type=file.content_type,
    )
    db.session.add(att)
    db.session.commit()
    flash(f"Uploaded '{file.filename}'.", "success")
    return redirect(url_for("tasks.detail_task", task_id=task_id))


@tasks_bp.route("/attachment/<int:att_id>/download")
@login_required
def download_attachment(att_id):
    att = db.session.get(Attachment, att_id)
    if not att:
        flash("File not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    if not current_user.has_project_permission(att.task.project_id, "viewer"):
        flash("Access denied.", "danger")
        return redirect(url_for("projects.list_projects"))
    upload_dir = Path(current_app.instance_path).parent / "data" / "attachments" / str(att.task_id)
    return send_from_directory(str(upload_dir), att.stored_name, as_attachment=True, download_name=att.filename)


@tasks_bp.route("/attachment/<int:att_id>/delete", methods=["POST"])
@login_required
def delete_attachment(att_id):
    att = db.session.get(Attachment, att_id)
    if not att:
        flash("File not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    if not current_user.has_project_permission(att.task.project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("projects.detail_task", task_id=att.task_id))
    upload_dir = Path(current_app.instance_path).parent / "data" / "attachments" / str(att.task_id)
    fpath = upload_dir / att.stored_name
    if fpath.exists():
        fpath.unlink()
    task_id = att.task_id
    db.session.delete(att)
    db.session.commit()
    flash("File deleted.", "success")
    return redirect(url_for("tasks.detail_task", task_id=task_id))


@tasks_bp.route("/bulk", methods=["POST"])
@login_required
def bulk_action():
    task_ids = request.form.getlist("task_ids")
    action = request.form.get("bulk_action")
    if not task_ids or not action:
        flash("No tasks selected.", "warning")
        return redirect(url_for("projects.list_projects"))
    ids = [int(tid) for tid in task_ids if tid.isdigit()]
    tasks = Task.query.filter(Task.id.in_(ids)).all()
    if not tasks:
        flash("No tasks found.", "warning")
        return redirect(url_for("projects.list_projects"))
    project_id = tasks[0].project_id
    tasks = [t for t in tasks if t.project_id == project_id]
    if action == "delete":
        for t in tasks:
            if current_user.has_project_permission(t.project_id, "admin"):
                log_activity(t.project_id, current_user.id, "deleted", "task", t.id, t.title)
                db.session.delete(t)
        db.session.commit()
        flash(f"Deleted {len(tasks)} task(s).", "success")
    elif action.startswith("status_"):
        new_status = action.replace("status_", "")
        if new_status in ["todo", "in_progress", "review", "done"]:
            for t in tasks:
                if current_user.has_project_permission(t.project_id, "editor"):
                    t.status = new_status
            db.session.commit()
            flash(f"Updated {len(tasks)} task(s) to {new_status}.", "success")
    elif action.startswith("priority_"):
        new_priority = action.replace("priority_", "")
        if new_priority in ["low", "medium", "high", "critical"]:
            for t in tasks:
                if current_user.has_project_permission(t.project_id, "editor"):
                    t.priority = new_priority
            db.session.commit()
            flash(f"Updated {len(tasks)} task(s) to {new_priority}.", "success")
    elif action.startswith("assign_"):
        assignee = action.replace("assign_", "")
        assignee_id = int(assignee) if assignee != "none" else None
        for t in tasks:
            if current_user.has_project_permission(t.project_id, "editor"):
                t.assignee_id = assignee_id
        db.session.commit()
        flash(f"Reassigned {len(tasks)} task(s).", "success")
    return redirect(url_for("projects.detail_project", project_id=project_id))


# ── Subtasks ──

@tasks_bp.route("/<int:task_id>/subtask", methods=["POST"])
@login_required
def add_subtask(task_id):
    task = db.session.get(Task, task_id)
    if not task or not current_user.has_project_permission(task.project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("dashboard.index"))
    title = request.form.get("title", "").strip()
    if not title:
        flash("Subtask title is required.", "warning")
        return redirect(url_for("tasks.detail_task", task_id=task_id))
    from ..models import Subtask
    max_pos = db.session.query(db.func.max(Subtask.position)).filter_by(task_id=task_id).scalar()
    sub = Subtask(task_id=task_id, title=title, position=(max_pos or 0) + 1)
    db.session.add(sub)
    db.session.commit()
    return redirect(url_for("tasks.detail_task", task_id=task_id))


@tasks_bp.route("/subtask/<int:subtask_id>/toggle", methods=["POST"])
@login_required
def toggle_subtask(subtask_id):
    from ..models import Subtask
    sub = db.session.get(Subtask, subtask_id)
    if not sub:
        flash("Not found.", "danger")
        return redirect(url_for("dashboard.index"))
    task = db.session.get(Task, sub.task_id)
    if not task or not current_user.has_project_permission(task.project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("dashboard.index"))
    sub.is_done = not sub.is_done
    db.session.commit()
    return redirect(url_for("tasks.detail_task", task_id=sub.task_id))


@tasks_bp.route("/subtask/<int:subtask_id>/delete", methods=["POST"])
@login_required
def delete_subtask(subtask_id):
    from ..models import Subtask
    sub = db.session.get(Subtask, subtask_id)
    if not sub:
        flash("Not found.", "danger")
        return redirect(url_for("dashboard.index"))
    task = db.session.get(Task, sub.task_id)
    if not task or not current_user.has_project_permission(task.project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("dashboard.index"))
    task_id = sub.task_id
    db.session.delete(sub)
    db.session.commit()
    return redirect(url_for("tasks.detail_task", task_id=task_id))
