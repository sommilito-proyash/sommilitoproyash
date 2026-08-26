from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
import os
from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Sommilito@123")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required.")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
BUCKET = "member-photos"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def logged_in():
    return bool(session.get("admin") or session.get("member_id"))


def login_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        if not logged_in():
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return w


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


def members_all(include_inactive=True):
    rows = supabase.table("members").select("*").order("id").execute().data or []
    return rows if include_inactive else [m for m in rows if m.get("active", True)]


def member_by_id(member_id):
    rows = supabase.table("members").select("*").eq("id", member_id).limit(1).execute().data or []
    return rows[0] if rows else None


def years_all():
    rows = supabase.table("years").select("year").order("year", desc=True).execute().data or []
    return [str(r["year"]) for r in rows]


def _year_data():
    """Load yearly settings and all payment records in two queries per request."""
    settings_rows = supabase.table("annual_settings").select("*").execute().data or []
    records_rows = supabase.table("annual_records").select("*").execute().data or []
    settings = {}
    for x in settings_rows:
        y = str(x.get("year"))
        settings[y] = {
            "year": int(x.get("year")),
            "monthly_amount": float(x.get("monthly_amount") or 0),
            "down_payment_1_required": bool(x.get("down_payment_1_required")),
            "down_payment_1_amount": float(x.get("down_payment_1_amount") or 0),
            "down_payment_2_required": bool(x.get("down_payment_2_required")),
            "down_payment_2_amount": float(x.get("down_payment_2_amount") or 0),
        }
    records = {}
    for r in records_rows:
        records[(str(r.get("year")), r.get("member_id"))] = r
    return settings, records


def _blank_record(year, member_id):
    return {"year": int(year), "member_id": member_id, "payments": [False] * 12,
            "down_payment_1_paid": False, "down_payment_2_paid": False}


def _record(records, year, member_id):
    r = records.get((str(year), member_id))
    if r:
        r = dict(r)
        r["payments"] = (list(r.get("payments") or [False] * 12) + [False] * 12)[:12]
        r.setdefault("down_payment_1_paid", False)
        r.setdefault("down_payment_2_paid", False)
        return r
    return _blank_record(year, member_id)


def _setting(settings, year):
    s = settings.get(str(year))
    if s:
        return s
    return {"year": int(year), "monthly_amount": 0.0,
            "down_payment_1_required": False, "down_payment_1_amount": 0.0,
            "down_payment_2_required": False, "down_payment_2_amount": 0.0}


def stats(rec, setting):
    pays = (list(rec.get("payments") or [False] * 12) + [False] * 12)[:12]
    monthly = float(setting["monthly_amount"])
    paid_months = sum(bool(x) for x in pays)
    monthly_paid = paid_months * monthly
    monthly_due = 12 * monthly
    monthly_arrear = monthly_due - monthly_paid
    d1_due = setting["down_payment_1_amount"] if setting["down_payment_1_required"] else 0.0
    d2_due = setting["down_payment_2_amount"] if setting["down_payment_2_required"] else 0.0
    d1_paid = d1_due if rec.get("down_payment_1_paid") else 0.0
    d2_paid = d2_due if rec.get("down_payment_2_paid") else 0.0
    down_paid = d1_paid + d2_paid
    down_arrear = (d1_due - d1_paid) + (d2_due - d2_paid)
    return monthly_paid + down_paid, monthly_arrear + down_arrear, down_paid, down_arrear


def member_totals(member_id, years, settings, records):
    total_paid = total_arrear = total_down = 0.0
    by_year = []
    for y in years:
        setting = _setting(settings, y)
        r = _record(records, y, member_id)
        paid, arrear, down, _ = stats(r, setting)
        total_paid += paid
        total_arrear += arrear
        total_down += down
        by_year.append((y, paid, arrear, down, setting))
    return total_paid, total_arrear, total_down, by_year


def overall_totals(members, years, settings, records):
    paid = arrear = down = 0.0
    for m in members:
        p, a, d, _ = member_totals(m["id"], years, settings, records)
        paid += p
        arrear += a
        down += d
    return paid, arrear, down

