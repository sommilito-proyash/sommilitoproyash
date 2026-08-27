from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
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
    rows = (supabase.table("annual_records").select("*")
            .eq("year", int(year)).eq("member_id", member_id).limit(1).execute().data or [])
    if rows:
        r = rows[0]
        r.setdefault("payments", [False] * 12)
        r.setdefault("down_payment_1", 0)
        r.setdefault("down_payment_2", 0)
        return r
    return {"year": int(year), "member_id": member_id, "payments": [False] * 12,
            "down_payment_1": 0, "down_payment_2": 0}


def stats(rec, member):
    pays = rec.get("payments") or [False] * 12
    monthly = float(member.get("monthly") or 0)
    paid = sum(bool(x) for x in pays) * monthly
    arrear = (12 - sum(bool(x) for x in pays)) * monthly
    down = float(rec.get("down_payment_1") or 0) + float(rec.get("down_payment_2") or 0)
    return paid, arrear, down


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


def comments_for(member_id):
    return (supabase.table("comments").select("*").eq("member_id", member_id)
            .order("created_at", desc=True).execute().data or [])


def get_setting(key, default=""):
    rows = (supabase.table("site_settings").select("value")
            .eq("key", key).limit(1).execute().data or [])
    return rows[0]["value"] if rows else default


def set_setting(key, value):
    existing = (supabase.table("site_settings").select("key")
                .eq("key", key).limit(1).execute().data or [])
    if existing:
        supabase.table("site_settings").update({"value": value}).eq("key", key).execute()
    else:
        supabase.table("site_settings").insert({"key": key, "value": value}).execute()


def member_credentials():
    email = get_setting("member_email", MEMBER_EMAIL_DEFAULT).strip()
    password_hash = get_setting("member_password_hash", "")
    return email, password_hash


def member_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        if not (session.get("member") or session.get("admin")):
            return redirect(url_for("member_login", next=request.path))
        return fn(*a, **kw)
    return w


@app.route("/")
@member_required
def index():
    years = years_all()
    if not years:
        abort(500, "No years found in database.")
    year = request.args.get("year", years[0])
    if year not in years:
        year = years[0]
    active = [m for m in members_all() if m.get("active", True)]
    rows, total_paid, total_arrear, total_down = [], 0, 0, 0
    for m in active:
        r = record_for(year, m["id"])
        paid, arrear, down = stats(r, m)
        rows.append((m, r, paid, arrear, down))
        total_paid += paid; total_arrear += arrear; total_down += down
    notices = (supabase.table("notices").select("*")
               .order("pinned", desc=True).order("created_at", desc=True).execute().data or [])
    return render_template("index.html", members=rows, years=years, year=year, months=MONTHS,
                           total_paid=total_paid, total_arrear=total_arrear, total_down=total_down,
                           admin=session.get("admin", False), notices=notices)


@app.route("/member/<int:member_id>")
@member_required
def member(member_id):
    m = member_by_id(member_id)
    if not m: abort(404)
    years = years_all()
    year = request.args.get("year", years[0])
    if year not in years: year = years[0]
    r = record_for(year, member_id)
    paid, arrear, down = stats(r, m)
    return render_template("member.html", member=m, record=r, months=MONTHS, years=years,
                           year=year, paid=paid, arrear=arrear, down=down,
                           admin=session.get("admin", False), comments=comments_for(member_id))


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
    year = request.args.get("year", years[0])
    if year not in years: year = years[0]
    rows = []
    for m in members_all():
        r = record_for(year, m["id"])
        paid, arrear, down = stats(r, m)
        rows.append((m, r, paid, arrear, down))
    notices = supabase.table("notices").select("*").order("created_at", desc=True).execute().data or []
    member_email, _ = member_credentials()
    return render_template("admin.html", members=rows, years=years, year=year, months=MONTHS,
                           notices=notices, member_email=member_email)


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
            "payments": [False] * 12, "down_payment_1": 0, "down_payment_2": 0}).execute()
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
    if year not in years_all() or slot not in (0, 1): abort(400)
    try: amount = float(request.form.get("amount", "0") or 0)
    except ValueError: amount = 0
    field = "down_payment_1" if slot == 0 else "down_payment_2"
    supabase.table("annual_records").update({field: max(0, amount), "updated_at": datetime.now(timezone.utc).isoformat()}).eq("year", int(year)).eq("member_id", member_id).execute()
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
                   "address": request.form.get("address", "").strip(), "monthly": max(0, monthly)}
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
           "address": request.form.get("address", "").strip(), "photo": "", "active": True}
    supabase.table("members").insert(row).execute()
    photo = upload_photo(request.files.get("photo"), new_id)
    if photo: supabase.table("members").update({"photo": photo}).eq("id", new_id).execute()
    for y in years_all():
        supabase.table("annual_records").insert({"year": int(y), "member_id": new_id, "payments": [False]*12,
            "down_payment_1": 0, "down_payment_2": 0}).execute()
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


if __name__ == "__main__":
    ensure_bucket()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
