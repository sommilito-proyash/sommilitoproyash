from flask import Flask, render_template, request, redirect, url_for, session, abort, flash, Response, send_file
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
import csv
import io
import json
load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Sommilito@123")
MEMBER_EMAIL_DEFAULT = os.environ.get("MEMBER_EMAIL", "member@sommilitoproyash.com")
MEMBER_PASSWORD_DEFAULT = os.environ.get("MEMBER_PASSWORD", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
BUCKET = "member-photos"
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


def admin_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return w


def ensure_bucket():
    try:
        supabase.storage.create_bucket(BUCKET, options={"public": True})
    except Exception:
        pass


def members_all():
    return supabase.table("members").select("*").order("id").execute().data or []


def member_by_id(member_id):
    rows = supabase.table("members").select("*").eq("id", member_id).limit(1).execute().data or []
    return rows[0] if rows else None


def years_all():
    rows = supabase.table("years").select("year").order("year", desc=True).execute().data or []
    return [str(r["year"]) for r in rows]


def record_for(year, member_id):
    """Fetch one record (used by write/update actions)."""
    rows = (supabase.table("annual_records").select("*")
            .eq("year", int(year)).eq("member_id", member_id).limit(1).execute().data or [])
    if rows:
        r = rows[0]
        r.setdefault("payments", [False] * 12)
        r.setdefault("down_payment_1", 0)
        r.setdefault("down_payment_2", 0)
        r.setdefault("down_payment_1_paid", False)
        r.setdefault("down_payment_2_paid", False)
        return r
    return {"year": int(year), "member_id": member_id, "payments": [False] * 12,
            "down_payment_1": 0, "down_payment_2": 0,
            "down_payment_1_paid": False, "down_payment_2_paid": False}


def records_for_year(year):
    """Fetch all member records for one year in ONE database request."""
    rows = (supabase.table("annual_records").select("*")
            .eq("year", int(year)).execute().data or [])
    result = {}
    for r in rows:
        r.setdefault("payments", [False] * 12)
        r.setdefault("down_payment_1", 0)
        r.setdefault("down_payment_2", 0)
        r.setdefault("down_payment_1_paid", False)
        r.setdefault("down_payment_2_paid", False)
        result[int(r["member_id"])] = r
    return result


def records_for_years(years):
    """Fetch all records for all supplied years in ONE database request."""
    year_ints = [int(y) for y in years]
    if not year_ints:
        return {}
    rows = (supabase.table("annual_records").select("*")
            .in_("year", year_ints).execute().data or [])
    result = {}
    for r in rows:
        r.setdefault("payments", [False] * 12)
        r.setdefault("down_payment_1", 0)
        r.setdefault("down_payment_2", 0)
        r.setdefault("down_payment_1_paid", False)
        r.setdefault("down_payment_2_paid", False)
        result[(int(r["year"]), int(r["member_id"]))] = r
    return result


def annual_settings_all(years=None):
    """Fetch yearly settings together instead of one query per year."""
    rows = supabase.table("annual_settings").select("*").execute().data or []
    wanted = None if years is None else {int(y) for y in years}
    result = {}
    for s in rows:
        y = int(s["year"])
        if wanted is None or y in wanted:
            result[y] = {
                "year": y,
                "monthly_amount": s.get("monthly_amount"),
                "down_payment_1_required": bool(s.get("down_payment_1_required", False)),
                "down_payment_1_amount": float(s.get("down_payment_1_amount") or 0),
                "down_payment_2_required": bool(s.get("down_payment_2_required", False)),
                "down_payment_2_amount": float(s.get("down_payment_2_amount") or 0),
                "mandatory_months": list(s.get("mandatory_months") or [True] * 12),
            }
    return result


def default_annual_setting(year):
    return {
        "year": int(year),
        "monthly_amount": None,
        "down_payment_1_required": False,
        "down_payment_1_amount": 0,
        "down_payment_2_required": False,
        "down_payment_2_amount": 0,
        "mandatory_months": [True] * 12,
    }


def annual_setting(year):
    """Return one year's settings. Used by write actions/fallback paths."""
    default = default_annual_setting(year)
    try:
        rows = (supabase.table("annual_settings").select("*")
                .eq("year", int(year)).limit(1).execute().data or [])
        if rows:
            s = rows[0]
            default.update({
                "monthly_amount": s.get("monthly_amount"),
                "down_payment_1_required": bool(s.get("down_payment_1_required", False)),
                "down_payment_1_amount": float(s.get("down_payment_1_amount") or 0),
                "down_payment_2_required": bool(s.get("down_payment_2_required", False)),
                "down_payment_2_amount": float(s.get("down_payment_2_amount") or 0),
                "mandatory_months": list(s.get("mandatory_months") or [True] * 12),
            })
    except Exception:
        pass
    return default


def year_summary(year, members, records, setting):
    total_paid = total_arrear = total_down = 0.0
    yi = int(year)
    for m in members:
        r = records.get((yi, int(m["id"])), {"year": yi, "member_id": m["id"], "payments": [False] * 12, "down_payment_1": 0, "down_payment_2": 0, "down_payment_1_paid": False, "down_payment_2_paid": False})
        paid, arrear, down = stats(r, m, setting)
        total_paid += paid; total_arrear += arrear; total_down += down
    return total_paid, total_arrear, total_down


def stats(rec, member, setting=None):
    setting = setting or annual_setting(rec["year"])
    pays = list(rec.get("payments") or [False] * 12)
    pays = (pays + [False] * 12)[:12]
    monthly_value = setting.get("monthly_amount")
    monthly = float(member.get("monthly") or 0) if monthly_value in (None, "") else float(monthly_value or 0)

    mandatory = list(setting.get("mandatory_months") or [True] * 12)
    mandatory = [(bool(x) if i < len(mandatory) else True) for i, x in enumerate((mandatory + [True] * 12)[:12])]
    mandatory_count = sum(mandatory)
    paid_mandatory_months = sum(bool(pays[i]) and mandatory[i] for i in range(12))
    paid_optional_months = sum(bool(pays[i]) and not mandatory[i] for i in range(12))

    # Every actual payment counts as deposited, including optional/advance months.
    paid = sum(bool(x) for x in pays) * monthly
    # Only unpaid Mandatory months create arrears. Optional unpaid months never do.
    arrear = (mandatory_count - paid_mandatory_months) * monthly

    dp1_amount = float(setting.get("down_payment_1_amount") or 0)
    dp2_amount = float(setting.get("down_payment_2_amount") or 0)
    dp1_required = bool(setting.get("down_payment_1_required"))
    dp2_required = bool(setting.get("down_payment_2_required"))
    dp1_paid = bool(rec.get("down_payment_1_paid"))
    dp2_paid = bool(rec.get("down_payment_2_paid"))

    if "down_payment_1_paid" not in rec and float(rec.get("down_payment_1") or 0) > 0:
        dp1_paid = True
    if "down_payment_2_paid" not in rec and float(rec.get("down_payment_2") or 0) > 0:
        dp2_paid = True

    dp1_paid_amount = dp1_amount if dp1_paid and dp1_amount > 0 else (float(rec.get("down_payment_1") or 0) if dp1_paid else 0)
    dp2_paid_amount = dp2_amount if dp2_paid and dp2_amount > 0 else (float(rec.get("down_payment_2") or 0) if dp2_paid else 0)
    paid += dp1_paid_amount + dp2_paid_amount
    if dp1_required and not dp1_paid:
        arrear += dp1_amount
    if dp2_required and not dp2_paid:
        arrear += dp2_amount

    down = dp1_paid_amount + dp2_paid_amount
    return paid, arrear, down


def yearly_member_totals(member_id, member, years=None, records=None, settings=None):
    """Calculate grand totals from already-fetched data when available."""
    years = years if years is not None else years_all()
    if records is None:
        records = records_for_years(years)
    if settings is None:
        try:
            settings = annual_settings_all(years)
        except Exception:
            settings = {}
    total_paid = total_arrear = total_down = 0.0
    for y in years:
        yi = int(y)
        r = records.get((yi, member_id), {
            "year": yi, "member_id": member_id, "payments": [False] * 12,
            "down_payment_1": 0, "down_payment_2": 0,
            "down_payment_1_paid": False, "down_payment_2_paid": False
        })
        setting = settings.get(yi) or default_annual_setting(yi)
        paid, arrear, down = stats(r, member, setting)
        total_paid += paid
        total_arrear += arrear
        total_down += down
    return total_paid, total_arrear, total_down


def upload_photo(file, member_id):
    if not file or not file.filename:
        return None
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        return None
    path = f"member_{member_id}{ext}"
    content_type = file.mimetype or "image/jpeg"
    supabase.storage.from_(BUCKET).upload(path, file.read(), {"content-type": content_type, "upsert": "true"})
    return supabase.storage.from_(BUCKET).get_public_url(path)


def bank_balance():
    """Return the current bank/cash balance from the fund_settings table."""
    try:
        rows = (supabase.table("fund_settings").select("bank_balance")
                .eq("id", 1).limit(1).execute().data or [])
        return float(rows[0].get("bank_balance") or 0) if rows else 0.0
    except Exception:
        return 0.0


def fdr_investments():
    try:
        return (supabase.table("fdr_investments").select("*")
                .eq("active", True).order("maturity_date").execute().data or [])
    except Exception:
        return []


def dps_accounts():
    try:
        return (supabase.table("dps_accounts").select("*")
                .eq("active", True).order("name").execute().data or [])
    except Exception:
        return []

def yearly_investment_summary(year):
    """Return DPS paid and FDR added amounts for one report year."""
    yi = int(year)
    dps_paid = 0.0
    fdr_added = 0.0
    try:
        payments = (supabase.table("dps_payments").select("dps_id,year,month")
                    .eq("year", yi).execute().data or [])
        if payments:
            ids = sorted({int(x["dps_id"]) for x in payments if x.get("dps_id") is not None})
            accounts = (supabase.table("dps_accounts").select("id,monthly_installment")
                        .in_("id", ids).execute().data or []) if ids else []
            amounts = {int(x["id"]): float(x.get("monthly_installment") or 0) for x in accounts}
            dps_paid = sum(amounts.get(int(x["dps_id"]), 0.0) for x in payments)
    except Exception:
        dps_paid = 0.0
    try:
        fdrs = (supabase.table("fdr_investments").select("amount,created_at")
                .eq("active", True).execute().data or [])
        for x in fdrs:
            created = str(x.get("created_at") or "")
            if created[:4] == str(yi):
                fdr_added += float(x.get("amount") or 0)
    except Exception:
        fdr_added = 0.0
    return dps_paid, fdr_added

def investment_settings():
    """Return investment/account-statement settings used by the private dashboard."""
    defaults = {"id": 1, "land_purchase_amount": 0.0, "statement_balance": 0.0}
    try:
        rows = (supabase.table("investment_settings").select("*")
                .eq("id", 1).limit(1).execute().data or [])
        if rows:
            row = rows[0]
            defaults["land_purchase_amount"] = float(row.get("land_purchase_amount") or 0)
            defaults["statement_balance"] = float(row.get("statement_balance") or 0)
    except Exception:
        pass
    return defaults


def dps_paid_months(dps_id, years):
    """Return {year: [12 booleans]} for DPS installments already deducted."""
    result = {int(y): [False] * 12 for y in years}
    if not years:
        return result
    try:
        rows = (supabase.table("dps_payments").select("year,month")
                .eq("dps_id", int(dps_id)).in_("year", [int(y) for y in years]).execute().data or [])
        for row in rows:
            y, m = int(row["year"]), int(row["month"])
            if y in result and 1 <= m <= 12:
                result[y][m-1] = True
    except Exception:
        pass
    return result


def enrich_dps_accounts(dps_list, years):
    total = 0.0
    enriched = []
    for d in dps_list:
        item = dict(d)
        paid_months = dps_paid_months(d["id"], years)
        item["paid_months"] = paid_months
        installment = float(d.get("monthly_installment") or 0)
        item["paid_amount"] = sum(sum(months) * installment for months in paid_months.values())
        total += item["paid_amount"]
        enriched.append(item)
    return enriched, total


def comments_for(member_id):
    return (supabase.table("comments").select("*").eq("member_id", member_id)
            .order("created_at", desc=True).execute().data or [])


def get_site_content():
    defaults = {
        "home_title": "সম্মিলিত প্রয়াস",
        "home_purpose_title": "আমাদের উদ্দেশ্য",
        "home_purpose_text": "সমিতির সদস্যদের সম্মিলিত সঞ্চয়, পারস্পরিক সহযোগিতা এবং ভবিষ্যৎ ফ্ল্যাট নির্মাণ প্রকল্প বাস্তবায়নের লক্ষ্যে এই উদ্যোগ পরিচালিত হচ্ছে।",
    }
    try:
        rows = supabase.table("site_settings").select("key,value").execute().data or []
        values = {r.get("key"): r.get("value", "") for r in rows}
        return {k: values.get(k, v) or v for k, v in defaults.items()}
    except Exception:
        return defaults


def save_site_content(home_title, purpose_title, purpose_text):
    values = {"home_title": home_title.strip()[:150], "home_purpose_title": purpose_title.strip()[:150], "home_purpose_text": purpose_text.strip()[:2000]}
    for key, value in values.items():
        supabase.table("site_settings").upsert({"key": key, "value": value, "updated_at": datetime.now(timezone.utc).isoformat()}, on_conflict="key").execute()


def get_setting(key, default=""):
    if key not in ("member_email", "member_password_hash"):
        return default
    try:
        rows = (supabase.table("site_settings")
                .select(key)
                .order("id", desc=True)
                .limit(1)
                .execute().data or [])
        return rows[0].get(key, default) if rows else default
    except Exception:
        return default


def set_setting(key, value):
    if key not in ("member_email", "member_password_hash"):
        return

    rows = (supabase.table("site_settings")
            .select("id")
            .order("id", desc=True)
            .limit(1)
            .execute().data or [])

    if rows:
        supabase.table("site_settings").update({
            key: value,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", rows[0]["id"]).execute()
    else:
        supabase.table("site_settings").insert({
            key: value,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).execute()


def member_credentials():
    """Read both login settings with one request."""
    try:
        rows = (supabase.table("site_settings")
                .select("member_email,member_password_hash")
                .order("id", desc=True)
                .limit(1)
                .execute().data or [])
        if rows:
            row = rows[0]
            return (
                (row.get("member_email") or MEMBER_EMAIL_DEFAULT).strip(),
                row.get("member_password_hash") or ""
            )
    except Exception:
        pass
    return MEMBER_EMAIL_DEFAULT.strip(), ""


def member_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        if not (session.get("member") or session.get("admin")):
            return redirect(url_for("member_login", next=request.path))
        return fn(*a, **kw)
    return w


@app.route("/")
def index():
    """Public home page plus private financial dashboard after login."""
    notices = (supabase.table("notices").select("*")
               .order("pinned", desc=True).order("created_at", desc=True).execute().data or [])
    site_content = get_site_content()
    logged_member = bool(session.get("member") or session.get("admin"))
    dashboard = None
    if logged_member:
        years = years_all()
        active_members = [m for m in members_all() if m.get("active", True)]
        all_records = records_for_years(years)
        settings = annual_settings_all(years)
        year_summaries = []
        for y in years:
            yp, ya, yd = year_summary(y, active_members, all_records, settings.get(int(y)) or default_annual_setting(y))
            year_summaries.append({"year": int(y), "paid": yp, "arrear": ya, "down": yd})
        grand_paid = sum(x["paid"] for x in year_summaries)
        grand_arrear = sum(x["arrear"] for x in year_summaries)
        fdrs = fdr_investments()
        dps_raw = dps_accounts()
        dps, total_dps_paid = enrich_dps_accounts(dps_raw, years)
        inv = investment_settings()
        total_fdr = sum(float(x.get("amount") or 0) for x in fdrs)
        land = float(inv["land_purchase_amount"])
        total_invested = land + total_fdr + total_dps_paid
        current_balance = grand_paid - total_invested
        statement_balance = float(inv["statement_balance"])
        profit = statement_balance - current_balance
        dashboard = {"years": years, "year_summaries": year_summaries,
                     "grand_paid": grand_paid, "grand_arrear": grand_arrear,
                     "fdrs": fdrs, "dps": dps, "land_purchase_amount": land,
                     "total_fdr": total_fdr, "total_dps_paid": total_dps_paid,
                     "total_invested": total_invested, "current_balance": current_balance,
                     "statement_balance": statement_balance, "profit": profit,
                     "is_admin": bool(session.get("admin"))}
    active_members = []
    if logged_member:
        active_members = [m for m in members_all() if m.get("active", True)]
        # Reuse the records/settings already fetched for the dashboard so the
        # member list does not create one database query per member/year.
        member_list = []
        for m in active_members:
            item = dict(m)
            item["year_summaries"] = []
            for y in years:
                yi = int(y)
                setting = settings.get(yi) or default_annual_setting(yi)
                rec = all_records.get((yi, int(m["id"])), {
                    "year": yi, "member_id": m["id"], "payments": [False] * 12,
                    "down_payment_1": 0, "down_payment_2": 0,
                    "down_payment_1_paid": False, "down_payment_2_paid": False
                })
                paid, arrear, _ = stats(rec, m, setting)
                item["year_summaries"].append({"year": yi, "paid": paid, "arrear": arrear})
            member_list.append(item)
        active_members = member_list
    return render_template("index.html", notices=notices, logged_member=logged_member,
                           active_members=active_members, admin=session.get("admin", False),
                           dashboard=dashboard, site_content=site_content)


@app.route("/member/<int:member_id>")
@member_required
def member(member_id):
    m = member_by_id(member_id)
    if not m:
        abort(404)
    years = years_all()
    if not years:
        abort(500, "No years found in database.")
    year = request.args.get("year", years[0])
    if year not in years:
        year = years[0]

    # One bulk request gets this member's records for every year.
    all_records = records_for_years(years)
    try:
        settings = annual_settings_all(years)
    except Exception:
        settings = {}
    yi = int(year)
    r = all_records.get((yi, member_id), {
        "year": yi, "member_id": member_id, "payments": [False] * 12,
        "down_payment_1": 0, "down_payment_2": 0,
        "down_payment_1_paid": False, "down_payment_2_paid": False
    })
    setting = settings.get(yi) or annual_setting(year)
    paid, arrear, down = stats(r, m, setting)
    grand_paid, grand_arrear, grand_down = yearly_member_totals(
        member_id, m, years=years, records=all_records, settings=settings
    )
    fdrs = fdr_investments()
    dps = dps_accounts()
    total_fdr = sum(float(x.get("amount") or 0) for x in fdrs)
    total_dps_installment = sum(float(x.get("monthly_installment") or 0) for x in dps)
    return render_template("member.html", member=m, record=r, months=MONTHS, years=years,
                           year=year, paid=paid, arrear=arrear, down=down,
                           grand_paid=grand_paid, grand_arrear=grand_arrear, grand_down=grand_down,
                           setting=setting, admin=session.get("admin", False), comments=comments_for(member_id),
                           bank_balance=bank_balance(), fdrs=fdrs, dps=dps,
                           total_fdr=total_fdr, total_dps_installment=total_dps_installment)


@app.route("/member/<int:member_id>/comment", methods=["POST"])
@member_required
def add_comment(member_id):
    if not member_by_id(member_id): abort(404)
    author = (request.form.get("author") or "সদস্য").strip()[:80]
    text = (request.form.get("text") or "").strip()[:1000]
    year = request.form.get("year", "")
    if text:
        supabase.table("comments").insert({"member_id": member_id, "author": author or "সদস্য", "text": text}).execute()
        flash("মন্তব্য যোগ হয়েছে।", "ok")
    return redirect(url_for("member", member_id=member_id, year=year))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session.clear()
            session["admin"] = True
            return redirect(request.args.get("next") or url_for("index"))
        return render_template("login.html", error="পাসওয়ার্ড সঠিক নয়।")
    return render_template("login.html", error=None)


@app.route("/member-login", methods=["GET", "POST"])
def member_login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        saved_email, password_hash = member_credentials()
        valid = email == saved_email.lower() and (
            bool(password_hash) and check_password_hash(password_hash, password)
            or (not password_hash and MEMBER_PASSWORD_DEFAULT and password == MEMBER_PASSWORD_DEFAULT)
        )
        if valid:
            session.clear()
            session["member"] = True
            return redirect(request.args.get("next") or url_for("index"))
        return render_template("member_login.html", error="ইমেইল বা পাসওয়ার্ড সঠিক নয়।")
    return render_template("member_login.html", error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("member_login"))


@app.route("/admin/member-login-settings", methods=["POST"])
@admin_required
def update_member_login_settings():
    email = (request.form.get("member_email") or "").strip().lower()
    password = request.form.get("member_password") or ""
    confirm = request.form.get("member_password_confirm") or ""
    if "@" not in email or len(email) > 200:
        flash("সঠিক Member Email দিন।", "error")
        return redirect(url_for("admin"))
    if password and len(password) < 6:
        flash("Member Password কমপক্ষে 6 অক্ষরের হতে হবে।", "error")
        return redirect(url_for("admin"))
    if password != confirm:
        flash("দুটি Member Password একই নয়।", "error")
        return redirect(url_for("admin"))
    set_setting("member_email", email)
    if password:
        set_setting("member_password_hash", generate_password_hash(password))
    flash("Member Login তথ্য সফলভাবে আপডেট হয়েছে।", "ok")
    return redirect(url_for("admin"))


@app.route("/admin")
@admin_required
def admin():
    years = years_all()
    if not years:
        abort(500, "No years found in database.")
    year = request.args.get("year", years[0])
    if year not in years:
        year = years[0]

    members = members_all()
    current_records = records_for_year(year)
    try:
        settings = annual_settings_all(years)
    except Exception:
        settings = {}
    setting = settings.get(int(year)) or annual_setting(year)

    rows = []
    yi = int(year)
    for m in members:
        r = current_records.get(int(m["id"]), {
            "year": yi, "member_id": m["id"], "payments": [False] * 12,
            "down_payment_1": 0, "down_payment_2": 0,
            "down_payment_1_paid": False, "down_payment_2_paid": False
        })
        paid, arrear, down = stats(r, m, setting)
        rows.append((m, r, paid, arrear, down))

    notices = supabase.table("notices").select("*").order("created_at", desc=True).execute().data or []
    member_email, _ = member_credentials()
    current_bank_balance = bank_balance()
    current_fdrs = fdr_investments()
    current_dps_raw = dps_accounts()
    current_dps, current_dps_paid_total = enrich_dps_accounts(current_dps_raw, years)
    current_fdr_total = sum(float(x.get("amount") or 0) for x in current_fdrs)
    current_dps_installment_total = sum(float(x.get("monthly_installment") or 0) for x in current_dps)
    current_investments = investment_settings()

    # Dashboard totals and year comparison chart data.
    # Home Page editable content is also needed by the Admin template.
    site_content = get_site_content()
    active_members = [m for m in members if m.get("active", True)]
    all_records = records_for_years(years)
    year_summaries = []
    for y in years:
        ys = settings.get(int(y)) or default_annual_setting(y)
        yp, ya, yd = year_summary(y, active_members, all_records, ys)
        year_summaries.append({"year": int(y), "paid": yp, "arrear": ya, "down": yd})

    # Monthly collection report for the selected year/month.
    try:
        month_idx = int(request.args.get("month", "0"))
    except ValueError:
        month_idx = 0
    month_idx = max(0, min(11, month_idx))
    monthly_rows = []
    monthly_collected = monthly_due = 0.0
    monthly_paid_count = 0
    monthly_due_count = 0
    for m in active_members:
        r = current_records.get(int(m["id"]), {"payments": [False] * 12})
        pays = list(r.get("payments") or [False] * 12)
        is_paid = bool(pays[month_idx]) if month_idx < len(pays) else False
        monthly_value = setting.get("monthly_amount")
        amount = float(m.get("monthly") or 0) if monthly_value in (None, "") else float(monthly_value or 0)
        mandatory = bool((setting.get("mandatory_months") or [True] * 12)[month_idx])
        if is_paid:
            monthly_collected += amount
            monthly_paid_count += 1
        elif mandatory:
            monthly_due += amount
            monthly_due_count += 1
        monthly_rows.append({"member": m, "paid": is_paid, "mandatory": mandatory, "amount": amount})

    current_summary = next((x for x in year_summaries if x["year"] == yi), {"paid": 0, "arrear": 0, "down": 0})
    # Grand totals across all years (active members only).
    grand_paid = sum(float(x.get("paid") or 0) for x in year_summaries)
    grand_arrear = sum(float(x.get("arrear") or 0) for x in year_summaries)
    grand_down = sum(float(x.get("down") or 0) for x in year_summaries)
    max_chart = max([max(float(x["paid"]), float(x["arrear"])) for x in year_summaries] or [1])
    return render_template("admin.html", members=rows, years=years, year=year, months=MONTHS,
                           notices=notices, member_email=member_email, setting=setting,
                           year_summaries=year_summaries, max_chart=max_chart,
                           current_paid=current_summary["paid"], current_arrear=current_summary["arrear"], current_down=current_summary["down"],
                           grand_paid=grand_paid, grand_arrear=grand_arrear, grand_down=grand_down,
                           monthly_rows=monthly_rows, selected_month=month_idx,
                           monthly_collected=monthly_collected, monthly_due=monthly_due,
                           monthly_paid_count=monthly_paid_count, monthly_due_count=monthly_due_count,
                           active_member_count=len(active_members), site_content=site_content,
                           bank_balance=current_bank_balance, fdrs=current_fdrs, dps=current_dps,
                           fdr_total=current_fdr_total, dps_installment_total=current_dps_installment_total,
                           dps_paid_total=current_dps_paid_total, investment_settings=current_investments)


@app.route("/admin/report/csv")
@admin_required
def download_report_csv():
    years = years_all()
    year = request.args.get("year", years[0] if years else "")
    if year not in years:
        abort(400)
    members = [m for m in members_all() if m.get("active", True)]
    records = records_for_year(year)
    setting = annual_setting(year)
    dps_paid_year, fdr_added_year = yearly_investment_summary(year)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Financial Report", year])
    writer.writerow([])
    writer.writerow(["Summary", "Amount"])
    writer.writerow(["Total Deposit", 0])
    # Summary totals are filled below after member rows are calculated.
    report_rows = []
    total_paid = total_arrear = total_down = 0.0
    for m in members:
        r = records.get(int(m["id"]), {"payments": [False]*12, "down_payment_1_paid": False, "down_payment_2_paid": False})
        paid, arrear, down = stats(r, m, setting)
        total_paid += paid
        total_arrear += arrear
        total_down += down
        report_rows.append((m, r, paid, arrear, down))
    # Rewrite the summary section cleanly.
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Financial Report", year])
    writer.writerow([])
    writer.writerow(["Summary", "Amount"])
    writer.writerow(["Total Deposit", round(total_paid, 2)])
    writer.writerow(["Total Arrear", round(total_arrear, 2)])
    writer.writerow(["Down Payment Paid", round(total_down, 2)])
    writer.writerow(["DPS Paid in Year", round(dps_paid_year, 2)])
    writer.writerow(["FDR Added in Year", round(fdr_added_year, 2)])
    writer.writerow([])
    writer.writerow(["Member", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December", "Year Deposit", "Year Arrear", "Down Payment Paid"])
    for m, r, paid, arrear, down in report_rows:
        pays = (list(r.get("payments") or [False]*12) + [False]*12)[:12]
        writer.writerow([m.get("name", "")] + ["Paid" if x else "Unpaid" for x in pays] + [round(paid,2), round(arrear,2), round(down,2)])
    data = out.getvalue().encode("utf-8-sig")
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=sommilitoproyash-{year}-report.csv"})


@app.route("/admin/report/print")
@admin_required
def print_report():
    years = years_all()
    year = request.args.get("year", years[0] if years else "")
    if year not in years:
        abort(400)
    members = [m for m in members_all() if m.get("active", True)]
    records = records_for_year(year)
    setting = annual_setting(year)
    report_rows = []
    total_paid = total_arrear = total_down = 0.0
    for m in members:
        r = records.get(int(m["id"]), {"payments": [False]*12, "down_payment_1_paid": False, "down_payment_2_paid": False})
        paid, arrear, down = stats(r, m, setting)
        total_paid += paid; total_arrear += arrear; total_down += down
        report_rows.append((m, r, paid, arrear, down))
    dps_paid_year, fdr_added_year = yearly_investment_summary(year)
    return render_template("report.html", report_scope="admin", year=year, years=years, months=MONTHS,
                           rows=report_rows, total_paid=total_paid, total_arrear=total_arrear,
                           total_down=total_down, dps_paid_year=dps_paid_year,
                           fdr_added_year=fdr_added_year)


@app.route("/member/<int:member_id>/report/csv")
@member_required
def download_member_report_csv(member_id):
    m = member_by_id(member_id)
    if not m:
        abort(404)
    years = years_all()
    year = request.args.get("year", years[0] if years else "")
    if year not in years:
        abort(400)
    r = record_for(year, member_id)
    setting = annual_setting(year)
    paid, arrear, down = stats(r, m, setting)
    dps_paid_year, fdr_added_year = yearly_investment_summary(year)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Member Financial Report", year])
    writer.writerow([])
    writer.writerow(["Member", m.get("name", "")])
    writer.writerow(["Total Deposit", round(paid,2)])
    writer.writerow(["Total Arrear", round(arrear,2)])
    writer.writerow(["Down Payment Paid", round(down,2)])
    writer.writerow(["DPS Paid in Year (Association)", round(dps_paid_year,2)])
    writer.writerow(["FDR Added in Year (Association)", round(fdr_added_year,2)])
    writer.writerow([])
    writer.writerow(["Month", "Status", "Amount"])
    pays = (list(r.get("payments") or [False]*12) + [False]*12)[:12]
    monthly_value = setting.get("monthly_amount")
    monthly = float(m.get("monthly") or 0) if monthly_value in (None, "") else float(monthly_value or 0)
    mandatory = list(setting.get("mandatory_months") or [True]*12)
    mandatory = (mandatory + [True]*12)[:12]
    for i, month in enumerate(MONTHS):
        status = "Paid" if pays[i] else ("Unpaid / Arrear" if mandatory[i] else "Optional")
        amount = monthly if pays[i] or mandatory[i] else 0
        writer.writerow([month, status, round(amount,2)])
    data = out.getvalue().encode("utf-8-sig")
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=sommilitoproyash-member-{member_id}-{year}-report.csv"})


@app.route("/member/<int:member_id>/report/print")
@member_required
def print_member_report(member_id):
    m = member_by_id(member_id)
    if not m:
        abort(404)
    years = years_all()
    year = request.args.get("year", years[0] if years else "")
    if year not in years:
        abort(400)
    r = record_for(year, member_id)
    setting = annual_setting(year)
    paid, arrear, down = stats(r, m, setting)
    dps_paid_year, fdr_added_year = yearly_investment_summary(year)
    return render_template("report.html", report_scope="member", member=m, record=r,
                           setting=setting, year=year, years=years, months=MONTHS, paid=paid, arrear=arrear,
                           down=down, dps_paid_year=dps_paid_year, fdr_added_year=fdr_added_year)

@app.route("/admin/home-content", methods=["POST"])
@admin_required
def update_home_content():
    try:
        save_site_content(request.form.get("home_title") or "সম্মিলিত প্রয়াস", request.form.get("home_purpose_title") or "আমাদের উদ্দেশ্য", request.form.get("home_purpose_text") or "")
        flash("Home page-এর লেখা সফলভাবে Save হয়েছে।", "ok")
    except Exception:
        app.logger.exception("Home content save failed")
        flash("Home page-এর লেখা Save করা যায়নি।", "error")
    return redirect(url_for("admin"))


@app.route("/admin/investment-settings", methods=["POST"])
@admin_required
def update_investment_settings():
    """Save land investment and actual account-statement balance reliably."""
    try:
        land_raw = (request.form.get("land_purchase_amount") or "0").strip()
        statement_raw = (request.form.get("statement_balance") or "0").strip()
        land = max(0, float(land_raw or 0))
        statement = max(0, float(statement_raw or 0))
        payload = {
            "id": 1,
            "land_purchase_amount": land,
            "statement_balance": statement,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Upsert makes Save work whether the single settings row already exists or not.
        supabase.table("investment_settings").upsert(payload, on_conflict="id").execute()
        flash("Investment ও Account Statement তথ্য সফলভাবে Save হয়েছে।", "ok")
    except ValueError:
        flash("Amount-এর ঘরে শুধু সঠিক সংখ্যা দিন।", "error")
    except Exception as e:
        app.logger.exception("Investment settings save failed")
        flash("Settings Save করা যায়নি। Supabase-এ v6.5.3 migration SQL Run করা হয়েছে কি না নিশ্চিত করুন।", "error")
    return redirect(url_for("admin"))


@app.route("/admin/fdr/add", methods=["POST"])
@admin_required
def add_fdr():
    name=(request.form.get("name") or "").strip()
    bank=(request.form.get("bank") or "").strip()
    if not name or not bank:
        flash("FDR Name ও Bank Name দিন।", "error")
        return redirect(url_for("admin"))
    try: amount=max(0,float(request.form.get("amount","0") or 0))
    except ValueError: amount=0
    supabase.table("fdr_investments").insert({
        "name":name[:150], "bank":bank[:150], "amount":amount,
        "maturity_date":(request.form.get("maturity_date") or None),
        "notes":(request.form.get("notes") or "").strip()[:500], "active":True
    }).execute()
    flash("FDR যোগ হয়েছে।","ok")
    return redirect(url_for("admin"))


@app.route("/admin/fdr/<int:fdr_id>/delete", methods=["POST"])
@admin_required
def delete_fdr(fdr_id):
    supabase.table("fdr_investments").update({"active":False}).eq("id",fdr_id).execute()
    flash("FDR সরানো হয়েছে।","ok")
    return redirect(url_for("admin"))


@app.route("/admin/dps/add", methods=["POST"])
@admin_required
def add_dps():
    name=(request.form.get("name") or "").strip()
    bank=(request.form.get("bank") or "").strip()
    if not name or not bank:
        flash("DPS Name ও Bank Name দিন।","error")
        return redirect(url_for("admin"))
    try: installment=max(0,float(request.form.get("monthly_installment","0") or 0))
    except ValueError: installment=0
    supabase.table("dps_accounts").insert({
        "name":name[:150], "bank":bank[:150], "monthly_installment":installment,
        "start_date":(request.form.get("start_date") or None),
        "maturity_date":(request.form.get("maturity_date") or None),
        "notes":(request.form.get("notes") or "").strip()[:500], "active":True
    }).execute()
    flash("DPS যোগ হয়েছে।","ok")
    return redirect(url_for("admin"))


@app.route("/admin/dps/<int:dps_id>/toggle-payment", methods=["POST"])
@admin_required
def toggle_dps_payment(dps_id):
    try:
        year = int(request.form.get("year", "0"))
        month = int(request.form.get("month", "0"))
        if year not in [int(y) for y in years_all()] or not 1 <= month <= 12:
            abort(400)
        existing = (supabase.table("dps_payments").select("id")
                    .eq("dps_id", dps_id).eq("year", year).eq("month", month).limit(1).execute().data or [])
        if existing:
            supabase.table("dps_payments").delete().eq("id", existing[0]["id"]).execute()
        else:
            supabase.table("dps_payments").insert({"dps_id": dps_id, "year": year, "month": month}).execute()
        flash("DPS মাসের status পরিবর্তন হয়েছে।", "ok")
    except Exception:
        flash("DPS payment status পরিবর্তন করা যায়নি। Migration SQL আগে Run করুন।", "error")
    return redirect(url_for("admin"))


@app.route("/admin/dps/<int:dps_id>/delete", methods=["POST"])
@admin_required
def delete_dps(dps_id):
    supabase.table("dps_accounts").update({"active":False}).eq("id",dps_id).execute()
    flash("DPS সরানো হয়েছে।","ok")
    return redirect(url_for("admin"))


@app.route("/admin/backup")
@admin_required
def backup_data():
    # Export application data without exposing login password hashes/secrets.
    payload = {
        "backup_version": "6.5.6",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "members": supabase.table("members").select("*").execute().data or [],
        "years": supabase.table("years").select("*").order("year").execute().data or [],
        "annual_records": supabase.table("annual_records").select("*").execute().data or [],
        "annual_settings": supabase.table("annual_settings").select("*").execute().data or [],
        "fund_settings": supabase.table("fund_settings").select("*").execute().data or [],
        "fdr_investments": supabase.table("fdr_investments").select("*").execute().data or [],
        "dps_accounts": supabase.table("dps_accounts").select("*").execute().data or [],
        "dps_payments": supabase.table("dps_payments").select("*").execute().data or [],
        "investment_settings": supabase.table("investment_settings").select("*").execute().data or [],
        "notices": supabase.table("notices").select("*").execute().data or [],
        "comments": supabase.table("comments").select("*").execute().data or [],
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    bio = io.BytesIO(raw); bio.seek(0)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return send_file(bio, mimetype="application/json", as_attachment=True, download_name=f"sommilitoproyash-backup-{stamp}.json")


@app.route("/admin/delete-year", methods=["POST"])
@admin_required
def delete_year():
    year = (request.form.get("year") or "").strip()
    years = years_all()
    if year not in years:
        abort(400)
    if len(years) <= 1:
        flash("শেষ অবশিষ্ট বছর মুছে ফেলা যাবে না।", "error")
        return redirect(url_for("admin", year=year))
    try:
        yi = int(year)
        # Delete year-specific records/settings first, then the year itself.
        supabase.table("annual_records").delete().eq("year", yi).execute()
        try:
            supabase.table("annual_settings").delete().eq("year", yi).execute()
        except Exception:
            pass
        supabase.table("years").delete().eq("year", yi).execute()
        remaining = years_all()
        next_year = remaining[0] if remaining else None
        flash(f"{year} সালের হিসাব ও Settings সফলভাবে মুছে ফেলা হয়েছে।", "ok")
        return redirect(url_for("admin", year=next_year) if next_year else url_for("admin"))
    except Exception:
        flash(f"{year} সাল মুছে ফেলা যায়নি। কোনো data সমস্যা থাকলে Supabase-এ পরীক্ষা করুন।", "error")
        return redirect(url_for("admin", year=year))


@app.route("/admin/add-year", methods=["POST"])
@admin_required
def add_year():
    y = (request.form.get("year") or "").strip()
    if not y.isdigit() or len(y) != 4:
        flash("সঠিক ৪ সংখ্যার বছর দিন।", "error"); return redirect(url_for("admin"))
    if y in years_all():
        flash("এই বছর আগে থেকেই আছে।", "error"); return redirect(url_for("admin", year=y))
    supabase.table("years").insert({"year": int(y)}).execute()
    ms = members_all()
    for m in ms:
        supabase.table("annual_records").insert({"year": int(y), "member_id": m["id"],
            "payments": [False] * 12, "down_payment_1": 0, "down_payment_2": 0,
            "down_payment_1_paid": False, "down_payment_2_paid": False}).execute()
    # New annual settings are optional; the migration will create the table.
    try:
        supabase.table("annual_settings").insert({
            "year": int(y), "monthly_amount": None,
            "down_payment_1_required": False, "down_payment_1_amount": 0,
            "down_payment_2_required": False, "down_payment_2_amount": 0,
            "mandatory_months": [True] * 12
        }).execute()
    except Exception:
        pass
    flash(f"{y} সালের হিসাব যোগ হয়েছে।", "ok")
    return redirect(url_for("admin", year=y))


@app.route("/admin/toggle/<int:member_id>/<int:month_idx>", methods=["POST"])
@admin_required
def toggle(member_id, month_idx):
    year = request.form.get("year")
    if year not in years_all() or not 0 <= month_idx < 12:
        abort(400)
    r = record_for(year, member_id)
    payments = list(r.get("payments") or [False] * 12)
    payments[month_idx] = not bool(payments[month_idx])
    supabase.table("annual_records").update({"payments": payments, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("year", int(year)).eq("member_id", member_id).execute()
    return redirect(url_for("admin", year=year))


@app.route("/admin/down-payment/<int:member_id>/<int:slot>", methods=["POST"])
@admin_required
def down_payment(member_id, slot):
    year = request.form.get("year")
    if year not in years_all() or slot not in (0, 1):
        abort(400)
    field = "down_payment_1_paid" if slot == 0 else "down_payment_2_paid"
    r = record_for(year, member_id)
    new_value = not bool(r.get(field, False))
    try:
        supabase.table("annual_records").update({
            field: new_value,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("year", int(year)).eq("member_id", member_id).execute()
    except Exception:
        # If migration is not yet installed, do not destroy old V6.2 data.
        flash("Down Payment নতুন ব্যবস্থা চালু করতে Supabase migration SQL আগে Run করুন।", "error")
    return redirect(url_for("admin", year=year))


@app.route("/admin/year-settings", methods=["POST"])
@admin_required
def update_year_settings():
    year = request.form.get("year", "")
    if year not in years_all():
        abort(400)

    try:
        monthly_raw = (request.form.get("monthly_amount") or "").strip()
        monthly_amount = None if monthly_raw == "" else max(0, float(monthly_raw))
        dp1_required = request.form.get("down_payment_1_required") == "1"
        dp2_required = request.form.get("down_payment_2_required") == "1"
        dp1_amount = max(0, float(request.form.get("down_payment_1_amount", "0") or 0))
        dp2_amount = max(0, float(request.form.get("down_payment_2_amount", "0") or 0))
        mandatory_months = [request.form.get(f"mandatory_month_{i}") == "1" for i in range(12)]

        if dp1_required and dp1_amount <= 0:
            flash("Down Payment 1 Mandatory হলে Amount অবশ্যই 0-এর বেশি হতে হবে।", "error")
            return redirect(url_for("admin", year=year))
        if dp2_required and dp2_amount <= 0:
            flash("Down Payment 2 Mandatory হলে Amount অবশ্যই 0-এর বেশি হতে হবে।", "error")
            return redirect(url_for("admin", year=year))

        payload = {
            "year": int(year),
            "monthly_amount": monthly_amount,
            "down_payment_1_required": dp1_required,
            "down_payment_1_amount": dp1_amount,
            "down_payment_2_required": dp2_required,
            "down_payment_2_amount": dp2_amount,
            "mandatory_months": mandatory_months,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        try:
            existing = supabase.table("annual_settings").select("year").eq("year", int(year)).limit(1).execute().data or []
            if existing:
                supabase.table("annual_settings").update(payload).eq("year", int(year)).execute()
            else:
                supabase.table("annual_settings").insert(payload).execute()
            flash(f"{year} সালের Year Settings সংরক্ষণ হয়েছে।", "ok")
        except Exception:
            flash("Year Settings সংরক্ষণ হয়নি। আগে v6.3_supabase_migration.sql Supabase-এ Run করুন।", "error")
    except ValueError:
        flash("Amount-এর ঘরে সঠিক সংখ্যা দিন।", "error")
    return redirect(url_for("admin", year=year))


@app.route("/admin/member/<int:member_id>", methods=["GET", "POST"])
@admin_required
def edit_member(member_id):
    m = member_by_id(member_id)
    if not m: abort(404)
    if request.method == "POST":
        try: monthly = float(request.form.get("monthly", "1000") or 0)
        except ValueError: monthly = 1000
        updates = {"name": request.form.get("name", "").strip(), "phone": request.form.get("phone", "").strip(),
                   "address": request.form.get("address", "").strip(), "monthly": max(0, monthly),
                   "blood_group": request.form.get("blood_group", "").strip(),
                   "personal_email": request.form.get("personal_email", "").strip()}
        photo = upload_photo(request.files.get("photo"), member_id)
        if photo: updates["photo"] = photo
        supabase.table("members").update(updates).eq("id", member_id).execute()
        flash("সদস্যের তথ্য সংরক্ষণ হয়েছে।", "ok")
        return redirect(url_for("admin"))
    return render_template("edit_member.html", member=m)


@app.route("/admin/add-member", methods=["POST"])
@admin_required
def add_member():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("সদস্যের নাম দিন।", "error"); return redirect(url_for("admin"))
    existing = members_all()
    new_id = max([int(m["id"]) for m in existing] or [0]) + 1
    try: monthly = float(request.form.get("monthly", "1000") or 1000)
    except ValueError: monthly = 1000
    row = {"id": new_id, "name": name, "monthly": max(0, monthly), "phone": request.form.get("phone", "").strip(),
           "address": request.form.get("address", "").strip(), "blood_group": request.form.get("blood_group", "").strip(),
           "personal_email": request.form.get("personal_email", "").strip(), "photo": "", "active": True}
    supabase.table("members").insert(row).execute()
    photo = upload_photo(request.files.get("photo"), new_id)
    if photo: supabase.table("members").update({"photo": photo}).eq("id", new_id).execute()
    for y in years_all():
        supabase.table("annual_records").insert({"year": int(y), "member_id": new_id, "payments": [False]*12,
            "down_payment_1": 0, "down_payment_2": 0,
            "down_payment_1_paid": False, "down_payment_2_paid": False}).execute()
    flash("নতুন সদস্য যোগ হয়েছে।", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/member/<int:member_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_member_status(member_id):
    m = member_by_id(member_id)
    if not m: abort(404)
    new_status = not bool(m.get("active", True))
    supabase.table("members").update({"active": new_status}).eq("id", member_id).execute()
    flash("সদস্যকে Active করা হয়েছে।" if new_status else "সদস্যকে Removed/Inactive করা হয়েছে。", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/notice/add", methods=["POST"])
@admin_required
def add_notice():
    title = (request.form.get("title") or "").strip()
    body = (request.form.get("body") or "").strip()
    pinned = request.form.get("pinned") == "1"
    if title and body:
        supabase.table("notices").insert({"title": title[:150], "body": body[:2000], "pinned": pinned}).execute()
        flash("নোটিশ যোগ হয়েছে।", "ok")
    else: flash("নোটিশের শিরোনাম ও লেখা দুটোই দিন।", "error")
    return redirect(url_for("admin"))


@app.route("/admin/notice/<int:notice_id>/delete", methods=["POST"])
@admin_required
def delete_notice(notice_id):
    supabase.table("notices").delete().eq("id", notice_id).execute()
    flash("নোটিশ মুছে ফেলা হয়েছে।", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/comment/<int:member_id>/<int:comment_id>/delete", methods=["POST"])
@admin_required
def delete_comment(member_id, comment_id):
    supabase.table("comments").delete().eq("id", comment_id).eq("member_id", member_id).execute()
    flash("মন্তব্য মুছে ফেলা হয়েছে।", "ok")
    return redirect(url_for("member", member_id=member_id))

@app.route("/admin/comment/<int:member_id>/delete-selected", methods=["POST"])
@admin_required
def delete_selected_comments(member_id):
    selected = request.form.getlist("comment_ids")
    ids = []
    for value in selected:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            pass
    if ids:
        supabase.table("comments").delete().eq("member_id", member_id).in_("id", ids).execute()
        flash(f"{len(ids)}টি মন্তব্য মুছে ফেলা হয়েছে।", "ok")
    else:
        flash("মোছার জন্য অন্তত একটি মন্তব্য নির্বাচন করুন।", "error")
    return redirect(url_for("member", member_id=member_id, year=request.form.get("year", "")))


if __name__ == "__main__":
    ensure_bucket()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
