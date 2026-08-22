from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
from functools import wraps
from werkzeug.utils import secure_filename
import os, json
from datetime import datetime

app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","change-this-secret-key")
ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD","Sommilito@123")
DATA_FILE=os.path.join(os.path.dirname(__file__),"data.json")
UPLOAD_DIR=os.path.join(os.path.dirname(__file__),"static","uploads")
os.makedirs(UPLOAD_DIR,exist_ok=True)

def load_data():
    with open(DATA_FILE,encoding="utf-8") as f:
        d=json.load(f)
    # Backward-compatible defaults for V2 data
    d.setdefault('notices', [])
    d.setdefault('comments', {})
    for m in d.get('members',[]):
        m.setdefault('active', True)
    return d

def save_data(d):
    with open(DATA_FILE,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)

def admin_required(fn):
    @wraps(fn)
    def w(*a,**kw):
        if not session.get("admin"): return redirect(url_for("login",next=request.path))
        return fn(*a,**kw)
    return w

def get_year(d,year):
    if str(year) not in d['years']: abort(404)
    return d['years'][str(year)]

def stats(rec, member):
    pays=rec['payments']; paid=sum(pays)*member['monthly']; arrear=(len(pays)-sum(pays))*member['monthly']
    down=sum(rec.get('down_payments',[0,0]))
    return paid,arrear,down

def comments_for(d, member_id):
    return d.get('comments',{}).get(str(member_id),[])

@app.route('/')
def index():
    d=load_data(); years=sorted(d['years'],reverse=True); year=request.args.get('year',years[0])
    if year not in d['years']: year=years[0]
    yr=d['years'][year]; rows=[]; total_paid=total_arrear=total_down=0
    active_members=[m for m in d['members'] if m.get('active',True)]
    for m in active_members:
        r=yr[str(m['id'])]; paid,arrear,down=stats(r,m); rows.append((m,r,paid,arrear,down)); total_paid+=paid; total_arrear+=arrear; total_down+=down
    notices=sorted(d.get('notices',[]), key=lambda x:(x.get('pinned',False),x.get('created_at','')), reverse=True)
    return render_template('index.html',members=rows,years=years,year=year,months=d['months'],total_paid=total_paid,total_arrear=total_arrear,total_down=total_down,admin=session.get('admin',False),notices=notices)

@app.route('/member/<int:member_id>')
def member(member_id):
    d=load_data(); m=next((x for x in d['members'] if x['id']==member_id),None)
    if not m: abort(404)
    years=sorted(d['years'],reverse=True); year=request.args.get('year',years[0])
    if year not in d['years']: year=years[0]
    r=d['years'][year][str(member_id)]; paid,arrear,down=stats(r,m)
    return render_template('member.html',member=m,record=r,months=d['months'],years=years,year=year,paid=paid,arrear=arrear,down=down,admin=session.get('admin',False),comments=comments_for(d,member_id))

@app.route('/member/<int:member_id>/comment',methods=['POST'])
def add_comment(member_id):
    d=load_data(); m=next((x for x in d['members'] if x['id']==member_id),None)
    if not m: abort(404)
    author=request.form.get('author','').strip() or 'সদস্য'
    text=request.form.get('text','').strip()
    year=request.form.get('year','')
    if text:
        d.setdefault('comments',{}).setdefault(str(member_id),[]).append({'author':author[:80],'text':text[:1000],'created_at':datetime.now().strftime('%Y-%m-%d %H:%M')})
        save_data(d); flash('মন্তব্য যোগ হয়েছে।','ok')
    return redirect(url_for('member',member_id=member_id,year=year))

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        if request.form.get('password')==ADMIN_PASSWORD:
            session['admin']=True; return redirect(request.args.get('next') or url_for('index'))
        return render_template('login.html',error='পাসওয়ার্ড সঠিক নয়।')
    return render_template('login.html',error=None)
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin():
    d=load_data(); years=sorted(d['years'],reverse=True); year=request.args.get('year',years[0])
    if year not in d['years']: year=years[0]
    yr=d['years'][year]; rows=[]
    for m in d['members']:
        r=yr[str(m['id'])]; paid,arrear,down=stats(r,m); rows.append((m,r,paid,arrear,down))
    return render_template('admin.html',members=rows,years=years,year=year,months=d['months'],notices=d.get('notices',[]),comments=d.get('comments',{}))

@app.route('/admin/add-year',methods=['POST'])
@admin_required
def add_year():
    d=load_data(); y=request.form.get('year','').strip()
    if not y.isdigit() or len(y)!=4: flash('সঠিক ৪ সংখ্যার বছর দিন।','error'); return redirect(url_for('admin'))
    if y in d['years']: flash('এই বছর আগে থেকেই আছে।','error'); return redirect(url_for('admin',year=y))
    d['years'][y]={str(m['id']):{'payments':[False]*12,'down_payments':[0,0]} for m in d['members']}
    save_data(d); flash(f'{y} সালের হিসাব যোগ হয়েছে।','ok'); return redirect(url_for('admin',year=y))

