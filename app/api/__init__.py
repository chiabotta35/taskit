import hashlib
import secrets
import json
from functools import wraps
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g
from flask_login import login_required, current_user

from .. import limiter
from ..models import (
    db, User, Project, Task, Comment, ApiToken, TaskTemplate,
    ProjectPermission, Subtask, TimeEntry, Asset, TaskType, ProjectStatus,
    TASK_STATUSES, TASK_PRIORITIES,
)

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _generate_token():
    return secrets.token_urlsafe(32)


def require_api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token_raw = auth[7:]
        token_hash = _hash_token(token_raw)
        token = ApiToken.query.filter_by(token_hash=token_hash, is_active=True).first()
        if not token:
            return jsonify({"error": "Invalid or revoked token"}), 401
        if not token.user or not token.user.is_active_user:
            return jsonify({"error": "Account is disabled"}), 401
        token.last_used_at = datetime.now(timezone.utc)
        db.session.commit()
        g.api_user = token.user
        g.api_token = token
        return f(*args, **kwargs)
    return decorated


def _json_task(task):
    return {
        "id": task.id,
        "project_id": task.project_id,
        "task_number": task.task_number,
        "display_id": task.display_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "assignee_id": task.assignee_id,
        "created_by": task.created_by,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _json_project(project):
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "prefix": project.prefix,
        "color": project.color,
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


@api_bp.before_request
@limiter.limit("60/minute")
def api_rate_limit():
    pass


# ── Token Management ──

@api_bp.route("/tokens", methods=["POST"])
@login_required
@limiter.limit("5/minute")
def create_token():
    data = request.get_json() or {}
    name = data.get("name", "API Token")
    raw_token = _generate_token()
    token = ApiToken(
        user_id=current_user.id,
        name=name,
        token_hash=_hash_token(raw_token),
        prefix=raw_token[:8],
    )
    db.session.add(token)
    db.session.commit()
    return jsonify({
        "id": token.id,
        "name": token.name,
        "token": raw_token,
        "prefix": token.prefix,
        "message": "Save this token — it won't be shown again",
    }), 201


@api_bp.route("/tokens", methods=["GET"])
@login_required
def list_tokens():
    tokens = ApiToken.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        "id": t.id, "name": t.name, "prefix": t.prefix,
        "is_active": t.is_active, "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in tokens])


@api_bp.route("/tokens/<int:token_id>", methods=["DELETE"])
@login_required
def revoke_token(token_id):
    token = ApiToken.query.filter_by(id=token_id, user_id=current_user.id).first()
    if not token:
        return jsonify({"error": "Not found"}), 404
    token.is_active = False
    db.session.commit()
    return jsonify({"message": "Token revoked"})


# ── Projects ──

@api_bp.route("/projects", methods=["GET"])
@require_api_auth
def list_projects():
    user = g.api_user
    if user.can_manage_all_projects():
        projects = Project.query.order_by(Project.name).all()
    else:
        ids = set()
        for perm in ProjectPermission.query.filter(ProjectPermission.user_id == user.id).all():
            ids.add(perm.project_id)
        for m in user.group_memberships:
            for perm in ProjectPermission.query.filter(ProjectPermission.group_id == m.group_id).all():
                ids.add(perm.project_id)
        projects = Project.query.filter(Project.id.in_(ids)).order_by(Project.name).all()
    return jsonify([_json_project(p) for p in projects])


@api_bp.route("/projects/<int:project_id>", methods=["GET"])
@require_api_auth
def get_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Not found"}), 404
    if not g.api_user.has_project_permission(project_id, "viewer"):
        return jsonify({"error": "Access denied"}), 403
    return jsonify(_json_project(project))


# ── Tasks ──

@api_bp.route("/projects/<int:project_id>/tasks", methods=["GET"])
@require_api_auth
def list_tasks(project_id):
    if not g.api_user.has_project_permission(project_id, "viewer"):
        return jsonify({"error": "Access denied"}), 403
    tasks = Task.query.filter_by(project_id=project_id).order_by(Task.position, Task.created_at).all()
    return jsonify([_json_task(t) for t in tasks])


@api_bp.route("/projects/<int:project_id>/tasks", methods=["POST"])
@require_api_auth
def create_task(project_id):
    if not g.api_user.has_project_permission(project_id, "editor"):
        return jsonify({"error": "Access denied"}), 403
    data = request.get_json() or {}
    if not data.get("title"):
        return jsonify({"error": "title is required"}), 400
    max_num = db.session.query(db.func.max(Task.task_number)).filter_by(project_id=project_id).scalar()
    task = Task(
        project_id=project_id,
        task_number=(max_num or 0) + 1,
        title=data["title"],
        description=data.get("description", ""),
        status=data.get("status", "todo"),
        priority=data.get("priority", "medium"),
        assignee_id=data.get("assignee_id"),
        created_by=g.api_user.id,
    )
    if data.get("due_date"):
        try:
            task.due_date = datetime.fromisoformat(data["due_date"]).date()
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid due_date format"}), 400
    db.session.add(task)
    db.session.commit()
    return jsonify(_json_task(task)), 201


@api_bp.route("/tasks/<int:task_id>", methods=["GET"])
@require_api_auth
def get_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"error": "Not found"}), 404
    if not g.api_user.has_project_permission(task.project_id, "viewer"):
        return jsonify({"error": "Access denied"}), 403
    data = _json_task(task)
    data["subtasks"] = [{"id": s.id, "title": s.title, "is_done": s.is_done, "position": s.position}
                        for s in Subtask.query.filter_by(task_id=task_id).order_by(Subtask.position).all()]
    return jsonify(data)


