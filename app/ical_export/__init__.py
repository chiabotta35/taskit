from datetime import date, timedelta

from flask import Blueprint, Response
from flask_login import login_required, current_user

from ..models import db, Task, Project, ProjectPermission, GroupMembership

ical_bp = Blueprint("ical", __name__, url_prefix="/ical")


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


def _escape_ics(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@ical_bp.route("/tasks.ics")
@login_required
def export_tasks():
    project_ids = _visible_project_ids(current_user)
    tasks = Task.query.filter(
        Task.project_id.in_(project_ids),
        Task.due_date.isnot(None),
        Task.status != "done",
    ).order_by(Task.due_date).all()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Taskit//Task Export//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Taskit Tasks",
    ]

    for task in tasks:
        uid = f"taskit-task-{task.id}@taskit"
        dtstart = task.due_date.strftime("%Y%m%d")
        dtend = (task.due_date + timedelta(days=1)).strftime("%Y%m%d")
        summary = f"[{task.display_id}] {task.title}"
        desc = f"Project: {task.project.name}\\nStatus: {task.status}\\nPriority: {task.priority}"
        if task.assignee:
            desc += f"\\nAssignee: {task.assignee.username}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{_escape_ics(summary)}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")

    return Response(
        "\r\n".join(lines),
        mimetype="text/calendar",
        headers={"Content-Disposition": "attachment; filename=taskit-tasks.ics"},
    )
