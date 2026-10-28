import os
import re
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
DB_NAME = os.environ.get('MONGO_DB_NAME', 'student_od_db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')

_client = None

def get_client():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client

def get_db(db_name=None):
    client = get_client()
    return client[db_name or DB_NAME]

def close_db():
    global _client
    if _client is not None:
        _client.close()
        _client = None

def to_object_id(val):
    if val is None:
        return None
    if isinstance(val, ObjectId):
        return val
    if isinstance(val, str) and ObjectId.is_valid(val):
        return ObjectId(val)
    return val

def format_doc(doc):
    """Ensure standard id and string representation for templates and API."""
    if doc is None:
        return None
    doc['id'] = str(doc['_id'])
    if 'student_id' in doc and doc['student_id'] is not None:
        doc['student_id'] = str(doc['student_id'])
    if 'reviewed_by' in doc and doc['reviewed_by'] is not None:
        doc['reviewed_by'] = str(doc['reviewed_by'])
    if 'application_id' in doc and doc['application_id'] is not None:
        doc['application_id'] = str(doc['application_id'])
    return doc

def init_db(db=None):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    if db is None:
        db = get_db()

    # Users indexes: unique user_id_code, unique email
    db.users.create_index([('user_id_code', ASCENDING)], unique=True)
    db.users.create_index([('email', ASCENDING)], unique=True)

    # Applications indexes
    db.applications.create_index([('student_id', ASCENDING)])
    db.applications.create_index([('status', ASCENDING)])
    db.applications.create_index([('created_at', DESCENDING)])

    # Attendance indexes: unique compound index on student_id + date + period
    db.attendance.create_index(
        [('student_id', ASCENDING), ('date', ASCENDING), ('period', ASCENDING)],
        unique=True
    )
    db.attendance.create_index([('status', ASCENDING)])

    # Activity log index
    db.activity_logs.create_index([('timestamp', DESCENDING)])

def reset_db(db=None):
    """Reset all collections in the database (useful for test isolation or fresh seed)."""
    if db is None:
        db = get_db()
    db.users.drop()
    db.applications.drop()
    db.attendance.drop()
    db.activity_logs.drop()

def seed_data(db=None, force=False):
    if db is None:
        db = get_db()

    if force:
        reset_db(db)
        init_db(db)

    count = db.users.count_documents({})
    if count == 0:
        default_pw = generate_password_hash("password123")
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 1. Seed Demo Admin (HOD)
        admin_doc = {
            'user_id_code': "HOD-CSE-01",
            'name': "Dr. Anita Rao",
            'email': "admin@college.edu",
            'password_hash': default_pw,
            'role': "ADMIN",
            'department': "Computer Science",
            'semester': None,
            'created_at': now_str
        }
        admin_res = db.users.insert_one(admin_doc)
        admin_id = str(admin_res.inserted_id)

        # 2. Seed Demo Faculty
        faculty_doc = {
            'user_id_code': "FAC-CSE-05",
            'name': "Prof. Ramesh Kumar",
            'email': "faculty@college.edu",
            'password_hash': default_pw,
            'role': "FACULTY",
            'department': "Computer Science",
            'semester': None,
            'created_at': now_str
        }
        faculty_res = db.users.insert_one(faculty_doc)
        faculty_id = str(faculty_res.inserted_id)

        # 3. Seed Demo Students
        students = [
            ("CS21B001", "Rahul Sharma", "student@college.edu", 6),
            ("CS21B002", "Priya Patel", "priya@college.edu", 6),
            ("CS21B003", "Karthik Raja", "karthik@college.edu", 6),
            ("CS21B004", "Sneha Reddy", "sneha@college.edu", 6),
        ]

        student_ids = []
        for code, name, email, sem in students:
            s_doc = {
                'user_id_code': code,
                'name': name,
                'email': email,
                'password_hash': default_pw,
                'role': "STUDENT",
                'department': "Computer Science",
                'semester': sem,
                'created_at': now_str
            }
            s_res = db.users.insert_one(s_doc)
            student_ids.append(str(s_res.inserted_id))

        rahul_id = student_ids[0]
        priya_id = student_ids[1]

        # 4. Seed Attendance for past 10 working days for all students
        today = date.today()
        past_days = []
        cur_day = today - timedelta(days=14)
        while len(past_days) < 10 and cur_day <= today:
            if cur_day.weekday() != 6:  # Not Sunday
                past_days.append(cur_day.strftime('%Y-%m-%d'))
            cur_day += timedelta(days=1)

        attendance_records = []
        for s_id in student_ids:
            for idx, d_str in enumerate(past_days):
                # 4 periods per day for simplicity in demo
                for p in range(1, 5):
                    # Give Rahul a couple absent days on past_days[-2] to demonstrate OD fix
                    if s_id == rahul_id and idx == len(past_days) - 2:
                        status = 'ABSENT'
                    elif s_id == priya_id and idx % 4 == 0:
                        status = 'ABSENT'
                    else:
                        status = 'PRESENT'

                    attendance_records.append({
                        'student_id': str(s_id),
                        'date': d_str,
                        'period': p,
                        'status': status,
                        'application_id': None,
                        'updated_at': now_str
                    })

        if attendance_records:
            db.attendance.insert_many(attendance_records)

        # 5. Seed Sample Applications
        target_od_date = past_days[-2] if len(past_days) >= 2 else today.strftime('%Y-%m-%d')

        # Application 1: Rahul pending OD application
        app1_doc = {
            'student_id': rahul_id,
            'type': 'OD_EXTERNAL',
            'event_title': 'National Smart India Hackathon 2026',
            'start_date': target_od_date,
            'end_date': target_od_date,
            'start_period': 1,
            'end_period': 4,
            'reason': 'Represented college in the Grand Finale of SIH at IIT Bombay. Secured 2nd place.',
            'document_filename': 'sample_hackathon_ticket.pdf',
            'status': 'PENDING',
            'reviewed_by': None,
            'review_remarks': None,
            'created_at': now_str,
            'updated_at': now_str
        }
        db.applications.insert_one(app1_doc)

        # Application 2: Priya Approved Medical Leave
        past_leave_date = past_days[1] if len(past_days) >= 2 else today.strftime('%Y-%m-%d')
        app2_doc = {
            'student_id': priya_id,
            'type': 'LEAVE_MEDICAL',
            'event_title': 'Viral Fever & Doctor Advised Rest',
            'start_date': past_leave_date,
            'end_date': past_leave_date,
            'start_period': 1,
            'end_period': 4,
            'reason': 'Diagnosed with severe viral fever with 3 days bed rest advised by medical practitioner.',
            'document_filename': 'sample_medical_certificate.pdf',
            'status': 'APPROVED',
            'reviewed_by': faculty_id,
            'review_remarks': 'Verified medical certificate from Govt Hospital. Approved.',
            'created_at': now_str,
            'updated_at': now_str
        }
        app2_res = db.applications.insert_one(app2_doc)
        app2_id = str(app2_res.inserted_id)

        # Update attendance for Priya's approved leave
        db.attendance.update_many(
            {'student_id': priya_id, 'date': past_leave_date},
            {'$set': {'status': 'ON_LEAVE', 'application_id': app2_id, 'updated_at': now_str}}
        )

        # Create sample placeholder certificate files in uploads
        sample_doc_path = os.path.join(UPLOAD_FOLDER, 'sample_hackathon_ticket.pdf')
        if not os.path.exists(sample_doc_path):
            with open(sample_doc_path, 'w', encoding='utf-8') as f:
                f.write("%PDF-1.4 Mock SIH Grand Finale Invitation Letter & Participation Certificate")

        sample_med_path = os.path.join(UPLOAD_FOLDER, 'sample_medical_certificate.pdf')
        if not os.path.exists(sample_med_path):
            with open(sample_med_path, 'w', encoding='utf-8') as f:
                f.write("%PDF-1.4 Mock Medical Prescription & Fitness Certificate")

