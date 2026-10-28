import os
import csv
import io
import re
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_from_directory, Response
)
from pymongo import ASCENDING, DESCENDING
import database

app = Flask(__name__)
app.secret_key = 'campus_od_secure_secret_key_2026'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_attendance_metrics(student_id, db=None):
    if db is None:
        db = database.get_db()

    sid_str = str(student_id)
    sid_oid = database.to_object_id(student_id)

    pipeline = [
        {'$match': {'student_id': {'$in': [sid_str, sid_oid]}}},
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
    ]
    rows = list(db.attendance.aggregate(pipeline))

    counts = {'PRESENT': 0, 'ABSENT': 0, 'OD': 0, 'ON_LEAVE': 0}
    for r in rows:
        status_key = r['_id']
        counts[status_key] = r['count']

    total = sum(counts.values())
    present = counts.get('PRESENT', 0)
    od_credits = counts.get('OD', 0)
    attended_effective = present + od_credits  # OD counts toward authorized attendance!
    percentage = round((attended_effective / total * 100), 1) if total > 0 else 100.0

    return {
        'total': total,
        'present': present,
        'od_credits': od_credits,
        'leaves': counts.get('ON_LEAVE', 0),
        'absent': counts.get('ABSENT', 0),
        'attended_effective': attended_effective,
        'percentage': percentage
    }

def sync_attendance_for_application(app_id, db=None):
    """
    Automatic Attendance Synchronization Engine:
    When an OD or Leave request is approved, this updates/creates
    the attendance records for the target dates and periods.
    """
    if db is None:
        db = database.get_db()

    app_oid = database.to_object_id(app_id)
    app_data = db.applications.find_one({'_id': app_oid})

    if not app_data:
        return

    student_id = str(app_data['student_id'])
    req_type = app_data.get('type', '')
    start_d = datetime.strptime(app_data['start_date'], '%Y-%m-%d').date()
    end_d = datetime.strptime(app_data['end_date'], '%Y-%m-%d').date()
    p_start = int(app_data.get('start_period') or 1)
    p_end = int(app_data.get('end_period') or 4)

    new_status = 'OD' if 'OD' in req_type else 'ON_LEAVE'
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    curr_d = start_d
    while curr_d <= end_d:
        if curr_d.weekday() != 6:  # Exclude Sunday
            d_str = curr_d.strftime('%Y-%m-%d')
            for p in range(p_start, p_end + 1):
                db.attendance.update_one(
                    {
                        'student_id': student_id,
                        'date': d_str,
                        'period': p
                    },
                    {
                        '$set': {
                            'status': new_status,
                            'application_id': str(app_data['_id']),
                            'updated_at': now_str
                        }
                    },
                    upsert=True
                )
        curr_d += timedelta(days=1)

