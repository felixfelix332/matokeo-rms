import json
import sqlite3
import shutil
import os
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.http import FileResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .backends import (
    TeacherBackend, get_student_by_admission,
)


DEFAULT_SCHOOL_NAME = 'MUN INTERNATIONAL SCHOOL'
DEFAULT_SCHOOL_DETAILS = '(PRIMARY)\nMombasa,Kenya\nMotto: Education is Treasure\nmuninternational@gmail.com'

SCHOOL_CLASS_EXTRA_COLUMNS = {
    'class_teacher_name': "varchar(200) DEFAULT ''",
    'promoting_class': "varchar(120) DEFAULT ''",
    'repeating_class': "varchar(120) DEFAULT ''",
    'template_name': "varchar(120) DEFAULT ''",
}

STUDENT_EXTRA_COLUMNS = {
    'email': "varchar(254) DEFAULT ''",
    'address': "TEXT DEFAULT ''",
    'date_of_admission': 'date',
    'state_of_origin': "varchar(120) DEFAULT ''",
    'local_government': "varchar(120) DEFAULT ''",
}

def _authenticate_db_action(request):
    """Validate the login-page credentials before DB actions run."""
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')

    if not username or not password:
        messages.error(
            request,
            'Enter the correct admin username and password before using database tools.',
            extra_tags='db-modal',
        )
        return None

    user = authenticate(request, username=username, password=password)
    if user is None:
        messages.error(
            request,
            'Input the correct admin username and password to continue this action.',
            extra_tags='db-modal',
        )
        return None

    return user


def _default_abbreviation(name):
    parts = [part for part in (name or '').replace('-', ' ').split() if part]
    if not parts:
        return 'SCH'
    if len(parts) == 1:
        cleaned = ''.join(ch for ch in parts[0] if ch.isalnum())
        return (cleaned[:3] or 'SCH').upper()
    return ''.join(part[0] for part in parts[:6]).upper()


def _media_url(relative_path):
    if not relative_path:
        return ''
    normalized = str(relative_path).replace('\\', '/')
    if normalized.startswith(('http://', 'https://', '/')):
        return normalized
    return f"{settings.MEDIA_URL.rstrip('/')}/{normalized.lstrip('/')}"


def _save_school_media(uploaded_file, folder_name='schools'):
    target_dir = Path(settings.MEDIA_ROOT) / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(Path(uploaded_file.name).stem) or 'asset'
    suffix = Path(uploaded_file.name).suffix.lower() or '.bin'
    filename = f'{stem}-{datetime.now().strftime("%Y%m%d%H%M%S%f")}{suffix}'
    destination = target_dir / filename
    with destination.open('wb+') as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)
    return str(Path(folder_name) / filename).replace('\\', '/')


def _table_columns(conn, table_name):
    rows = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    columns = set()
    for row in rows:
        if isinstance(row, sqlite3.Row):
            columns.add(row['name'])
        else:
            columns.add(row[1])
    return columns


def _delete_school_media(relative_path):
    normalized = (relative_path or '').strip().replace('\\', '/')
    if not normalized or normalized.startswith(('http://', 'https://', '/')):
        return

    target = Path(settings.MEDIA_ROOT) / Path(normalized)
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass


def _extract_school_details(other_details):
    details = (other_details or '').strip()
    email = ''
    phone = ''
    tagline = ''
    for line in [item.strip() for item in details.splitlines() if item.strip()]:
        lower = line.lower()
        if not email and '@' in line and '.' in line.split('@')[-1]:
            email = line
        if not phone and sum(ch.isdigit() for ch in line) >= 7:
            phone = line
        if not tagline and lower.startswith('motto:'):
            tagline = line.split(':', 1)[1].strip()
    return {
        'email': email,
        'phone': phone,
        'tagline': tagline,
        'address': details,
    }


def _decorate_school_record(school):
    school = dict(school)
    school['logo_path'] = school.get('logo') or ''
    school['secondary_logo_path'] = school.get('secondary_logo') or school.get('stamp') or ''
    school['logo_url'] = _media_url(school['logo_path'])
    school['secondary_logo_url'] = _media_url(school['secondary_logo_path'])
    return school


def _ensure_school_data_schema(conn):
    """Create the minimal school-data schema for login/add-school/select-school."""
    conn.executescript(
        '''
        CREATE TABLE IF NOT EXISTS portal_school (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name varchar(200),
            abbreviation varchar(20),
            email varchar(254),
            phone varchar(20),
            address TEXT,
            website varchar(200),
            principal_name varchar(200),
            logo varchar(100)
        );

        CREATE TABLE IF NOT EXISTS portal_schoolclass (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name varchar(100) NOT NULL,
            level varchar(50) NOT NULL,
            school_id bigint NOT NULL
        );

        CREATE TABLE IF NOT EXISTS portal_student (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_number varchar(50) NOT NULL,
            first_name varchar(100) NOT NULL,
            last_name varchar(100) NOT NULL,
            middle_name varchar(100) DEFAULT '',
            date_of_birth date,
            gender varchar(10) DEFAULT '',
            parent_name varchar(200) DEFAULT '',
            parent_phone varchar(20) DEFAULT '',
            is_active bool NOT NULL DEFAULT 1,
            portal_access_enabled bool NOT NULL DEFAULT 0,
            class_field_id bigint NOT NULL,
            school_id bigint NOT NULL,
            image varchar(100) DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS portal_academicsession (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_name varchar(120) NOT NULL,
            start_date date,
            end_date date,
            is_active bool NOT NULL DEFAULT 0,
            school_id bigint NOT NULL
        );

        CREATE TABLE IF NOT EXISTS portal_term (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term_name varchar(120) NOT NULL,
            start_date date,
            end_date date,
            is_active bool NOT NULL DEFAULT 0,
            session_id bigint NOT NULL,
            times_school_open integer DEFAULT 0,
            term_duration integer DEFAULT 0,
            next_term_begins date
        );

        CREATE TABLE IF NOT EXISTS teacher_teacheruser (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name varchar(100) NOT NULL,
            last_name varchar(100) DEFAULT '',
            middle_name varchar(100) DEFAULT '',
            gender varchar(10) DEFAULT '',
            date_of_birth date,
            phone varchar(30) DEFAULT '',
            email varchar(254) DEFAULT '',
            address TEXT DEFAULT '',
            experience varchar(200) DEFAULT '',
            qualifications TEXT DEFAULT '',
            image varchar(255) DEFAULT '',
            signature varchar(120) DEFAULT '',
            school_id bigint NOT NULL,
            is_active bool NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS rps_school (
            id INTEGER PRIMARY KEY,
            name varchar(200) NOT NULL,
            abbreviation varchar(20) DEFAULT '',
            email varchar(254) DEFAULT '',
            phone varchar(20) DEFAULT '',
            address TEXT DEFAULT '',
            website varchar(200) DEFAULT '',
            principal_name varchar(200) DEFAULT '',
            logo varchar(100) DEFAULT '',
            created_at datetime NOT NULL,
            updated_at datetime NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rps_schoolbranding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name varchar(255) DEFAULT '',
            system_name varchar(255) DEFAULT '',
            tagline TEXT DEFAULT '',
            logo varchar(255) DEFAULT '',
            favicon varchar(255) DEFAULT '',
            primary_color varchar(50) DEFAULT '',
            secondary_color varchar(50) DEFAULT '',
            accent_color varchar(50) DEFAULT '',
            success_color varchar(50) DEFAULT '',
            warning_color varchar(50) DEFAULT '',
            danger_color varchar(50) DEFAULT '',
            show_powered_by bool NOT NULL DEFAULT 1,
            show_vendor_contact bool NOT NULL DEFAULT 1,
            custom_domain varchar(255),
            allow_user_customization bool NOT NULL DEFAULT 1,
            created_at datetime NOT NULL,
            updated_at datetime NOT NULL,
            school_id bigint NOT NULL,
            background_image varchar(255) DEFAULT '',
            background_opacity integer DEFAULT 18,
            background_pattern varchar(50) DEFAULT 'dots',
            branding_preview_enabled bool NOT NULL DEFAULT 1,
            css_version integer DEFAULT 1,
            custom_css TEXT DEFAULT '',
            font_family varchar(100) DEFAULT 'Inter',
            font_url varchar(255),
            logo_cropped varchar(255),
            logo_position_x integer DEFAULT 50,
            logo_position_y integer DEFAULT 50,
            footer_text TEXT DEFAULT '',
            secondary_logo varchar(255) DEFAULT '',
            headteacher_name varchar(255) DEFAULT '',
            director_name varchar(255) DEFAULT '',
            stamp varchar(100) DEFAULT ''
        );

        '''
    )
    conn.commit()

    class_columns = _table_columns(conn, 'portal_schoolclass')
    for name, definition in SCHOOL_CLASS_EXTRA_COLUMNS.items():
        if name not in class_columns:
            conn.execute(f'ALTER TABLE portal_schoolclass ADD COLUMN {name} {definition}')

    student_columns = _table_columns(conn, 'portal_student')
    for name, definition in STUDENT_EXTRA_COLUMNS.items():
        if name not in student_columns:
            conn.execute(f'ALTER TABLE portal_student ADD COLUMN {name} {definition}')

    conn.commit()