def get_user_by_id(user_id, db=None):
    if not user_id:
        return None
    if db is None:
        db = get_db()
    oid = to_object_id(user_id)
    user = db.users.find_one({'_id': oid})
    return format_doc(user)

def get_user_by_email(email, db=None):
    if not email:
        return None
    if db is None:
        db = get_db()
    user = db.users.find_one({'email': {'$regex': f'^{re.escape(email.strip())}$', '$options': 'i'}})
    return format_doc(user)

def get_all_students(db=None):
    if db is None:
        db = get_db()
    cursor = db.users.find({'role': 'STUDENT'}).sort([('user_id_code', ASCENDING)])
    return [format_doc(u) for u in cursor]

def _populate_applications(cursor, db):
    """Helper to attach student and reviewer details to application documents."""
    apps = [format_doc(a) for a in cursor]
    if not apps:
        return []

    # Cache users for fast joins
    user_ids = set()
    for a in apps:
        if a.get('student_id'):
            user_ids.add(to_object_id(a['student_id']))
        if a.get('reviewed_by'):
            user_ids.add(to_object_id(a['reviewed_by']))

    users_map = {}
    if user_ids:
        for u in db.users.find({'_id': {'$in': list(user_ids)}}):
            users_map[str(u['_id'])] = u

    for a in apps:
        s = users_map.get(str(a.get('student_id')))
        if s:
            a['student_name'] = s.get('name', 'Unknown')
            a['user_id_code'] = s.get('user_id_code', '')
            a['department'] = s.get('department', '')
            a['semester'] = s.get('semester', '')
        else:
            a['student_name'] = 'Unknown'
            a['user_id_code'] = ''
            a['department'] = ''
            a['semester'] = ''

        rev = users_map.get(str(a.get('reviewed_by'))) if a.get('reviewed_by') else None
        a['reviewer_name'] = rev.get('name') if rev else None

    return apps

def get_student_applications(student_id, db=None):
    if db is None:
        db = get_db()
    cursor = db.applications.find({'student_id': str(student_id)}).sort([('created_at', DESCENDING)])
    return _populate_applications(cursor, db)

def get_pending_applications(db=None):
    if db is None:
        db = get_db()
    cursor = db.applications.find({'status': 'PENDING'}).sort([('created_at', ASCENDING)])
    return _populate_applications(cursor, db)

def get_reviewed_applications(limit=20, db=None):
    if db is None:
        db = get_db()
    cursor = db.applications.find({'status': {'$ne': 'PENDING'}}).sort([('updated_at', DESCENDING)]).limit(limit)
    return _populate_applications(cursor, db)

def get_all_applications(db=None):
    if db is None:
        db = get_db()
    cursor = db.applications.find().sort([('created_at', DESCENDING)])
    return _populate_applications(cursor, db)

def log_activity(user_id, action, details=None, db=None):
    if db is None:
        db = get_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.activity_logs.insert_one({
        'user_id': str(user_id) if user_id else None,
        'action': action,
        'details': details,
        'timestamp': now_str
    })

if __name__ == '__main__':
    init_db()
    seed_data(force=True)
    print("MongoDB database initialized and demo data seeded successfully!")