# --------------------------------------------------------------------------
# Authentication & Access Control
# --------------------------------------------------------------------------
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    role = session.get('role')
    if role == 'STUDENT':
        return redirect(url_for('student_dashboard'))
    elif role == 'FACULTY':
        return redirect(url_for('faculty_dashboard'))
    elif role == 'ADMIN':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = database.get_user_by_email(email)

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['user_id_code'] = user['user_id_code']
            session['name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
            session['department'] = user['department']

            flash(f"Welcome back, {user['name']}!", 'success')
            return redirect(url_for('index'))
        else:
            flash("Invalid email address or password. Try one of the quick demo buttons.", 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out successfully.", 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        user_id_code = request.form.get('user_id_code', '').strip().upper()
        email = request.form.get('email', '').strip().lower()
        department = request.form.get('department')
        semester = int(request.form.get('semester', 1))
        password = request.form.get('password', '')

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", 'warning')
            return render_template('register.html')

        db = database.get_db()
        existing_user = db.users.find_one({
            '$or': [
                {'email': {'$regex': f'^{re.escape(email)}$', '$options': 'i'}},
                {'user_id_code': user_id_code}
            ]
        })
        if existing_user:
            flash("User with this email or Register Number already exists.", 'danger')
            return render_template('register.html')

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_user = {
            'user_id_code': user_id_code,
            'name': name,
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'STUDENT',
            'department': department,
            'semester': semester,
            'created_at': now_str
        }
        res = db.users.insert_one(new_user)
        new_student_id = str(res.inserted_id)

        # Seed sample baseline attendance so student has non-zero records
        today = date.today()
        for offset in range(1, 6):
            past_d = (today - timedelta(days=offset)).strftime('%Y-%m-%d')
            for p in range(1, 5):
                db.attendance.update_one(
                    {
                        'student_id': new_student_id,
                        'date': past_d,
                        'period': p
                    },
                    {
                        '$setOnInsert': {
                            'student_id': new_student_id,
                            'date': past_d,
                            'period': p,
                            'status': 'PRESENT',
                            'application_id': None,
                            'updated_at': now_str
                        }
                    },
                    upsert=True
                )

        database.log_activity(new_student_id, 'USER_REGISTERED', f"Student {name} ({user_id_code}) registered.")
        flash("Registration successful! You can now log in.", 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# --------------------------------------------------------------------------
# Student Portal
# --------------------------------------------------------------------------
@app.route('/student/dashboard')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'STUDENT':
        flash("Please log in as a student.", 'warning')
        return redirect(url_for('login'))

    student_id = session['user_id']
    db = database.get_db()

    user = database.get_user_by_id(student_id, db)
    if not user:
        session.clear()
        return redirect(url_for('login'))

    # Applications list
    applications = database.get_student_applications(student_id, db)

    # Calculate statistics
    attendance_stats = calculate_attendance_metrics(student_id, db)

    pending_count = db.applications.count_documents({
        'student_id': str(student_id),
        'status': 'PENDING'
    })

    approved_od_count = db.applications.count_documents({
        'student_id': str(student_id),
        'status': 'APPROVED',
        'type': {'$regex': '^OD'}
    })

    # Recent attendance grouping by date
    att_cursor = db.attendance.find({
        'student_id': str(student_id)
    }).sort([('date', DESCENDING), ('period', ASCENDING)]).limit(40)
    att_rows = list(att_cursor)

    # Group by date for grid display
    daily_attendance = {}
    for row in att_rows:
        d = row['date']
        if d not in daily_attendance:
            daily_attendance[d] = {'date': d, 'periods': {}}
        daily_attendance[d]['periods'][row['period']] = row['status']

    recent_attendance = list(daily_attendance.values())[:7]  # Show last 7 days
    today_str = date.today().strftime('%Y-%m-%d')

    return render_template(
        'student_dashboard.html',
        user=user,
        applications=applications,
        attendance_stats=attendance_stats,
        pending_count=pending_count,
        approved_od_count=approved_od_count,
        recent_attendance=recent_attendance,
        today_str=today_str
    )

@app.route('/student/apply', methods=['POST'])
def apply_request():
    if 'user_id' not in session or session.get('role') != 'STUDENT':
        return redirect(url_for('login'))

    student_id = session['user_id']
    req_type = request.form.get('type')
    event_title = request.form.get('event_title', '').strip()
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    start_period = int(request.form.get('start_period', 1))
    end_period = int(request.form.get('end_period', 4))
    reason = request.form.get('reason', '').strip()

    if not event_title or not start_date or not end_date or not reason:
        flash("Please fill in all mandatory fields.", 'danger')
        return redirect(url_for('student_dashboard'))

    # Handle document upload
    filename = None
    if 'document' in request.files:
        file = request.files['document']
        if file and file.filename != '' and allowed_file(file.filename):
            clean_name = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{timestamp}_{clean_name}"
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db = database.get_db()
    app_doc = {
        'student_id': str(student_id),
        'type': req_type,
        'event_title': event_title,
        'start_date': start_date,
        'end_date': end_date,
        'start_period': start_period,
        'end_period': end_period,
        'reason': reason,
        'document_filename': filename,
        'status': 'PENDING',
        'reviewed_by': None,
        'review_remarks': None,
        'created_at': now_str,
        'updated_at': now_str
    }
    db.applications.insert_one(app_doc)
    database.log_activity(student_id, 'APPLICATION_SUBMITTED', f"Submitted {req_type} for {event_title}")

    flash(f"Your application for '{event_title}' has been submitted for faculty review!", 'success')
    return redirect(url_for('student_dashboard'))

# --------------------------------------------------------------------------
# Faculty Portal
# --------------------------------------------------------------------------
@app.route('/faculty/dashboard')
def faculty_dashboard():
    if 'user_id' not in session or session.get('role') not in ['FACULTY', 'ADMIN']:
        flash("Faculty login required to access review desk.", 'warning')
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = database.get_db()
    user = database.get_user_by_id(user_id, db)

    # Pending applications
    pending_raw = database.get_pending_applications(db)

    # Augment pending apps with student's current attendance %
    pending_apps = []
    for item in pending_raw:
        metrics = calculate_attendance_metrics(item['student_id'], db)
        item['student_attendance_pct'] = metrics['percentage']
        pending_apps.append(item)

    # Reviewed history
    reviewed_apps = database.get_reviewed_applications(limit=20, db=db)

    approved_count = db.applications.count_documents({'status': 'APPROVED'})
    rejected_count = db.applications.count_documents({'status': 'REJECTED'})

    return render_template(
        'faculty_dashboard.html',
        user=user,
        pending_apps=pending_apps,
        reviewed_apps=reviewed_apps,
        approved_count=approved_count,
        rejected_count=rejected_count
    )

@app.route('/faculty/review', methods=['POST'])
def faculty_review():
    if 'user_id' not in session or session.get('role') not in ['FACULTY', 'ADMIN']:
        return redirect(url_for('login'))

    reviewer_id = session['user_id']
    app_id = request.form.get('application_id')
    decision = request.form.get('decision')  # 'APPROVE' or 'REJECT'
    remarks = request.form.get('review_remarks', '').strip()

    status = 'APPROVED' if decision == 'APPROVE' else 'REJECTED'
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    db = database.get_db()
    app_oid = database.to_object_id(app_id)
    db.applications.update_one(
        {'_id': app_oid},
        {
            '$set': {
                'status': status,
                'reviewed_by': str(reviewer_id),
                'review_remarks': remarks,
                'updated_at': now_str
            }
        }
    )

    # Trigger Attendance Synchronization Engine on APPROVAL
    if status == 'APPROVED':
        sync_attendance_for_application(app_id, db)
        database.log_activity(reviewer_id, 'APPLICATION_APPROVED', f"Approved application #{app_id}")
        flash(f"Application approved. Attendance records have been automatically synchronized!", 'success')
    else:
        database.log_activity(reviewer_id, 'APPLICATION_REJECTED', f"Rejected application #{app_id}")
        flash(f"Application was rejected with remarks recorded.", 'warning')

    return redirect(url_for('faculty_dashboard'))

# --------------------------------------------------------------------------
# Administrator & HOD Portal
# --------------------------------------------------------------------------
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'ADMIN':
        flash("Administrator privileges required.", 'danger')
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = database.get_db()
    user = database.get_user_by_id(user_id, db)

    # All students summary
    students = database.get_all_students(db)

    students_summary = []
    shortage_count = 0
    total_pct_sum = 0

    for s in students:
        metrics = calculate_attendance_metrics(s['id'], db)
        s_data = dict(s)
        s_data.update(metrics)
        if metrics['percentage'] < 75.0:
            shortage_count += 1
        total_pct_sum += metrics['percentage']
        students_summary.append(s_data)

    avg_attendance = round(total_pct_sum / len(students_summary), 1) if students_summary else 0.0

    total_approved_od = db.applications.count_documents({
        'status': 'APPROVED',
        'type': {'$regex': '^OD'}
    })

    # Master applications audit
    all_applications = database.get_all_applications(db)

    return render_template(
        'admin_dashboard.html',
        user=user,
        students_summary=students_summary,
        shortage_count=shortage_count,
        avg_attendance=avg_attendance,
        total_approved_od=total_approved_od,
        all_applications=all_applications
    )

@app.route('/admin/export-attendance-csv')
def export_attendance_csv():
    if 'user_id' not in session or session.get('role') != 'ADMIN':
        return redirect(url_for('login'))

    db = database.get_db()
    students = database.get_all_students(db)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Register No', 'Student Name', 'Department', 'Semester',
        'Total Sessions', 'Present Sessions', 'OD Credited Sessions',
        'Effective Attended', 'Attendance Percentage', 'Eligibility Status'
    ])

    for s in students:
        metrics = calculate_attendance_metrics(s['id'], db)
        status_elig = 'ELIGIBLE' if metrics['percentage'] >= 75.0 else 'DETAINED / SHORTAGE'
        writer.writerow([
            s['user_id_code'],
            s['name'],
            s['department'],
            s['semester'],
            metrics['total'],
            metrics['present'],
            metrics['od_credits'],
            metrics['attended_effective'],
            f"{metrics['percentage']}%",
            status_elig
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=master_student_attendance_od_report.csv"}
    )

# --------------------------------------------------------------------------
# Static File & Upload Serving
# --------------------------------------------------------------------------
@app.route('/uploads/<filename>')
def view_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    # Initialize DB on start if not already done
    database.init_db()
    database.seed_data()
    print("=" * 65)
    print("🎓 CampusOD System running at: http://127.0.0.1:5000")
    print("MongoDB Connected: mongodb://localhost:27017/student_od_db")
    print("Demo Student:  student@college.edu / password123")
    print("Demo Faculty:  faculty@college.edu / password123")
    print("Demo Admin:    admin@college.edu   / password123")
    print("=" * 65)
    app.run(debug=True, port=5000)