def _create_school(
    conn,
    name,
    abbreviation,
    email='',
    phone='',
    address='',
    logo_path='',
    secondary_logo_path='',
    tagline='',
):
    _ensure_school_data_schema(conn)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    abbreviation = abbreviation or _default_abbreviation(name)
    website = ''
    principal_name = ''

    conn.execute(
        '''
        INSERT INTO portal_school (name, abbreviation, email, phone, address, website, principal_name, logo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (name, abbreviation, email, phone, address, website, principal_name, logo_path),
    )
    school_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    rps_school_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rps_school'"
    ).fetchone()
    if rps_school_exists:
        conn.execute(
            '''
            INSERT INTO rps_school (id, name, abbreviation, email, phone, address, website, principal_name, logo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (school_id, name, abbreviation, email, phone, address, website, principal_name, logo_path, now, now),
        )

    branding_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rps_schoolbranding'"
    ).fetchone()
    if branding_exists:
        conn.execute(
            '''
            INSERT INTO rps_schoolbranding (
                display_name, system_name, tagline, logo, favicon,
                primary_color, secondary_color, accent_color, success_color,
                warning_color, danger_color, show_powered_by, show_vendor_contact,
                custom_domain, allow_user_customization, created_at, updated_at,
                school_id, background_image, background_opacity, background_pattern,
                branding_preview_enabled, css_version, custom_css, font_family,
                font_url, logo_cropped, logo_position_x, logo_position_y, footer_text,
                secondary_logo, stamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, NULL, 1, ?, ?, ?, '', 18, 'dots', 1, 1, '', 'Inter', NULL, NULL, 50, 50, '', ?, ?)
            ''',
            (
                name,
                f'{abbreviation.lower()}-matokeo-rms',
                tagline or 'Results & analytics platform',
                logo_path,
                secondary_logo_path,
                '#1f7a4c',
                '#f5f7f6',
                '#f59e0b',
                '#16a34a',
                '#d97706',
                '#dc2626',
                now,
                now,
                school_id,
                secondary_logo_path,
                secondary_logo_path,
            ),
        )

    conn.commit()
    return school_id, abbreviation


def _fetch_school(conn, school_id):
    row = conn.execute(
        '''
        SELECT s.id, s.name, s.abbreviation, s.email, s.phone, s.address,
               b.tagline, b.primary_color, b.logo, b.secondary_logo, b.stamp
        FROM portal_school s
        LEFT JOIN rps_schoolbranding b ON b.school_id = s.id
        WHERE s.id = ?
        ''',
        (school_id,),
    ).fetchone()
    if not row:
        return None

    school = _decorate_school_record(row)
    count = conn.execute(
        'SELECT COUNT(*) as c FROM portal_student WHERE school_id=? AND is_active=1',
        (school['id'],)
    ).fetchone()
    school['student_count'] = count['c'] if count else 0
    class_count = conn.execute(
        'SELECT COUNT(*) as c FROM portal_schoolclass WHERE school_id=?',
        (school['id'],)
    ).fetchone()
    school['class_count'] = class_count['c'] if class_count else 0
    return school


