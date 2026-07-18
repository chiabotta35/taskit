from datetime import date

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField
from wtforms.validators import DataRequired, Optional

from ..models import db, Asset, Project

assets_bp = Blueprint("assets", __name__, url_prefix="/assets")

ASSET_TYPES = ["server", "network", "storage", "hardware", "software", "license", "other"]
ASSET_STATUSES = ["active", "inactive", "decommissioned", "maintenance"]


class AssetForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    asset_type = SelectField("Type", choices=[(t, t.title()) for t in ASSET_TYPES])
    project_id = SelectField("Project", coerce=lambda x: int(x) if x and str(x).strip() else None)
    ip_address = StringField("IP Address", validators=[Optional()])
    location = StringField("Location", validators=[Optional()])
    serial_number = StringField("Serial Number", validators=[Optional()])
    purchase_date = DateField("Purchase Date", validators=[Optional()], format="%Y-%m-%d")
    warranty_date = DateField("Warranty Expiry", validators=[Optional()], format="%Y-%m-%d")
    status = SelectField("Status", choices=[(s, s.title()) for s in ASSET_STATUSES])
    notes = TextAreaField("Notes")


def _project_choices():
    if current_user.can_manage_all_projects():
        return [(None, "-- None --")] + [(p.id, p.name) for p in Project.query.order_by(Project.name).all()]
    return [(None, "-- None --")]


@assets_bp.route("/")
@login_required
def index():
    type_filter = request.args.get("type", "")
    query = Asset.query
    if type_filter:
        query = query.filter_by(asset_type=type_filter)
    assets = query.order_by(Asset.name).all()
    return render_template("assets/index.html", assets=assets, type_filter=type_filter, asset_types=ASSET_TYPES)


@assets_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    form = AssetForm()
    form.project_id.choices = _project_choices()
    if form.validate_on_submit():
        asset = Asset(
            name=form.name.data,
            asset_type=form.asset_type.data,
            project_id=form.project_id.data,
            ip_address=form.ip_address.data or None,
            location=form.location.data or None,
            serial_number=form.serial_number.data or None,
            purchase_date=form.purchase_date.data,
            warranty_date=form.warranty_date.data,
            status=form.status.data,
            notes=form.notes.data or "",
        )
        db.session.add(asset)
        db.session.commit()
        flash(f"Asset '{asset.name}' created.", "success")
        return redirect(url_for("assets.index"))
    return render_template("assets/form.html", form=form, editing=False)


@assets_bp.route("/<int:asset_id>/edit", methods=["GET", "POST"])
@login_required
def edit(asset_id):
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash("Asset not found.", "danger")
        return redirect(url_for("assets.index"))
    form = AssetForm(obj=asset)
    form.project_id.choices = _project_choices()
    if form.validate_on_submit():
        form.populate_obj(asset)
        db.session.commit()
        flash(f"Asset '{asset.name}' updated.", "success")
        return redirect(url_for("assets.index"))
    return render_template("assets/form.html", form=form, editing=True, asset=asset)


@assets_bp.route("/<int:asset_id>/delete", methods=["POST"])
@login_required
def delete(asset_id):
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash("Asset not found.", "danger")
        return redirect(url_for("assets.index"))
    name = asset.name
    db.session.delete(asset)
    db.session.commit()
    flash(f"Asset '{name}' deleted.", "success")
    return redirect(url_for("assets.index"))
