from flask import Blueprint, render_template
from flask_login import login_required

views_bp = Blueprint("views", __name__)


@views_bp.get("/")
@login_required
def dashboard():
    return render_template("dashboard.html")
