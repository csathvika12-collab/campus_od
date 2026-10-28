import os
import unittest
from app import app
import database

class CampusODTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        # Use clean isolated test database or reset test collection
        database.reset_db()
        database.init_db()
        database.seed_data(force=True)

    def test_login_page_renders(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Portal Sign In', response.data)
        self.assertIn(b'student@college.edu', response.data)

    def test_student_login_and_dashboard(self):
        # Login as student
        response = self.client.post('/login', data={
            'email': 'student@college.edu',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Rahul Sharma', response.data)
        self.assertIn(b'Apply for OD / Leave', response.data)

    def test_faculty_login_and_approval_workflow(self):
        # 1. Login as Faculty
        response = self.client.post('/login', data={
            'email': 'faculty@college.edu',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Faculty Evaluation Desk', response.data)

        # 2. Get pending application from MongoDB
        db = database.get_db()
        pending_app = db.applications.find_one({'status': 'PENDING'})

        self.assertIsNotNone(pending_app, "Should have a pending application seeded in MongoDB")
        app_id = str(pending_app['_id'])
        student_id = str(pending_app['student_id'])

        # 3. Approve the application
        review_resp = self.client.post('/faculty/review', data={
            'application_id': app_id,
            'decision': 'APPROVE',
            'review_remarks': 'Verified participation certificate. Attendance updated.'
        }, follow_redirects=True)
        self.assertEqual(review_resp.status_code, 200)
        self.assertIn(b'Attendance records have been automatically synchronized', review_resp.data)

        # 4. Verify in MongoDB that attendance was synchronized to 'OD'
        od_count = db.attendance.count_documents({'student_id': student_id, 'status': 'OD'})
        self.assertGreater(od_count, 0, "OD attendance records should be generated in MongoDB upon approval!")

    def test_admin_dashboard_and_csv_export(self):
        # Login as Admin
        response = self.client.post('/login', data={
            'email': 'admin@college.edu',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Master Attendance & OD Credit Register', response.data)

        # Test CSV export
        csv_resp = self.client.get('/admin/export-attendance-csv')
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn(b'Register No,Student Name', csv_resp.data)

    def test_student_application_submission(self):
        # Login as student
        self.client.post('/login', data={
            'email': 'student@college.edu',
            'password': 'password123'
        }, follow_redirects=True)

        resp = self.client.post('/student/apply', data={
            'type': 'OD_INTERNAL',
            'event_title': 'Inter-College RoboWars 2026',
            'start_date': '2026-09-10',
            'end_date': '2026-09-10',
            'start_period': '1',
            'end_period': '4',
            'reason': 'Selected for finals of robotics competition.'
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        db = database.get_db()
        app_created = db.applications.find_one({'event_title': 'Inter-College RoboWars 2026'})
        self.assertIsNotNone(app_created)
        self.assertEqual(app_created['status'], 'PENDING')

    def test_new_student_registration(self):
        resp = self.client.post('/register', data={
            'name': 'Anita Verma',
            'user_id_code': 'CS21B099',
            'email': 'anita.v@college.edu',
            'department': 'Computer Science',
            'semester': '6',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Registration successful', resp.data)

        db = database.get_db()
        user = db.users.find_one({'user_id_code': 'CS21B099'})
        self.assertIsNotNone(user)
        self.assertEqual(user['name'], 'Anita Verma')

if __name__ == '__main__':
    unittest.main()