def _update_school(
    conn,
    school_id,
    name,
    abbreviation,
    email='',
    phone='',
    address='',
    logo_path='',
    secondary_logo_path='',
    tagline='',
):
    _ensure_school_data_schema(conn)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    abbreviation = abbreviation or _default_abbreviation(name)
    website = ''
    principal_name = ''

    conn.execute(
        '''
        UPDATE portal_school
        SET name=?, abbreviation=?, email=?, phone=?, address=?, website=?, principal_name=?, logo=?
        WHERE id=?
        ''',
        (name, abbreviation, email, phone, address, website, principal_name, logo_path, school_id),
    )

    rps_school_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rps_school'"
    ).fetchone()
    if rps_school_exists:
        row = conn.execute('SELECT 1 FROM rps_school WHERE id=?', (school_id,)).fetchone()
        if row:
            conn.execute(
                '''
                UPDATE rps_school
                SET name=?, abbreviation=?, email=?, phone=?, address=?, website=?, principal_name=?, logo=?, updated_at=?
                WHERE id=?
                ''',
                (name, abbreviation, email, phone, address, website, principal_name, logo_path, now, school_id),
            )
        else:
            conn.execute(
                '''
                INSERT INTO rps_school (id, name, abbreviation, email, phone, address, website, principal_name, logo, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (school_id, name, abbreviation, email, phone, address, website, principal_name, logo_path, now, now),
            )

    branding_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rps_schoolbranding'"
    ).fetchone()
    if branding_exists:
        system_name = f'{abbreviation.lower()}-matokeo-rms'
        row = conn.execute(
            'SELECT id FROM rps_schoolbranding WHERE school_id=?',
            (school_id,),
        ).fetchone()
        if row:
            conn.execute(
                '''
                UPDATE rps_schoolbranding
                SET display_name=?, system_name=?, tagline=?, logo=?, updated_at=?, secondary_logo=?, stamp=?
                WHERE school_id=?
                ''',
                (
                    name,
                    system_name,
                    tagline or 'Results & analytics platform',
                    logo_path,
                    now,
                    secondary_logo_path,
                    secondary_logo_path,
                    school_id,
                ),
            )
        else:
            conn.execute(
                '''
                INSERT INTO rps_schoolbranding (
                    display_name, system_name, tagline, logo, favicon,
                    primary_color, secondary_color, accent_color, success_color,
                    warning_color, danger_color, show_powered_by, show_vendor_contact,
                    custom_domain, allow_user_customization, created_at, updated_at,
                    school_id, background_image, background_opacity, background_pattern,
                    branding_preview_enabled, css_version, custom_css, font_family,
                    font_url, logo_cropped, logo_position_x, logo_position_y, footer_text,
                    secondary_logo, stamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, NULL, 1, ?, ?, ?, '', 18, 'dots', 1, 1, '', 'Inter', NULL, NULL, 50, 50, '', ?, ?)
                ''',
                (
                    name,
                    system_name,
                    tagline or 'Results & analytics platform',
                    logo_path,
                    secondary_logo_path,
                    '#1f7a4c',
                    '#f5f7f6',
                    '#f59e0b',
                    '#16a34a',
                    '#d97706',
                    '#dc2626',
                    now,
                    now,
                    school_id,
                    secondary_logo_path,
                    secondary_logo_path,
                ),
            )

    conn.commit()
    return abbreviation


def _delete_school(conn, school_id):
    school = _fetch_school(conn, school_id)
    if not school:
        return False

    if conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rps_schoolbranding'"
    ).fetchone():
        conn.execute('DELETE FROM rps_schoolbranding WHERE school_id=?', (school_id,))
    if conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rps_school'"
    ).fetchone():
        conn.execute('DELETE FROM rps_school WHERE id=?', (school_id,))

    conn.execute('DELETE FROM portal_student WHERE school_id=?', (school_id,))
    conn.execute('DELETE FROM portal_schoolclass WHERE school_id=?', (school_id,))
    conn.execute('DELETE FROM portal_school WHERE id=?', (school_id,))
    conn.commit()

    _delete_school_media(school.get('logo_path'))
    if school.get('secondary_logo_path') != school.get('logo_path'):
        _delete_school_media(school.get('secondary_logo_path'))
    return True


def _fetch_schools(conn):
    _ensure_school_data_schema(conn)
    schools = conn.execute(
        '''
        SELECT s.id, s.name, s.abbreviation, s.email, s.phone, s.address,
               b.tagline, b.primary_color, b.logo, b.secondary_logo, b.stamp
        FROM portal_school s
        LEFT JOIN rps_schoolbranding b ON b.school_id = s.id
        ORDER BY s.name
        '''
    ).fetchall()
    schools = [_decorate_school_record(s) for s in schools]

    for school in schools:
        count = conn.execute(
            'SELECT COUNT(*) as c FROM portal_student WHERE school_id=? AND is_active=1',
            (school['id'],)
        ).fetchone()
        school['student_count'] = count['c'] if count else 0
        class_count = conn.execute(
            'SELECT COUNT(*) as c FROM portal_schoolclass WHERE school_id=?',
            (school['id'],)
        ).fetchone()
        school['class_count'] = class_count['c'] if class_count else 0

    return schools


def _school_setup_route():
    """Single setup hub while the school-management pages are being built."""
    return 'accounts:add_school'


def _build_school_sidebar_items(school_id, active_key=''):
    """Build the Gestio-style sidebar for school setup pages."""
    items = [
        {
            'key': 'session',
            'label': 'Session',
            'icon': 'session',
            'href': reverse('accounts:school_session', kwargs={'school_id': school_id}),
        },
        {
            'key': 'registration',
            'label': 'Registration',
            'icon': 'registration',
            'href': reverse('accounts:school_registration', kwargs={'school_id': school_id}),
        },
        {
            'key': 'template',
            'label': 'Template Editor',
            'icon': 'template',
            'href': reverse('accounts:school_template_editor', kwargs={'school_id': school_id}),
        },
        {'key': 'class', 'label': 'Class Data', 'icon': 'class', 'href': 'javascript:void(0)'},
        {'key': 'reports', 'label': 'Reports', 'icon': 'reports', 'href': 'javascript:void(0)'},
        {'key': 'settings', 'label': 'Settings', 'icon': 'settings', 'href': 'javascript:void(0)'},
    ]

    for item in items:
        item['active'] = item['key'] == active_key
    return items


def _build_school_shell_context(school, active_key=''):
    """Common shell context shared by school landing pages."""
    return {
        'school': school,
        'sidebar_items': _build_school_sidebar_items(school['id'], active_key=active_key),
        'current_stamp': timezone.localtime().strftime('%a, %d %b %Y %H:%M:%S'),
    }


def _split_student_name(name):
    parts = [part for part in (name or '').split() if part]
    if not parts:
        return '', '', ''
    if len(parts) == 1:
        return parts[0], '', ''
    if len(parts) == 2:
        return parts[0], parts[1], ''
    return parts[0], parts[-1], ' '.join(parts[1:-1])


def _student_full_name(student_row):
    parts = [
        (student_row.get('first_name') or '').strip(),
        (student_row.get('middle_name') or '').strip(),
        (student_row.get('last_name') or '').strip(),
    ]
    return ' '.join(part for part in parts if part)


def _fetch_school_classes(conn, school_id):
    _ensure_school_data_schema(conn)
    rows = conn.execute(
        '''
        SELECT id, name, level, class_teacher_name, promoting_class, repeating_class, template_name
        FROM portal_schoolclass
        WHERE school_id = ?
        ORDER BY name
        ''',
        (school_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_school_students(conn, school_id, selected_class_id='', search=''):
    _ensure_school_data_schema(conn)
    sql = '''
        SELECT
            s.id,
            s.admission_number,
            s.first_name,
            s.last_name,
            s.middle_name,
            s.date_of_birth,
            s.gender,
            s.parent_name,
            s.parent_phone,
            s.email,
            s.address,
            s.date_of_admission,
            s.state_of_origin,
            s.local_government,
            s.image,
            s.class_field_id,
            c.name AS class_name
        FROM portal_student s
        LEFT JOIN portal_schoolclass c ON c.id = s.class_field_id
        WHERE s.school_id = ?
    '''
    params = [school_id]
    if selected_class_id:
        sql += ' AND s.class_field_id = ?'
        params.append(selected_class_id)
    if search:
        sql += '''
            AND (
                s.admission_number LIKE ?
                OR s.first_name LIKE ?
                OR s.last_name LIKE ?
                OR s.middle_name LIKE ?
            )
        '''
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term, search_term])
    sql += ' ORDER BY s.admission_number, s.first_name, s.last_name'

    rows = conn.execute(sql, params).fetchall()
    students = []
    for row in rows:
        item = dict(row)
        item['name'] = _student_full_name(item)
        item['sex_display'] = (item.get('gender') or '').upper()
        item['tel'] = item.get('parent_phone') or ''
        item['parent_guardian_name'] = item.get('parent_name') or ''
        item['image_url'] = _media_url(item.get('image') or '')
        students.append(item)
    return students


def _fetch_school_sessions(conn, school_id):
    _ensure_school_data_schema(conn)
    rows = conn.execute(
        '''
        SELECT id, session_name, start_date, end_date, is_active
        FROM portal_academicsession
        WHERE school_id = ?
        ORDER BY is_active DESC, session_name DESC, id DESC
        ''',
        (school_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_school_terms(conn, school_id, session_id=''):
    _ensure_school_data_schema(conn)
    sql = '''
        SELECT
            t.id,
            t.term_name,
            t.start_date,
            t.end_date,
            t.is_active,
            t.session_id,
            t.times_school_open,
            t.term_duration,
            t.next_term_begins,
            s.session_name
        FROM portal_term t
        INNER JOIN portal_academicsession s ON s.id = t.session_id
        WHERE s.school_id = ?
    '''
    params = [school_id]
    if session_id:
        sql += ' AND t.session_id = ?'
        params.append(session_id)
    sql += ' ORDER BY t.id DESC'
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _teacher_full_name(teacher_row):
    parts = [
        (teacher_row.get('first_name') or '').strip(),
        (teacher_row.get('middle_name') or '').strip(),
        (teacher_row.get('last_name') or '').strip(),
    ]
    return ' '.join(part for part in parts if part)


def _fetch_school_teachers(conn, school_id, search=''):
    _ensure_school_data_schema(conn)
    sql = '''
        SELECT
            id,
            first_name,
            last_name,
            middle_name,
            gender,
            date_of_birth,
            phone,
            email,
            address,
            experience,
            qualifications,
            image,
            signature
        FROM teacher_teacheruser
        WHERE school_id = ?
    '''
    params = [school_id]
    if search:
        sql += '''
            AND (
                first_name LIKE ?
                OR last_name LIKE ?
                OR middle_name LIKE ?
                OR email LIKE ?
                OR phone LIKE ?
            )
        '''
        term = f'%{search}%'
        params.extend([term, term, term, term, term])
    sql += ' ORDER BY first_name, last_name, id'
    rows = conn.execute(sql, params).fetchall()
    teachers = []
    for row in rows:
        item = dict(row)
        item['name'] = _teacher_full_name(item)
        item['image_url'] = _media_url(item.get('image') or '')
        teachers.append(item)
    return teachers


def login_view(request):
    """Admin login (Django auth)."""
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            request.session.pop('teacher_user', None)
            request.session.pop('teacher_id', None)
            request.session.pop('student_user', None)
            request.session['user_role'] = 'admin'
            return redirect(_school_setup_route())
        error = 'Invalid username or password.'
    return render(request, 'accounts/login.html', {'error': error, 'login_tab': 'admin'})


def teacher_login_view(request):
    """Teacher login against teacher_teacheruser table."""
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        backend = TeacherBackend()
        teacher = backend.authenticate(request, teacher_username=username, teacher_password=password)
        if teacher is not None:
            request.session['teacher_user'] = teacher.to_session()
            request.session['teacher_id'] = teacher.id
            request.session.pop('student_user', None)
            request.session['user_role'] = 'teacher'
            return redirect(_school_setup_route())
        error = 'Invalid teacher credentials.'
    return render(request, 'accounts/login.html', {'error': error, 'login_tab': 'teacher'})


def student_login_view(request):
    """Student login by admission number."""
    error = ''
    if request.method == 'POST':
        admission = request.POST.get('admission_number', '').strip()
        if admission:
            student = get_student_by_admission(admission)
            if student:
                request.session['student_user'] = student
                request.session['school_id'] = student.get('school_id')
                request.session['user_role'] = 'student'
                return redirect('/my-portal/')
            else:
                error = 'No active student found with that admission number.'
        else:
            error = 'Please enter your admission number.'
    return render(request, 'accounts/login.html', {'error': error, 'login_tab': 'student'})


def logout_view(request):
    request.session.flush()
    logout(request)
    return redirect('accounts:login')


def db_backup(request):
    """Download a backup copy of school_data.sqlite3."""
    if request.method != 'POST':
        messages.error(
            request,
            'Enter the correct admin username and password before using database tools.',
            extra_tags='db-modal',
        )
        return redirect('accounts:login')

    if _authenticate_db_action(request) is None:
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])
    if not os.path.exists(db_path):
        messages.error(request, 'Database file not found.', extra_tags='db-modal')
        return redirect('accounts:login')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    db_name = os.path.basename(db_path).replace('.sqlite3', '')
    backup_name = f'{db_name}_backup_{timestamp}.sqlite3'
    backup_path = os.path.join(os.path.dirname(db_path), backup_name)

    shutil.copy2(db_path, backup_path)

    response = FileResponse(
        open(backup_path, 'rb'),
        content_type='application/x-sqlite3',
        as_attachment=True,
        filename=backup_name,
    )
    return response


def db_restore(request):
    """Restore school_data.sqlite3 from an uploaded file."""
    if request.method != 'POST':
        messages.error(
            request,
            'Enter the correct admin username and password before using database tools.',
            extra_tags='db-modal',
        )
        return redirect('accounts:login')

    if _authenticate_db_action(request) is None:
        return redirect('accounts:login')

    uploaded = request.FILES.get('db_file')
    if not uploaded:
        messages.error(request, 'No file uploaded.', extra_tags='db-modal')
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = db_path.replace('.sqlite3', f'_pre_restore_{timestamp}.sqlite3')
    if os.path.exists(db_path):
        shutil.copy2(db_path, backup_path)

    with open(db_path, 'wb') as handle:
        for chunk in uploaded.chunks():
            handle.write(chunk)

    try:
        conn = sqlite3.connect(db_path)
        conn.execute('SELECT name FROM sqlite_master WHERE type="table" LIMIT 1')
        conn.close()
    except Exception:
        shutil.copy2(backup_path, db_path)
        messages.error(
            request,
            'Invalid database file. Previous database restored.',
            extra_tags='db-modal',
        )
        return redirect('accounts:login')

    messages.success(request, 'Database restored successfully.', extra_tags='db-modal')
    return redirect('accounts:login')


def db_delete(request):
    """Delete (reset) the school_data.sqlite3 database."""
    if request.method != 'POST':
        messages.error(
            request,
            'Enter the correct admin username and password before using database tools.',
            extra_tags='db-modal',
        )
        return redirect('accounts:login')

    if _authenticate_db_action(request) is None:
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])

    if os.path.exists(db_path):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = db_path.replace('.sqlite3', f'_deleted_{timestamp}.sqlite3')
        shutil.copy2(db_path, backup_path)
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    _ensure_school_data_schema(conn)
    conn.close()

    messages.success(request, 'Database deleted. A backup was saved.', extra_tags='db-modal')
    request.session.flush()
    return redirect('accounts:login')


def select_school(request):
    """Show list of schools for user to select."""
    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    schools = _fetch_schools(conn)

    if request.method == 'POST':
        school_id = request.POST.get('school_id')
        if school_id:
            request.session['school_id'] = int(school_id)
            for school in schools:
                if str(school['id']) == str(school_id):
                    request.session['school_name'] = school['name']
                    break
            conn.close()
            return redirect('accounts:school_entry', school_id=school_id)

    conn.close()
    return render(
        request,
        'accounts/select_school.html',
        {
            'schools': schools,
            'has_schools': bool(schools),
        },
    )


def school_entry(request, school_id):
    """Placeholder school landing page after entering a school."""
    if not request.user.is_authenticated and not request.session.get('teacher_id'):
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    school = _fetch_school(conn, school_id)
    conn.close()

    if not school:
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']

    stat_cards = [
        {
            'label': 'Students',
            'value': school.get('student_count', 0),
            'tone': 'students',
            'icon': 'students',
        },
        {
            'label': 'Teachers',
            'value': 0,
            'tone': 'teachers',
            'icon': 'teachers',
        },
        {
            'label': 'Classes',
            'value': school.get('class_count', 0),
            'tone': 'classes',
            'icon': 'classes',
        },
    ]

    return render(
        request,
        'accounts/school_entry.html',
        {
            **_build_school_shell_context(school, active_key='session'),
            'stat_cards': stat_cards,
        },
    )


def school_session(request, school_id):
    """Gestio-style Session module menu."""
    if not request.user.is_authenticated and not request.session.get('teacher_id'):
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    school = _fetch_school(conn, school_id)
    conn.close()

    if not school:
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']

    session_tiles = [
        {'label': 'New Session', 'tone': 'new', 'icon': 'plus'},
        {'label': 'Edit Session', 'tone': 'edit', 'icon': 'edit'},
        {'label': 'Activate Session', 'tone': 'activate', 'icon': 'check'},
        {'label': 'Delete Session', 'tone': 'delete', 'icon': 'delete'},
    ]

    return render(
        request,
        'accounts/school_session.html',
        {
            **_build_school_shell_context(school, active_key='session'),
            'session_tiles': session_tiles,
        },
    )


def school_registration(request, school_id):
    """Gestio-style Registration menu."""
    if not request.user.is_authenticated and not request.session.get('teacher_id'):
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    school = _fetch_school(conn, school_id)
    conn.close()

    if not school:
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']

    registration_tiles = [
        {
            'label': 'Term',
            'tone': 'term',
            'icon': 'clipboard',
            'href': reverse('accounts:school_term_settings', kwargs={'school_id': school['id']}),
        },
        {
            'label': 'Teachers',
            'tone': 'teachers',
            'icon': 'teacher',
            'href': reverse('accounts:school_teachers', kwargs={'school_id': school['id']}),
        },
        {
            'label': 'Students\' Data',
            'tone': 'students',
            'icon': 'student',
            'href': reverse('accounts:school_students', kwargs={'school_id': school['id']}),
        },
        {
            'label': 'Class Registration',
            'tone': 'classes',
            'icon': 'classroom',
            'href': reverse('accounts:school_class_registration', kwargs={'school_id': school['id']}),
        },
    ]

    return render(
        request,
        'accounts/school_registration.html',
        {
            **_build_school_shell_context(school, active_key='registration'),
            'registration_tiles': registration_tiles,
        },
    )


def school_template_editor(request, school_id):
    """Legacy wrapper kept for compatibility with older imports."""
    from .views_template_editor import template_editor_view

    return template_editor_view(request, school_id)


def school_term_settings(request, school_id):
    """Minimal terminal settings page used by Registration > Term."""
    if not request.user.is_authenticated and not request.session.get('teacher_id'):
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    school = _fetch_school(conn, school_id)

    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']

    sessions = _fetch_school_sessions(conn, school['id'])
    selected_session_id = request.GET.get('session_id', '').strip()
    if not selected_session_id and sessions:
        selected_session_id = str(sessions[0]['id'])

    terms = _fetch_school_terms(conn, school['id'], session_id=selected_session_id)
    selected_term_id = request.GET.get('term_id', '').strip()
    if not selected_term_id and terms:
        selected_term_id = str(terms[0]['id'])

    term_form = {
        'session_name': '',
        'term_name': '',
        'start_date': '',
        'end_date': '',
        'times_school_open': '',
        'term_duration': '',
        'next_term_begins': '',
    }

    if request.method == 'POST':
        selected_session_id = request.POST.get('session_id', '').strip()
        selected_term_id = request.POST.get('term_id', '').strip()
        term_form = {
            'session_name': request.POST.get('session_name', '').strip(),
            'term_name': request.POST.get('term_name', '').strip(),
            'start_date': request.POST.get('start_date', '').strip(),
            'end_date': request.POST.get('end_date', '').strip(),
            'times_school_open': request.POST.get('times_school_open', '').strip(),
            'term_duration': request.POST.get('term_duration', '').strip(),
            'next_term_begins': request.POST.get('next_term_begins', '').strip(),
        }

        session_name = term_form['session_name']
        term_name = term_form['term_name']
        session_id = selected_session_id
        active_session = None
        if session_id:
            active_session = conn.execute(
                'SELECT id FROM portal_academicsession WHERE id=? AND school_id=?',
                (session_id, school['id']),
            ).fetchone()

        if not active_session and not session_name:
            if sessions:
                messages.error(request, 'Please select a session.')
            else:
                messages.error(request, 'Please, input the session name.')
        elif not term_name:
            messages.error(request, 'Please, input the term name.')
        else:
            if not active_session:
                conn.execute(
                    'UPDATE portal_academicsession SET is_active=0 WHERE school_id=?',
                    (school['id'],),
                )
                conn.execute(
                    '''
                    INSERT INTO portal_academicsession (session_name, start_date, end_date, is_active, school_id)
                    VALUES (?, ?, ?, 1, ?)
                    ''',
                    (
                        session_name,
                        term_form['start_date'] or None,
                        term_form['end_date'] or None,
                        school['id'],
                    ),
                )
                session_id = str(conn.execute('SELECT last_insert_rowid()').fetchone()[0])
            else:
                conn.execute(
                    'UPDATE portal_academicsession SET is_active=1 WHERE id=? AND school_id=?',
                    (session_id, school['id']),
                )
                conn.execute(
                    'UPDATE portal_academicsession SET is_active=0 WHERE school_id=? AND id<>?',
                    (school['id'], session_id),
                )

            conn.execute(
                '''
                UPDATE portal_term
                SET is_active = 0
                WHERE session_id IN (SELECT id FROM portal_academicsession WHERE school_id = ?)
                ''',
                (school['id'],),
            )

            payload = (
                term_name,
                term_form['start_date'] or None,
                term_form['end_date'] or None,
                1,
                int(session_id),
                int(term_form['times_school_open'] or 0),
                int(term_form['term_duration'] or 0),
                term_form['next_term_begins'] or None,
            )
            existing_term = None
            if selected_term_id:
                existing_term = conn.execute(
                    '''
                    SELECT t.id
                    FROM portal_term t
                    INNER JOIN portal_academicsession s ON s.id = t.session_id
                    WHERE t.id=? AND s.school_id=?
                    ''',
                    (selected_term_id, school['id']),
                ).fetchone()

            if existing_term:
                conn.execute(
                    '''
                    UPDATE portal_term
                    SET term_name=?, start_date=?, end_date=?, is_active=?, session_id=?,
                        times_school_open=?, term_duration=?, next_term_begins=?
                    WHERE id=?
                    ''',
                    (*payload, selected_term_id),
                )
                message_text = 'Terminal settings updated successfully.'
                redirect_term_id = selected_term_id
            else:
                conn.execute(
                    '''
                    INSERT INTO portal_term (
                        term_name, start_date, end_date, is_active, session_id,
                        times_school_open, term_duration, next_term_begins
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    payload,
                )
                redirect_term_id = str(conn.execute('SELECT last_insert_rowid()').fetchone()[0])
                message_text = 'Terminal settings saved successfully.'

            conn.commit()
            conn.close()
            messages.success(request, message_text)
            return redirect(
                reverse('accounts:school_term_settings', kwargs={'school_id': school['id']})
                + f'?session_id={session_id}&term_id={redirect_term_id}'
            )

    sessions = _fetch_school_sessions(conn, school['id'])
    if not selected_session_id and sessions:
        selected_session_id = str(sessions[0]['id'])
    terms = _fetch_school_terms(conn, school['id'], session_id=selected_session_id)
    if not selected_term_id and terms:
        selected_term_id = str(terms[0]['id'])

    selected_term = None
    for item in terms:
        if str(item['id']) == str(selected_term_id):
            selected_term = item
            break

    if selected_term and request.method != 'POST':
        term_form = {
            'session_name': '',
            'term_name': selected_term.get('term_name') or '',
            'start_date': selected_term.get('start_date') or '',
            'end_date': selected_term.get('end_date') or '',
            'times_school_open': selected_term.get('times_school_open') or '',
            'term_duration': selected_term.get('term_duration') or '',
            'next_term_begins': selected_term.get('next_term_begins') or '',
        }

    conn.close()
    return render(
        request,
        'accounts/school_term_settings.html',
        {
            **_build_school_shell_context(school, active_key='registration'),
            'sessions': sessions,
            'terms': terms,
            'selected_session_id': str(selected_session_id),
            'selected_term_id': str(selected_term_id),
            'term_form': term_form,
        },
    )


def school_teachers(request, school_id):
    """Minimal teacher list and add-teacher popup used by Registration > Teachers."""
    if not request.user.is_authenticated and not request.session.get('teacher_id'):
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    school = _fetch_school(conn, school_id)

    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']

    search = request.GET.get('search', '').strip()
    teacher_form = {
        'name': '',
        'gender': 'MALE',
        'date_of_birth': '',
        'phone': '',
        'email': '',
        'address': '',
        'experience': '',
        'qualifications': '',
        'signature': '',
        'image_url': '',
        'existing_image': '',
    }
    open_teacher_modal = False

    if request.method == 'POST' and request.POST.get('action') == 'create_teacher':
        teacher_form = {
            'name': request.POST.get('name', '').strip(),
            'gender': request.POST.get('gender', 'MALE').strip() or 'MALE',
            'date_of_birth': request.POST.get('date_of_birth', '').strip(),
            'phone': request.POST.get('phone', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'address': request.POST.get('address', '').strip(),
            'experience': request.POST.get('experience', '').strip(),
            'qualifications': request.POST.get('qualifications', '').strip(),
            'signature': request.POST.get('signature', '').strip(),
            'image_url': '',
            'existing_image': '',
        }
        open_teacher_modal = True
        if request.FILES.get('teacher_image'):
            image_path = _save_school_media(request.FILES['teacher_image'], 'teachers')
            teacher_form['image_url'] = _media_url(image_path)
            teacher_form['existing_image'] = image_path
        else:
            image_path = ''

        if not teacher_form['name']:
            messages.error(request, 'Please, input the teacher name.')
        else:
            first_name, last_name, middle_name = _split_student_name(teacher_form['name'])
            conn.execute(
                '''
                INSERT INTO teacher_teacheruser (
                    first_name, last_name, middle_name, gender, date_of_birth,
                    phone, email, address, experience, qualifications, image, signature, school_id, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ''',
                (
                    first_name,
                    last_name,
                    middle_name,
                    teacher_form['gender'],
                    teacher_form['date_of_birth'] or None,
                    teacher_form['phone'],
                    teacher_form['email'],
                    teacher_form['address'],
                    teacher_form['experience'],
                    teacher_form['qualifications'],
                    image_path,
                    teacher_form['signature'],
                    school['id'],
                ),
            )
            conn.commit()
            conn.close()
            messages.success(request, 'Teacher added successfully.')
            return redirect(reverse('accounts:school_teachers', kwargs={'school_id': school['id']}))

    teachers = _fetch_school_teachers(conn, school['id'], search=search)
    conn.close()
    return render(
        request,
        'accounts/school_teachers.html',
        {
            **_build_school_shell_context(school, active_key='registration'),
            'teachers': teachers,
            'search': search,
            'teacher_form': teacher_form,
            'open_teacher_modal': open_teacher_modal,
        },
    )


def school_class_registration(request, school_id):
    """Minimal class-registration screen used by the student registration flow."""
    if not request.user.is_authenticated and not request.session.get('teacher_id'):
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    school = _fetch_school(conn, school_id)

    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']

    panel_mode = request.GET.get('mode', 'add').strip() or 'add'
    selected_class_id = request.GET.get('class_id', '').strip()
    class_form = {
        'class_id': '',
        'current_name': '',
        'new_name': '',
        'class_teacher_name': '',
        'promoting_class': '',
        'repeating_class': '',
        'template_name': '',
    }

    if request.method == 'POST':
        action = request.POST.get('action', 'add').strip() or 'add'
        panel_mode = action
        selected_class_id = request.POST.get('class_id', '').strip()
        class_name = request.POST.get('class_name', '').strip()
        class_teacher_name = request.POST.get('class_teacher_name', '').strip()
        promoting_class = request.POST.get('promoting_class', '').strip()
        repeating_class = request.POST.get('repeating_class', '').strip()
        template_name = request.POST.get('template_name', '').strip()

        class_form = {
            'class_id': selected_class_id,
            'current_name': request.POST.get('current_name', '').strip(),
            'new_name': class_name,
            'class_teacher_name': class_teacher_name,
            'promoting_class': promoting_class,
            'repeating_class': repeating_class,
            'template_name': template_name,
        }

        if action == 'add':
            if not class_name:
                messages.error(request, 'Please, input the class name.')
            else:
                conn.execute(
                    '''
                    INSERT INTO portal_schoolclass (
                        name, level, school_id, class_teacher_name, promoting_class, repeating_class, template_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        class_name,
                        class_name,
                        school['id'],
                        class_teacher_name,
                        promoting_class,
                        repeating_class,
                        template_name,
                    ),
                )
                conn.commit()
                messages.success(request, 'Class registered successfully.')
                conn.close()
                return redirect(reverse('accounts:school_class_registration', kwargs={'school_id': school['id']}) + '?mode=add')

        elif action == 'edit':
            target = conn.execute(
                'SELECT id, name FROM portal_schoolclass WHERE id=? AND school_id=?',
                (selected_class_id, school['id']),
            ).fetchone()
            if not target:
                messages.error(request, 'That class could not be found.')
            elif not class_name:
                messages.error(request, 'Please, input the new class name.')
            else:
                conn.execute(
                    '''
                    UPDATE portal_schoolclass
                    SET name=?, level=?, class_teacher_name=?, promoting_class=?, repeating_class=?, template_name=?
                    WHERE id=? AND school_id=?
                    ''',
                    (
                        class_name,
                        class_name,
                        class_teacher_name,
                        promoting_class,
                        repeating_class,
                        template_name,
                        selected_class_id,
                        school['id'],
                    ),
                )
                conn.commit()
                messages.success(request, 'Class updated successfully.')
                conn.close()
                return redirect(
                    reverse('accounts:school_class_registration', kwargs={'school_id': school['id']})
                    + f'?mode=edit&class_id={selected_class_id}'
                )

        elif action == 'delete':
            target = conn.execute(
                'SELECT id, name FROM portal_schoolclass WHERE id=? AND school_id=?',
                (selected_class_id, school['id']),
            ).fetchone()
            if not target:
                messages.error(request, 'That class could not be found.')
            else:
                student_count = conn.execute(
                    'SELECT COUNT(*) AS c FROM portal_student WHERE class_field_id=? AND school_id=?',
                    (selected_class_id, school['id']),
                ).fetchone()['c']
                if student_count:
                    messages.error(request, 'You cannot delete a class that already has students.')
                else:
                    conn.execute(
                        'DELETE FROM portal_schoolclass WHERE id=? AND school_id=?',
                        (selected_class_id, school['id']),
                    )
                    conn.commit()
                    messages.success(request, 'Class deleted successfully.')
                    conn.close()
                    return redirect(reverse('accounts:school_class_registration', kwargs={'school_id': school['id']}) + '?mode=add')

    classes = _fetch_school_classes(conn, school['id'])
    if not selected_class_id and classes:
        selected_class_id = str(classes[0]['id'])

    selected_class = None
    if selected_class_id:
        for item in classes:
            if str(item['id']) == str(selected_class_id):
                selected_class = item
                break

    if selected_class and panel_mode in {'edit', 'delete'} and not class_form['new_name']:
        class_form = {
            'class_id': str(selected_class['id']),
            'current_name': selected_class.get('name') or '',
            'new_name': selected_class.get('name') or '',
            'class_teacher_name': selected_class.get('class_teacher_name') or '',
            'promoting_class': selected_class.get('promoting_class') or '',
            'repeating_class': selected_class.get('repeating_class') or '',
            'template_name': selected_class.get('template_name') or '',
        }

    conn.close()
    return render(
        request,
        'accounts/school_class_registration.html',
        {
            **_build_school_shell_context(school, active_key='registration'),
            'classes': classes,
            'panel_mode': panel_mode,
            'selected_class_id': str(selected_class_id),
            'class_form': class_form,
        },
    )


def school_students(request, school_id):
    """Students list plus the Gestio-style student registration popup."""
    if not request.user.is_authenticated and not request.session.get('teacher_id'):
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    school = _fetch_school(conn, school_id)

    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']

    classes = _fetch_school_classes(conn, school['id'])
    search = request.GET.get('search', '').strip()
    selected_class_id = request.GET.get('class_id', '').strip()
    if not selected_class_id and classes:
        selected_class_id = str(classes[0]['id'])

    student_form = {
        'name': '',
        'sex': 'MALE',
        'class_id': selected_class_id,
        'date_of_birth': '',
        'admission_number': '',
        'date_of_admission': '',
        'parent_name': '',
        'tel': '',
        'email': '',
        'address': '',
        'image_url': '',
        'existing_image': '',
    }
    open_student_modal = False

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        if action == 'create_student':
            student_form = {
                'name': request.POST.get('name', '').strip(),
                'sex': request.POST.get('sex', 'MALE').strip() or 'MALE',
                'class_id': request.POST.get('class_id', '').strip() or selected_class_id,
                'date_of_birth': request.POST.get('date_of_birth', '').strip(),
                'admission_number': request.POST.get('admission_number', '').strip(),
                'date_of_admission': request.POST.get('date_of_admission', '').strip(),
                'parent_name': request.POST.get('parent_name', '').strip(),
                'tel': request.POST.get('tel', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'address': request.POST.get('address', '').strip(),
                'image_url': '',
                'existing_image': '',
            }
            open_student_modal = True

            if request.FILES.get('student_image'):
                image_path = _save_school_media(request.FILES['student_image'], 'students')
                student_form['image_url'] = _media_url(image_path)
                student_form['existing_image'] = image_path
            else:
                image_path = ''

            if not classes:
                messages.error(request, 'Please register a class before adding students.')
            elif not student_form['admission_number']:
                messages.error(request, 'Please, input the Admission No.')
            elif not student_form['name']:
                messages.error(request, 'Please, input the student name.')
            elif not student_form['class_id']:
                messages.error(request, 'Please select a class.')
            else:
                first_name, last_name, middle_name = _split_student_name(student_form['name'])
                conn.execute(
                    '''
                    INSERT INTO portal_student (
                        admission_number, first_name, last_name, middle_name,
                        date_of_birth, gender, parent_name, parent_phone, is_active,
                        portal_access_enabled, class_field_id, school_id, image,
                        email, address, date_of_admission, state_of_origin, local_government
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?, '', '')
                    ''',
                    (
                        student_form['admission_number'],
                        first_name,
                        last_name,
                        middle_name,
                        student_form['date_of_birth'] or None,
                        student_form['sex'],
                        student_form['parent_name'],
                        student_form['tel'],
                        int(student_form['class_id']),
                        school['id'],
                        image_path,
                        student_form['email'],
                        student_form['address'],
                        student_form['date_of_admission'] or None,
                    ),
                )
                conn.commit()
                messages.success(request, 'Student registered successfully.')
                conn.close()
                return redirect(
                    reverse('accounts:school_students', kwargs={'school_id': school['id']})
                    + f'?class_id={student_form["class_id"]}'
                )

    students = _fetch_school_students(conn, school['id'], selected_class_id=selected_class_id, search=search)
    active_student_count = len(students)
    conn.close()

    return render(
        request,
        'accounts/school_students.html',
        {
            **_build_school_shell_context(school, active_key='registration'),
            'classes': classes,
            'students': students,
            'search': search,
            'selected_class_id': str(selected_class_id),
            'student_form': student_form,
            'open_student_modal': open_student_modal,
            'active_student_count': active_student_count,
            'has_classes': bool(classes),
        },
    )


def add_school(request):
    """Create a school from a dedicated page."""
    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    schools = _fetch_schools(conn)
    school_form = {
        'school_id': '',
        'name': DEFAULT_SCHOOL_NAME,
        'other_details': DEFAULT_SCHOOL_DETAILS,
        'logo_url': '',
        'secondary_logo_url': '',
        'existing_logo': '',
        'existing_secondary_logo': '',
    }
    success_redirect_url = request.session.pop('post_add_school_redirect', '')
    open_add_school_modal = not bool(schools)
    school_form_action = 'create_school'
    school_submit_label = 'Add'

    edit_school_id = request.GET.get('edit', '').strip()
    if request.method == 'GET' and edit_school_id:
        school = _fetch_school(conn, edit_school_id)
        if school:
            school_form = {
                'school_id': str(school['id']),
                'name': school.get('name') or DEFAULT_SCHOOL_NAME,
                'other_details': school.get('address') or DEFAULT_SCHOOL_DETAILS,
                'logo_url': school.get('logo_url') or '',
                'secondary_logo_url': school.get('secondary_logo_url') or '',
                'existing_logo': school.get('logo_path') or '',
                'existing_secondary_logo': school.get('secondary_logo_path') or '',
            }
            school_form_action = 'edit_school'
            school_submit_label = 'Save'
            open_add_school_modal = True
        else:
            messages.error(request, 'That school could not be found.')

    if request.method == 'POST':
        action = request.POST.get('action', 'create_school').strip() or 'create_school'

        if action == 'school_tools':
            messages.info(request, 'School actions will be connected next.')
            conn.close()
            return redirect('accounts:add_school')

        if action == 'delete_school':
            school_id = request.POST.get('school_id', '').strip()
            school = _fetch_school(conn, school_id) if school_id else None
            if not school:
                messages.error(request, 'That school could not be found.')
            else:
                _delete_school(conn, school['id'])
                if str(request.session.get('school_id', '')) == str(school['id']):
                    request.session.pop('school_id', None)
                    request.session.pop('school_name', None)
                request.session['post_add_school_redirect'] = ''
                conn.close()
                messages.success(
                    request,
                    'School deleted successfully.',
                    extra_tags='school-dialog',
                )
                return redirect('accounts:add_school')

        school_name = request.POST.get('name', '').strip()
        other_details = request.POST.get('other_details', '').strip()
        details = _extract_school_details(other_details)
        school_id = request.POST.get('school_id', '').strip()
        existing_logo_path = request.POST.get('existing_logo', '').strip()
        existing_secondary_logo_path = request.POST.get('existing_secondary_logo', '').strip()
        clear_logo = request.POST.get('clear_logo') == '1'
        clear_secondary_logo = request.POST.get('clear_secondary_logo') == '1'
        existing_school = _fetch_school(conn, school_id) if school_id else None

        abbreviation = request.POST.get('abbreviation', '').strip() or (
            existing_school.get('abbreviation', '') if existing_school else ''
        )
        email = request.POST.get('email', '').strip() or details['email']
        phone = request.POST.get('phone', '').strip() or details['phone']
        address = request.POST.get('address', '').strip() or details['address']
        tagline = request.POST.get('tagline', '').strip() or details['tagline']
        logo_path = existing_logo_path
        secondary_logo_path = existing_secondary_logo_path

        if request.FILES.get('logo'):
            logo_path = _save_school_media(request.FILES['logo'], 'schools')
            if existing_logo_path and existing_logo_path != logo_path:
                _delete_school_media(existing_logo_path)
        elif clear_logo:
            logo_path = ''
            _delete_school_media(existing_logo_path)

        if request.FILES.get('secondary_logo'):
            secondary_logo_path = _save_school_media(request.FILES['secondary_logo'], 'schools')
            if existing_secondary_logo_path and existing_secondary_logo_path != secondary_logo_path:
                _delete_school_media(existing_secondary_logo_path)
        elif clear_secondary_logo:
            secondary_logo_path = ''
            _delete_school_media(existing_secondary_logo_path)

        school_form = {
            'school_id': school_id,
            'name': school_name or DEFAULT_SCHOOL_NAME,
            'other_details': other_details or DEFAULT_SCHOOL_DETAILS,
            'logo_url': _media_url(logo_path),
            'secondary_logo_url': _media_url(secondary_logo_path),
            'existing_logo': logo_path,
            'existing_secondary_logo': secondary_logo_path,
        }
        school_form_action = 'edit_school' if action == 'edit_school' else 'create_school'
        school_submit_label = 'Save' if action == 'edit_school' else 'Add'

        if not school_name:
            messages.error(request, 'School name is required.')
            open_add_school_modal = True
        elif action == 'edit_school' and not existing_school:
            messages.error(request, 'That school could not be found.')
            school_form_action = 'create_school'
            school_submit_label = 'Add'
            open_add_school_modal = True
        else:
            if action == 'edit_school':
                _update_school(
                    conn,
                    school_id=existing_school['id'],
                    name=school_name,
                    abbreviation=abbreviation,
                    email=email,
                    phone=phone,
                    address=address,
                    logo_path=logo_path,
                    secondary_logo_path=secondary_logo_path,
                    tagline=tagline,
                )
                request.session['school_id'] = int(existing_school['id'])
                message_text = 'School updated successfully.'
            else:
                school_id, _saved_abbreviation = _create_school(
                    conn,
                    name=school_name,
                    abbreviation=abbreviation,
                    email=email,
                    phone=phone,
                    address=address,
                    logo_path=logo_path,
                    secondary_logo_path=secondary_logo_path,
                    tagline=tagline,
                )
                request.session['school_id'] = int(school_id)
                message_text = 'School added successfully.'
            request.session['school_name'] = school_name
            request.session['post_add_school_redirect'] = ''
            conn.close()
            messages.success(
                request,
                message_text,
                extra_tags='school-dialog',
            )
            return redirect('accounts:add_school')

    conn.close()
    return render(
        request,
        'accounts/add_school.html',
        {
            'schools': schools,
            'school_form': school_form,
            'has_schools': bool(schools),
            'open_add_school_modal': open_add_school_modal,
            'success_redirect_url': success_redirect_url,
            'school_form_action': school_form_action,
            'school_submit_label': school_submit_label,
            'default_school_name': DEFAULT_SCHOOL_NAME,
            'default_school_details': DEFAULT_SCHOOL_DETAILS,
        },
    )
