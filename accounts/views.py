import json
import csv
import sqlite3
import shutil
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .auth_defaults import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    ensure_default_admin_user,
    is_default_admin_password,
)
from .services.template_editor_state import (
    DEFAULT_TEMPLATE_NAME,
    JUNIOR_SECONDARY_TEMPLATE_NAME,
    PRIMARY_TEMPLATE_NAME,
    RESULT_TEMPLATE_AUTO,
    list_result_template_choices,
    normalize_template_name,
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

SUBJECT_EXTRA_COLUMNS = {
    'code': "varchar(20) DEFAULT ''",
    'is_active': 'bool NOT NULL DEFAULT 1',
    'school_id': 'bigint NOT NULL DEFAULT 0',
}

CLASS_DATA_SCORE_COMPONENTS = (
    ('ca1', 'CA1', 'continuous_assessment'),
    ('ca2', 'CA2', 'test_score'),
    ('exam', 'Exam', 'exam_score'),
)

CLASS_DATA_ATTRIBUTE_COLUMNS = (
    {'label': 'Attentiveness', 'name': 'Attentiveness', 'type': 'affective'},
    {'label': 'Attitude of School Work', 'name': 'Attitude of School Work', 'type': 'affective'},
    {'label': 'Cooperation', 'name': 'Cooperation with Others', 'type': 'affective'},
    {'label': 'Emotion Stability', 'name': 'Emotion Stability', 'type': 'affective'},
    {'label': 'Health', 'name': 'Health', 'type': 'affective'},
    {'label': 'Leadership', 'name': 'Leadership', 'type': 'affective'},
    {'label': 'Attendance / Writing', 'name': 'Speaking / Writing', 'type': 'affective'},
    {'label': 'Drawing & Painting', 'name': 'Drawing & Painting', 'type': 'psychomotor'},
    {'label': 'Handling of Tools', 'name': 'Handling of Tools', 'type': 'psychomotor'},
    {'label': 'Games', 'name': 'Games', 'type': 'psychomotor'},
    {'label': 'Handwriting', 'name': 'Handwriting', 'type': 'psychomotor'},
    {'label': 'Music', 'name': 'Music', 'type': 'psychomotor'},
    {'label': 'Verbal Fluency', 'name': 'Verbal Fluency', 'type': 'psychomotor'},
)

CLASS_DATA_COMMENT_TYPES = {
    'teacher': {
        'title': "Class Teacher's Comments",
        'empty_message': 'Manual Commenting not enabled',
        'template_message': 'for the Template used',
        'class_message': 'by this Class',
    },
    'headteacher': {
        'title': "HeadTeacher's Comments",
        'empty_message': 'Manual Commenting not enabled',
        'template_message': 'for the Template used',
        'class_message': 'by this Class',
    },
    'director': {
        'title': "Director's Comments",
        'empty_message': 'Manual Commenting not enabled',
        'template_message': 'for the Template used',
        'class_message': 'by this Class',
    },
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
        CREATE TABLE IF NOT EXISTS rms_school (
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

        CREATE TABLE IF NOT EXISTS rms_schoolclass (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name varchar(100) NOT NULL,
            level varchar(50) NOT NULL,
            school_id bigint NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rms_student (
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
            class_field_id bigint NOT NULL,
            school_id bigint NOT NULL,
            image varchar(100) DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS rms_academicsession (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_name varchar(120) NOT NULL,
            start_date date,
            end_date date,
            is_active bool NOT NULL DEFAULT 0,
            school_id bigint NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rms_term (
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

        CREATE TABLE IF NOT EXISTS rms_subject (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name varchar(100) NOT NULL,
            code varchar(20) DEFAULT '',
            is_active bool NOT NULL DEFAULT 1,
            school_id bigint NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rps_subject (
            id INTEGER PRIMARY KEY,
            name varchar(100) NOT NULL,
            code varchar(20) DEFAULT '',
            subject_type varchar(20) DEFAULT 'core',
            is_active bool NOT NULL DEFAULT 1,
            created_at datetime,
            updated_at datetime,
            school_id bigint NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rps_subjectgroup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name varchar(120) NOT NULL,
            group_subsubjects_as_one bool NOT NULL DEFAULT 0,
            exclude_scores_from_total_average bool NOT NULL DEFAULT 0,
            school_id bigint NOT NULL,
            created_at datetime,
            updated_at datetime
        );

        CREATE TABLE IF NOT EXISTS rps_subjectgroup_subject (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_group_id bigint NOT NULL,
            subject_id bigint NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rms_teacher (
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

        CREATE TABLE IF NOT EXISTS rms_teacher_assigned_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id bigint NOT NULL,
            subject_id bigint NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rps_classsubjectallocation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_class_id bigint NOT NULL,
            subject_id bigint NOT NULL,
            teacher_id bigint NULL,
            display_order integer DEFAULT 0,
            created_at datetime,
            updated_at datetime
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

    class_columns = _table_columns(conn, 'rms_schoolclass')
    for name, definition in SCHOOL_CLASS_EXTRA_COLUMNS.items():
        if name not in class_columns:
            conn.execute(f'ALTER TABLE rms_schoolclass ADD COLUMN {name} {definition}')

    student_columns = _table_columns(conn, 'rms_student')
    for name, definition in STUDENT_EXTRA_COLUMNS.items():
        if name not in student_columns:
            conn.execute(f'ALTER TABLE rms_student ADD COLUMN {name} {definition}')

    subject_columns = _table_columns(conn, 'rms_subject')
    for name, definition in SUBJECT_EXTRA_COLUMNS.items():
        if name not in subject_columns:
            conn.execute(f'ALTER TABLE rms_subject ADD COLUMN {name} {definition}')

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
        INSERT INTO rms_school (name, abbreviation, email, phone, address, website, principal_name, logo)
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
               s.principal_name,
               b.tagline, b.primary_color, b.logo, b.secondary_logo, b.stamp
        FROM rms_school s
        LEFT JOIN rps_schoolbranding b ON b.school_id = s.id
        WHERE s.id = ?
        ''',
        (school_id,),
    ).fetchone()
    if not row:
        return None

    school = _decorate_school_record(row)
    count = conn.execute(
        'SELECT COUNT(*) as c FROM rms_student WHERE school_id=? AND is_active=1',
        (school['id'],)
    ).fetchone()
    school['student_count'] = count['c'] if count else 0
    class_count = conn.execute(
        'SELECT COUNT(*) as c FROM rms_schoolclass WHERE school_id=?',
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
    existing_principal = conn.execute(
        'SELECT principal_name FROM rms_school WHERE id=?',
        (school_id,),
    ).fetchone()
    principal_name = existing_principal['principal_name'] if existing_principal else ''

    conn.execute(
        '''
        UPDATE rms_school
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

    conn.execute('DELETE FROM rms_student WHERE school_id=?', (school_id,))
    conn.execute('DELETE FROM rms_schoolclass WHERE school_id=?', (school_id,))
    conn.execute('DELETE FROM rms_school WHERE id=?', (school_id,))
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
               s.principal_name,
               b.tagline, b.primary_color, b.logo, b.secondary_logo, b.stamp
        FROM rms_school s
        LEFT JOIN rps_schoolbranding b ON b.school_id = s.id
        ORDER BY s.name
        '''
    ).fetchall()
    schools = [_decorate_school_record(s) for s in schools]

    for school in schools:
        count = conn.execute(
            'SELECT COUNT(*) as c FROM rms_student WHERE school_id=? AND is_active=1',
            (school['id'],)
        ).fetchone()
        school['student_count'] = count['c'] if count else 0
        class_count = conn.execute(
            'SELECT COUNT(*) as c FROM rms_schoolclass WHERE school_id=?',
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
        {
            'key': 'class',
            'label': 'Class Data',
            'icon': 'class',
            'href': reverse('accounts:school_class_data', kwargs={'school_id': school_id}),
        },
        {
            'key': 'reports',
            'label': 'Reports',
            'icon': 'reports',
            'href': reverse('accounts:school_reports', kwargs={'school_id': school_id}),
        },
        {
            'key': 'settings',
            'label': 'Settings',
            'icon': 'settings',
            'href': reverse('accounts:school_settings', kwargs={'school_id': school_id}),
        },
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
        FROM rms_schoolclass
        WHERE school_id = ?
        ORDER BY name
        ''',
        (school_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _resolve_result_template_name(template_name, class_item=None):
    """Resolve class-level template choice without creating duplicate default names."""
    normalized_name = normalize_template_name(template_name, allow_auto=True)
    if normalized_name != RESULT_TEMPLATE_AUTO:
        return normalized_name

    class_text = " ".join(
        str(value or "")
        for value in (
            (class_item or {}).get("name"),
            (class_item or {}).get("level"),
        )
    ).lower()
    if any(token in class_text for token in ("nursery", "kg", "pre-primary", "pre primary")):
        return DEFAULT_TEMPLATE_NAME
    if any(token in class_text for token in ("junior", "jss", "js ", "grade 7", "grade 8", "grade 9")):
        return JUNIOR_SECONDARY_TEMPLATE_NAME
    return PRIMARY_TEMPLATE_NAME


def _class_subject_allocations_exist(conn, class_id):
    row = conn.execute(
        '''
        SELECT 1
        FROM rps_classsubjectallocation
        WHERE school_class_id=?
        LIMIT 1
        ''',
        (class_id,),
    ).fetchone()
    return bool(row)


def _fetch_class_subjects(conn, school_id, selected_class_id='', search=''):
    _ensure_school_data_schema(conn)
    search_term = (search or '').strip().lower()
    search_like = f'%{search_term}%'
    params = []
    filters = ['s.school_id = ?']
    params.append(school_id)

    if search_term:
        filters.append(
            '''
            (
                LOWER(s.name) LIKE ?
                OR LOWER(COALESCE(s.code, '')) LIKE ?
                OR LOWER(TRIM(
                    COALESCE(t.first_name, '') || ' ' ||
                    COALESCE(t.middle_name, '') || ' ' ||
                    COALESCE(t.last_name, '')
                )) LIKE ?
            )
            '''
        )
        params.extend([search_like, search_like, search_like])

    teacher_name_sql = '''
        TRIM(
            COALESCE(t.first_name, '') || ' ' ||
            COALESCE(t.middle_name, '') || ' ' ||
            COALESCE(t.last_name, '')
        )
    '''

    if selected_class_id and _class_subject_allocations_exist(conn, selected_class_id):
        sql = f'''
            SELECT
                s.id,
                s.name,
                COALESCE(s.code, '') AS code,
                COALESCE(s.is_active, 1) AS is_active,
                csa.display_order,
                tas.teacher_id AS teacher_id,
                {teacher_name_sql} AS teacher_name
            FROM rms_subject s
            JOIN rps_classsubjectallocation csa
                ON csa.subject_id = s.id AND csa.school_class_id = ?
            LEFT JOIN rms_teacher_assigned_subjects tas ON tas.subject_id = s.id
            LEFT JOIN rms_teacher t ON t.id = tas.teacher_id
            WHERE {' AND '.join(filters)}
            GROUP BY s.id
            ORDER BY COALESCE(csa.display_order, 9999), s.name
        '''
        params.insert(0, selected_class_id)
    else:
        sql = f'''
            SELECT
                s.id,
                s.name,
                COALESCE(s.code, '') AS code,
                COALESCE(s.is_active, 1) AS is_active,
                NULL AS display_order,
                tas.teacher_id AS teacher_id,
                {teacher_name_sql} AS teacher_name
            FROM rms_subject s
            LEFT JOIN rms_teacher_assigned_subjects tas ON tas.subject_id = s.id
            LEFT JOIN rms_teacher t ON t.id = tas.teacher_id
            WHERE {' AND '.join(filters)}
            GROUP BY s.id
            ORDER BY s.name
        '''

    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _fetch_subject_groups(conn, school_id):
    _ensure_school_data_schema(conn)
    rows = conn.execute(
        '''
        SELECT
            id,
            name,
            group_subsubjects_as_one,
            exclude_scores_from_total_average
        FROM rps_subjectgroup
        WHERE school_id = ?
        ORDER BY name, id
        ''',
        (school_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_subject_ids_for_class(conn, selected_class_id):
    if not selected_class_id:
        return set()
    rows = conn.execute(
        '''
        SELECT subject_id
        FROM rps_classsubjectallocation
        WHERE school_class_id = ?
        ''',
        (selected_class_id,),
    ).fetchall()
    return {int(row['subject_id']) for row in rows}


def _make_subject_code(conn, school_id, subject_name):
    base = slugify(subject_name).replace('-', '').upper()[:16] or 'SUBJECT'
    code = base[:20]
    counter = 2
    while conn.execute(
        'SELECT 1 FROM rms_subject WHERE school_id = ? AND code = ? LIMIT 1',
        (school_id, code),
    ).fetchone():
        suffix = str(counter)
        code = f'{base[:20 - len(suffix)]}{suffix}'
        counter += 1
    return code


def _allocate_subject_to_class(conn, selected_class_id, subject_id, teacher_id=None):
    if not selected_class_id:
        return False

    class_id = int(selected_class_id)
    subject_id = int(subject_id)
    existing = conn.execute(
        '''
        SELECT id
        FROM rps_classsubjectallocation
        WHERE school_class_id = ? AND subject_id = ?
        LIMIT 1
        ''',
        (class_id, subject_id),
    ).fetchone()
    if existing:
        if teacher_id:
            conn.execute(
                '''
                UPDATE rps_classsubjectallocation
                SET teacher_id = ?, updated_at = ?
                WHERE id = ?
                ''',
                (int(teacher_id), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), existing['id']),
            )
        return False

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    next_order = conn.execute(
        '''
        SELECT COALESCE(MAX(display_order), 0) + 1
        FROM rps_classsubjectallocation
        WHERE school_class_id = ?
        ''',
        (class_id,),
    ).fetchone()[0]
    conn.execute(
        '''
        INSERT INTO rps_classsubjectallocation
            (school_class_id, subject_id, teacher_id, display_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (class_id, subject_id, int(teacher_id) if teacher_id else None, next_order, now, now),
    )
    return True


def _move_subject_allocation(conn, selected_class_id, subject_id, direction):
    if not selected_class_id or not subject_id:
        return False

    class_id = int(selected_class_id)
    rows = conn.execute(
        '''
        SELECT id, subject_id, COALESCE(display_order, 9999) AS display_order
        FROM rps_classsubjectallocation
        WHERE school_class_id = ?
        ORDER BY COALESCE(display_order, 9999), id
        ''',
        (class_id,),
    ).fetchall()
    ordered = [dict(row) for row in rows]
    for index, row in enumerate(ordered, start=1):
        if row['display_order'] != index:
            conn.execute(
                'UPDATE rps_classsubjectallocation SET display_order = ? WHERE id = ?',
                (index, row['id']),
            )
            row['display_order'] = index

    current_index = next(
        (index for index, row in enumerate(ordered) if int(row['subject_id']) == int(subject_id)),
        None,
    )
    if current_index is None:
        return False

    target_index = current_index - 1 if direction == 'up' else current_index + 1
    if target_index < 0 or target_index >= len(ordered):
        return False

    current = ordered[current_index]
    target = ordered[target_index]
    conn.execute(
        'UPDATE rps_classsubjectallocation SET display_order = ?, updated_at = ? WHERE id = ?',
        (target['display_order'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), current['id']),
    )
    conn.execute(
        'UPDATE rps_classsubjectallocation SET display_order = ?, updated_at = ? WHERE id = ?',
        (current['display_order'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), target['id']),
    )
    return True


def _assign_subject_teacher(conn, subject_id, teacher_id):
    conn.execute(
        'DELETE FROM rms_teacher_assigned_subjects WHERE subject_id = ?',
        (subject_id,),
    )
    if teacher_id:
        conn.execute(
            '''
            INSERT INTO rms_teacher_assigned_subjects (teacher_id, subject_id)
            VALUES (?, ?)
            ''',
            (int(teacher_id), int(subject_id)),
        )


def _link_subject_group(conn, subject_id, subject_group_id):
    if not subject_group_id:
        return
    conn.execute(
        'DELETE FROM rps_subjectgroup_subject WHERE subject_id = ?',
        (subject_id,),
    )
    conn.execute(
        '''
        INSERT INTO rps_subjectgroup_subject (subject_group_id, subject_id)
        VALUES (?, ?)
        ''',
        (int(subject_group_id), int(subject_id)),
    )


def _class_subjects_url(school_id, selected_class_id=''):
    url = reverse('accounts:school_class_subjects', kwargs={'school_id': school_id})
    if selected_class_id:
        return f'{url}?class_id={selected_class_id}'
    return url


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
        FROM rms_student s
        LEFT JOIN rms_schoolclass c ON c.id = s.class_field_id
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
        FROM rms_academicsession
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
        FROM rms_term t
        INNER JOIN rms_academicsession s ON s.id = t.session_id
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
        FROM rms_teacher
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


def _ensure_table_extra_columns(conn, table_name, extra_columns):
    existing_columns = _table_columns(conn, table_name)
    for name, definition in extra_columns.items():
        if name not in existing_columns:
            conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {name} {definition}')


def _ensure_class_data_schema(conn):
    _ensure_school_data_schema(conn)
    conn.executescript(
        '''
        CREATE TABLE IF NOT EXISTS rms_score (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id bigint NOT NULL,
            subject_id bigint NOT NULL,
            term_id bigint NOT NULL,
            continuous_assessment decimal(5, 2),
            test_score decimal(5, 2),
            exam_score decimal(5, 2),
            total_score decimal(5, 2),
            grade varchar(2) DEFAULT '',
            comment TEXT DEFAULT '',
            component_scores TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS rps_score (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id bigint NOT NULL,
            subject_id bigint NOT NULL,
            term_id bigint NOT NULL,
            continuous_assessment decimal(5, 2),
            test_score decimal(5, 2),
            exam_score decimal(5, 2),
            total_score decimal(5, 2),
            grade varchar(2) DEFAULT '',
            comment TEXT DEFAULT '',
            component_scores TEXT DEFAULT '',
            created_at datetime,
            updated_at datetime,
            teacher_id integer
        );

        CREATE TABLE IF NOT EXISTS rms_attendanceentry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id bigint NOT NULL,
            term_id bigint NOT NULL,
            date date NOT NULL,
            status varchar(1) NOT NULL,
            remark TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS rps_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            present integer NOT NULL DEFAULT 0,
            absent integer NOT NULL DEFAULT 0,
            late integer NOT NULL DEFAULT 0,
            total_school_days integer NOT NULL DEFAULT 0,
            created_at datetime,
            updated_at datetime,
            student_id bigint NOT NULL,
            term_id bigint NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rps_studentattribute (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            term_id INTEGER NOT NULL,
            school_id INTEGER NOT NULL,
            attribute_type TEXT NOT NULL,
            attribute_name TEXT NOT NULL,
            rating INTEGER
        );

        CREATE TABLE IF NOT EXISTS rps_studentcommentrecord (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_type varchar(20) NOT NULL,
            comment TEXT NOT NULL,
            created_at datetime NOT NULL,
            updated_at datetime NOT NULL,
            school_id bigint NOT NULL,
            student_id bigint NOT NULL,
            term_id bigint NOT NULL,
            updated_by_id integer NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rms_score_class_data
            ON rms_score(student_id, subject_id, term_id);
        CREATE INDEX IF NOT EXISTS idx_rps_score_class_data
            ON rps_score(student_id, subject_id, term_id);
        CREATE INDEX IF NOT EXISTS idx_rps_attendance_student_term
            ON rps_attendance(student_id, term_id);
        CREATE INDEX IF NOT EXISTS idx_student_attribute_entry
            ON rps_studentattribute(student_id, term_id, attribute_name);
        CREATE INDEX IF NOT EXISTS idx_student_comment_entry
            ON rps_studentcommentrecord(student_id, term_id, comment_type);
        '''
    )
    _ensure_table_extra_columns(
        conn,
        'rms_score',
        {
            'continuous_assessment': 'decimal(5, 2)',
            'test_score': 'decimal(5, 2)',
            'exam_score': 'decimal(5, 2)',
            'total_score': 'decimal(5, 2)',
            'grade': "varchar(2) DEFAULT ''",
            'comment': "TEXT DEFAULT ''",
            'component_scores': "TEXT DEFAULT ''",
        },
    )
    _ensure_table_extra_columns(
        conn,
        'rps_score',
        {
            'continuous_assessment': 'decimal(5, 2)',
            'test_score': 'decimal(5, 2)',
            'exam_score': 'decimal(5, 2)',
            'total_score': 'decimal(5, 2)',
            'grade': "varchar(2) DEFAULT ''",
            'comment': "TEXT DEFAULT ''",
            'component_scores': "TEXT DEFAULT ''",
            'created_at': 'datetime',
            'updated_at': 'datetime',
            'teacher_id': 'integer',
        },
    )
    _ensure_table_extra_columns(
        conn,
        'rps_attendance',
        {
            'present': 'integer NOT NULL DEFAULT 0',
            'absent': 'integer NOT NULL DEFAULT 0',
            'late': 'integer NOT NULL DEFAULT 0',
            'total_school_days': 'integer NOT NULL DEFAULT 0',
            'created_at': 'datetime',
            'updated_at': 'datetime',
        },
    )
    _ensure_table_extra_columns(
        conn,
        'rps_studentcommentrecord',
        {
            'updated_by_id': 'integer NULL',
        },
    )
    conn.commit()


def _term_display_name(term):
    raw_name = str((term or {}).get('term_name') or (term or {}).get('term') or '').strip()
    lookup = {
        '1': 'FIRST',
        'term 1': 'FIRST',
        'first': 'FIRST',
        'first term': 'FIRST',
        '2': 'SECOND',
        'term 2': 'SECOND',
        'second': 'SECOND',
        'second term': 'SECOND',
        '3': 'THIRD',
        'term 3': 'THIRD',
        'third': 'THIRD',
        'third term': 'THIRD',
    }
    return lookup.get(raw_name.lower(), raw_name.upper() or 'TERM')


def _selected_by_id(items, selected_id):
    return next((item for item in items if str(item.get('id')) == str(selected_id)), None)


def _fetch_class_data_subjects(conn, school_id, selected_class_id, search=''):
    subjects = _fetch_class_subjects(conn, school_id, selected_class_id, search)
    if subjects:
        return subjects

    sql = '''
        SELECT id, name, '' AS teacher_name
        FROM rms_subject
        WHERE school_id = ? AND COALESCE(is_active, 1) = 1
    '''
    params = [school_id]
    if search:
        sql += ' AND name LIKE ?'
        params.append(f'%{search}%')
    sql += ' ORDER BY name, id'
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _class_data_filters(request, conn, school, include_subject=False):
    classes = _fetch_school_classes(conn, school['id'])
    selected_class_id = (
        request.POST.get('class_id', '').strip()
        if request.method == 'POST'
        else request.GET.get('class_id', '').strip()
    )
    if not selected_class_id and classes:
        selected_class_id = str(classes[0]['id'])
    selected_class = _selected_by_id(classes, selected_class_id)

    terms = _fetch_school_terms(conn, school['id'])
    for term in terms:
        term['display_name'] = _term_display_name(term)
    selected_term_id = (
        request.POST.get('term_id', '').strip()
        if request.method == 'POST'
        else request.GET.get('term_id', '').strip()
    )
    if not selected_term_id and terms:
        active_term = next((item for item in terms if item.get('is_active')), None)
        selected_term_id = str((active_term or terms[0])['id'])
    selected_term = _selected_by_id(terms, selected_term_id)

    filters = {
        'classes': classes,
        'selected_class_id': str(selected_class_id),
        'selected_class': selected_class,
        'terms': terms,
        'selected_term_id': str(selected_term_id),
        'selected_term': selected_term,
        'search_query': request.GET.get('q', '').strip(),
    }

    if include_subject:
        subjects = _fetch_class_data_subjects(conn, school['id'], selected_class_id)
        selected_subject_id = (
            request.POST.get('subject_id', '').strip()
            if request.method == 'POST'
            else request.GET.get('subject_id', '').strip()
        )
        if not selected_subject_id and subjects:
            selected_subject_id = str(subjects[0]['id'])
        filters.update(
            {
                'subjects': subjects,
                'selected_subject_id': str(selected_subject_id),
                'selected_subject': _selected_by_id(subjects, selected_subject_id),
            }
        )

    return filters


def _class_data_query_url(route_name, school_id, filters, **route_kwargs):
    url = reverse(route_name, kwargs={'school_id': school_id, **route_kwargs})
    params = {}
    if filters.get('selected_class_id'):
        params['class_id'] = filters['selected_class_id']
    if filters.get('selected_subject_id'):
        params['subject_id'] = filters['selected_subject_id']
    if filters.get('selected_term_id'):
        params['term_id'] = filters['selected_term_id']
    if filters.get('search_query'):
        params['q'] = filters['search_query']
    return f'{url}?{urlencode(params)}' if params else url


def _number_or_none(value):
    text = str(value or '').strip()
    if text == '':
        return None
    try:
        return round(float(text), 2)
    except (TypeError, ValueError):
        return None


def _format_class_data_number(value):
    if value is None or value == '':
        return ''
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ''
    if number.is_integer():
        return str(int(number))
    return f'{number:.2f}'.rstrip('0').rstrip('.')


def _grade_for_score(total_score):
    if total_score is None:
        return ''
    if total_score >= 70:
        return 'A'
    if total_score >= 60:
        return 'B'
    if total_score >= 50:
        return 'C'
    if total_score >= 45:
        return 'D'
    if total_score >= 40:
        return 'E'
    return 'F'


def _write_score_record(conn, student_id, subject_id, term_id, values):
    filled_values = [value for value in values.values() if value is not None]
    total_score = round(sum(filled_values), 2) if filled_values else None
    grade = _grade_for_score(total_score)
    component_scores = json.dumps(
        {key: value for key, value in values.items() if value is not None}
    )
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    rms_existing = conn.execute(
        '''
        SELECT id
        FROM rms_score
        WHERE student_id = ? AND subject_id = ? AND term_id = ?
        LIMIT 1
        ''',
        (student_id, subject_id, term_id),
    ).fetchone()
    params = (
        values.get('ca1'),
        values.get('ca2'),
        values.get('exam'),
        total_score,
        grade,
        component_scores,
    )
    if rms_existing:
        conn.execute(
            '''
            UPDATE rms_score
            SET continuous_assessment = ?, test_score = ?, exam_score = ?,
                total_score = ?, grade = ?, component_scores = ?
            WHERE id = ?
            ''',
            (*params, rms_existing['id']),
        )
    elif filled_values:
        conn.execute(
            '''
            INSERT INTO rms_score
                (student_id, subject_id, term_id, continuous_assessment, test_score,
                 exam_score, total_score, grade, comment, component_scores)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?)
            ''',
            (
                student_id,
                subject_id,
                term_id,
                values.get('ca1'),
                values.get('ca2'),
                values.get('exam'),
                total_score,
                grade,
                component_scores,
            ),
        )

    rps_existing = conn.execute(
        '''
        SELECT id
        FROM rps_score
        WHERE student_id = ? AND subject_id = ? AND term_id = ?
        LIMIT 1
        ''',
        (student_id, subject_id, term_id),
    ).fetchone()
    if rps_existing:
        conn.execute(
            '''
            UPDATE rps_score
            SET continuous_assessment = ?, test_score = ?, exam_score = ?,
                total_score = ?, grade = ?, component_scores = ?, updated_at = ?
            WHERE id = ?
            ''',
            (*params, now, rps_existing['id']),
        )
    elif filled_values:
        conn.execute(
            '''
            INSERT INTO rps_score
                (student_id, subject_id, term_id, continuous_assessment, test_score,
                 exam_score, total_score, grade, comment, component_scores,
                 created_at, updated_at, teacher_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, NULL)
            ''',
            (
                student_id,
                subject_id,
                term_id,
                values.get('ca1'),
                values.get('ca2'),
                values.get('exam'),
                total_score,
                grade,
                component_scores,
                now,
                now,
            ),
        )


def _score_values_from_row(row):
    if not row:
        return {'ca1': None, 'ca2': None, 'exam': None}
    return {
        key: _number_or_none(row[field])
        for key, _label, field in CLASS_DATA_SCORE_COMPONENTS
    }


def _fetch_score_entry_rows(conn, school_id, filters):
    students = _fetch_school_students(
        conn,
        school_id,
        filters.get('selected_class_id', ''),
        filters.get('search_query', ''),
    )
    score_map = {}
    if filters.get('selected_subject_id') and filters.get('selected_term_id'):
        rows = conn.execute(
            '''
            SELECT ps.*
            FROM rms_score ps
            INNER JOIN rms_student s ON s.id = ps.student_id
            WHERE s.school_id = ?
              AND s.class_field_id = ?
              AND ps.subject_id = ?
              AND ps.term_id = ?
            ''',
            (
                school_id,
                filters['selected_class_id'],
                filters['selected_subject_id'],
                filters['selected_term_id'],
            ),
        ).fetchall()
        score_map = {int(row['student_id']): row for row in rows}

    score_rows = []
    for student in students:
        values = _score_values_from_row(score_map.get(int(student['id'])))
        student['score_values'] = {
            key: _format_class_data_number(value)
            for key, value in values.items()
        }
        score_rows.append(student)
    return score_rows


def _save_score_entry_rows(conn, school_id, filters, post_data):
    if not filters.get('selected_subject_id') or not filters.get('selected_term_id'):
        return 0
    students = _fetch_school_students(conn, school_id, filters.get('selected_class_id', ''))
    for student in students:
        values = {
            key: _number_or_none(post_data.get(f'{key}_{student["id"]}'))
            for key, _label, _field in CLASS_DATA_SCORE_COMPONENTS
        }
        _write_score_record(
            conn,
            int(student['id']),
            int(filters['selected_subject_id']),
            int(filters['selected_term_id']),
            values,
        )
    return len(students)


def _moderate_score_entry_rows(conn, school_id, filters, post_data):
    if not filters.get('selected_term_id'):
        return 0
    add_values = {
        key: _number_or_none(post_data.get(f'moderate_{key}')) or 0
        for key, _label, _field in CLASS_DATA_SCORE_COMPONENTS
    }
    if not any(add_values.values()):
        return 0

    students = _fetch_school_students(conn, school_id, filters.get('selected_class_id', ''))
    subjects = filters.get('subjects', [])
    if not post_data.get('apply_all_subjects') and filters.get('selected_subject_id'):
        subjects = [filters['selected_subject']]

    updated = 0
    for subject in subjects:
        if not subject:
            continue
        for student in students:
            existing = conn.execute(
                '''
                SELECT *
                FROM rms_score
                WHERE student_id = ? AND subject_id = ? AND term_id = ?
                LIMIT 1
                ''',
                (student['id'], subject['id'], filters['selected_term_id']),
            ).fetchone()
            values = _score_values_from_row(existing)
            for key, amount in add_values.items():
                if amount:
                    values[key] = round((values.get(key) or 0) + amount, 2)
            _write_score_record(
                conn,
                int(student['id']),
                int(subject['id']),
                int(filters['selected_term_id']),
                values,
            )
            updated += 1
    return updated


def _fetch_attendance_rows(conn, school_id, filters):
    students = _fetch_school_students(
        conn,
        school_id,
        filters.get('selected_class_id', ''),
        filters.get('search_query', ''),
    )
    attendance_map = {}
    if filters.get('selected_term_id'):
        rows = conn.execute(
            '''
            SELECT student_id, absent
            FROM rps_attendance
            WHERE term_id = ?
            ''',
            (filters['selected_term_id'],),
        ).fetchall()
        attendance_map = {int(row['student_id']): row['absent'] for row in rows}
    for student in students:
        student['absent_count'] = attendance_map.get(int(student['id']), '')
    return students


def _save_attendance_rows(conn, school_id, filters, post_data):
    if not filters.get('selected_term_id'):
        return 0
    students = _fetch_school_students(conn, school_id, filters.get('selected_class_id', ''))
    selected_term = filters.get('selected_term') or {}
    total_school_days = int(_number_or_none(selected_term.get('times_school_open')) or 0)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for student in students:
        absent = int(_number_or_none(post_data.get(f'absent_{student["id"]}')) or 0)
        present = max(total_school_days - absent, 0)
        existing = conn.execute(
            '''
            SELECT id, late
            FROM rps_attendance
            WHERE student_id = ? AND term_id = ?
            LIMIT 1
            ''',
            (student['id'], filters['selected_term_id']),
        ).fetchone()
        if existing:
            conn.execute(
                '''
                UPDATE rps_attendance
                SET present = ?, absent = ?, total_school_days = ?, updated_at = ?
                WHERE id = ?
                ''',
                (present, absent, total_school_days, now, existing['id']),
            )
        else:
            conn.execute(
                '''
                INSERT INTO rps_attendance
                    (present, absent, late, total_school_days, created_at, updated_at,
                     student_id, term_id)
                VALUES (?, ?, 0, ?, ?, ?, ?, ?)
                ''',
                (present, absent, total_school_days, now, now, student['id'], filters['selected_term_id']),
            )
    return len(students)


def _fetch_attribute_entry_rows(conn, school_id, filters):
    students = _fetch_school_students(
        conn,
        school_id,
        filters.get('selected_class_id', ''),
        filters.get('search_query', ''),
    )
    attribute_map = {}
    if filters.get('selected_term_id'):
        rows = conn.execute(
            '''
            SELECT student_id, attribute_name, rating
            FROM rps_studentattribute
            WHERE school_id = ? AND term_id = ?
            ''',
            (school_id, filters['selected_term_id']),
        ).fetchall()
        for row in rows:
            attribute_map.setdefault(int(row['student_id']), {})[row['attribute_name']] = row['rating']
    for student in students:
        attribute_values = {
            column['name']: attribute_map.get(int(student['id']), {}).get(column['name'], '')
            for column in CLASS_DATA_ATTRIBUTE_COLUMNS
        }
        student['attribute_values'] = attribute_values
        student['attribute_cells'] = [
            {
                'field_name': f'attr_{student["id"]}_{slugify(column["name"])}',
                'value': attribute_values.get(column['name'], ''),
            }
            for column in CLASS_DATA_ATTRIBUTE_COLUMNS
        ]
    return students


def _save_attribute_entry_rows(conn, school_id, filters, post_data):
    if not filters.get('selected_term_id'):
        return 0
    students = _fetch_school_students(conn, school_id, filters.get('selected_class_id', ''))
    for student in students:
        for column in CLASS_DATA_ATTRIBUTE_COLUMNS:
            field_name = f'attr_{student["id"]}_{slugify(column["name"])}'
            rating = post_data.get(field_name, '').strip()
            existing = conn.execute(
                '''
                SELECT id
                FROM rps_studentattribute
                WHERE student_id = ? AND term_id = ? AND attribute_name = ?
                LIMIT 1
                ''',
                (student['id'], filters['selected_term_id'], column['name']),
            ).fetchone()
            if rating:
                safe_rating = max(1, min(int(_number_or_none(rating) or 1), 5))
                if existing:
                    conn.execute(
                        '''
                        UPDATE rps_studentattribute
                        SET school_id = ?, attribute_type = ?, rating = ?
                        WHERE id = ?
                        ''',
                        (school_id, column['type'], safe_rating, existing['id']),
                    )
                else:
                    conn.execute(
                        '''
                        INSERT INTO rps_studentattribute
                            (student_id, term_id, school_id, attribute_type, attribute_name, rating)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            student['id'],
                            filters['selected_term_id'],
                            school_id,
                            column['type'],
                            column['name'],
                            safe_rating,
                        ),
                    )
            elif existing:
                conn.execute('DELETE FROM rps_studentattribute WHERE id = ?', (existing['id'],))
    return len(students)


def _open_class_data_context(school_id):
    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_class_data_schema(conn)
    return conn, _fetch_school(conn, school_id)


def _ensure_settings_schema(conn):
    _ensure_school_data_schema(conn)

    branding_columns = _table_columns(conn, 'rps_schoolbranding')
    for name, definition in {
        'headteacher_name': "varchar(255) DEFAULT ''",
        'director_name': "varchar(255) DEFAULT ''",
        'headteacher_signature': "varchar(255) DEFAULT ''",
        'stamp': "varchar(100) DEFAULT ''",
    }.items():
        if name not in branding_columns:
            conn.execute(f'ALTER TABLE rps_schoolbranding ADD COLUMN {name} {definition}')

    conn.executescript(
        '''
        CREATE TABLE IF NOT EXISTS rps_schoolemailsetting (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id bigint NOT NULL UNIQUE,
            sender varchar(255) DEFAULT '',
            subject varchar(255) DEFAULT '',
            body TEXT DEFAULT '',
            created_at datetime NOT NULL,
            updated_at datetime NOT NULL
        );
        '''
    )
    conn.commit()


def _open_settings_context(school_id):
    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_settings_schema(conn)
    return conn, _fetch_school(conn, school_id)


def _ensure_settings_branding_row(conn, school):
    _ensure_settings_schema(conn)
    row = conn.execute(
        'SELECT * FROM rps_schoolbranding WHERE school_id=?',
        (school['id'],),
    ).fetchone()
    if row:
        return dict(row)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    columns = _table_columns(conn, 'rps_schoolbranding')
    defaults = {
        'display_name': school.get('name') or '',
        'system_name': f"{(school.get('abbreviation') or _default_abbreviation(school.get('name'))).lower()}-matokeo-rms",
        'tagline': school.get('tagline') or '',
        'logo': school.get('logo_path') or '',
        'favicon': '',
        'primary_color': '#1f7a4c',
        'secondary_color': '#f5f7f6',
        'accent_color': '#f59e0b',
        'success_color': '#16a34a',
        'warning_color': '#d97706',
        'danger_color': '#dc2626',
        'show_powered_by': 1,
        'show_vendor_contact': 1,
        'custom_domain': None,
        'allow_user_customization': 1,
        'created_at': now,
        'updated_at': now,
        'school_id': school['id'],
        'background_image': '',
        'background_opacity': 18,
        'background_pattern': 'dots',
        'branding_preview_enabled': 1,
        'css_version': 1,
        'custom_css': '',
        'font_family': 'Inter',
        'font_url': None,
        'logo_cropped': None,
        'logo_position_x': 50,
        'logo_position_y': 50,
        'footer_text': '',
        'secondary_logo': school.get('secondary_logo_path') or '',
        'headteacher_name': '',
        'director_name': '',
        'headteacher_signature': '',
        'stamp': school.get('secondary_logo_path') or '',
    }
    insert_columns = [column for column in defaults if column in columns]
    placeholders = ', '.join('?' for _ in insert_columns)
    conn.execute(
        f'''
        INSERT INTO rps_schoolbranding ({', '.join(insert_columns)})
        VALUES ({placeholders})
        ''',
        [defaults[column] for column in insert_columns],
    )
    conn.commit()
    row = conn.execute(
        'SELECT * FROM rps_schoolbranding WHERE school_id=?',
        (school['id'],),
    ).fetchone()
    return dict(row) if row else {}


def _default_email_settings(school):
    return {
        'sender': (school.get('name') or '').upper(),
        'subject': '[SESSION] [TERM] TERM REPORT SHEET',
        'body': 'Dear [NAME],\n\nKindly download the attachment to view your [TERM] Term Report Sheet.\n\nThanks.',
    }


def _fetch_email_settings(conn, school):
    defaults = _default_email_settings(school)
    row = conn.execute(
        'SELECT sender, subject, body FROM rps_schoolemailsetting WHERE school_id=?',
        (school['id'],),
    ).fetchone()
    if not row:
        return defaults
    return {
        'sender': row['sender'] or defaults['sender'],
        'subject': row['subject'] or defaults['subject'],
        'body': row['body'] or defaults['body'],
    }


def _upsert_email_settings(conn, school_id, sender, subject, body):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row = conn.execute(
        'SELECT id FROM rps_schoolemailsetting WHERE school_id=?',
        (school_id,),
    ).fetchone()
    if row:
        conn.execute(
            '''
            UPDATE rps_schoolemailsetting
            SET sender=?, subject=?, body=?, updated_at=?
            WHERE school_id=?
            ''',
            (sender, subject, body, now, school_id),
        )
    else:
        conn.execute(
            '''
            INSERT INTO rps_schoolemailsetting (school_id, sender, subject, body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (school_id, sender, subject, body, now, now),
        )
    conn.commit()


def login_view(request):
    """Admin login (Django auth)."""
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        if (
            username.lower() == DEFAULT_ADMIN_USERNAME
            and password == DEFAULT_ADMIN_PASSWORD
        ):
            ensure_default_admin_user()
            username = DEFAULT_ADMIN_USERNAME
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            request.session['user_role'] = 'admin'
            if is_default_admin_password(user):
                messages.warning(
                    request,
                    'You are using the default admin password. Change it in Settings > Users before entering real school data.',
                )
            return redirect(_school_setup_route())
        error = 'Invalid username or password.'
    return render(
        request,
        'accounts/login.html',
        {
            'error': error,
            'login_tab': 'admin',
            'product_name': 'Matokeo RMS',
            'product_tagline': 'A powerful result management system',
            'product_summary': 'Sign in to manage schools, templates, class data, and reports from one focused workspace.',
        },
    )

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
    if not request.user.is_authenticated:
        return redirect('accounts:login')

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
    if not request.user.is_authenticated:
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
    if not request.user.is_authenticated:
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
    if not request.user.is_authenticated:
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


def school_class_data(request, school_id):
    """Gestio-style Class Data module menu."""
    if not request.user.is_authenticated:
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

    class_data_tiles = [
        {
            'label': 'Subjects',
            'tone': 'subjects',
            'icon_path': 'accounts/icons/class_data/subjects.svg',
            'href': reverse('accounts:school_class_subjects', kwargs={'school_id': school['id']}),
        },
        {
            'label': 'Marks / Scores',
            'tone': 'scores',
            'icon_path': 'accounts/icons/class_data/marks-scores.svg',
            'href': reverse('accounts:school_class_marks_scores', kwargs={'school_id': school['id']}),
        },
        {
            'label': 'Attendance',
            'tone': 'attendance',
            'icon_path': 'accounts/icons/class_data/attendance.svg',
            'href': reverse('accounts:school_class_attendance', kwargs={'school_id': school['id']}),
        },
        {
            'label': 'Attributes / Skills',
            'tone': 'attributes',
            'icon_path': 'accounts/icons/class_data/attributes-skills.svg',
            'href': reverse('accounts:school_class_attributes', kwargs={'school_id': school['id']}),
        },
        {
            'label': "Class Teacher's Comments",
            'tone': 'class-comments',
            'icon_path': 'accounts/icons/class_data/comments.svg',
            'href': reverse(
                'accounts:school_class_comments',
                kwargs={'school_id': school['id'], 'comment_type': 'teacher'},
            ),
        },
        {
            'label': "Headteacher's Comments",
            'tone': 'head-comments',
            'icon_path': 'accounts/icons/class_data/comments.svg',
            'href': reverse(
                'accounts:school_class_comments',
                kwargs={'school_id': school['id'], 'comment_type': 'headteacher'},
            ),
        },
        {
            'label': "Director's Comments",
            'tone': 'director-comments',
            'icon_path': 'accounts/icons/class_data/comments.svg',
            'href': reverse(
                'accounts:school_class_comments',
                kwargs={'school_id': school['id'], 'comment_type': 'director'},
            ),
        },
    ]

    return render(
        request,
        'accounts/school_class_data.html',
        {
            **_build_school_shell_context(school, active_key='class'),
            'class_data_tiles': class_data_tiles,
            'close_href': reverse('accounts:school_entry', kwargs={'school_id': school['id']}),
        },
    )


def school_reports(request, school_id):
    """Gestio-style Reports module menu."""
    if not request.user.is_authenticated:
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

    report_tiles = [
        {
            'key': 'student-result-sheet',
            'label': 'Student Result Sheet',
            'tone': 'student-result',
            'icon_path': 'accounts/icons/class_data/subjects.svg',
            'href': reverse('accounts:school_report_results', kwargs={'school_id': school['id']}),
        },
        {
            'key': 'broadsheet-class-view',
            'label': 'Broadsheet (Class View)',
            'tone': 'broadsheet-class',
            'icon_path': 'accounts/icons/class_data/database-add.svg',
            'href': reverse('accounts:school_report_broadsheet_class', kwargs={'school_id': school['id']}),
        },
        {
            'key': 'subject-champions',
            'label': 'Subject Champions',
            'tone': 'subject-champions',
            'icon_path': 'accounts/icons/class_data/group.svg',
            'href': reverse('accounts:school_report_subject_champions', kwargs={'school_id': school['id']}),
        },
        {
            'key': 'broadsheet-subject-view',
            'label': 'Broadsheet (Subject View)',
            'tone': 'broadsheet-subject',
            'icon_path': 'accounts/icons/class_data/marks-scores.svg',
            'href': reverse('accounts:school_report_broadsheet_subject', kwargs={'school_id': school['id']}),
        },
    ]

    for tile in report_tiles:
        tile['active'] = False

    return render(
        request,
        'accounts/school_reports.html',
        {
            **_build_school_shell_context(school, active_key='reports'),
            'report_tiles': report_tiles,
            'close_href': reverse('accounts:school_entry', kwargs={'school_id': school['id']}),
        },
    )


def _report_remark_for_score(score):
    if score is None:
        return ''
    if score >= 70:
        return 'EXCELLENT'
    if score >= 60:
        return 'VERY GOOD'
    if score >= 50:
        return 'GOOD'
    if score >= 45:
        return 'FAIR'
    if score >= 40:
        return 'POOR'
    return 'VERY POOR'


def _report_ordinal(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ''
    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


def _report_score_query_params(filters, **extras):
    params = {}
    if filters.get('selected_class_id'):
        params['class_id'] = filters['selected_class_id']
    if filters.get('selected_subject_id'):
        params['subject_id'] = filters['selected_subject_id']
    if filters.get('selected_term_id'):
        params['term_id'] = filters['selected_term_id']
    if filters.get('search_query'):
        params['q'] = filters['search_query']
    for key, value in extras.items():
        if value not in (None, ''):
            params[key] = value
    return urlencode(params)


def _report_title(filters):
    class_name = (filters.get('selected_class') or {}).get('name') or 'Class'
    term_name = (filters.get('selected_term') or {}).get('display_name') or 'TERM'
    return f'{class_name} ({term_name} TERM)'


def _fetch_report_score_matrix(conn, school_id, filters):
    students = _fetch_school_students(
        conn,
        school_id,
        filters.get('selected_class_id', ''),
        filters.get('search_query', ''),
    )
    subjects = _fetch_class_data_subjects(conn, school_id, filters.get('selected_class_id', ''))
    score_map = {}
    if filters.get('selected_class_id') and filters.get('selected_term_id'):
        rows = conn.execute(
            '''
            SELECT ps.*
            FROM rms_score ps
            INNER JOIN rms_student s ON s.id = ps.student_id
            WHERE s.school_id = ?
              AND s.class_field_id = ?
              AND ps.term_id = ?
            ''',
            (school_id, filters['selected_class_id'], filters['selected_term_id']),
        ).fetchall()
        score_map = {
            (int(row['student_id']), int(row['subject_id'])): row
            for row in rows
        }

    matrix_rows = []
    for student in students:
        subject_results = []
        total_score = 0
        scored_count = 0
        pass_count = 0

        for subject in subjects:
            values = _score_values_from_row(score_map.get((int(student['id']), int(subject['id']))))
            filled_values = [value for value in values.values() if value is not None]
            subject_total = round(sum(filled_values), 2) if filled_values else None
            if subject_total is not None:
                total_score += subject_total
                scored_count += 1
                if subject_total >= 40:
                    pass_count += 1

            subject_results.append(
                {
                    'id': subject['id'],
                    'name': subject['name'],
                    'ca1': _format_class_data_number(values.get('ca1')),
                    'ca2': _format_class_data_number(values.get('ca2')),
                    'exam': _format_class_data_number(values.get('exam')),
                    'total': _format_class_data_number(subject_total),
                    'total_raw': subject_total,
                }
            )

        offered_count = len(subjects)
        average_score = round(total_score / offered_count, 2) if offered_count else None
        matrix_rows.append(
            {
                'student': student,
                'subjects': subject_results,
                'total_score': _format_class_data_number(total_score if scored_count else None),
                'total_score_raw': total_score if scored_count else None,
                'scored_count': scored_count,
                'offered_count': offered_count,
                'pass_count': pass_count,
                'average': _format_class_data_number(average_score),
                'average_raw': average_score,
                'remarks': _report_remark_for_score(average_score),
            }
        )

    ranked = sorted(
        [row for row in matrix_rows if row['average_raw'] is not None],
        key=lambda row: row['average_raw'],
        reverse=True,
    )
    last_score = None
    current_position = 0
    for index, row in enumerate(ranked, start=1):
        if row['average_raw'] != last_score:
            current_position = index
            last_score = row['average_raw']
        row['position'] = _report_ordinal(current_position)

    for row in matrix_rows:
        row.setdefault('position', '')

    return students, subjects, matrix_rows


def _report_grade_counts(matrix_rows):
    labels = ['EXCELLENT', 'VERY GOOD', 'GOOD', 'FAIR', 'POOR', 'VERY POOR']
    counts = {label: 0 for label in labels}
    for row in matrix_rows:
        remark = row.get('remarks') or ''
        if remark in counts:
            counts[remark] += 1
    counts['TOTAL'] = sum(counts.values())
    return [{'label': label, 'count': counts[label]} for label in [*labels, 'TOTAL']]


def _report_pass_fail_counts(matrix_rows, pass_mark):
    passed = 0
    failed = 0
    for row in matrix_rows:
        average = row.get('average_raw')
        if average is None:
            continue
        if average >= pass_mark:
            passed += 1
        else:
            failed += 1
    return {
        'passes': passed,
        'fails': failed,
        'total': passed + failed,
    }


def _report_csv_response(filename, headers, rows):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response


def school_report_results(request, school_id):
    """Student result sheet report workspace."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_class_data_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']
    filters = _class_data_filters(request, conn, school)
    students, subjects, matrix_rows = _fetch_report_score_matrix(conn, school['id'], filters)

    selected_student_id = request.GET.get('student_id', '').strip()
    if not selected_student_id and students:
        selected_student_id = str(students[0]['id'])
    selected_row = next(
        (row for row in matrix_rows if str(row['student']['id']) == str(selected_student_id)),
        None,
    )
    result_template_name = _resolve_result_template_name(
        (filters.get('selected_class') or {}).get('template_name'),
        filters.get('selected_class'),
    )
    result_template_preview_url = (
        reverse('accounts:school_template_editor', kwargs={'school_id': school['id']})
        + '?'
        + urlencode({'template': result_template_name, 'preview_only': '1'})
    )

    if request.GET.get('export') == '1':
        conn.close()
        csv_rows = []
        if selected_row:
            for subject in selected_row['subjects']:
                csv_rows.append(
                    [
                        subject['name'],
                        subject['ca1'],
                        subject['ca2'],
                        subject['exam'],
                        subject['total'],
                    ]
                )
        return _report_csv_response(
            'student_result_sheet.csv',
            ['Subject', 'CA1', 'CA2', 'Exam', 'TotalScore'],
            csv_rows,
        )

    query_string = _report_score_query_params(filters, student_id=selected_student_id)
    conn.close()
    return render(
        request,
        'accounts/school_report_results.html',
        {
            **_build_school_shell_context(school, active_key='reports'),
            **filters,
            'students': students,
            'matrix_rows': matrix_rows,
            'selected_student_id': str(selected_student_id),
            'selected_row': selected_row,
            'subjects': subjects,
            'report_heading': _report_title(filters),
            'result_template_name': result_template_name,
            'result_template_preview_url': result_template_preview_url,
            'query_string': query_string,
            'close_href': reverse('accounts:school_reports', kwargs={'school_id': school['id']}),
        },
    )


def school_report_broadsheet_class(request, school_id):
    """Class-view broadsheet workspace."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_class_data_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']
    filters = _class_data_filters(request, conn, school)
    model = request.GET.get('model', '1').strip() or '1'
    pass_mark = _number_or_none(request.GET.get('pass_mark')) or 50
    cumulative = request.GET.get('cumulative') == '1'
    students, subjects, matrix_rows = _fetch_report_score_matrix(conn, school['id'], filters)
    summary_counts = _report_grade_counts(matrix_rows) if model == '2' else []
    pass_fail_counts = _report_pass_fail_counts(matrix_rows, pass_mark)

    if request.GET.get('export') == '1':
        conn.close()
        headers = [
            'Admission No.',
            'Name',
            *[subject['name'] for subject in subjects],
            'Subjects Offered',
            'Subjects Passed',
            'Average %',
            'Position',
            'Remarks',
        ]
        csv_rows = []
        for row in matrix_rows:
            csv_rows.append(
                [
                    row['student'].get('admission_number') or '',
                    row['student'].get('name') or '',
                    *[subject['total'] for subject in row['subjects']],
                    row['offered_count'],
                    row['pass_count'],
                    row['average'],
                    row['position'],
                    row['remarks'],
                ]
            )
        return _report_csv_response('broadsheet_class_view.csv', headers, csv_rows)

    query_string = _report_score_query_params(
        filters,
        model=model,
        pass_mark=_format_class_data_number(pass_mark),
        cumulative='1' if cumulative else '',
    )
    conn.close()
    return render(
        request,
        'accounts/school_report_broadsheet_class.html',
        {
            **_build_school_shell_context(school, active_key='reports'),
            **filters,
            'students': students,
            'subjects': subjects,
            'rows': matrix_rows,
            'report_heading': _report_title(filters),
            'model': model,
            'pass_mark': _format_class_data_number(pass_mark),
            'cumulative': cumulative,
            'summary_counts': summary_counts,
            'pass_fail_counts': pass_fail_counts,
            'query_string': query_string,
            'close_href': reverse('accounts:school_reports', kwargs={'school_id': school['id']}),
        },
    )


def school_report_subject_champions(request, school_id):
    """Subject champions report workspace."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_class_data_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']
    filters = _class_data_filters(request, conn, school)
    _students, subjects, matrix_rows = _fetch_report_score_matrix(conn, school['id'], filters)
    champions = []
    for subject_index, subject in enumerate(subjects):
        contenders = [
            {
                'subject': subject,
                'student': row['student'],
                'score': row['subjects'][subject_index]['total_raw'],
            }
            for row in matrix_rows
            if subject_index < len(row['subjects']) and row['subjects'][subject_index]['total_raw'] is not None
        ]
        contenders.sort(key=lambda row: row['score'], reverse=True)
        if contenders:
            top = contenders[0]
            champions.append(
                {
                    'subject': subject['name'],
                    'admission_number': top['student'].get('admission_number') or '',
                    'student_name': top['student'].get('name') or '',
                    'score': _format_class_data_number(top['score']),
                    'position': '1st',
                }
            )

    if request.GET.get('export') == '1':
        conn.close()
        return _report_csv_response(
            'subject_champions.csv',
            ['Subject', 'Admission No.', 'Name', 'Score', 'Position'],
            [
                [
                    row['subject'],
                    row['admission_number'],
                    row['student_name'],
                    row['score'],
                    row['position'],
                ]
                for row in champions
            ],
        )

    query_string = _report_score_query_params(
        filters,
        cumulative='1' if request.GET.get('cumulative') == '1' else '',
    )
    conn.close()
    return render(
        request,
        'accounts/school_report_subject_champions.html',
        {
            **_build_school_shell_context(school, active_key='reports'),
            **filters,
            'rows': champions,
            'report_heading': _report_title(filters),
            'cumulative': request.GET.get('cumulative') == '1',
            'query_string': query_string,
            'close_href': reverse('accounts:school_reports', kwargs={'school_id': school['id']}),
        },
    )


def school_report_broadsheet_subject(request, school_id):
    """Subject-view broadsheet workspace."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_class_data_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']
    filters = _class_data_filters(request, conn, school, include_subject=True)
    model = request.GET.get('model', '1').strip() or '1'
    pass_mark = _number_or_none(request.GET.get('pass_mark')) or 50
    cumulative = request.GET.get('cumulative') == '1'
    rows = _fetch_score_entry_rows(conn, school['id'], filters)
    subject_rows = []
    for row in rows:
        values = {
            key: _number_or_none(row['score_values'].get(key))
            for key, _label, _field in CLASS_DATA_SCORE_COMPONENTS
        }
        filled_values = [value for value in values.values() if value is not None]
        total_score = round(sum(filled_values), 2) if filled_values else None
        average_score = total_score
        subject_rows.append(
            {
                'student': row,
                'ca1': _format_class_data_number(values.get('ca1')),
                'ca2': _format_class_data_number(values.get('ca2')),
                'exam': _format_class_data_number(values.get('exam')),
                'total': _format_class_data_number(total_score),
                'total_raw': total_score,
                'average': _format_class_data_number(average_score),
                'average_raw': average_score,
                'remarks': _report_remark_for_score(average_score),
            }
        )

    ranked = sorted(
        [row for row in subject_rows if row['average_raw'] is not None],
        key=lambda row: row['average_raw'],
        reverse=True,
    )
    last_score = None
    current_position = 0
    for index, row in enumerate(ranked, start=1):
        if row['average_raw'] != last_score:
            current_position = index
            last_score = row['average_raw']
        row['position'] = _report_ordinal(current_position)
    for row in subject_rows:
        row.setdefault('position', '')

    pass_fail_counts = _report_pass_fail_counts(subject_rows, pass_mark)

    if request.GET.get('export') == '1':
        conn.close()
        return _report_csv_response(
            'broadsheet_subject_view.csv',
            ['Admission No.', 'Name', 'CA1', 'CA2', 'Exam', 'TotalScore', 'Average (%)', 'Position', 'Remarks'],
            [
                [
                    row['student'].get('admission_number') or '',
                    row['student'].get('name') or '',
                    row['ca1'],
                    row['ca2'],
                    row['exam'],
                    row['total'],
                    row['average'],
                    row['position'],
                    row['remarks'],
                ]
                for row in subject_rows
            ],
        )

    query_string = _report_score_query_params(
        filters,
        model=model,
        pass_mark=_format_class_data_number(pass_mark),
        cumulative='1' if cumulative else '',
    )
    conn.close()
    return render(
        request,
        'accounts/school_report_broadsheet_subject.html',
        {
            **_build_school_shell_context(school, active_key='reports'),
            **filters,
            'rows': subject_rows,
            'report_heading': _report_title(filters),
            'model': model,
            'pass_mark': _format_class_data_number(pass_mark),
            'cumulative': cumulative,
            'pass_fail_counts': pass_fail_counts,
            'query_string': query_string,
            'close_href': reverse('accounts:school_reports', kwargs={'school_id': school['id']}),
        },
    )


def school_settings(request, school_id):
    """Gestio-style Settings module menu."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_settings_context(school_id)

    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']

    settings_tiles = [
        {
            'key': 'school-details',
            'label': 'School Details',
            'tone': 'school-details',
            'icon_path': 'accounts/icons/class_data/subjects.svg',
            'href': reverse('accounts:school_settings_details', kwargs={'school_id': school['id']}),
        },
        {
            'key': 'school-headteacher',
            'label': 'School Headteacher',
            'tone': 'headteacher',
            'icon_path': 'accounts/icons/class_data/comments.svg',
            'href': reverse('accounts:school_settings_headteacher', kwargs={'school_id': school['id']}),
        },
        {
            'key': 'school-email',
            'label': 'School Email',
            'tone': 'school-email',
            'icon_path': 'accounts/icons/class_data/export.svg',
            'href': reverse('accounts:school_settings_email', kwargs={'school_id': school['id']}),
        },
        {
            'key': 'users',
            'label': 'Users',
            'tone': 'users',
            'icon_path': 'accounts/icons/class_data/group.svg',
            'href': reverse('accounts:school_settings_users', kwargs={'school_id': school['id']}),
        },
    ]
    conn.close()

    return render(
        request,
        'accounts/school_settings.html',
        {
            **_build_school_shell_context(school, active_key='settings'),
            'settings_tiles': settings_tiles,
            'close_href': reverse('accounts:school_entry', kwargs={'school_id': school['id']}),
        },
    )


def school_settings_details(request, school_id):
    """School details settings screen."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_settings_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    if request.method == 'POST':
        school_name = request.POST.get('name', '').strip()
        other_details = request.POST.get('other_details', '').strip()
        details = _extract_school_details(other_details)
        existing_logo_path = request.POST.get('existing_logo', '').strip()
        existing_secondary_logo_path = request.POST.get('existing_secondary_logo', '').strip()
        logo_path = existing_logo_path
        secondary_logo_path = existing_secondary_logo_path

        if request.FILES.get('logo'):
            logo_path = _save_school_media(request.FILES['logo'], 'schools')
            if existing_logo_path and existing_logo_path != logo_path:
                _delete_school_media(existing_logo_path)
        elif request.POST.get('clear_logo') == '1':
            logo_path = ''
            _delete_school_media(existing_logo_path)

        if request.FILES.get('secondary_logo'):
            secondary_logo_path = _save_school_media(request.FILES['secondary_logo'], 'schools')
            if existing_secondary_logo_path and existing_secondary_logo_path != secondary_logo_path:
                _delete_school_media(existing_secondary_logo_path)
        elif request.POST.get('clear_secondary_logo') == '1':
            secondary_logo_path = ''
            _delete_school_media(existing_secondary_logo_path)

        if not school_name:
            messages.error(request, 'School name is required.')
        else:
            _update_school(
                conn,
                school_id=school['id'],
                name=school_name,
                abbreviation=request.POST.get('abbreviation', '').strip() or school.get('abbreviation', ''),
                email=request.POST.get('email', '').strip() or details['email'],
                phone=request.POST.get('phone', '').strip() or details['phone'],
                address=request.POST.get('address', '').strip() or details['address'],
                logo_path=logo_path,
                secondary_logo_path=secondary_logo_path,
                tagline=request.POST.get('tagline', '').strip() or details['tagline'],
            )
            request.session['school_name'] = school_name
            conn.close()
            messages.success(request, 'School details saved.')
            return redirect('accounts:school_settings_details', school_id=school['id'])

    form = {
        'name': school.get('name') or '',
        'other_details': school.get('address') or DEFAULT_SCHOOL_DETAILS,
        'logo_url': school.get('logo_url') or '',
        'secondary_logo_url': school.get('secondary_logo_url') or '',
        'existing_logo': school.get('logo_path') or '',
        'existing_secondary_logo': school.get('secondary_logo_path') or '',
    }
    conn.close()
    return render(
        request,
        'accounts/school_settings_details.html',
        {
            **_build_school_shell_context(school, active_key='settings'),
            'form': form,
            'close_href': reverse('accounts:school_settings', kwargs={'school_id': school['id']}),
        },
    )


def school_settings_headteacher(request, school_id):
    """School headteacher settings screen."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_settings_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    branding = _ensure_settings_branding_row(conn, school)
    if request.method == 'POST':
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        headteacher_name = request.POST.get('name', '').strip()
        existing_signature = request.POST.get('existing_signature', '').strip()
        signature_path = existing_signature

        if request.FILES.get('signature'):
            signature_path = _save_school_media(request.FILES['signature'], 'signatures')
            if existing_signature and existing_signature != signature_path:
                _delete_school_media(existing_signature)
        elif request.POST.get('clear_signature') == '1':
            signature_path = ''
            _delete_school_media(existing_signature)

        conn.execute(
            '''
            UPDATE rps_schoolbranding
            SET headteacher_name=?, headteacher_signature=?, updated_at=?
            WHERE school_id=?
            ''',
            (headteacher_name, signature_path, now, school['id']),
        )
        conn.execute(
            'UPDATE rms_school SET principal_name=? WHERE id=?',
            (headteacher_name, school['id']),
        )
        if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rps_school'").fetchone():
            conn.execute(
                'UPDATE rps_school SET principal_name=?, updated_at=? WHERE id=?',
                (headteacher_name, now, school['id']),
            )
        conn.commit()
        conn.close()
        messages.success(request, 'Headteacher details saved.')
        return redirect('accounts:school_settings_headteacher', school_id=school['id'])

    signature_path = branding.get('headteacher_signature') or ''
    headteacher = {
        'name': branding.get('headteacher_name') or school.get('principal_name') or '',
        'signature_path': signature_path,
        'signature_url': _media_url(signature_path),
    }
    conn.close()
    return render(
        request,
        'accounts/school_settings_headteacher.html',
        {
            **_build_school_shell_context(school, active_key='settings'),
            'headteacher': headteacher,
            'close_href': reverse('accounts:school_settings', kwargs={'school_id': school['id']}),
        },
    )


def school_settings_email(request, school_id):
    """School email template settings screen."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_settings_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    if request.method == 'POST':
        _upsert_email_settings(
            conn,
            school['id'],
            request.POST.get('sender', '').strip(),
            request.POST.get('subject', '').strip(),
            request.POST.get('body', '').strip(),
        )
        conn.close()
        messages.success(request, 'School email settings saved.')
        return redirect('accounts:school_settings_email', school_id=school['id'])

    email_settings = _fetch_email_settings(conn, school)
    conn.close()
    return render(
        request,
        'accounts/school_settings_email.html',
        {
            **_build_school_shell_context(school, active_key='settings'),
            'email_settings': email_settings,
            'close_href': reverse('accounts:school_settings', kwargs={'school_id': school['id']}),
        },
    )


def _active_admin_count(user_model):
    return user_model.objects.filter(is_active=True, is_superuser=True).count()


def _would_remove_last_active_admin(user_model, user, *, is_active=None, is_superuser=None):
    next_active = user.is_active if is_active is None else is_active
    next_superuser = user.is_superuser if is_superuser is None else is_superuser
    if not user.is_active or not user.is_superuser:
        return False
    if next_active and next_superuser:
        return False
    return _active_admin_count(user_model) <= 1


def _settings_user_rows(user_model):
    users = []
    for user in user_model.objects.order_by('username'):
        role = 'Admin' if user.is_superuser else 'User'
        users.append({
            'id': user.id,
            'username': user.username,
            'password_label': 'Hidden',
            'role': role,
            'status': 'Active' if user.is_active else 'Disabled',
            'limits': 'No Limits' if role == 'Admin' else 'Limited Access',
        })
    return users


def school_settings_users(request, school_id):
    """User management settings screen."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_settings_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')
    conn.close()

    User = get_user_model()
    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        if action == 'create':
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            role = request.POST.get('role', 'User').strip() or 'User'
            if not username or not password:
                messages.error(request, 'Username and password are required.')
            elif User.objects.filter(username__iexact=username).exists():
                messages.error(request, 'That username is already in use.')
            else:
                is_admin = role == 'Admin'
                user = User(username=username, is_active=True, is_staff=True, is_superuser=is_admin)
                user.set_password(password)
                user.save()
                messages.success(request, 'User created successfully.')
        elif action == 'update':
            user_id = request.POST.get('user_id', '').strip()
            username = request.POST.get('edit_username', '').strip()
            password = request.POST.get('edit_password', '')
            role = request.POST.get('edit_role', 'User').strip() or 'User'
            status = request.POST.get('edit_status', 'active').strip() or 'active'
            target_user = User.objects.filter(id=user_id).first()
            if not target_user:
                messages.error(request, 'User not found.')
            elif not username:
                messages.error(request, 'Username is required.')
            elif User.objects.filter(username__iexact=username).exclude(id=target_user.id).exists():
                messages.error(request, 'That username is already in use.')
            else:
                next_active = status == 'active'
                next_superuser = role == 'Admin'
                if target_user.id == request.user.id and not next_active:
                    messages.error(request, 'You cannot disable the account you are currently using.')
                elif _would_remove_last_active_admin(
                    User,
                    target_user,
                    is_active=next_active,
                    is_superuser=next_superuser,
                ):
                    messages.error(request, 'At least one active admin account is required.')
                else:
                    target_user.username = username
                    target_user.is_active = next_active
                    target_user.is_staff = True
                    target_user.is_superuser = next_superuser
                    if password:
                        target_user.set_password(password)
                    target_user.save()
                    if target_user.id == request.user.id and password:
                        update_session_auth_hash(request, target_user)
                    messages.success(request, 'User updated successfully.')
        elif action == 'delete':
            user_id = request.POST.get('user_id', '').strip()
            target_user = User.objects.filter(id=user_id).first()
            if not target_user:
                messages.error(request, 'User not found.')
            elif target_user.id == request.user.id:
                messages.error(request, 'You cannot delete the account you are currently using.')
            elif _would_remove_last_active_admin(User, target_user, is_active=False, is_superuser=False):
                messages.error(request, 'At least one active admin account is required.')
            else:
                target_user.delete()
                messages.success(request, 'User deleted successfully.')
        return redirect('accounts:school_settings_users', school_id=school['id'])

    users = _settings_user_rows(User)

    return render(
        request,
        'accounts/school_settings_users.html',
        {
            **_build_school_shell_context(school, active_key='settings'),
            'users': users,
            'close_href': reverse('accounts:school_settings', kwargs={'school_id': school['id']}),
        },
    )


def school_class_subjects(request, school_id):
    """Subjects screen inside Class Data."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    db_path = str(settings.DATABASES['school_data']['NAME'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_school_data_schema(conn)
    school = _fetch_school(conn, school_id)

    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']

    classes = _fetch_school_classes(conn, school['id'])
    selected_class_id = (
        request.POST.get('class_id', '').strip()
        if request.method == 'POST'
        else request.GET.get('class_id', '').strip()
    )
    if not selected_class_id and classes:
        selected_class_id = str(classes[0]['id'])

    selected_class = next(
        (item for item in classes if str(item['id']) == str(selected_class_id)),
        None,
    )

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        try:
            if action == 'create_subject':
                subject_name = request.POST.get('subject_name', '').strip()
                teacher_id = request.POST.get('teacher_id', '').strip()
                subject_group_id = request.POST.get('subject_group_id', '').strip()

                if not subject_name:
                    messages.error(request, 'Subject name is required.')
                else:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    subject_code = _make_subject_code(conn, school['id'], subject_name)
                    conn.execute(
                        '''
                        INSERT INTO rms_subject (name, code, is_active, school_id)
                        VALUES (?, ?, 1, ?)
                        ''',
                        (subject_name, subject_code, school['id']),
                    )
                    new_subject_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                    conn.execute(
                        '''
                        INSERT INTO rps_subject
                            (id, name, code, subject_type, is_active, created_at, updated_at, school_id)
                        VALUES (?, ?, ?, 'core', 1, ?, ?, ?)
                        ''',
                        (new_subject_id, subject_name, subject_code, now, now, school['id']),
                    )
                    _assign_subject_teacher(conn, new_subject_id, teacher_id)
                    _link_subject_group(conn, new_subject_id, subject_group_id)
                    _allocate_subject_to_class(conn, selected_class_id, new_subject_id, teacher_id)
                    conn.commit()
                    messages.success(request, 'Subject added successfully.')

            elif action == 'create_subject_group':
                group_name = request.POST.get('subject_group_name', '').strip()
                group_as_one = 1 if request.POST.get('group_subsubjects_as_one') else 0
                exclude_average = 1 if request.POST.get('exclude_scores_from_total_average') else 0

                if not group_name:
                    messages.error(request, 'Subject group name is required.')
                else:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    conn.execute(
                        '''
                        INSERT INTO rps_subjectgroup
                            (name, group_subsubjects_as_one, exclude_scores_from_total_average,
                             school_id, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ''',
                        (group_name, group_as_one, exclude_average, school['id'], now, now),
                    )
                    conn.commit()
                    messages.success(request, 'Subject group added successfully.')

            elif action == 'delete_subject_group':
                subject_group_id = request.POST.get('subject_group_id', '').strip()
                if not subject_group_id:
                    messages.error(request, 'Select a subject group first.')
                else:
                    conn.execute(
                        'DELETE FROM rps_subjectgroup_subject WHERE subject_group_id = ?',
                        (int(subject_group_id),),
                    )
                    conn.execute(
                        'DELETE FROM rps_subjectgroup WHERE id = ? AND school_id = ?',
                        (int(subject_group_id), school['id']),
                    )
                    conn.commit()
                    messages.success(request, 'Subject group removed successfully.')

            elif action == 'import_subjects':
                requested_subject_ids = request.POST.getlist('subject_ids')
                imported_count = 0
                for raw_subject_id in requested_subject_ids:
                    try:
                        subject_id = int(raw_subject_id)
                    except (TypeError, ValueError):
                        continue

                    subject_exists = conn.execute(
                        '''
                        SELECT id
                        FROM rms_subject
                        WHERE id = ? AND school_id = ?
                        LIMIT 1
                        ''',
                        (subject_id, school['id']),
                    ).fetchone()
                    if subject_exists and _allocate_subject_to_class(conn, selected_class_id, subject_id):
                        imported_count += 1

                conn.commit()
                if imported_count:
                    messages.success(request, f'{imported_count} subject(s) imported successfully.')
                else:
                    messages.info(request, 'No new subjects were imported.')

            elif action == 'move_subject':
                subject_id = request.POST.get('subject_id', '').strip()
                direction = request.POST.get('direction', '').strip()
                if direction not in {'up', 'down'}:
                    messages.error(request, 'Choose a valid move direction.')
                elif _move_subject_allocation(conn, selected_class_id, subject_id, direction):
                    conn.commit()
                else:
                    messages.info(request, 'Select a saved subject that can move in this class.')

            else:
                messages.error(request, 'Select a valid subject action.')
        except sqlite3.DatabaseError as exc:
            conn.rollback()
            messages.error(request, f'Subject update failed: {exc}')

        conn.close()
        return redirect(_class_subjects_url(school['id'], selected_class_id))

    search_query = request.GET.get('q', '').strip()
    open_modal = request.GET.get('open_modal', '').strip()
    subjects = _fetch_class_subjects(conn, school['id'], selected_class_id, search_query)
    teachers = _fetch_school_teachers(conn, school['id'])
    subject_groups = _fetch_subject_groups(conn, school['id'])
    sessions = _fetch_school_sessions(conn, school['id'])
    selected_session_id = request.GET.get('import_session_id', '').strip()
    if not selected_session_id and sessions:
        selected_session_id = str(sessions[0]['id'])

    import_class_id = request.GET.get('import_class_id', '').strip() or selected_class_id
    import_subjects = _fetch_class_subjects(conn, school['id'], import_class_id, '')
    allocated_subject_ids = _fetch_subject_ids_for_class(conn, selected_class_id)
    for subject in import_subjects:
        subject['already_in_selected_class'] = int(subject['id']) in allocated_subject_ids

    if request.GET.get('export') == '1':
        conn.close()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="subjects.csv"'
        writer = csv.writer(response)
        writer.writerow(['Name', 'Subject Teacher'])
        for subject in subjects:
            writer.writerow([subject.get('name') or '', subject.get('teacher_name') or ''])
        return response

    conn.close()
    return render(
        request,
        'accounts/school_class_subjects.html',
        {
            **_build_school_shell_context(school, active_key='class'),
            'classes': classes,
            'selected_class_id': str(selected_class_id),
            'selected_class': selected_class,
            'subjects': subjects,
            'teachers': teachers,
            'subject_groups': subject_groups,
            'sessions': sessions,
            'selected_session_id': str(selected_session_id),
            'import_class_id': str(import_class_id),
            'import_subjects': import_subjects,
            'search_query': search_query,
            'open_modal': open_modal,
            'close_href': reverse('accounts:school_class_data', kwargs={'school_id': school['id']}),
        },
    )


def school_class_marks_scores(request, school_id):
    """Marks / Scores screen inside Class Data."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_class_data_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']
    filters = _class_data_filters(request, conn, school, include_subject=True)

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        try:
            if action == 'save_scores':
                saved_count = _save_score_entry_rows(conn, school['id'], filters, request.POST)
                conn.commit()
                messages.success(request, f'Scores saved for {saved_count} student(s).')
            elif action == 'moderate_scores':
                updated_count = _moderate_score_entry_rows(conn, school['id'], filters, request.POST)
                conn.commit()
                if updated_count:
                    messages.success(request, f'{updated_count} score row(s) moderated.')
                else:
                    messages.info(request, 'Enter at least one moderation value first.')
            else:
                messages.error(request, 'Select a valid score action.')
        except sqlite3.DatabaseError as exc:
            conn.rollback()
            messages.error(request, f'Score update failed: {exc}')

        redirect_url = _class_data_query_url(
            'accounts:school_class_marks_scores',
            school['id'],
            filters,
        )
        conn.close()
        return redirect(redirect_url)

    rows = _fetch_score_entry_rows(conn, school['id'], filters)

    if request.GET.get('export') == '1':
        conn.close()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="marks_scores.csv"'
        writer = csv.writer(response)
        writer.writerow(['Admission No.', 'Name', 'CA1', 'CA2', 'Exam'])
        for row in rows:
            writer.writerow(
                [
                    row.get('admission_number') or '',
                    row.get('name') or '',
                    row['score_values'].get('ca1', ''),
                    row['score_values'].get('ca2', ''),
                    row['score_values'].get('exam', ''),
                ]
            )
        return response

    conn.close()
    return render(
        request,
        'accounts/school_class_marks_scores.html',
        {
            **_build_school_shell_context(school, active_key='class'),
            **filters,
            'rows': rows,
            'score_components': CLASS_DATA_SCORE_COMPONENTS,
            'close_href': reverse('accounts:school_class_data', kwargs={'school_id': school['id']}),
        },
    )


def school_class_attendance(request, school_id):
    """Attendance screen inside Class Data."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_class_data_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']
    filters = _class_data_filters(request, conn, school)

    if request.method == 'POST':
        try:
            saved_count = _save_attendance_rows(conn, school['id'], filters, request.POST)
            conn.commit()
            messages.success(request, f'Attendance saved for {saved_count} student(s).')
        except sqlite3.DatabaseError as exc:
            conn.rollback()
            messages.error(request, f'Attendance update failed: {exc}')

        redirect_url = _class_data_query_url(
            'accounts:school_class_attendance',
            school['id'],
            filters,
        )
        conn.close()
        return redirect(redirect_url)

    rows = _fetch_attendance_rows(conn, school['id'], filters)

    if request.GET.get('export') == '1':
        conn.close()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="attendance.csv"'
        writer = csv.writer(response)
        writer.writerow(['Admission No.', 'Name', 'NoOfAbsent'])
        for row in rows:
            writer.writerow([row.get('admission_number') or '', row.get('name') or '', row.get('absent_count') or 0])
        return response

    conn.close()
    return render(
        request,
        'accounts/school_class_attendance.html',
        {
            **_build_school_shell_context(school, active_key='class'),
            **filters,
            'rows': rows,
            'close_href': reverse('accounts:school_class_data', kwargs={'school_id': school['id']}),
        },
    )


def school_class_attributes(request, school_id):
    """Attributes / Skills screen inside Class Data."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    conn, school = _open_class_data_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']
    filters = _class_data_filters(request, conn, school)

    if request.method == 'POST':
        try:
            saved_count = _save_attribute_entry_rows(conn, school['id'], filters, request.POST)
            conn.commit()
            messages.success(request, f'Attributes / skills saved for {saved_count} student(s).')
        except sqlite3.DatabaseError as exc:
            conn.rollback()
            messages.error(request, f'Attributes update failed: {exc}')

        redirect_url = _class_data_query_url(
            'accounts:school_class_attributes',
            school['id'],
            filters,
        )
        conn.close()
        return redirect(redirect_url)

    rows = _fetch_attribute_entry_rows(conn, school['id'], filters)

    if request.GET.get('export') == '1':
        conn.close()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="attributes_skills.csv"'
        writer = csv.writer(response)
        writer.writerow(['Name', 'Admission No.', *[column['label'] for column in CLASS_DATA_ATTRIBUTE_COLUMNS]])
        for row in rows:
            writer.writerow(
                [
                    row.get('name') or '',
                    row.get('admission_number') or '',
                    *[
                        row['attribute_values'].get(column['name'], '')
                        for column in CLASS_DATA_ATTRIBUTE_COLUMNS
                    ],
                ]
            )
        return response

    conn.close()
    return render(
        request,
        'accounts/school_class_attributes.html',
        {
            **_build_school_shell_context(school, active_key='class'),
            **filters,
            'rows': rows,
            'attribute_columns': CLASS_DATA_ATTRIBUTE_COLUMNS,
            'rating_options': ('', '1', '2', '3', '4', '5'),
            'close_href': reverse('accounts:school_class_data', kwargs={'school_id': school['id']}),
        },
    )


def school_class_comments(request, school_id, comment_type):
    """Comment screens inside Class Data."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    comment_config = CLASS_DATA_COMMENT_TYPES.get(comment_type)
    if not comment_config:
        return redirect('accounts:school_class_data', school_id=school_id)

    conn, school = _open_class_data_context(school_id)
    if not school:
        conn.close()
        messages.error(request, 'That school could not be found.')
        return redirect('accounts:add_school')

    request.session['school_id'] = int(school['id'])
    request.session['school_name'] = school['name']
    filters = _class_data_filters(request, conn, school)

    rows = []
    if request.GET.get('export') == '1':
        students = _fetch_school_students(
            conn,
            school['id'],
            filters.get('selected_class_id', ''),
            filters.get('search_query', ''),
        )
        comment_rows = conn.execute(
            '''
            SELECT student_id, comment
            FROM rps_studentcommentrecord
            WHERE school_id = ? AND term_id = ? AND comment_type = ?
            ''',
            (school['id'], filters.get('selected_term_id') or 0, comment_type),
        ).fetchall()
        comment_map = {int(row['student_id']): row['comment'] for row in comment_rows}
        conn.close()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{comment_type}_comments.csv"'
        writer = csv.writer(response)
        writer.writerow(['Admission No.', 'Name', 'Comment'])
        for student in students:
            writer.writerow(
                [
                    student.get('admission_number') or '',
                    student.get('name') or '',
                    comment_map.get(int(student['id']), ''),
                ]
            )
        return response

    if request.method == 'POST':
        messages.info(request, 'Manual commenting is not enabled for the selected template.')
        redirect_url = _class_data_query_url(
            'accounts:school_class_comments',
            school['id'],
            filters,
            comment_type=comment_type,
        )
        conn.close()
        return redirect(redirect_url)

    conn.close()
    return render(
        request,
        'accounts/school_class_comments.html',
        {
            **_build_school_shell_context(school, active_key='class'),
            **filters,
            'rows': rows,
            'comment_type': comment_type,
            'comment_config': comment_config,
            'close_href': reverse('accounts:school_class_data', kwargs={'school_id': school['id']}),
        },
    )


def school_term_settings(request, school_id):
    """Minimal terminal settings page used by Registration > Term."""
    if not request.user.is_authenticated:
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
                'SELECT id FROM rms_academicsession WHERE id=? AND school_id=?',
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
                    'UPDATE rms_academicsession SET is_active=0 WHERE school_id=?',
                    (school['id'],),
                )
                conn.execute(
                    '''
                    INSERT INTO rms_academicsession (session_name, start_date, end_date, is_active, school_id)
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
                    'UPDATE rms_academicsession SET is_active=1 WHERE id=? AND school_id=?',
                    (session_id, school['id']),
                )
                conn.execute(
                    'UPDATE rms_academicsession SET is_active=0 WHERE school_id=? AND id<>?',
                    (school['id'], session_id),
                )

            conn.execute(
                '''
                UPDATE rms_term
                SET is_active = 0
                WHERE session_id IN (SELECT id FROM rms_academicsession WHERE school_id = ?)
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
                    FROM rms_term t
                    INNER JOIN rms_academicsession s ON s.id = t.session_id
                    WHERE t.id=? AND s.school_id=?
                    ''',
                    (selected_term_id, school['id']),
                ).fetchone()

            if existing_term:
                conn.execute(
                    '''
                    UPDATE rms_term
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
                    INSERT INTO rms_term (
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
    if not request.user.is_authenticated:
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
                INSERT INTO rms_teacher (
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
    if not request.user.is_authenticated:
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
        'template_name': RESULT_TEMPLATE_AUTO,
    }

    if request.method == 'POST':
        action = request.POST.get('action', 'add').strip() or 'add'
        panel_mode = action
        selected_class_id = request.POST.get('class_id', '').strip()
        class_name = request.POST.get('class_name', '').strip()
        class_teacher_name = request.POST.get('class_teacher_name', '').strip()
        promoting_class = request.POST.get('promoting_class', '').strip()
        repeating_class = request.POST.get('repeating_class', '').strip()
        template_name = normalize_template_name(request.POST.get('template_name'), allow_auto=True)

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
                    INSERT INTO rms_schoolclass (
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
                'SELECT id, name FROM rms_schoolclass WHERE id=? AND school_id=?',
                (selected_class_id, school['id']),
            ).fetchone()
            if not target:
                messages.error(request, 'That class could not be found.')
            elif not class_name:
                messages.error(request, 'Please, input the new class name.')
            else:
                conn.execute(
                    '''
                    UPDATE rms_schoolclass
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
                'SELECT id, name FROM rms_schoolclass WHERE id=? AND school_id=?',
                (selected_class_id, school['id']),
            ).fetchone()
            if not target:
                messages.error(request, 'That class could not be found.')
            else:
                student_count = conn.execute(
                    'SELECT COUNT(*) AS c FROM rms_student WHERE class_field_id=? AND school_id=?',
                    (selected_class_id, school['id']),
                ).fetchone()['c']
                if student_count:
                    messages.error(request, 'You cannot delete a class that already has students.')
                else:
                    conn.execute(
                        'DELETE FROM rms_schoolclass WHERE id=? AND school_id=?',
                        (selected_class_id, school['id']),
                    )
                    conn.commit()
                    messages.success(request, 'Class deleted successfully.')
                    conn.close()
                    return redirect(reverse('accounts:school_class_registration', kwargs={'school_id': school['id']}) + '?mode=add')

    classes = _fetch_school_classes(conn, school['id'])
    for class_item in classes:
        class_item['template_name'] = normalize_template_name(
            class_item.get('template_name'),
            allow_auto=True,
        )
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
            'template_name': normalize_template_name(selected_class.get('template_name'), allow_auto=True),
        }

    template_options = list_result_template_choices(school['id'])
    if class_form.get('template_name') and class_form['template_name'] not in template_options:
        template_options.append(class_form['template_name'])

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
            'template_options': template_options,
        },
    )


def school_students(request, school_id):
    """Students list plus the Gestio-style student registration popup."""
    if not request.user.is_authenticated:
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
                    INSERT INTO rms_student (
                        admission_number, first_name, last_name, middle_name,
                        date_of_birth, gender, parent_name, parent_phone, is_active,
                        class_field_id, school_id, image,
                        email, address, date_of_admission, state_of_origin, local_government
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, '', '')
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
    if not request.user.is_authenticated:
        return redirect('accounts:login')

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