def upload_photo(file, member_id):
    if not file or not file.filename:
        return None
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        return None
    path = f"member_{member_id}{ext}"
    supabase.storage.from_(BUCKET).upload(path, file.read(), {"content-type": file.mimetype or "image/jpeg", "upsert": "true"})
    return supabase.storage.from_(BUCKET).get_public_url(path)


def comments_for(member_id):
    return supabase.table("comments").select("*").eq("member_id", member_id).order("created_at", desc=True).execute().data or []


@app.route("/")
@login_required
def index():
    years = years_all()
    if not years: abort(500, "No years found in database.")
    year = request.args.get("year", years[0]); year = year if year in years else years[0]
    settings, records = _year_data()
    setting = _setting(settings, year)
    active = members_all(False)
    rows=[]; year_paid=year_arrear=year_down=0.0
    for m in active:
        r=_record(records,year,m["id"]); paid,arrear,down,_=stats(r,setting)
        rows.append((m,r,paid,arrear,down)); year_paid+=paid; year_arrear+=arrear; year_down+=down
    overall_paid,overall_arrear,overall_down=overall_totals(active, years, settings, records)
    notices=supabase.table("notices").select("*").order("pinned",desc=True).order("created_at",desc=True).execute().data or []
    return render_template("index.html", members=rows, years=years, year=year, months=MONTHS, setting=setting,
        year_paid=year_paid,year_arrear=year_arrear,year_down=year_down,overall_paid=overall_paid,overall_arrear=overall_arrear,
        overall_down=overall_down,admin=session.get("admin",False),notices=notices,current_member_id=session.get("member_id"))


@app.route("/member/<int:member_id>")
@login_required
def member(member_id):
    m=member_by_id(member_id)
    if not m: abort(404)
    years=years_all()
    if not years: abort(500,"No years found in database.")
    year=request.args.get("year",years[0]); year=year if year in years else years[0]
    settings, records = _year_data()
    setting=_setting(settings,year); r=_record(records,year,member_id)
    paid,arrear,down,down_arrear=stats(r,setting)
    overall_paid,overall_arrear,overall_down,by_year=member_totals(member_id,years,settings,records)
    return render_template("member.html",member=m,record=r,setting=setting,months=MONTHS,years=years,year=year,
        paid=paid,arrear=arrear,down=down,down_arrear=down_arrear,overall_paid=overall_paid,overall_arrear=overall_arrear,
        overall_down=overall_down,by_year=by_year,admin=session.get("admin",False),comments=comments_for(member_id),
        current_member_id=session.get("member_id"))


@app.route("/member/<int:member_id>/comment",methods=["POST"])
@login_required
def add_comment(member_id):
    if not member_by_id(member_id): abort(404)
    author=(request.form.get("author") or "সদস্য").strip()[:80]
    text=(request.form.get("text") or "").strip()[:1000]
    year=request.form.get("year","")
    if text:
        supabase.table("comments").insert({"member_id":member_id,"author":author or "সদস্য","text":text}).execute()
        flash("মন্তব্য যোগ হয়েছে।","ok")
    return redirect(url_for("member",member_id=member_id,year=year))


@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        kind=request.form.get("kind","member")
        if kind=="admin" and request.form.get("password")==ADMIN_PASSWORD:
            session.clear(); session["admin"]=True
            return redirect(request.args.get("next") or url_for("index"))
        if kind=="member":
            email=(request.form.get("email") or "").strip().lower(); password=request.form.get("password") or ""
            rows=supabase.table("members").select("*").eq("email",email).eq("active",True).limit(1).execute().data or []
            if rows:
                m=rows[0]; ph=m.get("password_hash") or ""
                try: valid=bool(ph) and check_password_hash(ph,password)
                except Exception: valid=False
                if valid:
                    session.clear(); session["member_id"]=m["id"]
                    return redirect(request.args.get("next") or url_for("index"))
        return render_template("login.html",error="Login information is not correct.")
    return render_template("login.html",error=None)


@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))