@app.route('/admin/toggle/<int:member_id>/<int:month_idx>',methods=['POST'])
@admin_required
def toggle(member_id,month_idx):
    d=load_data(); y=request.form.get('year'); r=d['years'].get(y,{}).get(str(member_id))
    if r and 0<=month_idx<12: r['payments'][month_idx]=not r['payments'][month_idx]; save_data(d)
    return redirect(url_for('admin',year=y))

@app.route('/admin/down-payment/<int:member_id>/<int:slot>',methods=['POST'])
@admin_required
def down_payment(member_id,slot):
    d=load_data(); y=request.form.get('year')
    try: amount=float(request.form.get('amount','0') or 0)
    except ValueError: amount=0
    r=d['years'].get(y,{}).get(str(member_id))
    if r and slot in (0,1): r['down_payments'][slot]=amount; save_data(d)
    return redirect(url_for('admin',year=y))

@app.route('/admin/member/<int:member_id>',methods=['GET','POST'])
@admin_required
def edit_member(member_id):
    d=load_data(); m=next((x for x in d['members'] if x['id']==member_id),None)
    if not m: abort(404)
    if request.method=='POST':
        m['name']=request.form.get('name','').strip(); m['phone']=request.form.get('phone','').strip(); m['address']=request.form.get('address','').strip()
        try: m['monthly']=float(request.form.get('monthly','1000') or 0)
        except ValueError: m['monthly']=1000
        f=request.files.get('photo')
        if f and f.filename:
            ext=os.path.splitext(secure_filename(f.filename))[1].lower()
            if ext in ['.jpg','.jpeg','.png','.webp']:
                filename=f'member_{member_id}{ext}'; f.save(os.path.join(UPLOAD_DIR,filename)); m['photo']='/static/uploads/'+filename
        save_data(d); flash('সদস্যের তথ্য সংরক্ষণ হয়েছে।','ok'); return redirect(url_for('admin'))
    return render_template('edit_member.html',member=m)

@app.route('/admin/add-member',methods=['POST'])
@admin_required
def add_member():
    d=load_data()
    name=request.form.get('name','').strip()
    if not name: flash('সদস্যের নাম দিন।','error'); return redirect(url_for('admin'))
    new_id=max([m['id'] for m in d['members']] or [0])+1
    try: monthly=float(request.form.get('monthly','1000') or 1000)
    except ValueError: monthly=1000
    m={'id':new_id,'name':name,'monthly':monthly,'phone':request.form.get('phone','').strip(),'address':request.form.get('address','').strip(),'photo':'','active':True}
    f=request.files.get('photo')
    if f and f.filename:
        ext=os.path.splitext(secure_filename(f.filename))[1].lower()
        if ext in ['.jpg','.jpeg','.png','.webp']:
            filename=f'member_{new_id}{ext}'; f.save(os.path.join(UPLOAD_DIR,filename)); m['photo']='/static/uploads/'+filename
    d['members'].append(m)
    for y in d['years'].values(): y[str(new_id)]={'payments':[False]*12,'down_payments':[0,0]}
    save_data(d); flash('নতুন সদস্য যোগ হয়েছে।','ok'); return redirect(url_for('admin'))

@app.route('/admin/member/<int:member_id>/toggle-status',methods=['POST'])
@admin_required
def toggle_member_status(member_id):
    d=load_data(); m=next((x for x in d['members'] if x['id']==member_id),None)
    if not m: abort(404)
    m['active']=not m.get('active',True); save_data(d)
    flash(('সদস্যকে Active করা হয়েছে।' if m['active'] else 'সদস্যকে Removed/Inactive করা হয়েছে।'),'ok')
    return redirect(url_for('admin'))

@app.route('/admin/notice/add',methods=['POST'])
@admin_required
def add_notice():
    d=load_data(); title=request.form.get('title','').strip(); body=request.form.get('body','').strip(); pinned=request.form.get('pinned')=='1'
    if title and body:
        d.setdefault('notices',[]).append({'id':max([n.get('id',0) for n in d['notices']] or [0])+1,'title':title[:150],'body':body[:2000],'pinned':pinned,'created_at':datetime.now().strftime('%Y-%m-%d %H:%M')})
        save_data(d); flash('নোটিশ যোগ হয়েছে।','ok')
    else: flash('নোটিশের শিরোনাম ও লেখা দুটোই দিন।','error')
    return redirect(url_for('admin'))

@app.route('/admin/notice/<int:notice_id>/delete',methods=['POST'])
@admin_required
def delete_notice(notice_id):
    d=load_data(); d['notices']=[n for n in d.get('notices',[]) if n.get('id')!=notice_id]; save_data(d); flash('নোটিশ মুছে ফেলা হয়েছে।','ok'); return redirect(url_for('admin'))

@app.route('/admin/comment/<int:member_id>/<int:comment_id>/delete',methods=['POST'])
@admin_required
def delete_comment(member_id,comment_id):
    d=load_data(); arr=d.get('comments',{}).get(str(member_id),[])
    if 0<=comment_id<len(arr): arr.pop(comment_id); save_data(d); flash('মন্তব্য মুছে ফেলা হয়েছে।','ok')
    return redirect(url_for('member',member_id=member_id))

if __name__=='__main__': app.run(debug=True)
