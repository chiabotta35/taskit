from datetime import date, timedelta
from collections import Counter

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from ..models import db, Task, Project, ProjectPermission

mytasks_bp = Blueprint("mytasks", __name__, url_prefix="/my-tasks")


@mytasks_bp.route("/")
@login_required
def index():
    status_filter = request.args.get("status", "")
    priority_filter = request.args.get("priority", "")

    query = Task.query.filter(Task.assignee_id == current_user.id)

    if status_filter:
        query = query.filter(Task.status == status_filter)
    if priority_filter:
        query = query.filter(Task.priority == priority_filter)

    tasks = query.order_by(
        Task.due_date.asc().nullslast(), Task.priority.desc()
    ).all()

    overdue = [t for t in tasks if t.due_date and t.due_date < date.today() and t.status != "done"]

    return render_template(
        "mytasks/index.html",
        tasks=tasks,
        overdue=overdue,
        status_filter=status_filter,
        priority_filter=priority_filter,
    )