@app.route("/admin")
@admin_required
def admin():
    years=years_all()
    if not years: abort(500,"No years found in database.")
    year=request.args.get("year",years[0]); year=year if year in years else years[0]
    settings, records = _year_data()
    setting=_setting(settings,year); rows=[]
    for m in members_all():
        r=_record(records,year,m["id"]); paid,arrear,down,_=stats(r,setting); rows.append((m,r,paid,arrear,down))
    active=[m for m in members_all() if m.get("active",True)]
    overall_paid,overall_arrear,overall_down=overall_totals(active, years, settings, records)
    notices=supabase.table("notices").select("*").order("created_at",desc=True).execute().data or []
    return render_template("admin.html",members=rows,years=years,year=year,months=MONTHS,setting=setting,
        overall_paid=overall_paid,overall_arrear=overall_arrear,overall_down=overall_down,notices=notices)


@app.route("/admin/year-settings",methods=["POST"])
@admin_required
def year_settings():
    year=request.form.get("year")
    if year not in years_all(): abort(400)
    def money(name):
        try:return max(0,float(request.form.get(name,"0") or 0))
        except ValueError:return 0
    row={"year":int(year),"monthly_amount":money("monthly_amount"),
         "down_payment_1_required":request.form.get("down_payment_1_required")=="1",
         "down_payment_1_amount":money("down_payment_1_amount"),
         "down_payment_2_required":request.form.get("down_payment_2_required")=="1",
         "down_payment_2_amount":money("down_payment_2_amount"),"updated_at":datetime.now(timezone.utc).isoformat()}
    supabase.table("annual_settings").upsert(row).execute()
    flash(f"{year} সালের হিসাবের নিয়ম সংরক্ষণ হয়েছে।","ok")
    return redirect(url_for("admin",year=year))


@app.route("/admin/add-year",methods=["POST"])
@admin_required
def add_year():
    y=(request.form.get("year") or "").strip()
    if not y.isdigit() or len(y)!=4: flash("সঠিক ৪ সংখ্যার বছর দিন।","error"); return redirect(url_for("admin"))
    if y in years_all(): flash("এই বছর আগে থেকেই আছে।","error"); return redirect(url_for("admin",year=y))
    supabase.table("years").insert({"year":int(y)}).execute()
    supabase.table("annual_settings").upsert({"year":int(y),"monthly_amount":0,"down_payment_1_required":False,"down_payment_1_amount":0,"down_payment_2_required":False,"down_payment_2_amount":0}).execute()
    for m in members_all():
        supabase.table("annual_records").insert({"year":int(y),"member_id":m["id"],"payments":[False]*12,"down_payment_1_paid":False,"down_payment_2_paid":False}).execute()
    flash(f"{y} সালের হিসাব যোগ হয়েছে।","ok"); return redirect(url_for("admin",year=y))


@app.route("/admin/toggle/<int:member_id>/<int:month_idx>",methods=["POST"])
@admin_required
def toggle(member_id,month_idx):
    year=request.form.get("year")
    if year not in years_all() or not 0<=month_idx<12: abort(400)
    if not member_by_id(member_id): abort(404)
    _, records = _year_data()
    r=_record(records,year,member_id); payments=(list(r.get("payments") or [False]*12)+[False]*12)[:12]
    payments[month_idx]=not bool(payments[month_idx])
    supabase.table("annual_records").update({"payments":payments,"updated_at":datetime.now(timezone.utc).isoformat()}).eq("year",int(year)).eq("member_id",member_id).execute()
    return redirect(url_for("admin",year=year))


@app.route("/admin/down-payment/<int:member_id>/<int:slot>",methods=["POST"])
@admin_required
def down_payment(member_id,slot):
    year=request.form.get("year")
    if year not in years_all() or slot not in (0,1): abort(400)
    field="down_payment_1_paid" if slot==0 else "down_payment_2_paid"
    paid=request.form.get("paid")=="1"
    supabase.table("annual_records").update({field:paid,"updated_at":datetime.now(timezone.utc).isoformat()}).eq("year",int(year)).eq("member_id",member_id).execute()
    return redirect(url_for("admin",year=year))