@api_bp.route("/tasks/<int:task_id>", methods=["PATCH"])
@require_api_auth
def update_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"error": "Not found"}), 404
    if not g.api_user.has_project_permission(task.project_id, "editor"):
        return jsonify({"error": "Access denied"}), 403
    data = request.get_json() or {}
    if "status" in data and data["status"] not in TASK_STATUSES:
        return jsonify({"error": f"Invalid status. Must be one of: {', '.join(TASK_STATUSES)}"}), 400
    if "priority" in data and data["priority"] not in TASK_PRIORITIES:
        return jsonify({"error": f"Invalid priority. Must be one of: {', '.join(TASK_PRIORITIES)}"}), 400
    if "assignee_id" in data:
        aid = data["assignee_id"]
        if aid is not None:
            if not isinstance(aid, int) or not db.session.get(User, aid):
                return jsonify({"error": "Invalid assignee_id"}), 400
    for field in ["title", "description", "status", "priority", "assignee_id"]:
        if field in data:
            setattr(task, field, data[field])
    if "due_date" in data:
        if data["due_date"]:
            try:
                task.due_date = datetime.fromisoformat(data["due_date"]).date()
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid due_date format"}), 400
        else:
            task.due_date = None
    db.session.commit()
    return jsonify(_json_task(task))


@api_bp.route("/tasks/<int:task_id>", methods=["DELETE"])
@require_api_auth
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"error": "Not found"}), 404
    if not g.api_user.has_project_permission(task.project_id, "admin"):
        return jsonify({"error": "Access denied"}), 403
    db.session.delete(task)
    db.session.commit()
    return jsonify({"message": "Deleted"})


# ── Subtasks ──

@api_bp.route("/tasks/<int:task_id>/subtasks", methods=["GET"])
@require_api_auth
def list_subtasks(task_id):
    task = db.session.get(Task, task_id)
    if not task or not g.api_user.has_project_permission(task.project_id, "viewer"):
        return jsonify({"error": "Access denied"}), 403
    subs = Subtask.query.filter_by(task_id=task_id).order_by(Subtask.position).all()
    return jsonify([{"id": s.id, "title": s.title, "is_done": s.is_done, "position": s.position} for s in subs])


@api_bp.route("/tasks/<int:task_id>/subtasks", methods=["POST"])
@require_api_auth
def create_subtask(task_id):
    task = db.session.get(Task, task_id)
    if not task or not g.api_user.has_project_permission(task.project_id, "editor"):
        return jsonify({"error": "Access denied"}), 403
    data = request.get_json() or {}
    if not data.get("title"):
        return jsonify({"error": "title is required"}), 400
    max_pos = db.session.query(db.func.max(Subtask.position)).filter_by(task_id=task_id).scalar()
    sub = Subtask(task_id=task_id, title=data["title"], position=(max_pos or 0) + 1)
    db.session.add(sub)
    db.session.commit()
    return jsonify({"id": sub.id, "title": sub.title, "is_done": sub.is_done, "position": sub.position}), 201


