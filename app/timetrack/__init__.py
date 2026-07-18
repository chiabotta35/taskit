from datetime import datetime, timezone, timedelta

from flask import Blueprint, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from ..models import db, TimeEntry, Task

timetrack_bp = Blueprint("timetrack", __name__, url_prefix="/time")


@timetrack_bp.route("/start/<int:task_id>", methods=["POST"])
@login_required
def start_timer(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("dashboard.index"))
    if not current_user.has_project_permission(task.project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("dashboard.index"))

    # Stop any existing running timer for this user
    running = TimeEntry.query.filter_by(user_id=current_user.id, ended_at=None, is_paused=False).first()
    if running:
        now = datetime.now(timezone.utc)
        running.ended_at = now
        running.duration_seconds = int((now - running.started_at).total_seconds())

    entry = TimeEntry(task_id=task_id, user_id=current_user.id)
    db.session.add(entry)
    db.session.commit()
    return jsonify({"id": entry.id, "status": "started"})


@timetrack_bp.route("/stop/<int:entry_id>", methods=["POST"])
@login_required
def stop_timer(entry_id):
    entry = db.session.get(TimeEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        return jsonify({"error": "Not found"}), 404
    if entry.ended_at:
        return jsonify({"error": "Already stopped"}), 400
    now = datetime.now(timezone.utc)
    entry.ended_at = now
    entry.duration_seconds = int((now - entry.started_at).total_seconds())
    db.session.commit()
    return jsonify({"id": entry.id, "duration_seconds": entry.duration_seconds})


@timetrack_bp.route("/pause/<int:entry_id>", methods=["POST"])
@login_required
def pause_timer(entry_id):
    entry = db.session.get(TimeEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        return jsonify({"error": "Not found"}), 404
    if entry.ended_at:
        return jsonify({"error": "Already stopped"}), 400
    now = datetime.now(timezone.utc)
    entry.duration_seconds = int((now - entry.started_at).total_seconds())
    entry.ended_at = now
    entry.is_paused = True
    db.session.commit()
    return jsonify({"id": entry.id, "duration_seconds": entry.duration_seconds, "paused": True})


@timetrack_bp.route("/running", methods=["GET"])
@login_required
def running_timer():
    entry = TimeEntry.query.filter_by(user_id=current_user.id, ended_at=None, is_paused=False).first()
    if not entry:
        return jsonify({"running": False})
    elapsed = int((datetime.now(timezone.utc) - entry.started_at).total_seconds())
    return jsonify({
        "running": True,
        "entry_id": entry.id,
        "task_id": entry.task_id,
        "elapsed_seconds": elapsed,
        "started_at": entry.started_at.isoformat(),
    })