@app.route("/admin/member/<int:member_id>",methods=["GET","POST"])
@admin_required
def edit_member(member_id):
    m=member_by_id(member_id)
    if not m: abort(404)
    if request.method=="POST":
        updates={"name":request.form.get("name","").strip(),"email":request.form.get("email","").strip().lower(),"phone":request.form.get("phone","").strip(),"address":request.form.get("address","").strip()}
        if not updates["name"]: flash("সদস্যের নাম দিন।","error"); return render_template("edit_member.html",member=m)
        new_password=request.form.get("password") or ""
        if new_password.strip(): updates["password_hash"]=generate_password_hash(new_password.strip())
        photo=upload_photo(request.files.get("photo"),member_id)
        if photo: updates["photo"]=photo
        supabase.table("members").update(updates).eq("id",member_id).execute()
        flash("সদস্যের তথ্য সংরক্ষণ হয়েছে।","ok")
        return redirect(url_for("admin",year=request.form.get("year") or years_all()[0]))
    return render_template("edit_member.html",member=m)


@app.route("/admin/add-member",methods=["POST"])
@admin_required
def add_member():
    name=(request.form.get("name") or "").strip()
    if not name: flash("সদস্যের নাম দিন।","error"); return redirect(url_for("admin"))
    existing=members_all(); new_id=max([int(m["id"]) for m in existing] or [0])+1
    password=(request.form.get("password") or "").strip()
    row={"id":new_id,"name":name,"email":request.form.get("email","").strip().lower(),"monthly":0,"phone":request.form.get("phone","").strip(),"address":request.form.get("address","").strip(),"photo":"","active":True,"password_hash":generate_password_hash(password) if password else ""}
    supabase.table("members").insert(row).execute()
    photo=upload_photo(request.files.get("photo"),new_id)
    if photo: supabase.table("members").update({"photo":photo}).eq("id",new_id).execute()
    for y in years_all():
        supabase.table("annual_records").upsert({"year":int(y),"member_id":new_id,"payments":[False]*12,"down_payment_1_paid":False,"down_payment_2_paid":False}).execute()
    flash("নতুন সদস্য যোগ হয়েছে।","ok"); return redirect(url_for("admin"))


@app.route("/admin/member/<int:member_id>/toggle-status",methods=["POST"])
@admin_required
def toggle_member_status(member_id):
    m=member_by_id(member_id)
    if not m: abort(404)
    new_status=not bool(m.get("active",True)); supabase.table("members").update({"active":new_status}).eq("id",member_id).execute()
    flash("সদস্যকে Active করা হয়েছে।" if new_status else "সদস্যকে Removed/Inactive করা হয়েছে।","ok"); return redirect(url_for("admin"))


@app.route("/admin/notice/add",methods=["POST"])
@admin_required
def add_notice():
    title=(request.form.get("title") or "").strip(); body=(request.form.get("body") or "").strip(); pinned=request.form.get("pinned")=="1"
    if title and body: supabase.table("notices").insert({"title":title[:150],"body":body[:2000],"pinned":pinned}).execute(); flash("নোটিশ যোগ হয়েছে।","ok")
    else: flash("নোটিশের শিরোনাম ও লেখা দুটোই দিন।","error")
    return redirect(url_for("admin"))

@app.route("/admin/notice/<int:notice_id>/delete",methods=["POST"])
@admin_required
def delete_notice(notice_id):
    supabase.table("notices").delete().eq("id",notice_id).execute(); flash("নোটিশ মুছে ফেলা হয়েছে।","ok"); return redirect(url_for("admin"))

@app.route("/admin/comment/<int:member_id>/<int:comment_id>/delete",methods=["POST"])
@admin_required
def delete_comment(member_id,comment_id):
    supabase.table("comments").delete().eq("id",comment_id).eq("member_id",member_id).execute(); flash("মন্তব্য মুছে ফেলা হয়েছে।","ok"); return redirect(url_for("member",member_id=member_id))

if __name__=="__main__":
    ensure_bucket(); app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
