from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField
from wtforms.validators import DataRequired

from ..models import db, TaskTemplate, Project

templates_bp = Blueprint("templates", __name__, url_prefix="/templates")

PRIORITIES = ["low", "medium", "high", "critical"]


class TemplateForm(FlaskForm):
    name = StringField("Template Name", validators=[DataRequired()])
    title = StringField("Task Title", validators=[DataRequired()])
    description = TextAreaField("Description")
    priority = SelectField("Priority", choices=[(p, p.title()) for p in PRIORITIES])
    is_global = BooleanField("Global (visible to all users)")


@templates_bp.route("/")
@login_required
def index():
    templates = TaskTemplate.query.filter(
        (TaskTemplate.created_by == current_user.id) | (TaskTemplate.is_global == True)
    ).order_by(TaskTemplate.name).all()
    return render_template("templates/index.html", templates=templates)


@templates_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    form = TemplateForm()
    if form.validate_on_submit():
        tmpl = TaskTemplate(
            name=form.name.data,
            title=form.title.data,
            description=form.description.data,
            priority=form.priority.data,
            created_by=current_user.id,
            is_global=form.is_global.data and current_user.can_manage_all_projects(),
        )
        db.session.add(tmpl)
        db.session.commit()
        flash(f"Template '{tmpl.name}' created.", "success")
        return redirect(url_for("templates.index"))
    return render_template("templates/form.html", form=form, editing=False)


@templates_bp.route("/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
def edit(template_id):
    tmpl = db.session.get(TaskTemplate, template_id)
    if not tmpl:
        flash("Template not found.", "danger")
        return redirect(url_for("templates.index"))
    if tmpl.created_by != current_user.id and not current_user.can_manage_all_projects():
        flash("Access denied.", "danger")
        return redirect(url_for("templates.index"))

    form = TemplateForm(obj=tmpl)
    if form.validate_on_submit():
        tmpl.name = form.name.data
        tmpl.title = form.title.data
        tmpl.description = form.description.data
        tmpl.priority = form.priority.data
        if current_user.can_manage_all_projects():
            tmpl.is_global = form.is_global.data
        db.session.commit()
        flash(f"Template '{tmpl.name}' updated.", "success")
        return redirect(url_for("templates.index"))
    return render_template("templates/form.html", form=form, editing=True, template=tmpl)


@templates_bp.route("/<int:template_id>/delete", methods=["POST"])
@login_required
def delete(template_id):
    tmpl = db.session.get(TaskTemplate, template_id)
    if not tmpl:
        flash("Template not found.", "danger")
        return redirect(url_for("templates.index"))
    if tmpl.created_by != current_user.id and not current_user.can_manage_all_projects():
        flash("Access denied.", "danger")
        return redirect(url_for("templates.index"))
    name = tmpl.name
    db.session.delete(tmpl)
    db.session.commit()
    flash(f"Template '{name}' deleted.", "success")
    return redirect(url_for("templates.index"))


@templates_bp.route("/<int:template_id>/use/<int:project_id>")
@login_required
def use_template(template_id, project_id):
    tmpl = db.session.get(TaskTemplate, template_id)
    project = db.session.get(Project, project_id)
    if not tmpl or not project:
        flash("Not found.", "danger")
        return redirect(url_for("templates.index"))
    if not current_user.has_project_permission(project_id, "editor"):
        flash("Access denied.", "danger")
        return redirect(url_for("templates.index"))

    from ..models import Task
    max_num = db.session.query(db.func.max(Task.task_number)).filter_by(project_id=project_id).scalar()
    task = Task(
        project_id=project_id,
        task_number=(max_num or 0) + 1,
        title=tmpl.title,
        description=tmpl.description,
        priority=tmpl.priority,
        created_by=current_user.id,
    )
    db.session.add(task)
    db.session.commit()
    flash(f"Task '{task.title}' created from template.", "success")
    return redirect(url_for("tasks.detail_task", task_id=task.id))
