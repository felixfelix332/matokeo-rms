import sqlite3

from django.conf import settings
from django.contrib.auth.hashers import check_password


def _school_db():
    return str(settings.DATABASES['school_data']['NAME'])


class TeacherBackend:
    """Authenticate teachers against teacher_teacheruser table in school_data db."""

    def authenticate(self, request, teacher_username=None, teacher_password=None, **kwargs):
        if not teacher_username or not teacher_password:
            return None
        conn = sqlite3.connect(_school_db())
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                'SELECT * FROM teacher_teacheruser WHERE username = ? AND is_active = 1',
                (teacher_username,)
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        conn.close()
        if not row:
            return None
        if not check_password(teacher_password, row['password_hash']):
            return None
        # Return a dict-like object stored in session (not a Django User)
        return TeacherUser(row)

    def get_user(self, user_id):
        return None


class TeacherUser:
    """Lightweight teacher representation for session storage."""
    def __init__(self, row):
        self.id = row['id']
        self.username = row['username']
        self.full_name = row['full_name']
        self.is_active = bool(row['is_active'])
        self.is_class_teacher_of_id = row['is_class_teacher_of_id']

    def to_session(self):
        return {
            'id': self.id,
            'username': self.username,
            'full_name': self.full_name,
            'is_class_teacher_of_id': self.is_class_teacher_of_id,
        }


def get_teacher_from_session(session):
    data = session.get('teacher_user')
    if not data:
        return None
    class Obj:
        pass
    t = Obj()
    t.id = data['id']
    t.username = data['username']
    t.full_name = data['full_name']
    t.is_class_teacher_of_id = data.get('is_class_teacher_of_id')
    return t


def get_teacher_assigned_classes(teacher_id, school_id=None):
    conn = sqlite3.connect(_school_db())
    conn.row_factory = sqlite3.Row
    query = (
        'SELECT tc.schoolclass_id, sc.name, sc.level '
        'FROM teacher_teacheruser_assigned_classes tc '
        'JOIN portal_schoolclass sc ON sc.id = tc.schoolclass_id '
        'WHERE tc.teacheruser_id = ?'
    )
    params = [teacher_id]
    if school_id is not None:
        query += ' AND sc.school_id = ?'
        params.append(school_id)
    query += ' ORDER BY sc.name'
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_teacher_assigned_subjects(teacher_id, school_id=None):
    conn = sqlite3.connect(_school_db())
    conn.row_factory = sqlite3.Row
    query = (
        'SELECT ts.subject_id, s.name, s.code '
        'FROM teacher_teacheruser_assigned_subjects ts '
        'JOIN portal_subject s ON s.id = ts.subject_id '
        'WHERE ts.teacheruser_id = ?'
    )
    params = [teacher_id]
    if school_id is not None:
        query += ' AND s.school_id = ?'
        params.append(school_id)
    query += ' ORDER BY s.name'
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_student_by_admission(admission_number):
    """Look up student by admission number for student login."""
    conn = sqlite3.connect(_school_db())
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            'SELECT s.*, sc.name as class_name FROM portal_student s '
            'JOIN portal_schoolclass sc ON sc.id = s.class_field_id '
            'WHERE s.admission_number = ? AND s.is_active = 1',
            (admission_number.strip().upper(),)
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    if row:
        return dict(row)
    return None
