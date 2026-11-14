from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models import Ad


main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    # MariaDB does not support NULLS LAST; a descending sort already places NULLs last.
    ads = Ad.query.order_by(Ad.run_date.desc(), Ad.id.desc()).all()
    return render_template("index.html", ads=ads)


@main_bp.route("/ads/new", methods=["GET", "POST"])
def create_ad():
    if request.method == "POST":
        ad = Ad(
            title=request.form.get("title", "").strip(),
            customer=request.form.get("customer", "").strip(),
            ad_type=request.form.get("ad_type", "").strip(),
            run_date=_parse_date(request.form.get("run_date")),
            notes=request.form.get("notes", "").strip() or None,
        )

        if not ad.title or not ad.customer or not ad.ad_type:
            flash("Title, customer, and ad type are required.", "error")
            return render_template("ad_form.html", ad=ad, form_mode="create")

        db.session.add(ad)
        db.session.commit()
        flash("Ad created.", "success")
        return redirect(url_for("main.index"))

    return render_template("ad_form.html", ad=None, form_mode="create")


@main_bp.route("/ads/<int:ad_id>/edit", methods=["GET", "POST"])
def edit_ad(ad_id: int):
    ad = Ad.query.get_or_404(ad_id)

    if request.method == "POST":
        ad.title = request.form.get("title", "").strip()
        ad.customer = request.form.get("customer", "").strip()
        ad.ad_type = request.form.get("ad_type", "").strip()
        ad.run_date = _parse_date(request.form.get("run_date"))
        ad.notes = request.form.get("notes", "").strip() or None

        if not ad.title or not ad.customer or not ad.ad_type:
            flash("Title, customer, and ad type are required.", "error")
            return render_template("ad_form.html", ad=ad, form_mode="edit")

        db.session.commit()
        flash("Ad updated.", "success")
        return redirect(url_for("main.index"))

    return render_template("ad_form.html", ad=ad, form_mode="edit")


@main_bp.post("/ads/<int:ad_id>/delete")
def delete_ad(ad_id: int):
    ad = Ad.query.get_or_404(ad_id)
    db.session.delete(ad)
    db.session.commit()
    flash("Ad deleted.", "success")
    return redirect(url_for("main.index"))


def _parse_date(value: str | None):
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
