from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from ..models import db, Project, Task

kanban_bp = Blueprint("kanban", __name__, url_prefix="/kanban")


@kanban_bp.route("/<int:project_id>")
@login_required
def board(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        flash("Project not found.", "danger")
        return redirect(url_for("projects.list_projects"))
    if not current_user.has_project_permission(project_id, "viewer"):
        flash("Access denied.", "danger")
        return redirect(url_for("projects.list_projects"))
    tasks = Task.query.filter_by(project_id=project_id).order_by(
        Task.position, Task.created_at
    ).all()
    columns = {
        "todo": [t for t in tasks if t.status == "todo"],
        "in_progress": [t for t in tasks if t.status == "in_progress"],
        "review": [t for t in tasks if t.status == "review"],
        "done": [t for t in tasks if t.status == "done"],
    }
    return render_template("kanban/board.html", project=project, columns=columns)


@kanban_bp.route("/<int:project_id>/move", methods=["POST"])
@login_required
def move_task(project_id):
    if not current_user.has_project_permission(project_id, "editor"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    task_id = data.get("task_id")
    new_status = data.get("new_status")
    new_position = data.get("new_position", 0)

    if new_status not in ["todo", "in_progress", "review", "done"]:
        return jsonify({"error": "invalid status"}), 400

    task = db.session.get(Task, task_id)
    if not task or task.project_id != project_id:
        return jsonify({"error": "task not found"}), 404

    task.status = new_status
    task.position = new_position
    db.session.commit()
    return jsonify({"ok": True})
