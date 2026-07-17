import hashlib
import hmac
import json

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, SelectField, PasswordField
from wtforms.validators import DataRequired, URL, Optional

from ..models import db, Webhook, WEBHOOK_EVENTS

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


class WebhookForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    url = StringField("URL", validators=[DataRequired(), URL()])
    secret = PasswordField("Secret (optional)", validators=[Optional()])
    is_active = BooleanField("Active", default=True)


def _require_admin():
    if not current_user.can_manage_all_projects():
        flash("Access denied.", "danger")
        return redirect(url_for("projects.list_projects"))
    return None


@webhooks_bp.route("/")
@login_required
def list_webhooks():
    denied = _require_admin()
    if denied:
        return denied
    webhooks = Webhook.query.order_by(Webhook.created_at.desc()).all()
    return render_template("webhooks/list.html", webhooks=webhooks, all_events=WEBHOOK_EVENTS)


@webhooks_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_webhook():
    denied = _require_admin()
    if denied:
        return denied
    form = WebhookForm()
    if form.validate_on_submit():
        wh = Webhook(
            name=form.name.data,
            url=form.url.data,
            secret=form.secret.data or None,
            is_active=form.is_active.data,
            created_by=current_user.id,
        )
        events = request.form.getlist("events")
        if not events:
            events = ["task.created", "task.updated", "task.status_changed", "comment.created"]
        wh.set_events_list(events)
        db.session.add(wh)
        db.session.commit()
        flash(f"Webhook '{wh.name}' created.", "success")
        return redirect(url_for("webhooks.list_webhooks"))
    return render_template("webhooks/form.html", form=form, title="Create Webhook", all_events=WEBHOOK_EVENTS)


@webhooks_bp.route("/<int:webhook_id>/edit", methods=["GET", "POST"])
@login_required
def edit_webhook(webhook_id):
    denied = _require_admin()
    if denied:
        return denied
    wh = db.session.get(Webhook, webhook_id)
    if not wh:
        flash("Webhook not found.", "danger")
        return redirect(url_for("webhooks.list_webhooks"))
    form = WebhookForm(obj=wh)
    if form.validate_on_submit():
        wh.name = form.name.data
        wh.url = form.url.data
        if form.secret.data:
            wh.secret = form.secret.data
        wh.is_active = form.is_active.data
        events = request.form.getlist("events")
        if not events:
            events = ["task.created", "task.updated", "task.status_changed", "comment.created"]
        wh.set_events_list(events)
        db.session.commit()
        flash(f"Webhook '{wh.name}' updated.", "success")
        return redirect(url_for("webhooks.list_webhooks"))
    return render_template(
        "webhooks/form.html", form=form, title="Edit Webhook",
        all_events=WEBHOOK_EVENTS, webhook=wh,
    )


@webhooks_bp.route("/<int:webhook_id>/delete", methods=["POST"])
@login_required
def delete_webhook(webhook_id):
    denied = _require_admin()
    if denied:
        return denied
    wh = db.session.get(Webhook, webhook_id)
    if not wh:
        flash("Webhook not found.", "danger")
        return redirect(url_for("webhooks.list_webhooks"))
    name = wh.name
    db.session.delete(wh)
    db.session.commit()
    flash(f"Webhook '{name}' deleted.", "success")
    return redirect(url_for("webhooks.list_webhooks"))


@webhooks_bp.route("/<int:webhook_id>/test", methods=["POST"])
@login_required
def test_webhook(webhook_id):
    denied = _require_admin()
    if denied:
        return denied
    wh = db.session.get(Webhook, webhook_id)
    if not wh:
        flash("Webhook not found.", "danger")
        return redirect(url_for("webhooks.list_webhooks"))
    from ..webhooks import fire_webhook
    fire_webhook("task.created", {
        "task_id": 0,
        "title": "Test webhook",
        "status": "todo",
        "priority": "medium",
        "project_id": 0,
        "project_name": "Test",
        "assignee": None,
        "created_by": current_user.username,
        "action": "test",
    })
    flash(f"Test event sent to '{wh.name}'.", "success")
    return redirect(url_for("webhooks.list_webhooks"))