@api_bp.route("/subtasks/<int:subtask_id>", methods=["PATCH"])
@require_api_auth
def update_subtask(subtask_id):
    sub = db.session.get(Subtask, subtask_id)
    if not sub:
        return jsonify({"error": "Not found"}), 404
    task = db.session.get(Task, sub.task_id)
    if not g.api_user.has_project_permission(task.project_id, "editor"):
        return jsonify({"error": "Access denied"}), 403
    data = request.get_json() or {}
    if "is_done" in data:
        sub.is_done = data["is_done"]
    if "title" in data:
        sub.title = data["title"]
    db.session.commit()
    return jsonify({"id": sub.id, "title": sub.title, "is_done": sub.is_done, "position": sub.position})


@api_bp.route("/subtasks/<int:subtask_id>", methods=["DELETE"])
@require_api_auth
def delete_subtask(subtask_id):
    sub = db.session.get(Subtask, subtask_id)
    if not sub:
        return jsonify({"error": "Not found"}), 404
    task = db.session.get(Task, sub.task_id)
    if not task or not g.api_user.has_project_permission(task.project_id, "editor"):
        return jsonify({"error": "Access denied"}), 403
    db.session.delete(sub)
    db.session.commit()
    return jsonify({"message": "Deleted"})


# ── Comments ──

@api_bp.route("/tasks/<int:task_id>/comments", methods=["GET"])
@require_api_auth
def list_comments(task_id):
    task = db.session.get(Task, task_id)
    if not task or not g.api_user.has_project_permission(task.project_id, "viewer"):
        return jsonify({"error": "Access denied"}), 403
    comments = Comment.query.filter_by(task_id=task_id).order_by(Comment.created_at).all()
    return jsonify([{
        "id": c.id, "user_id": c.user_id, "content": c.content,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in comments])


@api_bp.route("/tasks/<int:task_id>/comments", methods=["POST"])
@require_api_auth
def create_comment(task_id):
    task = db.session.get(Task, task_id)
    if not task or not g.api_user.has_project_permission(task.project_id, "editor"):
        return jsonify({"error": "Access denied"}), 403
    data = request.get_json() or {}
    if not data.get("content"):
        return jsonify({"error": "content is required"}), 400
    comment = Comment(task_id=task_id, user_id=g.api_user.id, content=data["content"])
    db.session.add(comment)
    db.session.commit()
    return jsonify({"id": comment.id, "content": comment.content, "created_at": comment.created_at.isoformat()}), 201


# ── Users ──

@api_bp.route("/users", methods=["GET"])
@require_api_auth
def list_users():
    user = g.api_user
    if user.can_manage_all_projects():
        users = User.query.filter_by(is_active_user=True).order_by(User.username).all()
    else:
        ids = set()
        for perm in ProjectPermission.query.filter(ProjectPermission.user_id == user.id).all():
            ids.add(perm.user_id)
        for m in user.group_memberships:
            for perm in ProjectPermission.query.filter(ProjectPermission.group_id == m.group_id).all():
                if perm.user_id:
                    ids.add(perm.user_id)
        ids.add(user.id)
        users = User.query.filter(User.id.in_(ids), User.is_active_user == True).order_by(User.username).all()
    return jsonify([{"id": u.id, "username": u.username, "is_admin": u.is_admin} for u in users])


# ── Time Entries ──

@api_bp.route("/tasks/<int:task_id>/time", methods=["GET"])
@require_api_auth
def list_time_entries(task_id):
    task = db.session.get(Task, task_id)
    if not task or not g.api_user.has_project_permission(task.project_id, "viewer"):
        return jsonify({"error": "Access denied"}), 403
    entries = TimeEntry.query.filter_by(task_id=task_id).order_by(TimeEntry.started_at.desc()).all()
    return jsonify([{
        "id": e.id, "user_id": e.user_id, "duration_seconds": e.duration_seconds,
        "started_at": e.started_at.isoformat(), "ended_at": e.ended_at.isoformat() if e.ended_at else None,
    } for e in entries])
