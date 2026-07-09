"""
Web front end for the Grain Procurement Management System (Version 1).

This is a thin Flask layer over the same service functions the CLI
(main.py) uses -- app/auth.py, app/purchase_service.py,
app/admin_service.py, app/notification_service.py. No business logic
lives in this file; it only handles HTTP, sessions, and rendering.

Run:
    python seed.py     # once, to create the database + starter accounts
    python webapp.py   # then open http://127.0.0.1:5000
"""

import os
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash

from app.database import init_db
from app import auth, admin_service, purchase_service, notification_service
from app.auth import CurrentUser
from app.exceptions import GrainProcurementError

flask_app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
flask_app.secret_key = os.environ.get("GRAIN_LEDGER_SECRET_KEY", "dev-secret-change-me")


def current_user() -> CurrentUser | None:
    if "user_id" not in session:
        return None
    return CurrentUser(session["user_id"], session["username"], session["role"])


def login_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                flash("Please log in to continue.", "info")
                return redirect(url_for("login"))
            if roles and user.role not in roles:
                flash("You don't have access to that page.", "error")
                return redirect(url_for("dashboard"))
            return view(user, *args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@flask_app.route("/")
def index():
    return redirect(url_for("dashboard") if current_user() else url_for("login"))


@flask_app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        try:
            user = auth.login(username, password)
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role
            return redirect(url_for("dashboard"))
        except GrainProcurementError as e:
            flash(str(e), "error")

    return render_template("login.html")


@flask_app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


@flask_app.route("/dashboard")
def dashboard():
    user = current_user()
    if user is None:
        return redirect(url_for("login"))
    return redirect(url_for(f"{user.role.lower()}_home"))


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@flask_app.route("/agent", endpoint="agent_home")
@login_required("AGENT")
def agent_home(user):
    categories = admin_service.list_active_config()
    categories = [c for c in categories if c["category_active"]]
    notifications = notification_service.list_for_role("AGENT", user.user_id)
    return render_template(
        "agent.html",
        categories=categories,
        notifications=notifications,
        pending_calc=session.get("pending_calc"),
    )


@flask_app.route("/agent/calculate", methods=["POST"])
@login_required("AGENT")
def agent_calculate(user):
    category = request.form.get("category", "")
    weight_kg = request.form.get("weight_kg", "")

    try:
        calc = purchase_service.calculate_purchase(category, weight_kg)
        session["pending_calc"] = calc
    except GrainProcurementError as e:
        flash(str(e), "error")

    return redirect(url_for("agent_home"))


@flask_app.route("/agent/submit", methods=["POST"])
@login_required("AGENT")
def agent_submit(user):
    calc = session.get("pending_calc")
    if not calc:
        flash("Start a calculation first.", "error")
        return redirect(url_for("agent_home"))

    try:
        purchase = purchase_service.submit_purchase(
            user,
            calc["category_name"],
            calc["weight_kg"],
            request.form.get("supplier_name", ""),
            request.form.get("momo_provider", ""),
            request.form.get("momo_number", ""),
            request.form.get("id_info", ""),
        )
        session.pop("pending_calc", None)
        flash(
            f"Purchase {purchase['purchase_ref']} saved. Status: {purchase['status']}.",
            "success",
        )
    except GrainProcurementError as e:
        flash(str(e), "error")

    return redirect(url_for("agent_home"))


@flask_app.route("/agent/cancel")
@login_required("AGENT")
def agent_cancel(user):
    session.pop("pending_calc", None)
    return redirect(url_for("agent_home"))


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

@flask_app.route("/manager", endpoint="manager_home")
@login_required("MANAGER")
def manager_home(user):
    pending = purchase_service.list_pending_purchases()
    notifications = notification_service.list_for_role("MANAGER")
    return render_template("manager.html", pending=pending, notifications=notifications)


@flask_app.route("/manager/confirm", methods=["POST"])
@login_required("MANAGER")
def manager_confirm(user):
    try:
        purchase_id = int(request.form.get("purchase_id", ""))
        payment_type = request.form.get("payment_type", "")
        reference = request.form.get("transaction_reference", "")

        purchase = purchase_service.confirm_payment(user, purchase_id, payment_type, reference)
        flash(
            f"Recorded. {purchase['purchase_ref']} is now {purchase['status']}.",
            "success",
        )
    except (ValueError, GrainProcurementError) as e:
        flash(str(e), "error")

    return redirect(url_for("manager_home"))


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@flask_app.route("/admin", endpoint="admin_home")
@login_required("ADMIN")
def admin_home(user):
    config = admin_service.list_active_config()
    categories = admin_service.list_all_categories()
    return render_template("admin.html", config=config, categories=categories)


@flask_app.route("/admin/category", methods=["POST"])
@login_required("ADMIN")
def admin_add_category(user):
    try:
        admin_service.add_category(user, request.form.get("name", ""))
        flash("Category added.", "success")
    except GrainProcurementError as e:
        flash(str(e), "error")
    return redirect(url_for("admin_home"))


@flask_app.route("/admin/price", methods=["POST"])
@login_required("ADMIN")
def admin_set_price(user):
    try:
        category = request.form.get("category", "")
        price = float(request.form.get("price_per_kg", "0"))
        admin_service.set_price(user, category, price)
        flash(f"Price for {category} updated to {price}/kg.", "success")
    except (ValueError, GrainProcurementError) as e:
        flash(str(e), "error")
    return redirect(url_for("admin_home"))


@flask_app.route("/admin/commission", methods=["POST"])
@login_required("ADMIN")
def admin_set_commission(user):
    try:
        category = request.form.get("category", "")
        rate = float(request.form.get("rate_per_kg", "0"))
        admin_service.set_commission_rate(user, category, rate)
        flash(f"Commission rate for {category} updated to {rate}/kg.", "success")
    except (ValueError, GrainProcurementError) as e:
        flash(str(e), "error")
    return redirect(url_for("admin_home"))


@flask_app.route("/admin/toggle", methods=["POST"])
@login_required("ADMIN")
def admin_toggle_category(user):
    try:
        category = request.form.get("category", "")
        active = request.form.get("active", "1") == "1"
        admin_service.set_category_active(user, category, active)
        flash(f"{category} is now {'active' if active else 'inactive'}.", "success")
    except GrainProcurementError as e:
        flash(str(e), "error")
    return redirect(url_for("admin_home"))


if __name__ == "__main__":
    init_db()
    flask_app.run(debug=True, host="127.0.0.1", port=5000)
