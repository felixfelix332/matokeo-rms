import json
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils.text import slugify

from accounts.backends import (
    get_teacher_from_session,
    get_teacher_assigned_classes,
    get_teacher_assigned_subjects,
)
from .models import (
    AcademicSession,
    AttendanceEntry,
    ResultSheet,
    School,
    SchoolClass,
    Score,
    Student,
    Subject,
    Term,
)
from .marks_helpers import (
    get_scheme_for_term,
    get_subjects_for_class,
    get_students_for_class,
    get_scores_for_entry,
    get_terms_for_school,
    save_scores,
    compute_grade,
)


def _db():
    return str(settings.DATABASES['school_data']['NAME'])


def _get_school_id(request):
    """Get school_id from session. Falls back to 5 for Joyland."""
    return request.session.get('school_id', 5)


def teacher_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        teacher = get_teacher_from_session(request.session)
        if not teacher:
            return redirect('accounts:teacher_login')
        if not request.session.get('school_id'):
            return redirect('accounts:add_school')
        request.teacher = teacher
        request.school_id = _get_school_id(request)
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_active_term(school_id):
    return Term.objects.using('school_data').filter(
        session__school_id=school_id, is_active=True
    ).select_related('session').first()


AFFECTIVE_TRAITS = [
    'Attentiveness',
    'Attitude of Subject',
    'Cooperation',
    'Emotion Stability',
    'Health',
]

PSYCHOMOTOR_SKILLS = [
    'Handwriting',
    'Verbal Fluency',
    'Sports',
    'Drawing',
    'Music',
]

AVAILABLE_PERMISSIONS = [
    'Settings',
    'Generate Reports',
    'Registration',
    'Class Data',
    'Template Editor',
]

TEACHER_EXTRA_COLUMNS = {
    'first_name': "varchar(100) DEFAULT ''",
    'last_name': "varchar(100) DEFAULT ''",
    'date_of_birth': 'date',
    'gender': "varchar(20) DEFAULT ''",
    'phone': "varchar(30) DEFAULT ''",
    'email': "varchar(254) DEFAULT ''",
    'address': "TEXT DEFAULT ''",
    'qualifications': "varchar(255) DEFAULT ''",
    'experience': "varchar(120) DEFAULT ''",
}

BRANDING_EXTRA_COLUMNS = {
    'headteacher_name': "varchar(255) DEFAULT ''",
    'director_name': "varchar(255) DEFAULT ''",
    'stamp': "varchar(100) DEFAULT ''",
}

USER_ROLE_EXTRA_COLUMNS = {
    'permissions': "TEXT DEFAULT ''",
}


def _connect_school_db():
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table_name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _column_exists(conn, table_name, column_name):
    return any(
        row[1] == column_name
        for row in conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    )


def _ensure_columns(conn, table_name, column_map):
    if not _table_exists(conn, table_name):
        return
    for column_name, column_def in column_map.items():
        if not _column_exists(conn, table_name, column_name):
            conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}')


def _ensure_teacher_tables(conn):
    if not _table_exists(conn, 'teacher_teacheruser'):
        conn.execute('''
            CREATE TABLE teacher_teacheruser (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username varchar(150) NOT NULL UNIQUE,
                password_hash varchar(255) NOT NULL,
                full_name varchar(200) NOT NULL,
                is_active bool NOT NULL DEFAULT 1,
                created_at datetime NOT NULL,
                is_class_teacher_of_id bigint NULL,
                first_name varchar(100) DEFAULT '',
                last_name varchar(100) DEFAULT '',
                date_of_birth date,
                gender varchar(20) DEFAULT '',
                phone varchar(30) DEFAULT '',
                email varchar(254) DEFAULT '',
                address TEXT DEFAULT '',
                qualifications varchar(255) DEFAULT '',
                experience varchar(120) DEFAULT ''
            )
        ''')
    if not _table_exists(conn, 'teacher_teacheruser_assigned_classes'):
        conn.execute('''
            CREATE TABLE teacher_teacheruser_assigned_classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacheruser_id bigint NOT NULL,
                schoolclass_id bigint NOT NULL
            )
        ''')
        conn.execute('''
            CREATE UNIQUE INDEX teacher_teacheruser_assigned_classes_teacheruser_class_idx
            ON teacher_teacheruser_assigned_classes (teacheruser_id, schoolclass_id)
        ''')
    if not _table_exists(conn, 'teacher_teacheruser_assigned_subjects'):
        conn.execute('''
            CREATE TABLE teacher_teacheruser_assigned_subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacheruser_id bigint NOT NULL,
                subject_id bigint NOT NULL
            )
        ''')
        conn.execute('''
            CREATE UNIQUE INDEX teacher_teacheruser_assigned_subjects_teacheruser_subject_idx
            ON teacher_teacheruser_assigned_subjects (teacheruser_id, subject_id)
        ''')
    _ensure_columns(conn, 'teacher_teacheruser', TEACHER_EXTRA_COLUMNS)


def _ensure_attribute_tables(conn):
    if not _table_exists(conn, 'rps_studentattribute'):
        conn.execute('''
            CREATE TABLE rps_studentattribute (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                term_id INTEGER NOT NULL,
                school_id INTEGER NOT NULL,
                attribute_type TEXT NOT NULL,
                attribute_name TEXT NOT NULL,
                rating INTEGER,
                UNIQUE(student_id, term_id, attribute_name)
            )
        ''')
    if not _table_exists(conn, 'rps_studentcommentrecord'):
        conn.execute('''
            CREATE TABLE rps_studentcommentrecord (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment_type varchar(20) NOT NULL,
                comment TEXT NOT NULL,
                created_at datetime NOT NULL,
                updated_at datetime NOT NULL,
                school_id bigint NOT NULL,
                student_id bigint NOT NULL,
                term_id bigint NOT NULL,
                updated_by_id integer NULL
            )
        ''')


def _ensure_branding_schema(conn):
    if _table_exists(conn, 'rps_schoolbranding'):
        _ensure_columns(conn, 'rps_schoolbranding', BRANDING_EXTRA_COLUMNS)


def _ensure_user_role_schema(conn):
    if not _table_exists(conn, 'rps_userrole'):
        conn.execute('''
            CREATE TABLE rps_userrole (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role varchar(20) NOT NULL,
                is_active bool NOT NULL DEFAULT 1,
                created_at datetime NOT NULL,
                updated_at datetime NOT NULL,
                user_id integer NOT NULL UNIQUE,
                require_password_change bool NOT NULL DEFAULT 0,
                permissions TEXT DEFAULT ''
            )
        ''')
    else:
        _ensure_columns(conn, 'rps_userrole', USER_ROLE_EXTRA_COLUMNS)


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()
    if ' ' in text:
        text = text.split(' ', 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _term_duration_days(start_value, end_value):
    start_date = _parse_date(start_value)
    end_date = _parse_date(end_value)
    if not start_date or not end_date:
        return None
    return max((end_date - start_date).days, 0)


def _count_school_days(start_value, end_value, work_days='1,2,3,4,5'):
    start_date = _parse_date(start_value)
    end_date = _parse_date(end_value)
    if not start_date or not end_date or end_date < start_date:
        return 0
    open_days = {
        int(part)
        for part in str(work_days).split(',')
        if part.strip().isdigit()
    }
    current = start_date
    count = 0
    while current <= end_date:
        if current.isoweekday() in open_days:
            count += 1
        current += timedelta(days=1)
    return count


def _build_term_ranges(start_value, end_value):
    session_start = _parse_date(start_value)
    session_end = _parse_date(end_value)
    if not session_start or not session_end:
        return []
    if session_end < session_start:
        session_end = session_start

    total_days = max((session_end - session_start).days + 1, 1)
    base_days, extra_days = divmod(total_days, 3)
    ranges = []
    current_start = session_start

    for index in range(3):
        span = base_days + (1 if index < extra_days else 0)
        term_end = current_start + timedelta(days=max(span - 1, 0))
        ranges.append({
            'term': str(index + 1),
            'start_date': current_start,
            'end_date': term_end,
        })
        current_start = term_end + timedelta(days=1)

    for index, term_info in enumerate(ranges):
        term_info['school_days'] = _count_school_days(
            term_info['start_date'],
            term_info['end_date'],
        )
        term_info['next_term_begins'] = (
            ranges[index + 1]['start_date']
            if index < len(ranges) - 1
            else None
        )
    return ranges


def _redirect_with_query(view_name, **params):
    url = reverse(view_name)
    query = urlencode({
        key: value
        for key, value in params.items()
        if value not in (None, '')
    })
    if query:
        url = f'{url}?{query}'
    return redirect(url)


def _split_full_name(full_name):
    parts = [part for part in str(full_name or '').split() if part]
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


def _serialize_teacher_row(row):
    data = dict(row)
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    if not first_name and not last_name:
        first_name, last_name = _split_full_name(data.get('full_name'))
    full_name = ' '.join(part for part in [first_name, last_name] if part).strip()
    if not full_name:
        full_name = (data.get('full_name') or '').strip()
    data['first_name'] = first_name
    data['last_name'] = last_name
    data['full_name'] = full_name
    data['date_of_birth'] = _parse_date(data.get('date_of_birth'))
    data['gender'] = data.get('gender') or ''
    data['phone'] = data.get('phone') or ''
    data['email'] = data.get('email') or ''
    data['address'] = data.get('address') or ''
    data['qualifications'] = data.get('qualifications') or ''
    data['experience'] = data.get('experience') or ''
    data['assigned_classes'] = data.get('assigned_classes') or ''
    return data


def _get_teacher_rows(conn, school_id):
    _ensure_teacher_tables(conn)
    rows = conn.execute('''
        SELECT t.*,
               GROUP_CONCAT(sc.name, ', ') AS assigned_classes
        FROM teacher_teacheruser t
        LEFT JOIN teacher_teacheruser_assigned_classes tac
            ON tac.teacheruser_id = t.id
        LEFT JOIN portal_schoolclass sc
            ON sc.id = tac.schoolclass_id AND sc.school_id = ?
        GROUP BY t.id
        ORDER BY COALESCE(NULLIF(t.first_name, ''), t.full_name), COALESCE(NULLIF(t.last_name, ''), '')
    ''', (school_id,)).fetchall()
    return [_serialize_teacher_row(row) for row in rows]


def _get_teacher_row(conn, teacher_id):
    _ensure_teacher_tables(conn)
    row = conn.execute('SELECT * FROM teacher_teacheruser WHERE id=?', (teacher_id,)).fetchone()
    if not row:
        return None
    return _serialize_teacher_row(row)


def _get_teacher_assigned_class_ids(conn, teacher_id):
    rows = conn.execute(
        'SELECT schoolclass_id FROM teacher_teacheruser_assigned_classes WHERE teacheruser_id=?',
        (teacher_id,),
    ).fetchall()
    return [row[0] for row in rows]


def _unique_teacher_username(conn, base_text):
    base_username = slugify(base_text or 'teacher').replace('-', '')
    base_username = (base_username or 'teacher')[:40]
    candidate = base_username
    suffix = 1
    while conn.execute(
        'SELECT 1 FROM teacher_teacheruser WHERE username=?',
        (candidate,),
    ).fetchone():
        candidate = f'{base_username}{suffix}'
        suffix += 1
    return candidate


def _subject_options_for_class(conn, school_id, selected_class=''):
    if selected_class and _table_exists(conn, 'rps_classsubjectallocation'):
        rows = conn.execute('''
            SELECT DISTINCT s.id, s.name
            FROM portal_subject s
            JOIN rps_classsubjectallocation csa ON csa.subject_id = s.id
            WHERE s.school_id = ? AND csa.school_class_id = ?
            ORDER BY COALESCE(csa.display_order, 9999), s.name
        ''', (school_id, int(selected_class))).fetchall()
    else:
        rows = conn.execute(
            'SELECT id, name FROM portal_subject WHERE school_id=? ORDER BY name',
            (school_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _get_default_comment_template(conn, school_id, comment_type):
    return ''


def _attach_term_settings(term, conn):
    if not term:
        return None
    if _table_exists(conn, 'rps_term'):
        row = conn.execute(
            'SELECT school_opens_count, next_term_begins FROM rps_term WHERE id=?',
            (term.id,),
        ).fetchone()
    else:
        row = None
    term.school_days = row['school_opens_count'] if row else ''
    term.next_term_begins = _parse_date(row['next_term_begins']) if row else None
    return term


def _media_url(relative_path):
    if not relative_path:
        return ''
    normalized = str(relative_path).replace('\\', '/')
    if normalized.startswith(('http://', 'https://', '/')):
        return normalized
    return f"{settings.MEDIA_URL.rstrip('/')}/{normalized.lstrip('/')}"


def _save_uploaded_media(uploaded_file, folder_name):
    target_dir = Path(settings.MEDIA_ROOT) / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(Path(uploaded_file.name).stem) or 'asset'
    suffix = Path(uploaded_file.name).suffix.lower()
    filename = f'{stem}-{datetime.now().strftime("%Y%m%d%H%M%S%f")}{suffix}'
    destination = target_dir / filename
    with destination.open('wb+') as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)
    return str(Path(folder_name) / filename).replace('\\', '/')


def _ensure_branding_row(conn, school, school_id):
    _ensure_branding_schema(conn)
    row = conn.execute(
        'SELECT * FROM rps_schoolbranding WHERE school_id=?',
        (school_id,),
    ).fetchone()
    if row:
        return dict(row)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        INSERT INTO rps_schoolbranding (
            display_name, system_name, tagline, logo, favicon,
            primary_color, secondary_color, accent_color, success_color,
            warning_color, danger_color, show_powered_by, show_vendor_contact,
            custom_domain, allow_user_customization, created_at, updated_at,
            school_id, background_image, background_opacity, background_pattern,
            branding_preview_enabled, css_version, custom_css, font_family,
            font_url, logo_cropped, logo_position_x, logo_position_y,
            footer_text, secondary_logo
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        school.name,
        'School Results System',
        '',
        '',
        '',
        '#1f894d',
        '#2a5fa8',
        '#ff6b6b',
        '#27ae60',
        '#f39c12',
        '#e74c3c',
        0,
        0,
        None,
        1,
        now,
        now,
        school_id,
        '',
        100,
        'none',
        0,
        0,
        '',
        'Segoe UI',
        None,
        '',
        0,
        0,
        '(c) {year} {school_name}. Your Results Management System.',
        '',
    ))
    row = conn.execute(
        'SELECT * FROM rps_schoolbranding WHERE school_id=?',
        (school_id,),
    ).fetchone()
    return dict(row) if row else {}


@teacher_required
def teacher_dashboard(request):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    assigned_subjects = get_teacher_assigned_subjects(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]

    total_students = Student.objects.using('school_data').filter(
        school_id=school_id, class_field_id__in=class_ids, is_active=True
    ).count()

    active_term = _get_active_term(school_id)

    class_performance = []
    if active_term:
        for c in assigned_classes:
            avg = Score.objects.using('school_data').filter(
                term=active_term,
                student__class_field_id=c['schoolclass_id'],
                total_score__isnull=False,
            ).aggregate(avg=Avg('total_score'))['avg']
            if avg is not None:
                class_performance.append({'name': c['name'], 'avg': round(float(avg), 1)})

    top_results = []
    if active_term:
        top_results = list(
            ResultSheet.objects.using('school_data').filter(
                term=active_term,
                student__class_field_id__in=class_ids,
            ).select_related('student', 'student__class_field').order_by('position')[:10]
        )

    context = {
        'teacher': teacher,
        'assigned_classes': assigned_classes,
        'assigned_subjects': assigned_subjects,
        'total_students': total_students,
        'total_classes': len(assigned_classes),
        'total_subjects': len(assigned_subjects),
        'active_term': active_term,
        'class_performance': json.dumps(class_performance),
        'top_results': top_results,
        'active_page': 'teacher_dashboard',
    }
    return render(request, 'portal/teacher/dashboard.html', context)


@teacher_required
def teacher_class_students(request, class_id):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]

    if class_id not in class_ids:
        return redirect('portal:teacher_dashboard')

    school_class = SchoolClass.objects.using('school_data').get(id=class_id)
    students = Student.objects.using('school_data').filter(
        school_id=school_id, class_field_id=class_id, is_active=True
    ).order_by('first_name', 'last_name')

    active_term = _get_active_term(school_id)

    student_data = []
    for s in students:
        result = None
        if active_term:
            result = ResultSheet.objects.using('school_data').filter(
                student=s, term=active_term
            ).first()
        student_data.append({'student': s, 'result': result})

    context = {
        'teacher': teacher,
        'school_class': school_class,
        'student_data': student_data,
        'active_term': active_term,
        'assigned_classes': assigned_classes,
        'active_page': 'teacher_classes',
    }
    return render(request, 'portal/teacher/class_students.html', context)


@teacher_required
def teacher_scores(request):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    assigned_subjects = get_teacher_assigned_subjects(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]

    active_term = _get_active_term(school_id)
    class_id = request.GET.get('class', '')
    subject_id = request.GET.get('subject', '')

    scores = Score.objects.using('school_data').filter(
        student__school_id=school_id,
        student__class_field_id__in=class_ids,
    ).select_related('student', 'student__class_field', 'subject', 'term', 'term__session')

    if active_term:
        scores = scores.filter(term=active_term)
    if class_id:
        scores = scores.filter(student__class_field_id=class_id)
    if subject_id:
        scores = scores.filter(subject_id=subject_id)

    scores = scores.order_by('student__class_field__name', 'student__first_name', 'subject__name')

    context = {
        'teacher': teacher,
        'scores': scores[:500],
        'assigned_classes': assigned_classes,
        'assigned_subjects': assigned_subjects,
        'class_id': class_id,
        'subject_id': subject_id,
        'active_term': active_term,
        'total_count': scores.count(),
        'active_page': 'teacher_scores',
    }
    return render(request, 'portal/teacher/scores.html', context)


@teacher_required
def marks_entry_menu(request):
    """Marks entry menu: select class, subject, term."""
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    terms = get_terms_for_school(school_id)

    # When class is selected, load subjects for that class
    selected_class = request.GET.get('class', '')
    class_subjects = []
    if selected_class:
        all_subjects = get_subjects_for_class(int(selected_class), school_id)
        assigned_subj_ids = {s['subject_id'] for s in get_teacher_assigned_subjects(teacher.id, school_id)}
        class_subjects = [s for s in all_subjects if s['subject_id'] in assigned_subj_ids]

    context = {
        'teacher': teacher,
        'assigned_classes': assigned_classes,
        'terms': terms,
        'class_subjects': class_subjects,
        'selected_class': selected_class,
        'selected_subject': request.GET.get('subject', ''),
        'selected_term': request.GET.get('term', ''),
        'active_page': 'teacher_marks',
    }
    return render(request, 'portal/teacher/marks_menu.html', context)


@teacher_required
def marks_entry_sheet(request):
    """The actual broadsheet for entering/editing marks."""
    school_id = _get_school_id(request)
    teacher = request.teacher
    class_id = request.GET.get('class') or request.POST.get('class')
    subject_id = request.GET.get('subject') or request.POST.get('subject')
    term_id = request.GET.get('term') or request.POST.get('term')

    if not all([class_id, subject_id, term_id]):
        return redirect('portal:marks_menu')

    class_id = int(class_id)
    subject_id = int(subject_id)
    term_id = int(term_id)

    # Verify teacher has access to this class
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]
    if class_id not in class_ids:
        return redirect('portal:marks_menu')

    # Get scheme + components for this term
    scheme, components = get_scheme_for_term(term_id)
    if not scheme:
        messages.error(request, 'No assessment scheme configured for this term.')
        return redirect('portal:marks_menu')

    # Get students and existing scores
    students = get_students_for_class(class_id, school_id)
    existing_scores = get_scores_for_entry(term_id, class_id, subject_id, school_id)

    # Get class and subject names
    school_class = SchoolClass.objects.using('school_data').get(id=class_id)
    subject = Subject.objects.using('school_data').get(id=subject_id)
    term = Term.objects.using('school_data').filter(id=term_id).select_related('session').first()

    # Handle POST: save marks
    saved = False
    if request.method == 'POST':
        student_marks = {}
        for student in students:
            sid = str(student['id'])
            comp_values = {}
            for comp in components:
                field_name = f'score_{sid}_{comp["id"]}'
                val = request.POST.get(field_name, '').strip()
                if val:
                    comp_values[str(comp['id'])] = val
            if comp_values:
                student_marks[sid] = comp_values

        if student_marks:
            save_scores(term_id, subject_id, class_id, components, student_marks, school_id)
            messages.success(request, f'Scores saved successfully for {len(student_marks)} students.')
            saved = True
            # Refresh existing scores
            existing_scores = get_scores_for_entry(term_id, class_id, subject_id, school_id)

    # Build rows for template — each row gets a flat list of component values
    # aligned with the components list, so template can zip them
    rows = []
    for student in students:
        sid = student['id']
        score_data = existing_scores.get(sid, {})
        comp_parsed = score_data.get('_components', {})
        # Build list of (comp, value) tuples for easy template iteration
        comp_entries = []
        for comp in components:
            key = f'component_{comp["id"]}'
            val = comp_parsed.get(key, '')
            comp_entries.append({
                'comp': comp,
                'value': val if val != '' else '',
                'has_value': val != '' and val is not None,
            })
        grade = score_data.get('grade', '')
        _, points = compute_grade(score_data.get('total_score')) if score_data.get('total_score') else ('', 0)
        rows.append({
            'student': student,
            'total_score': score_data.get('total_score', ''),
            'grade': grade,
            'points': points if points else '',
            'comp_entries': comp_entries,
        })

    context = {
        'teacher': teacher,
        'school_class': school_class,
        'subject': subject,
        'term': term,
        'scheme': scheme,
        'components': components,
        'rows': rows,
        'class_id': class_id,
        'subject_id': subject_id,
        'term_id': term_id,
        'saved': saved,
        'active_page': 'teacher_marks',
    }
    return render(request, 'portal/teacher/marks_sheet.html', context)


# ── ATTENDANCE ──────────────────────────────────────────────────────────────────

@teacher_required
def teacher_attendance(request):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]
    active_term = _get_active_term(school_id)

    selected_class = request.GET.get('class', '')
    selected_date = request.GET.get('date', str(date.today()))

    students = []
    school_class = None
    attendance_data = {}

    if selected_class and int(selected_class) in class_ids:
        class_id = int(selected_class)
        school_class = SchoolClass.objects.using('school_data').get(id=class_id)
        students = Student.objects.using('school_data').filter(
            school_id=school_id, class_field_id=class_id, is_active=True
        ).order_by('first_name', 'last_name')

        # Get existing attendance for selected date
        entries = AttendanceEntry.objects.using('school_data').filter(
            student__class_field_id=class_id,
            date=selected_date,
        )
        for e in entries:
            attendance_data[e.student_id] = e.status

    # Handle POST: save attendance
    if request.method == 'POST' and selected_class and active_term:
        class_id = int(selected_class)
        att_date = request.POST.get('date', selected_date)
        conn = sqlite3.connect(_db())
        for s in students:
            status = request.POST.get(f'status_{s.id}', '')
            if status in ('P', 'A', 'L'):
                existing = conn.execute(
                    'SELECT id FROM portal_attendanceentry WHERE student_id=? AND date=?',
                    (s.id, att_date)
                ).fetchone()
                if existing:
                    conn.execute(
                        'UPDATE portal_attendanceentry SET status=? WHERE id=?',
                        (status, existing[0])
                    )
                else:
                    conn.execute(
                        'INSERT INTO portal_attendanceentry (student_id, term_id, date, status, remark) VALUES (?,?,?,?,?)',
                        (s.id, active_term.id, att_date, status, '')
                    )
        conn.commit()

        # Update rps_attendance summary
        for s in students:
            present = conn.execute(
                'SELECT COUNT(*) FROM portal_attendanceentry WHERE student_id=? AND term_id=? AND status=?',
                (s.id, active_term.id, 'P')
            ).fetchone()[0]
            absent = conn.execute(
                'SELECT COUNT(*) FROM portal_attendanceentry WHERE student_id=? AND term_id=? AND status=?',
                (s.id, active_term.id, 'A')
            ).fetchone()[0]
            late = conn.execute(
                'SELECT COUNT(*) FROM portal_attendanceentry WHERE student_id=? AND term_id=? AND status=?',
                (s.id, active_term.id, 'L')
            ).fetchone()[0]
            total = present + absent + late
            existing_sum = conn.execute(
                'SELECT id FROM rps_attendance WHERE student_id=? AND term_id=?',
                (s.id, active_term.id)
            ).fetchone()
            if existing_sum:
                conn.execute(
                    'UPDATE rps_attendance SET present=?, absent=?, late=?, total_school_days=?, updated_at=? WHERE id=?',
                    (present, absent, late, total, datetime.now().isoformat(), existing_sum[0])
                )
            else:
                conn.execute(
                    'INSERT INTO rps_attendance (present, absent, late, total_school_days, created_at, updated_at, student_id, term_id) VALUES (?,?,?,?,?,?,?,?)',
                    (present, absent, late, total, datetime.now().isoformat(), datetime.now().isoformat(), s.id, active_term.id)
                )
        conn.commit()
        conn.close()

        messages.success(request, f'Attendance saved for {att_date}.')
        # Refresh
        entries = AttendanceEntry.objects.using('school_data').filter(
            student__class_field_id=int(selected_class), date=att_date,
        )
        attendance_data = {e.student_id: e.status for e in entries}

    # Attendance summary for the term
    summary = {}
    if selected_class and active_term:
        conn = sqlite3.connect(_db())
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''
            SELECT student_id, present, absent, late, total_school_days
            FROM rps_attendance WHERE term_id=? AND student_id IN (
                SELECT id FROM portal_student WHERE class_field_id=? AND is_active=1
            )
        ''', (active_term.id, int(selected_class))).fetchall()
        conn.close()
        for r in rows:
            summary[r['student_id']] = dict(r)

    context = {
        'teacher': teacher,
        'assigned_classes': assigned_classes,
        'selected_class': selected_class,
        'selected_date': selected_date,
        'school_class': school_class,
        'students': students,
        'attendance_data': attendance_data,
        'summary': summary,
        'active_term': active_term,
        'active_page': 'teacher_attendance',
    }
    return render(request, 'portal/teacher/attendance.html', context)


# ── CLASS LIST CRUD ─────────────────────────────────────────────────────────────

@teacher_required
def teacher_class_list(request):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]

    selected_class = request.GET.get('class', '')
    students = []
    school_class = None
    search = request.GET.get('q', '')

    if selected_class and int(selected_class) in class_ids:
        class_id = int(selected_class)
        school_class = SchoolClass.objects.using('school_data').get(id=class_id)
        qs = Student.objects.using('school_data').filter(
            school_id=school_id, class_field_id=class_id
        )
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(admission_number__icontains=search)
            )
        students = qs.order_by('first_name', 'last_name')

    context = {
        'teacher': teacher,
        'assigned_classes': assigned_classes,
        'selected_class': selected_class,
        'school_class': school_class,
        'students': students,
        'search': search,
        'active_page': 'teacher_class_list',
    }
    return render(request, 'portal/teacher/class_list.html', context)


@teacher_required
def teacher_student_add(request):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]

    if request.method == 'POST':
        class_id = int(request.POST.get('class_id', 0))
        if class_id not in class_ids:
            messages.error(request, 'Invalid class.')
            return redirect('portal:teacher_class_list')

        conn = sqlite3.connect(_db())
        conn.execute('''
            INSERT INTO portal_student
            (admission_number, first_name, last_name, middle_name, date_of_birth, gender,
             parent_name, parent_phone, is_active, portal_access_enabled, class_field_id, school_id, image)
            VALUES (?,?,?,?,?,?,?,?,1,0,?,?,?)
        ''', (
            request.POST.get('admission_number', '').strip(),
            request.POST.get('first_name', '').strip().upper(),
            request.POST.get('last_name', '').strip().upper(),
            request.POST.get('middle_name', '').strip().upper(),
            request.POST.get('date_of_birth', '') or None,
            request.POST.get('gender', 'M'),
            request.POST.get('parent_name', '').strip(),
            request.POST.get('parent_phone', '').strip(),
            class_id, school_id, ''
        ))
        conn.commit()
        conn.close()
        messages.success(request, 'Student added successfully.')
        return redirect(f'/teacher/class-list/?class={class_id}')

    context = {
        'teacher': teacher,
        'assigned_classes': assigned_classes,
        'active_page': 'teacher_class_list',
    }
    return render(request, 'portal/teacher/student_form.html', context)


@teacher_required
def teacher_student_edit(request, student_id):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]

    student = Student.objects.using('school_data').get(id=student_id)
    if student.class_field_id not in class_ids:
        return redirect('portal:teacher_class_list')

    if request.method == 'POST':
        conn = sqlite3.connect(_db())
        conn.execute('''
            UPDATE portal_student SET
            admission_number=?, first_name=?, last_name=?, middle_name=?,
            date_of_birth=?, gender=?, parent_name=?, parent_phone=?,
            is_active=?, class_field_id=?
            WHERE id=?
        ''', (
            request.POST.get('admission_number', '').strip(),
            request.POST.get('first_name', '').strip().upper(),
            request.POST.get('last_name', '').strip().upper(),
            request.POST.get('middle_name', '').strip().upper(),
            request.POST.get('date_of_birth', '') or None,
            request.POST.get('gender', 'M'),
            request.POST.get('parent_name', '').strip(),
            request.POST.get('parent_phone', '').strip(),
            1 if request.POST.get('is_active') else 0,
            int(request.POST.get('class_id', student.class_field_id)),
            student_id
        ))
        conn.commit()
        conn.close()
        messages.success(request, 'Student updated.')
        return redirect(f'/teacher/class-list/?class={student.class_field_id}')

    context = {
        'teacher': teacher,
        'student': student,
        'assigned_classes': assigned_classes,
        'active_page': 'teacher_class_list',
    }
    return render(request, 'portal/teacher/student_form.html', context)


@teacher_required
def teacher_student_delete(request, student_id):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]

    student = Student.objects.using('school_data').get(id=student_id)
    if student.class_field_id not in class_ids:
        return redirect('portal:teacher_class_list')

    if request.method == 'POST':
        class_id = student.class_field_id
        conn = sqlite3.connect(_db())
        conn.execute('UPDATE portal_student SET is_active=0 WHERE id=?', (student_id,))
        conn.commit()
        conn.close()
        messages.success(request, f'{student.full_name} deactivated.')
        return redirect(f'/teacher/class-list/?class={class_id}')

    return redirect('portal:teacher_class_list')


# ── REMARKS ─────────────────────────────────────────────────────────────────────

CBC_REMARKS = {
    'EE1': 'Excellent work! Exceeding expectations consistently.',
    'EE2': 'Very good performance. Exceeding expectations.',
    'ME1': 'Good effort. Meeting expectations well.',
    'ME2': 'Satisfactory. Meeting expectations.',
    'AE1': 'Fair. Approaching expectations, needs more effort.',
    'AE2': 'Below average. Approaching expectations, needs improvement.',
    'BE1': 'Needs significant improvement.',
    'BE2': 'Very weak performance. Requires urgent intervention.',
}

CBC_TEACHER_COMMENTS = [
    (80, 100, 'An outstanding learner who consistently exceeds expectations. Keep it up!'),
    (70, 79, 'A very good learner showing great potential. Continue working hard.'),
    (60, 69, 'Good performance. With more effort, can achieve even better results.'),
    (50, 59, 'Satisfactory work but needs to put in more effort to improve.'),
    (40, 49, 'Fair performance. Needs to be more attentive and put in extra work.'),
    (30, 39, 'Below average. Requires close supervision and remedial support.'),
    (0, 29, 'Needs urgent intervention. Parent-teacher consultation recommended.'),
]

CBC_PROMOTION = [
    (60, 100, 'PROMOTED TO {next_class}. CONGRATULATIONS!'),
    (40, 59, 'PROMOTED ON TRIAL TO {next_class}.'),
    (0, 39, 'YOU ARE ADVISED TO REPEAT.'),
]


def _auto_remark(grade):
    return CBC_REMARKS.get(grade, '')


def _auto_teacher_comment(avg_score):
    if avg_score is None:
        return ''
    s = float(avg_score)
    for low, high, comment in CBC_TEACHER_COMMENTS:
        if low <= s <= high:
            return comment
    return ''


@teacher_required
def teacher_remarks(request):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]
    active_term = _get_active_term(school_id)

    selected_class = request.GET.get('class', '')
    students_data = []
    school_class = None

    if selected_class and int(selected_class) in class_ids and active_term:
        class_id = int(selected_class)
        school_class = SchoolClass.objects.using('school_data').get(id=class_id)
        students = Student.objects.using('school_data').filter(
            school_id=school_id, class_field_id=class_id, is_active=True
        ).order_by('first_name', 'last_name')

        # Get existing comments
        conn = sqlite3.connect(_db())
        conn.row_factory = sqlite3.Row
        comments = {}
        rows = conn.execute(
            'SELECT student_id, comment_type, comment FROM rps_studentcommentrecord WHERE term_id=? AND school_id=?',
            (active_term.id, school_id)
        ).fetchall()
        for r in rows:
            comments[(r['student_id'], r['comment_type'])] = r['comment']

        for s in students:
            # Get average score
            result = ResultSheet.objects.using('school_data').filter(
                student=s, term=active_term
            ).first()
            avg = float(result.average_score) if result else None

            students_data.append({
                'student': s,
                'avg': avg,
                'auto_comment': _auto_teacher_comment(avg),
                'teacher_comment': comments.get((s.id, 'teacher'), ''),
                'head_comment': comments.get((s.id, 'headteacher'), ''),
            })
        conn.close()

    # Handle POST: save comments
    if request.method == 'POST' and selected_class and active_term:
        conn = sqlite3.connect(_db())
        class_id = int(selected_class)
        students = Student.objects.using('school_data').filter(
            school_id=school_id, class_field_id=class_id, is_active=True
        )
        for s in students:
            for ctype in ('teacher', 'headteacher'):
                comment = request.POST.get(f'{ctype}_{s.id}', '').strip()
                if comment:
                    existing = conn.execute(
                        'SELECT id FROM rps_studentcommentrecord WHERE student_id=? AND term_id=? AND comment_type=?',
                        (s.id, active_term.id, ctype)
                    ).fetchone()
                    if existing:
                        conn.execute(
                            'UPDATE rps_studentcommentrecord SET comment=?, updated_at=? WHERE id=?',
                            (comment, datetime.now().isoformat(), existing[0])
                        )
                    else:
                        conn.execute(
                            'INSERT INTO rps_studentcommentrecord (comment_type, comment, created_at, updated_at, school_id, student_id, term_id, updated_by_id) VALUES (?,?,?,?,?,?,?,NULL)',
                            (ctype, comment, datetime.now().isoformat(), datetime.now().isoformat(), school_id, s.id, active_term.id)
                        )
        conn.commit()
        conn.close()
        messages.success(request, 'Comments saved.')
        return redirect(f'/teacher/remarks/?class={selected_class}')

    context = {
        'teacher': teacher,
        'assigned_classes': assigned_classes,
        'selected_class': selected_class,
        'school_class': school_class,
        'students_data': students_data,
        'active_term': active_term,
        'active_page': 'teacher_remarks',
    }
    return render(request, 'portal/teacher/remarks.html', context)


# ── REPORT CARDS / RESULT SHEETS ────────────────────────────────────────────────

@teacher_required
def teacher_results(request):
    """Report card generation and viewing."""
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]
    terms = get_terms_for_school(school_id)
    active_term = _get_active_term(school_id)

    selected_class = request.GET.get('class', '')
    selected_term = request.GET.get('term', str(active_term.id) if active_term else '')

    results = []
    school_class = None

    if selected_class and int(selected_class) in class_ids and selected_term:
        class_id = int(selected_class)
        term_id = int(selected_term)
        school_class = SchoolClass.objects.using('school_data').get(id=class_id)

        results = ResultSheet.objects.using('school_data').filter(
            student__class_field_id=class_id,
            term_id=term_id,
            student__is_active=True,
        ).select_related('student', 'term', 'term__session').order_by('position')

    context = {
        'teacher': teacher,
        'assigned_classes': assigned_classes,
        'terms': terms,
        'selected_class': selected_class,
        'selected_term': selected_term,
        'school_class': school_class,
        'results': results,
        'active_term': active_term,
        'active_page': 'teacher_results',
    }
    return render(request, 'portal/teacher/results.html', context)


@teacher_required
def teacher_report_card(request, student_id):
    """Generate individual CBC report card matching Gestio structure."""
    school_id = _get_school_id(request)
    teacher = request.teacher
    term_id = request.GET.get('term', '')
    if not term_id:
        active_term = _get_active_term(school_id)
        term_id = active_term.id if active_term else None

    if not term_id:
        return redirect('portal:teacher_results')

    term_id = int(term_id)
    student = Student.objects.using('school_data').select_related('class_field').get(id=student_id)
    term = Term.objects.using('school_data').select_related('session').get(id=term_id)

    # Get school info
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    school = dict(conn.execute('SELECT * FROM portal_school WHERE id=?', (school_id,)).fetchone())
    branding = conn.execute('SELECT * FROM rps_schoolbranding WHERE school_id=?', (school_id,)).fetchone()
    if branding:
        branding = dict(branding)

    # Get scores for this student + term
    scores = conn.execute('''
        SELECT ps.total_score, ps.grade, ps.component_scores, ps.subject_id,
               sub.name as subject_name
        FROM portal_score ps
        JOIN portal_subject sub ON sub.id = ps.subject_id
        WHERE ps.student_id=? AND ps.term_id=?
        ORDER BY sub.name
    ''', (student_id, term_id)).fetchall()
    scores = [dict(s) for s in scores]

    # Get scheme components
    scheme, components = get_scheme_for_term(term_id)

    # Parse component scores and calculate positions per subject
    all_class_scores = conn.execute('''
        SELECT ps.student_id, ps.subject_id, ps.total_score
        FROM portal_score ps
        JOIN portal_student st ON st.id = ps.student_id
        WHERE ps.term_id=? AND st.class_field_id=? AND st.is_active=1
    ''', (term_id, student.class_field_id)).fetchall()

    # Build subject position map
    from collections import defaultdict
    subject_scores_map = defaultdict(list)
    for r in all_class_scores:
        if r[2] is not None:
            subject_scores_map[r[1]].append((r[0], float(r[2])))

    subject_positions = {}
    subject_averages = {}
    for subj_id, score_list in subject_scores_map.items():
        sorted_list = sorted(score_list, key=lambda x: -x[1])
        for pos, (sid, sc) in enumerate(sorted_list, 1):
            if sid == student_id:
                subject_positions[subj_id] = pos
        avg = sum(s[1] for s in score_list) / len(score_list) if score_list else 0
        subject_averages[subj_id] = round(avg, 1)

    # Build score rows with parsed components
    score_rows = []
    total_obtained = 0
    total_obtainable = 0
    for s in scores:
        comp_data = json.loads(s['component_scores'] or '{}')
        comp_values = []
        for comp in components:
            key = f'component_{comp["id"]}'
            comp_values.append(comp_data.get(key, ''))

        grade_label, points = compute_grade(s['total_score'])
        remark = _auto_remark(grade_label)
        total_obtained += float(s['total_score'] or 0)
        total_obtainable += 100  # Each subject max = 100

        score_rows.append({
            'subject_name': s['subject_name'],
            'comp_values': comp_values,
            'total': s['total_score'],
            'grade': grade_label,
            'points': points,
            'remark': remark,
            'position': subject_positions.get(s['subject_id'], '-'),
            'class_avg': subject_averages.get(s['subject_id'], '-'),
        })

    # Result sheet data
    result = ResultSheet.objects.using('school_data').filter(
        student_id=student_id, term_id=term_id
    ).first()

    # Attendance
    attendance = conn.execute(
        'SELECT present, absent, late, total_school_days FROM rps_attendance WHERE student_id=? AND term_id=?',
        (student_id, term_id)
    ).fetchone()
    attendance = dict(attendance) if attendance else {'present': 0, 'absent': 0, 'late': 0, 'total_school_days': 0}

    # Attributes/Skills
    attributes = conn.execute(
        'SELECT attribute_type, attribute_name, rating FROM rps_studentattribute WHERE student_id=? AND term_id=?',
        (student_id, term_id)
    ).fetchall()
    affective = [dict(a) for a in attributes if a['attribute_type'] == 'affective']
    psychomotor = [dict(a) for a in attributes if a['attribute_type'] == 'psychomotor']

    # Comments
    comments = {}
    comment_rows = conn.execute(
        'SELECT comment_type, comment FROM rps_studentcommentrecord WHERE student_id=? AND term_id=?',
        (student_id, term_id)
    ).fetchall()
    for c in comment_rows:
        comments[c[0]] = c[1]

    # Auto-generate if not set
    avg_score = float(result.average_score) if result else (total_obtained / len(scores) if scores else 0)
    if not comments.get('teacher'):
        comments['teacher'] = _auto_teacher_comment(avg_score)
    if not comments.get('headteacher'):
        comments['headteacher'] = _auto_teacher_comment(avg_score)

    # Term dates
    term_info = conn.execute(
        'SELECT start_date, end_date FROM portal_term WHERE id=?', (term_id,)
    ).fetchone()

    # Number of students in class
    class_count = conn.execute(
        'SELECT COUNT(*) FROM portal_student WHERE class_field_id=? AND school_id=? AND is_active=1',
        (student.class_field_id, school_id)
    ).fetchone()[0]

    conn.close()

    # Default affective traits and psychomotor skills if empty
    if not affective:
        affective = [{'attribute_name': n, 'rating': 0} for n in [
            'Attentiveness', 'Attitude of School Work', 'Cooperation with Others',
            'Emotion Stability', 'Health', 'Leadership', 'Neatness',
            'Perseverance', 'Politeness', 'Punctuality', 'Speaking / Writing'
        ]]
    if not psychomotor:
        psychomotor = [{'attribute_name': n, 'rating': 0} for n in [
            'Drawing & Painting', 'Handling of Tools', 'Games',
            'Handwriting', 'Music', 'Verbal Fluency'
        ]]

    context = {
        'teacher': teacher,
        'student': student,
        'term': term,
        'school': school,
        'branding': branding,
        'scheme': scheme,
        'components': components,
        'score_rows': score_rows,
        'result': result,
        'attendance': attendance,
        'affective': affective,
        'psychomotor': psychomotor,
        'comments': comments,
        'term_start': term_info[0] if term_info else '',
        'term_end': term_info[1] if term_info else '',
        'class_count': class_count,
        'total_obtained': round(total_obtained, 1),
        'total_obtainable': total_obtainable,
        'avg_score': round(avg_score, 1),
        'total_subjects': len(scores),
        'active_page': 'teacher_results',
    }
    return render(request, 'portal/teacher/report_card.html', context)


@teacher_required
def teacher_generate_results(request):
    """Generate/regenerate result sheets for a class + term."""
    school_id = _get_school_id(request)
    if request.method != 'POST':
        return redirect('portal:teacher_results')

    teacher = request.teacher
    class_id = int(request.POST.get('class', 0))
    term_id = int(request.POST.get('term', 0))

    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]
    if class_id not in class_ids:
        return redirect('portal:teacher_results')

    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row

    # Get all students in class with their scores
    students = conn.execute(
        'SELECT id, first_name, last_name FROM portal_student WHERE class_field_id=? AND school_id=? AND is_active=1',
        (class_id, school_id)
    ).fetchall()

    student_totals = []
    for s in students:
        scores = conn.execute(
            'SELECT total_score FROM portal_score WHERE student_id=? AND term_id=? AND total_score IS NOT NULL',
            (s['id'], term_id)
        ).fetchall()
        if scores:
            total = sum(float(sc['total_score']) for sc in scores)
            avg = total / len(scores)
            student_totals.append({
                'id': s['id'], 'total': round(total, 2),
                'avg': round(avg, 2), 'subjects': len(scores)
            })

    # Sort by average desc for position
    student_totals.sort(key=lambda x: -x['avg'])

    now = datetime.now().isoformat()
    for pos, st in enumerate(student_totals, 1):
        # Check existing
        existing = conn.execute(
            'SELECT id FROM portal_resultsheet WHERE student_id=? AND term_id=?',
            (st['id'], term_id)
        ).fetchone()

        avg_score = st['avg']
        auto_comment = _auto_teacher_comment(avg_score)

        if existing:
            conn.execute('''
                UPDATE portal_resultsheet SET total_subjects=?, total_score=?, average_score=?,
                position=?, generated_at=? WHERE id=?
            ''', (st['subjects'], st['total'], st['avg'], pos, now, existing['id']))
            conn.execute('''
                UPDATE rps_resultsheet SET total_subjects=?, total_score=?, average_score=?,
                position=?, generated_at=?, updated_at=? WHERE student_id=? AND term_id=?
            ''', (st['subjects'], st['total'], st['avg'], pos, now, now, st['id'], term_id))
        else:
            conn.execute('''
                INSERT INTO portal_resultsheet
                (student_id, term_id, total_subjects, total_score, average_score, position,
                 form_teacher_remark, principal_remark, generated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            ''', (st['id'], term_id, st['subjects'], st['total'], st['avg'], pos, auto_comment, '', now))
            last_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.execute('''
                INSERT INTO rps_resultsheet
                (id, student_id, term_id, total_subjects, total_score, average_score, position,
                 form_teacher_remark, principal_remark, pdf_file, generated_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,'',?,?)
            ''', (last_id, st['id'], term_id, st['subjects'], st['total'], st['avg'], pos, auto_comment, '', now, now))

    conn.commit()
    conn.close()

    messages.success(request, f'Results generated for {len(student_totals)} students.')
    return redirect(f'/teacher/results/?class={class_id}&term={term_id}')


# ── TEMPLATE EDITOR ─────────────────────────────────────────────────────────────

@teacher_required
def teacher_template_editor(request):
    context = {
        'teacher': request.teacher,
        'removal_message': 'Template Editor has been removed from this project.',
        'active_page': 'teacher_template',
    }
    return render(request, 'portal/teacher/template_editor_disabled.html', context)


# ── ANALYTICS ───────────────────────────────────────────────────────────────────

@teacher_required
def teacher_analytics(request):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]
    active_term = _get_active_term(school_id)

    selected_class = request.GET.get('class', '')

    class_analysis = []
    subject_analysis = []
    grade_distribution = {}
    top_students = []

    if selected_class and int(selected_class) in class_ids and active_term:
        class_id = int(selected_class)

        conn = sqlite3.connect(_db())
        conn.row_factory = sqlite3.Row

        # Subject-wise analysis
        subj_rows = conn.execute('''
            SELECT sub.name, AVG(ps.total_score) as avg_score,
                   COUNT(ps.id) as student_count,
                   MAX(ps.total_score) as highest,
                   MIN(ps.total_score) as lowest
            FROM portal_score ps
            JOIN portal_subject sub ON sub.id = ps.subject_id
            JOIN portal_student st ON st.id = ps.student_id
            WHERE ps.term_id=? AND st.class_field_id=? AND st.is_active=1 AND ps.total_score IS NOT NULL
            GROUP BY ps.subject_id
            ORDER BY avg_score DESC
        ''', (active_term.id, class_id)).fetchall()
        subject_analysis = [dict(r) for r in subj_rows]

        # Grade distribution across all subjects
        all_scores = conn.execute('''
            SELECT ps.total_score
            FROM portal_score ps
            JOIN portal_student st ON st.id = ps.student_id
            WHERE ps.term_id=? AND st.class_field_id=? AND st.is_active=1 AND ps.total_score IS NOT NULL
        ''', (active_term.id, class_id)).fetchall()

        grade_counts = {'EE1': 0, 'EE2': 0, 'ME1': 0, 'ME2': 0, 'AE1': 0, 'AE2': 0, 'BE1': 0, 'BE2': 0}
        for r in all_scores:
            g, _ = compute_grade(r[0])
            if g in grade_counts:
                grade_counts[g] += 1
        grade_distribution = grade_counts

        # Top students by average
        top_rows = conn.execute('''
            SELECT st.first_name || ' ' || st.last_name as name, st.admission_number,
                   AVG(ps.total_score) as avg_score, COUNT(ps.id) as subjects
            FROM portal_score ps
            JOIN portal_student st ON st.id = ps.student_id
            WHERE ps.term_id=? AND st.class_field_id=? AND st.is_active=1 AND ps.total_score IS NOT NULL
            GROUP BY ps.student_id
            ORDER BY avg_score DESC
            LIMIT 20
        ''', (active_term.id, class_id)).fetchall()
        top_students = [dict(r) for r in top_rows]

        conn.close()

    # Cross-class comparison
    if active_term:
        conn = sqlite3.connect(_db())
        conn.row_factory = sqlite3.Row
        for c in assigned_classes:
            avg_row = conn.execute('''
                SELECT AVG(ps.total_score) as avg_score, COUNT(DISTINCT ps.student_id) as students
                FROM portal_score ps
                JOIN portal_student st ON st.id = ps.student_id
                WHERE ps.term_id=? AND st.class_field_id=? AND st.is_active=1 AND ps.total_score IS NOT NULL
            ''', (active_term.id, c['schoolclass_id'])).fetchone()
            class_analysis.append({
                'name': c['name'],
                'avg': round(float(avg_row['avg_score']), 1) if avg_row['avg_score'] else 0,
                'students': avg_row['students'] or 0,
            })
        conn.close()

    context = {
        'teacher': teacher,
        'assigned_classes': assigned_classes,
        'selected_class': selected_class,
        'class_analysis': class_analysis,
        'class_analysis_json': json.dumps(class_analysis),
        'subject_analysis': subject_analysis,
        'subject_analysis_json': json.dumps(subject_analysis),
        'grade_distribution': grade_distribution,
        'grade_distribution_json': json.dumps(grade_distribution),
        'top_students': top_students,
        'active_term': active_term,
        'active_page': 'teacher_analytics',
    }
    return render(request, 'portal/teacher/analytics.html', context)


# ── BROADSHEET ──────────────────────────────────────────────────────────────────

@teacher_required
def teacher_broadsheet(request):
    school_id = _get_school_id(request)
    teacher = request.teacher
    assigned_classes = get_teacher_assigned_classes(teacher.id, school_id)
    class_ids = [c['schoolclass_id'] for c in assigned_classes]
    terms = get_terms_for_school(school_id)
    active_term = _get_active_term(school_id)

    selected_class = request.GET.get('class', '')
    selected_term = request.GET.get('term', str(active_term.id) if active_term else '')

    rows = []
    subjects = []
    school_class = None
    grade_summary = {}

    if selected_class and int(selected_class) in class_ids and selected_term:
        class_id = int(selected_class)
        term_id = int(selected_term)
        school_class = SchoolClass.objects.using('school_data').get(id=class_id)

        conn = sqlite3.connect(_db())
        conn.row_factory = sqlite3.Row

        # Get subjects for this class
        subj_rows = conn.execute('''
            SELECT DISTINCT sub.id, sub.name
            FROM portal_score ps
            JOIN portal_subject sub ON sub.id = ps.subject_id
            JOIN portal_student st ON st.id = ps.student_id
            WHERE ps.term_id=? AND st.class_field_id=? AND st.is_active=1
            ORDER BY sub.name
        ''', (term_id, class_id)).fetchall()
        subjects = [dict(s) for s in subj_rows]

        # Get all students and their scores
        students = conn.execute('''
            SELECT id, admission_number, first_name, last_name
            FROM portal_student
            WHERE class_field_id=? AND school_id=? AND is_active=1
            ORDER BY first_name, last_name
        ''', (class_id, school_id)).fetchall()

        student_data = []
        for s in students:
            scores = conn.execute(
                'SELECT subject_id, total_score FROM portal_score WHERE student_id=? AND term_id=?',
                (s['id'], term_id)
            ).fetchall()
            score_map = {sc['subject_id']: sc['total_score'] for sc in scores}
            subject_scores = []
            total = 0
            count = 0
            for subj in subjects:
                val = score_map.get(subj['id'])
                subject_scores.append(val)
                if val is not None:
                    total += float(val)
                    count += 1

            avg = round(total / count, 1) if count else 0
            grade, points = compute_grade(avg)
            student_data.append({
                'name': f"{s['first_name']} {s['last_name']}",
                'adm': s['admission_number'],
                'scores': subject_scores,
                'total': round(total, 1),
                'subjects': count,
                'avg': avg,
                'grade': grade,
                'points': points,
            })

        # Sort by avg desc, assign positions
        student_data.sort(key=lambda x: -x['avg'])
        for i, sd in enumerate(student_data, 1):
            sd['position'] = i
            sd['remark'] = _auto_remark(sd['grade'])

        rows = student_data

        # Grade summary
        grade_summary = {'EE1': 0, 'EE2': 0, 'ME1': 0, 'ME2': 0, 'AE1': 0, 'AE2': 0, 'BE1': 0, 'BE2': 0}
        for sd in student_data:
            if sd['grade'] in grade_summary:
                grade_summary[sd['grade']] += 1

        conn.close()

    context = {
        'teacher': teacher,
        'assigned_classes': assigned_classes,
        'terms': terms,
        'selected_class': selected_class,
        'selected_term': selected_term,
        'school_class': school_class,
        'subjects': subjects,
        'rows': rows,
        'grade_summary': grade_summary,
        'active_term': active_term,
        'active_page': 'teacher_broadsheet',
    }
    return render(request, 'portal/teacher/broadsheet.html', context)


# ── ANNOUNCEMENTS ───────────────────────────────────────────────────────────────

@teacher_required
def teacher_announcements(request):
    teacher = request.teacher
    school_id = _get_school_id(request)

    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    events = conn.execute('''
        SELECT * FROM rps_schoolevent
        WHERE school_id=?
        ORDER BY created_at DESC
        LIMIT 50
    ''', (school_id,)).fetchall()
    events = [dict(e) for e in events]
    conn.close()

    context = {
        'teacher': teacher,
        'events': events,
        'active_page': 'teacher_announcements',
    }
    return render(request, 'portal/teacher/announcements.html', context)


@teacher_required
def term_settings(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    actual_active_term = _get_active_term(school_id)
    terms = list(
        Term.objects.using('school_data').filter(
            session__school_id=school_id
        ).select_related('session').order_by('-session__start_date', 'term')
    )
    for term in terms:
        _attach_term_settings(term, conn)

    selected_id = request.POST.get('term_id') or request.GET.get('term')
    selected_term = None
    if selected_id:
        for term in terms:
            if str(term.id) == str(selected_id):
                selected_term = term
                break
    if not selected_term:
        selected_term = actual_active_term or (terms[0] if terms else None)
    if selected_term:
        _attach_term_settings(selected_term, conn)

    if request.method == 'POST' and selected_term:
        start_date = request.POST.get('start_date', '').strip()
        end_date = request.POST.get('end_date', '').strip()
        next_term_begins = request.POST.get('next_term_begins', '').strip() or None
        school_days = int(request.POST.get('school_days') or 0)
        is_active = 1 if request.POST.get('is_active') else 0
        start_obj = _parse_date(start_date)
        end_obj = _parse_date(end_date)

        if not start_obj or not end_obj:
            messages.error(request, 'Please provide valid start and end dates.')
        elif end_obj < start_obj:
            messages.error(request, 'Term end date cannot be earlier than the start date.')
        else:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if is_active:
                conn.execute('''
                    UPDATE portal_term
                    SET is_active = 0
                    WHERE id != ? AND session_id IN (
                        SELECT id FROM portal_academicsession WHERE school_id = ?
                    )
                ''', (selected_term.id, school_id))
                if _table_exists(conn, 'rps_term'):
                    conn.execute('''
                        UPDATE rps_term
                        SET is_active = 0, updated_at = ?
                        WHERE id != ? AND session_id IN (
                            SELECT id FROM rps_academicsession WHERE school_id = ?
                        )
                    ''', (now, selected_term.id, school_id))

            conn.execute(
                'UPDATE portal_term SET start_date=?, end_date=?, is_active=? WHERE id=?',
                (start_date, end_date, is_active, selected_term.id),
            )
            if _table_exists(conn, 'rps_term'):
                conn.execute('''
                    UPDATE rps_term
                    SET start_date=?, end_date=?, is_active=?, school_opens_count=?,
                        next_term_begins=?, updated_at=?
                    WHERE id=?
                ''', (
                    start_date,
                    end_date,
                    is_active,
                    school_days,
                    next_term_begins,
                    now,
                    selected_term.id,
                ))
            conn.commit()
            messages.success(request, 'Term settings updated successfully.')
            conn.close()
            return _redirect_with_query('portal:term_settings', term=selected_term.id)

    context = {
        'teacher': request.teacher,
        'terms': terms,
        'active_term': selected_term or actual_active_term,
        'selected_term': selected_term,
        'term_duration': (
            _term_duration_days(selected_term.start_date, selected_term.end_date)
            if selected_term else None
        ),
        'active_page': 'term_settings',
    }
    conn.close()
    return render(request, 'portal/teacher/term_settings.html', context)


@teacher_required
def session_manage(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    active_term = _get_active_term(school_id)

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        session_id = int(request.POST.get('session_id') or 0)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if action == 'create':
            session_name = request.POST.get('session_name', '').strip()
            start_date = request.POST.get('start_date', '').strip()
            end_date = request.POST.get('end_date', '').strip()
            start_obj = _parse_date(start_date)
            end_obj = _parse_date(end_date)
            term_numbers = [
                term_no for term_no in ('1', '2', '3')
                if request.POST.get(f'create_term_{term_no}')
            ]

            if not session_name or not start_obj or not end_obj:
                messages.error(request, 'Session name, start date, and end date are required.')
            elif end_obj < start_obj:
                messages.error(request, 'Session end date cannot be earlier than the start date.')
            else:
                conn.execute('''
                    INSERT INTO portal_academicsession
                    (session_name, start_date, end_date, is_active, school_id)
                    VALUES (?, ?, ?, 0, ?)
                ''', (session_name, start_date, end_date, school_id))
                new_session_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

                if _table_exists(conn, 'rps_academicsession'):
                    conn.execute('''
                        INSERT INTO rps_academicsession
                        (id, session_name, start_date, end_date, is_active, created_at, updated_at, school_id)
                        VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                    ''', (new_session_id, session_name, start_date, end_date, now, now, school_id))

                for term_info in _build_term_ranges(start_date, end_date):
                    if term_info['term'] not in term_numbers:
                        continue
                    conn.execute('''
                        INSERT INTO portal_term (term, start_date, end_date, is_active, session_id)
                        VALUES (?, ?, ?, 0, ?)
                    ''', (
                        term_info['term'],
                        term_info['start_date'].isoformat(),
                        term_info['end_date'].isoformat(),
                        new_session_id,
                    ))
                    new_term_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

                    if _table_exists(conn, 'rps_term'):
                        conn.execute('''
                            INSERT INTO rps_term (
                                id, term, start_date, end_date, is_active,
                                created_at, updated_at, session_id,
                                school_opens_count, next_term_begins,
                                opens_friday, opens_monday, opens_saturday, opens_sunday,
                                opens_thursday, opens_tuesday, opens_wednesday, work_days
                            ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, 1, 1, 0, 0, 1, 1, 1, ?)
                        ''', (
                            new_term_id,
                            term_info['term'],
                            term_info['start_date'].isoformat(),
                            term_info['end_date'].isoformat(),
                            now,
                            now,
                            new_session_id,
                            term_info['school_days'],
                            (
                                term_info['next_term_begins'].isoformat()
                                if term_info['next_term_begins'] else None
                            ),
                            '1,2,3,4,5',
                        ))

                conn.commit()
                messages.success(request, 'Academic session created successfully.')

        elif action == 'edit' and session_id:
            session_name = request.POST.get('session_name', '').strip()
            start_date = request.POST.get('start_date', '').strip()
            end_date = request.POST.get('end_date', '').strip()
            start_obj = _parse_date(start_date)
            end_obj = _parse_date(end_date)

            if not session_name or not start_obj or not end_obj:
                messages.error(request, 'Session name, start date, and end date are required.')
            elif end_obj < start_obj:
                messages.error(request, 'Session end date cannot be earlier than the start date.')
            else:
                conn.execute('''
                    UPDATE portal_academicsession
                    SET session_name=?, start_date=?, end_date=?
                    WHERE id=? AND school_id=?
                ''', (session_name, start_date, end_date, session_id, school_id))
                if _table_exists(conn, 'rps_academicsession'):
                    conn.execute('''
                        UPDATE rps_academicsession
                        SET session_name=?, start_date=?, end_date=?, updated_at=?
                        WHERE id=? AND school_id=?
                    ''', (session_name, start_date, end_date, now, session_id, school_id))
                conn.commit()
                messages.success(request, 'Academic session updated successfully.')

        elif action == 'activate' and session_id:
            conn.execute(
                'UPDATE portal_academicsession SET is_active=0 WHERE school_id=?',
                (school_id,),
            )
            conn.execute(
                'UPDATE portal_academicsession SET is_active=1 WHERE id=? AND school_id=?',
                (session_id, school_id),
            )
            if _table_exists(conn, 'rps_academicsession'):
                conn.execute(
                    'UPDATE rps_academicsession SET is_active=0, updated_at=? WHERE school_id=?',
                    (now, school_id),
                )
                conn.execute(
                    'UPDATE rps_academicsession SET is_active=1, updated_at=? WHERE id=? AND school_id=?',
                    (now, session_id, school_id),
                )
            conn.commit()
            messages.success(request, 'Academic session activated.')

        elif action == 'delete' and session_id:
            session_row = conn.execute(
                'SELECT is_active FROM portal_academicsession WHERE id=? AND school_id=?',
                (session_id, school_id),
            ).fetchone()
            if not session_row:
                messages.error(request, 'Session not found.')
            elif session_row['is_active']:
                messages.error(request, 'Active sessions cannot be deleted.')
            else:
                conn.execute('DELETE FROM portal_term WHERE session_id=?', (session_id,))
                conn.execute('DELETE FROM portal_academicsession WHERE id=? AND school_id=?', (session_id, school_id))
                if _table_exists(conn, 'rps_term'):
                    conn.execute('DELETE FROM rps_term WHERE session_id=?', (session_id,))
                if _table_exists(conn, 'rps_academicsession'):
                    conn.execute('DELETE FROM rps_academicsession WHERE id=? AND school_id=?', (session_id, school_id))
                conn.commit()
                messages.success(request, 'Academic session deleted.')

        conn.close()
        return redirect('portal:session_manage')

    sessions = list(
        AcademicSession.objects.using('school_data').filter(
            school_id=school_id
        ).order_by('-start_date')
    )
    term_map = {}
    for term in Term.objects.using('school_data').filter(
        session__school_id=school_id
    ).order_by('term'):
        term_map.setdefault(term.session_id, []).append(term)
    for session in sessions:
        session.term_list = term_map.get(session.id, [])

    context = {
        'teacher': request.teacher,
        'sessions': sessions,
        'active_term': active_term,
        'active_page': 'session_manage',
    }
    conn.close()
    return render(request, 'portal/teacher/session_manage.html', context)


@teacher_required
def teacher_list_view(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    _ensure_teacher_tables(conn)
    active_term = _get_active_term(school_id)

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        if action == 'create':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            full_name = ' '.join(part for part in [first_name, last_name] if part).strip()

            if not first_name or not last_name:
                messages.error(request, 'First name and last name are required.')
            else:
                base_username = email.split('@', 1)[0] if email else f'{first_name}.{last_name}'
                username = _unique_teacher_username(conn, base_username)
                temp_password = 'ChangeMe123'
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                conn.execute('''
                    INSERT INTO teacher_teacheruser (
                        username, password_hash, full_name, is_active, created_at,
                        is_class_teacher_of_id, first_name, last_name, date_of_birth,
                        gender, phone, email, address, qualifications, experience
                    ) VALUES (?, ?, ?, 1, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    username,
                    make_password(temp_password),
                    full_name,
                    now,
                    first_name,
                    last_name,
                    request.POST.get('date_of_birth', '').strip() or None,
                    request.POST.get('gender', '').strip(),
                    request.POST.get('phone', '').strip(),
                    email,
                    request.POST.get('address', '').strip(),
                    request.POST.get('qualifications', '').strip(),
                    request.POST.get('experience', '').strip(),
                ))
                teacher_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                for class_id in request.POST.getlist('classes'):
                    conn.execute('''
                        INSERT OR IGNORE INTO teacher_teacheruser_assigned_classes
                        (teacheruser_id, schoolclass_id) VALUES (?, ?)
                    ''', (teacher_id, int(class_id)))
                conn.commit()
                messages.success(
                    request,
                    f'Teacher added. Username: {username} | Temporary password: {temp_password}',
                )

        elif action == 'delete':
            teacher_id = int(request.POST.get('teacher_id') or 0)
            if teacher_id == request.teacher.id:
                messages.error(request, 'You cannot delete the teacher account that is currently signed in.')
            else:
                conn.execute(
                    'DELETE FROM teacher_teacheruser_assigned_classes WHERE teacheruser_id=?',
                    (teacher_id,),
                )
                conn.execute(
                    'DELETE FROM teacher_teacheruser_assigned_subjects WHERE teacheruser_id=?',
                    (teacher_id,),
                )
                conn.execute('DELETE FROM teacher_teacheruser WHERE id=?', (teacher_id,))
                conn.commit()
                messages.success(request, 'Teacher deleted successfully.')

        conn.close()
        return redirect('portal:teacher_list')

    teachers = _get_teacher_rows(conn, school_id)
    classes = list(
        SchoolClass.objects.using('school_data').filter(
            school_id=school_id
        ).order_by('name')
    )

    context = {
        'teacher': request.teacher,
        'teachers': teachers,
        'classes': classes,
        'active_term': active_term,
        'active_page': 'teacher_list',
    }
    conn.close()
    return render(request, 'portal/teacher/teacher_list.html', context)


@teacher_required
def teacher_edit_view(request, teacher_id):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    _ensure_teacher_tables(conn)
    active_term = _get_active_term(school_id)
    teacher_obj = _get_teacher_row(conn, teacher_id)
    if not teacher_obj:
        conn.close()
        messages.error(request, 'Teacher not found.')
        return redirect('portal:teacher_list')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        if not first_name or not last_name:
            messages.error(request, 'First name and last name are required.')
        else:
            full_name = ' '.join(part for part in [first_name, last_name] if part).strip()
            conn.execute('''
                UPDATE teacher_teacheruser
                SET first_name=?, last_name=?, full_name=?, date_of_birth=?,
                    gender=?, phone=?, email=?, address=?, experience=?, qualifications=?
                WHERE id=?
            ''', (
                first_name,
                last_name,
                full_name,
                request.POST.get('date_of_birth', '').strip() or None,
                request.POST.get('gender', '').strip(),
                request.POST.get('phone', '').strip(),
                request.POST.get('email', '').strip(),
                request.POST.get('address', '').strip(),
                request.POST.get('experience', '').strip(),
                request.POST.get('qualifications', '').strip(),
                teacher_id,
            ))
            conn.execute(
                'DELETE FROM teacher_teacheruser_assigned_classes WHERE teacheruser_id=?',
                (teacher_id,),
            )
            for class_id in request.POST.getlist('classes'):
                conn.execute('''
                    INSERT OR IGNORE INTO teacher_teacheruser_assigned_classes
                    (teacheruser_id, schoolclass_id) VALUES (?, ?)
                ''', (teacher_id, int(class_id)))
            conn.commit()
            conn.close()
            messages.success(request, 'Teacher details updated.')
            return redirect('portal:teacher_list')

    classes = list(
        SchoolClass.objects.using('school_data').filter(
            school_id=school_id
        ).order_by('name')
    )
    assigned_class_ids = _get_teacher_assigned_class_ids(conn, teacher_id)

    context = {
        'teacher': request.teacher,
        'teacher_obj': teacher_obj,
        'classes': classes,
        'assigned_class_ids': assigned_class_ids,
        'active_term': active_term,
        'active_page': 'teacher_list',
    }
    conn.close()
    return render(request, 'portal/teacher/teacher_edit.html', context)


@teacher_required
def class_manage(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    _ensure_teacher_tables(conn)
    active_term = _get_active_term(school_id)

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        class_id = int(request.POST.get('class_id') or 0)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if action == 'create':
            class_name = request.POST.get('name', '').strip()
            level = request.POST.get('level', '').strip() or 'Primary'
            class_teacher_id = int(request.POST.get('class_teacher') or 0)

            if not class_name:
                messages.error(request, 'Class name is required.')
            else:
                conn.execute(
                    'INSERT INTO portal_schoolclass (name, level, school_id) VALUES (?, ?, ?)',
                    (class_name, level, school_id),
                )
                new_class_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                if _table_exists(conn, 'rps_schoolclass'):
                    conn.execute('''
                        INSERT INTO rps_schoolclass (
                            id, name, level, form_number, created_at, updated_at,
                            class_teacher_id, school_id, promoting_class_name,
                            repeating_class_name, result_template, class_teacher_profile_id,
                            report_theme_preset
                        ) VALUES (?, ?, ?, 0, ?, ?, NULL, ?, ?, ?, 'default', NULL, 'classic')
                    ''', (
                        new_class_id,
                        class_name,
                        level,
                        now,
                        now,
                        school_id,
                        class_name,
                        class_name,
                    ))
                if class_teacher_id:
                    conn.execute(
                        'UPDATE teacher_teacheruser SET is_class_teacher_of_id=NULL WHERE is_class_teacher_of_id=?',
                        (new_class_id,),
                    )
                    conn.execute(
                        'UPDATE teacher_teacheruser SET is_class_teacher_of_id=? WHERE id=?',
                        (new_class_id, class_teacher_id),
                    )
                conn.commit()
                messages.success(request, 'Class created successfully.')

        elif action == 'edit' and class_id:
            class_name = request.POST.get('name', '').strip()
            level = request.POST.get('level', '').strip() or 'Primary'
            if not class_name:
                messages.error(request, 'Class name is required.')
            else:
                conn.execute('''
                    UPDATE portal_schoolclass
                    SET name=?, level=?
                    WHERE id=? AND school_id=?
                ''', (class_name, level, class_id, school_id))
                if _table_exists(conn, 'rps_schoolclass'):
                    conn.execute('''
                        UPDATE rps_schoolclass
                        SET name=?, level=?, promoting_class_name=?, repeating_class_name=?, updated_at=?
                        WHERE id=? AND school_id=?
                    ''', (class_name, level, class_name, class_name, now, class_id, school_id))
                conn.commit()
                messages.success(request, 'Class updated successfully.')

        elif action == 'delete' and class_id:
            student_count = conn.execute('''
                SELECT COUNT(*)
                FROM portal_student
                WHERE class_field_id=? AND school_id=? AND is_active=1
            ''', (class_id, school_id)).fetchone()[0]
            if student_count:
                messages.error(request, 'Classes with enrolled students cannot be deleted.')
            else:
                conn.execute(
                    'UPDATE teacher_teacheruser SET is_class_teacher_of_id=NULL WHERE is_class_teacher_of_id=?',
                    (class_id,),
                )
                conn.execute(
                    'DELETE FROM teacher_teacheruser_assigned_classes WHERE schoolclass_id=?',
                    (class_id,),
                )
                if _table_exists(conn, 'rps_classsubjectallocation'):
                    conn.execute('DELETE FROM rps_classsubjectallocation WHERE school_class_id=?', (class_id,))
                if _table_exists(conn, 'rps_schoolclass'):
                    conn.execute('DELETE FROM rps_schoolclass WHERE id=? AND school_id=?', (class_id, school_id))
                conn.execute('DELETE FROM portal_schoolclass WHERE id=? AND school_id=?', (class_id, school_id))
                conn.commit()
                messages.success(request, 'Class deleted successfully.')

        conn.close()
        return redirect('portal:class_manage')

    class_rows = conn.execute('''
        SELECT sc.id, sc.name, sc.level,
               COALESCE(SUM(CASE WHEN st.is_active = 1 THEN 1 ELSE 0 END), 0) AS student_count,
               tt.full_name AS class_teacher
        FROM portal_schoolclass sc
        LEFT JOIN portal_student st ON st.class_field_id = sc.id AND st.school_id = sc.school_id
        LEFT JOIN teacher_teacheruser tt ON tt.is_class_teacher_of_id = sc.id
        WHERE sc.school_id = ?
        GROUP BY sc.id
        ORDER BY sc.name
    ''', (school_id,)).fetchall()
    classes = [dict(row) for row in class_rows]
    teachers = _get_teacher_rows(conn, school_id)

    context = {
        'teacher': request.teacher,
        'classes': classes,
        'teachers': teachers,
        'active_term': active_term,
        'active_page': 'class_manage',
    }
    conn.close()
    return render(request, 'portal/teacher/class_manage.html', context)


@teacher_required
def subject_manage(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    _ensure_teacher_tables(conn)
    active_term = _get_active_term(school_id)
    selected_class = request.GET.get('class', '').strip()

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        subject_id = int(request.POST.get('subject_id') or 0)
        subject_name = request.POST.get('name', '').strip()
        subject_code = request.POST.get('code', '').strip() or slugify(subject_name).replace('-', '').upper()[:20]
        teacher_id = int(request.POST.get('teacher_id') or 0)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if action == 'create':
            if not subject_name:
                messages.error(request, 'Subject name is required.')
            else:
                try:
                    conn.execute('''
                        INSERT INTO portal_subject (name, code, is_active, school_id)
                        VALUES (?, ?, 1, ?)
                    ''', (subject_name, subject_code, school_id))
                    new_subject_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                    if _table_exists(conn, 'rps_subject'):
                        conn.execute('''
                            INSERT INTO rps_subject
                            (id, name, code, subject_type, is_active, created_at, updated_at, school_id)
                            VALUES (?, ?, ?, 'core', 1, ?, ?, ?)
                        ''', (new_subject_id, subject_name, subject_code, now, now, school_id))
                    if selected_class and _table_exists(conn, 'rps_classsubjectallocation'):
                        next_order = conn.execute('''
                            SELECT COALESCE(MAX(display_order), 0) + 1
                            FROM rps_classsubjectallocation
                            WHERE school_class_id=?
                        ''', (int(selected_class),)).fetchone()[0]
                        conn.execute('''
                            INSERT INTO rps_classsubjectallocation
                            (school_class_id, subject_id, teacher_id, display_order, created_at, updated_at)
                            VALUES (?, ?, NULL, ?, ?, ?)
                        ''', (int(selected_class), new_subject_id, next_order, now, now))
                    if teacher_id:
                        conn.execute(
                            'DELETE FROM teacher_teacheruser_assigned_subjects WHERE subject_id=?',
                            (new_subject_id,),
                        )
                        conn.execute('''
                            INSERT OR IGNORE INTO teacher_teacheruser_assigned_subjects
                            (teacheruser_id, subject_id) VALUES (?, ?)
                        ''', (teacher_id, new_subject_id))
                    conn.commit()
                    messages.success(request, 'Subject created successfully.')
                except sqlite3.IntegrityError:
                    messages.error(request, 'That subject code already exists. Please choose a unique code.')

        elif action == 'edit' and subject_id:
            if not subject_name:
                messages.error(request, 'Subject name is required.')
            else:
                try:
                    conn.execute('''
                        UPDATE portal_subject
                        SET name=?, code=?
                        WHERE id=? AND school_id=?
                    ''', (subject_name, subject_code, subject_id, school_id))
                    if _table_exists(conn, 'rps_subject'):
                        conn.execute('''
                            UPDATE rps_subject
                            SET name=?, code=?, updated_at=?
                            WHERE id=? AND school_id=?
                        ''', (subject_name, subject_code, now, subject_id, school_id))
                    if selected_class and _table_exists(conn, 'rps_classsubjectallocation'):
                        allocation = conn.execute('''
                            SELECT id
                            FROM rps_classsubjectallocation
                            WHERE school_class_id=? AND subject_id=?
                        ''', (int(selected_class), subject_id)).fetchone()
                        if not allocation:
                            next_order = conn.execute('''
                                SELECT COALESCE(MAX(display_order), 0) + 1
                                FROM rps_classsubjectallocation
                                WHERE school_class_id=?
                            ''', (int(selected_class),)).fetchone()[0]
                            conn.execute('''
                                INSERT INTO rps_classsubjectallocation
                                (school_class_id, subject_id, teacher_id, display_order, created_at, updated_at)
                                VALUES (?, ?, NULL, ?, ?, ?)
                            ''', (int(selected_class), subject_id, next_order, now, now))
                        else:
                            conn.execute(
                                'UPDATE rps_classsubjectallocation SET updated_at=? WHERE id=?',
                                (now, allocation['id']),
                            )
                    conn.execute(
                        'DELETE FROM teacher_teacheruser_assigned_subjects WHERE subject_id=?',
                        (subject_id,),
                    )
                    if teacher_id:
                        conn.execute('''
                            INSERT OR IGNORE INTO teacher_teacheruser_assigned_subjects
                            (teacheruser_id, subject_id) VALUES (?, ?)
                        ''', (teacher_id, subject_id))
                    conn.commit()
                    messages.success(request, 'Subject updated successfully.')
                except sqlite3.IntegrityError:
                    messages.error(request, 'That subject code already exists. Please choose a unique code.')

        elif action == 'delete' and subject_id:
            score_count = conn.execute(
                'SELECT COUNT(*) FROM portal_score WHERE subject_id=?',
                (subject_id,),
            ).fetchone()[0]
            if score_count:
                messages.error(request, 'This subject already has recorded scores and cannot be deleted.')
            else:
                conn.execute(
                    'DELETE FROM teacher_teacheruser_assigned_subjects WHERE subject_id=?',
                    (subject_id,),
                )
                if _table_exists(conn, 'rps_classsubjectallocation'):
                    conn.execute('DELETE FROM rps_classsubjectallocation WHERE subject_id=?', (subject_id,))
                if _table_exists(conn, 'rps_subject'):
                    conn.execute('DELETE FROM rps_subject WHERE id=? AND school_id=?', (subject_id, school_id))
                conn.execute('DELETE FROM portal_subject WHERE id=? AND school_id=?', (subject_id, school_id))
                conn.commit()
                messages.success(request, 'Subject deleted successfully.')

        conn.close()
        return _redirect_with_query('portal:subject_manage', **({'class': selected_class} if selected_class else {}))

    if selected_class and _table_exists(conn, 'rps_classsubjectallocation'):
        subject_rows = conn.execute('''
            SELECT s.id, s.name, s.code, s.is_active,
                   t.id AS teacher_id, t.full_name AS teacher_name
            FROM portal_subject s
            JOIN rps_classsubjectallocation csa
                ON csa.subject_id = s.id AND csa.school_class_id = ?
            LEFT JOIN teacher_teacheruser_assigned_subjects tas ON tas.subject_id = s.id
            LEFT JOIN teacher_teacheruser t ON t.id = tas.teacheruser_id
            WHERE s.school_id = ?
            GROUP BY s.id
            ORDER BY COALESCE(csa.display_order, 9999), s.name
        ''', (int(selected_class), school_id)).fetchall()
    else:
        subject_rows = conn.execute('''
            SELECT s.id, s.name, s.code, s.is_active,
                   t.id AS teacher_id, t.full_name AS teacher_name
            FROM portal_subject s
            LEFT JOIN teacher_teacheruser_assigned_subjects tas ON tas.subject_id = s.id
            LEFT JOIN teacher_teacheruser t ON t.id = tas.teacheruser_id
            WHERE s.school_id = ?
            GROUP BY s.id
            ORDER BY s.name
        ''', (school_id,)).fetchall()

    subjects = [dict(row) for row in subject_rows]
    classes = list(
        SchoolClass.objects.using('school_data').filter(
            school_id=school_id
        ).order_by('name')
    )
    teachers = _get_teacher_rows(conn, school_id)

    context = {
        'teacher': request.teacher,
        'subjects': subjects,
        'classes': classes,
        'teachers': teachers,
        'selected_class': selected_class,
        'active_term': active_term,
        'active_page': 'subject_manage',
    }
    conn.close()
    return render(request, 'portal/teacher/subject_manage.html', context)


@teacher_required
def attributes_entry(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    _ensure_attribute_tables(conn)
    active_term = _get_active_term(school_id)
    assigned_classes = get_teacher_assigned_classes(request.teacher.id, school_id)
    assigned_class_ids = {str(item['schoolclass_id']) for item in assigned_classes}
    selected_class = request.POST.get('class_id') or request.GET.get('class', '')

    if request.method == 'POST' and active_term and selected_class in assigned_class_ids:
        students = Student.objects.using('school_data').filter(
            school_id=school_id,
            class_field_id=int(selected_class),
            is_active=True,
        ).order_by('first_name', 'last_name')

        for student in students:
            for index, trait_name in enumerate(AFFECTIVE_TRAITS):
                rating = request.POST.get(f'aff_{student.id}_{index}', '').strip()
                if rating:
                    conn.execute('''
                        INSERT INTO rps_studentattribute
                        (student_id, term_id, school_id, attribute_type, attribute_name, rating)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(student_id, term_id, attribute_name)
                        DO UPDATE SET rating=excluded.rating, school_id=excluded.school_id, attribute_type=excluded.attribute_type
                    ''', (student.id, active_term.id, school_id, 'affective', trait_name, int(rating)))
                else:
                    conn.execute('''
                        DELETE FROM rps_studentattribute
                        WHERE student_id=? AND term_id=? AND attribute_type='affective' AND attribute_name=?
                    ''', (student.id, active_term.id, trait_name))

            for index, skill_name in enumerate(PSYCHOMOTOR_SKILLS):
                rating = request.POST.get(f'psy_{student.id}_{index}', '').strip()
                if rating:
                    conn.execute('''
                        INSERT INTO rps_studentattribute
                        (student_id, term_id, school_id, attribute_type, attribute_name, rating)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(student_id, term_id, attribute_name)
                        DO UPDATE SET rating=excluded.rating, school_id=excluded.school_id, attribute_type=excluded.attribute_type
                    ''', (student.id, active_term.id, school_id, 'psychomotor', skill_name, int(rating)))
                else:
                    conn.execute('''
                        DELETE FROM rps_studentattribute
                        WHERE student_id=? AND term_id=? AND attribute_type='psychomotor' AND attribute_name=?
                    ''', (student.id, active_term.id, skill_name))

        conn.commit()
        messages.success(request, 'Student attributes saved successfully.')
        conn.close()
        return _redirect_with_query('portal:attributes_entry', **{'class': selected_class})

    students = []
    if active_term and selected_class in assigned_class_ids:
        students = list(
            Student.objects.using('school_data').filter(
                school_id=school_id,
                class_field_id=int(selected_class),
                is_active=True,
            ).order_by('first_name', 'last_name')
        )
        attribute_rows = conn.execute('''
            SELECT student_id, attribute_type, attribute_name, rating
            FROM rps_studentattribute
            WHERE term_id=? AND school_id=? AND student_id IN (
                SELECT id
                FROM portal_student
                WHERE class_field_id=? AND school_id=? AND is_active=1
            )
        ''', (active_term.id, school_id, int(selected_class), school_id)).fetchall()
        attribute_map = {}
        for row in attribute_rows:
            attribute_map.setdefault(row['student_id'], {}).setdefault(
                row['attribute_type'], {}
            )[row['attribute_name']] = '' if row['rating'] is None else str(row['rating'])

        for student in students:
            affective_map = attribute_map.get(student.id, {}).get('affective', {})
            psychomotor_map = attribute_map.get(student.id, {}).get('psychomotor', {})
            student.affective_ratings = [affective_map.get(name, '') for name in AFFECTIVE_TRAITS]
            student.psychomotor_ratings = [psychomotor_map.get(name, '') for name in PSYCHOMOTOR_SKILLS]

    context = {
        'teacher': request.teacher,
        'assigned_classes': assigned_classes,
        'selected_class': selected_class,
        'active_term': active_term,
        'students': students,
        'affective_traits': AFFECTIVE_TRAITS,
        'psychomotor_skills': PSYCHOMOTOR_SKILLS,
        'active_page': 'attributes_entry',
    }
    conn.close()
    return render(request, 'portal/teacher/attributes_entry.html', context)


@teacher_required
def comments_entry(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    _ensure_attribute_tables(conn)
    active_term = _get_active_term(school_id)
    assigned_classes = get_teacher_assigned_classes(request.teacher.id, school_id)
    assigned_class_ids = {str(item['schoolclass_id']) for item in assigned_classes}
    selected_class = request.POST.get('class_id') or request.GET.get('class', '')
    comment_type = request.POST.get('comment_type') or request.GET.get('type', 'teacher')
    if comment_type not in {'teacher', 'headteacher', 'director'}:
        comment_type = 'teacher'

    if request.method == 'POST' and active_term and selected_class in assigned_class_ids:
        students = Student.objects.using('school_data').filter(
            school_id=school_id,
            class_field_id=int(selected_class),
            is_active=True,
        ).order_by('first_name', 'last_name')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if comment_type == 'director':
            if not _column_exists(conn, 'portal_resultsheet', 'director_remark'):
                conn.execute("ALTER TABLE portal_resultsheet ADD COLUMN director_remark TEXT DEFAULT ''")
            if _table_exists(conn, 'rps_resultsheet') and not _column_exists(conn, 'rps_resultsheet', 'director_remark'):
                conn.execute("ALTER TABLE rps_resultsheet ADD COLUMN director_remark TEXT DEFAULT ''")

        for student in students:
            comment_text = request.POST.get(f'comment_{student.id}', '').strip()
            existing = conn.execute('''
                SELECT id
                FROM rps_studentcommentrecord
                WHERE student_id=? AND term_id=? AND comment_type=?
            ''', (student.id, active_term.id, comment_type)).fetchone()

            if comment_text:
                if existing:
                    conn.execute('''
                        UPDATE rps_studentcommentrecord
                        SET comment=?, updated_at=?
                        WHERE id=?
                    ''', (comment_text, now, existing['id']))
                else:
                    conn.execute('''
                        INSERT INTO rps_studentcommentrecord
                        (comment_type, comment, created_at, updated_at, school_id, student_id, term_id, updated_by_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    ''', (comment_type, comment_text, now, now, school_id, student.id, active_term.id))
            elif existing:
                conn.execute('DELETE FROM rps_studentcommentrecord WHERE id=?', (existing['id'],))

            if comment_type == 'teacher':
                conn.execute('''
                    UPDATE portal_resultsheet
                    SET form_teacher_remark=?
                    WHERE student_id=? AND term_id=?
                ''', (comment_text, student.id, active_term.id))
                if _table_exists(conn, 'rps_resultsheet'):
                    conn.execute('''
                        UPDATE rps_resultsheet
                        SET form_teacher_remark=?, updated_at=?
                        WHERE student_id=? AND term_id=?
                    ''', (comment_text, now, student.id, active_term.id))
            elif comment_type == 'headteacher':
                conn.execute('''
                    UPDATE portal_resultsheet
                    SET principal_remark=?
                    WHERE student_id=? AND term_id=?
                ''', (comment_text, student.id, active_term.id))
                if _table_exists(conn, 'rps_resultsheet'):
                    conn.execute('''
                        UPDATE rps_resultsheet
                        SET principal_remark=?, updated_at=?
                        WHERE student_id=? AND term_id=?
                    ''', (comment_text, now, student.id, active_term.id))
            else:
                conn.execute('''
                    UPDATE portal_resultsheet
                    SET director_remark=?
                    WHERE student_id=? AND term_id=?
                ''', (comment_text, student.id, active_term.id))
                if _table_exists(conn, 'rps_resultsheet'):
                    conn.execute('''
                        UPDATE rps_resultsheet
                        SET director_remark=?, updated_at=?
                        WHERE student_id=? AND term_id=?
                    ''', (comment_text, now, student.id, active_term.id))

        conn.commit()
        messages.success(request, 'Comments saved successfully.')
        conn.close()
        return _redirect_with_query('portal:comments_entry', **{'class': selected_class, 'type': comment_type})

    students = []
    default_comment = _get_default_comment_template(conn, school_id, comment_type)

    if active_term and selected_class in assigned_class_ids:
        students = list(
            Student.objects.using('school_data').filter(
                school_id=school_id,
                class_field_id=int(selected_class),
                is_active=True,
            ).order_by('first_name', 'last_name')
        )
        comment_rows = conn.execute('''
            SELECT student_id, comment
            FROM rps_studentcommentrecord
            WHERE term_id=? AND school_id=? AND comment_type=? AND student_id IN (
                SELECT id
                FROM portal_student
                WHERE class_field_id=? AND school_id=? AND is_active=1
            )
        ''', (
            active_term.id,
            school_id,
            comment_type,
            int(selected_class),
            school_id,
        )).fetchall()
        comment_map = {row['student_id']: row['comment'] for row in comment_rows}

        result_columns = 'student_id, average_score, form_teacher_remark, principal_remark'
        if _column_exists(conn, 'portal_resultsheet', 'director_remark'):
            result_columns += ', director_remark'
        result_rows = conn.execute(f'''
            SELECT {result_columns}
            FROM portal_resultsheet
            WHERE term_id=? AND student_id IN (
                SELECT id
                FROM portal_student
                WHERE class_field_id=? AND school_id=? AND is_active=1
            )
        ''', (active_term.id, int(selected_class), school_id)).fetchall()
        result_map = {row['student_id']: dict(row) for row in result_rows}

        for student in students:
            result_row = result_map.get(student.id, {})
            if comment_type == 'teacher':
                fallback_comment = result_row.get('form_teacher_remark', '')
            elif comment_type == 'headteacher':
                fallback_comment = result_row.get('principal_remark', '')
            else:
                fallback_comment = result_row.get('director_remark', '')
            student.existing_comment = comment_map.get(student.id) or fallback_comment or ''
            student.avg_score = result_row.get('average_score')

    context = {
        'teacher': request.teacher,
        'assigned_classes': assigned_classes,
        'selected_class': selected_class,
        'active_term': active_term,
        'comment_type': comment_type,
        'students': students,
        'default_comment': default_comment,
        'active_page': 'comments_entry',
    }
    conn.close()
    return render(request, 'portal/teacher/comments_entry.html', context)


@teacher_required
def broadsheet_subject(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    assigned_classes = get_teacher_assigned_classes(request.teacher.id, school_id)
    assigned_class_ids = {str(item['schoolclass_id']) for item in assigned_classes}
    active_term = _get_active_term(school_id)
    terms = list(
        Term.objects.using('school_data').filter(
            session__school_id=school_id
        ).select_related('session').order_by('-session__start_date', 'term')
    )

    selected_class = request.GET.get('class', '').strip()
    selected_subject = request.GET.get('subject', '').strip()
    selected_term = request.GET.get('term', str(active_term.id) if active_term else '').strip()
    subjects = _subject_options_for_class(conn, school_id, selected_class) if selected_class in assigned_class_ids else []

    rows = []
    components = []
    subject_name = ''
    class_name = ''
    class_avg = None
    highest = None
    lowest = None

    if (
        selected_class in assigned_class_ids and
        selected_subject and
        selected_term
    ):
        school_class = SchoolClass.objects.using('school_data').filter(
            id=int(selected_class),
            school_id=school_id,
        ).first()
        subject_obj = Subject.objects.using('school_data').filter(
            id=int(selected_subject),
            school_id=school_id,
        ).first()
        _, component_defs = get_scheme_for_term(int(selected_term))
        components = [
            {
                'id': component['id'],
                'name': component.get('label') or component.get('code') or f'Component {index + 1}',
            }
            for index, component in enumerate(component_defs)
        ]

        score_rows = conn.execute('''
            SELECT st.admission_number, st.first_name, st.last_name,
                   ps.total_score, ps.grade, ps.component_scores
            FROM portal_score ps
            JOIN portal_student st ON st.id = ps.student_id
            WHERE ps.term_id=? AND ps.subject_id=? AND st.class_field_id=? AND st.school_id=? AND st.is_active=1
            ORDER BY ps.total_score DESC, st.first_name, st.last_name
        ''', (
            int(selected_term),
            int(selected_subject),
            int(selected_class),
            school_id,
        )).fetchall()

        score_values = []
        for position, row in enumerate(score_rows, start=1):
            try:
                component_values = json.loads(row['component_scores'] or '{}')
            except (TypeError, json.JSONDecodeError):
                component_values = {}
            total_score = float(row['total_score']) if row['total_score'] is not None else None
            grade = row['grade'] or ''
            if total_score is not None:
                grade, points = compute_grade(total_score)
                score_values.append(total_score)
            else:
                points = ''
            rows.append({
                'position': position,
                'adm': row['admission_number'],
                'name': f"{row['first_name']} {row['last_name']}".strip(),
                'comp_scores': [
                    component_values.get(f'component_{component["id"]}')
                    for component in components
                ],
                'total': total_score if total_score is not None else 0,
                'grade': grade,
                'points': points if points else '',
                'remark': _auto_remark(grade),
            })

        subject_name = subject_obj.name if subject_obj else ''
        class_name = school_class.name if school_class else ''
        if score_values:
            class_avg = round(sum(score_values) / len(score_values), 1)
            highest = max(score_values)
            lowest = min(score_values)

    context = {
        'teacher': request.teacher,
        'assigned_classes': assigned_classes,
        'subjects': subjects,
        'terms': terms,
        'selected_class': selected_class,
        'selected_subject': selected_subject,
        'selected_term': selected_term,
        'rows': rows,
        'components': components,
        'subject_name': subject_name,
        'class_name': class_name,
        'class_avg': class_avg,
        'highest': highest,
        'lowest': lowest,
        'active_term': active_term,
        'active_page': 'broadsheet_subject',
    }
    conn.close()
    return render(request, 'portal/teacher/broadsheet_subject.html', context)


@teacher_required
def subject_champions(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    assigned_classes = get_teacher_assigned_classes(request.teacher.id, school_id)
    assigned_class_ids = {str(item['schoolclass_id']) for item in assigned_classes}
    active_term = _get_active_term(school_id)
    terms = list(
        Term.objects.using('school_data').filter(
            session__school_id=school_id
        ).select_related('session').order_by('-session__start_date', 'term')
    )

    selected_class = request.GET.get('class', '').strip()
    selected_term = request.GET.get('term', str(active_term.id) if active_term else '').strip()
    champions = []
    school_class = None

    if selected_class in assigned_class_ids and selected_term:
        school_class = SchoolClass.objects.using('school_data').filter(
            id=int(selected_class),
            school_id=school_id,
        ).first()
        teacher_rows = conn.execute('''
            SELECT tas.subject_id, tt.full_name
            FROM teacher_teacheruser_assigned_subjects tas
            JOIN teacher_teacheruser tt ON tt.id = tas.teacheruser_id
        ''').fetchall()
        teacher_map = {row['subject_id']: row['full_name'] for row in teacher_rows}

        for subject in _subject_options_for_class(conn, school_id, selected_class):
            champion = conn.execute('''
                SELECT st.admission_number,
                       st.first_name,
                       st.last_name,
                       AVG(ps.total_score) AS avg_score
                FROM portal_score ps
                JOIN portal_student st ON st.id = ps.student_id
                WHERE ps.term_id=? AND ps.subject_id=? AND st.class_field_id=? AND st.school_id=? AND st.is_active=1
                      AND ps.total_score IS NOT NULL
                GROUP BY st.id
                ORDER BY avg_score DESC, st.first_name, st.last_name
                LIMIT 1
            ''', (
                int(selected_term),
                subject['id'],
                int(selected_class),
                school_id,
            )).fetchone()
            if champion:
                champions.append({
                    'subject': subject['name'],
                    'admission_number': champion['admission_number'],
                    'student_name': f"{champion['first_name']} {champion['last_name']}".strip(),
                    'avg_score': champion['avg_score'],
                    'teacher_name': teacher_map.get(subject['id'], ''),
                })

    context = {
        'teacher': request.teacher,
        'assigned_classes': assigned_classes,
        'terms': terms,
        'selected_class': selected_class,
        'selected_term': selected_term,
        'champions': champions,
        'school_class': school_class,
        'active_term': active_term,
        'active_page': 'subject_champions',
    }
    conn.close()
    return render(request, 'portal/teacher/subject_champions.html', context)


@teacher_required
def school_settings(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    _ensure_branding_schema(conn)
    active_term = _get_active_term(school_id)
    school = School.objects.using('school_data').filter(id=school_id).first()

    if request.method == 'POST' and school:
        action = request.POST.get('action', '').strip()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        branding = _ensure_branding_row(conn, school, school_id)

        if action == 'save_school':
            values = (
                request.POST.get('name', '').strip(),
                request.POST.get('abbreviation', '').strip(),
                request.POST.get('address', '').strip(),
                request.POST.get('phone', '').strip(),
                request.POST.get('email', '').strip(),
                request.POST.get('website', '').strip(),
                school_id,
            )
            conn.execute('''
                UPDATE portal_school
                SET name=?, abbreviation=?, address=?, phone=?, email=?, website=?
                WHERE id=?
            ''', values)
            if _table_exists(conn, 'rps_school'):
                conn.execute('''
                    UPDATE rps_school
                    SET name=?, abbreviation=?, address=?, phone=?, email=?, website=?, updated_at=?
                    WHERE id=?
                ''', values[:-1] + (now, school_id))
            conn.commit()
            messages.success(request, 'School information updated.')

        elif action == 'save_branding':
            logo_path = branding.get('logo', '')
            stamp_path = branding.get('stamp', '')
            if request.FILES.get('logo'):
                logo_path = _save_uploaded_media(request.FILES['logo'], 'branding')
            if request.FILES.get('stamp'):
                stamp_path = _save_uploaded_media(request.FILES['stamp'], 'branding')
            conn.execute('''
                UPDATE rps_schoolbranding
                SET tagline=?, primary_color=?, logo=?, stamp=?, updated_at=?
                WHERE school_id=?
            ''', (
                request.POST.get('tagline', '').strip(),
                request.POST.get('primary_color', '').strip() or '#1f894d',
                logo_path,
                stamp_path,
                now,
                school_id,
            ))
            conn.commit()
            messages.success(request, 'Branding settings updated.')

        elif action == 'save_leadership':
            headteacher_name = request.POST.get('headteacher_name', '').strip()
            director_name = request.POST.get('director_name', '').strip()
            conn.execute('''
                UPDATE rps_schoolbranding
                SET headteacher_name=?, director_name=?, updated_at=?
                WHERE school_id=?
            ''', (headteacher_name, director_name, now, school_id))
            conn.execute(
                'UPDATE portal_school SET principal_name=? WHERE id=?',
                (headteacher_name, school_id),
            )
            if _table_exists(conn, 'rps_school'):
                conn.execute(
                    'UPDATE rps_school SET principal_name=?, updated_at=? WHERE id=?',
                    (headteacher_name, now, school_id),
                )
            conn.commit()
            messages.success(request, 'Leadership details updated.')

        conn.close()
        return redirect('portal:school_settings')

    branding = _ensure_branding_row(conn, school, school_id) if school else {}
    branding['logo_url'] = _media_url(branding.get('logo'))
    branding['stamp_url'] = _media_url(branding.get('stamp'))

    context = {
        'teacher': request.teacher,
        'school': school,
        'branding': branding,
        'active_term': active_term,
        'active_page': 'school_settings',
    }
    conn.close()
    return render(request, 'portal/teacher/school_settings.html', context)


@teacher_required
def user_manage(request):
    school_id = _get_school_id(request)
    conn = _connect_school_db()
    _ensure_user_role_schema(conn)
    active_term = _get_active_term(school_id)

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        user_id = int(request.POST.get('user_id') or 0)
        username = request.POST.get('username', '').strip()
        full_name = request.POST.get('full_name', '').strip()
        password = request.POST.get('password', '')
        role_label = request.POST.get('role', 'User').strip() or 'User'
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if action == 'create':
            if not username or not password:
                messages.error(request, 'Username and password are required.')
            elif conn.execute('SELECT 1 FROM auth_user WHERE username=?', (username,)).fetchone():
                messages.error(request, 'That username is already in use.')
            else:
                first_name, last_name = _split_full_name(full_name or username)
                conn.execute('''
                    INSERT INTO auth_user
                    (password, last_login, is_superuser, username, last_name, email, is_staff, is_active, date_joined, first_name)
                    VALUES (?, NULL, ?, ?, ?, '', 1, 1, ?, ?)
                ''', (
                    make_password(password),
                    1 if role_label == 'Admin' else 0,
                    username,
                    last_name,
                    now,
                    first_name,
                ))
                new_user_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                permissions = request.POST.getlist('permissions') if role_label != 'Admin' else []
                conn.execute('''
                    INSERT INTO rps_userrole
                    (role, is_active, created_at, updated_at, user_id, require_password_change, permissions)
                    VALUES (?, 1, ?, ?, ?, 0, ?)
                ''', (
                    role_label.lower(),
                    now,
                    now,
                    new_user_id,
                    ','.join(permissions),
                ))
                conn.commit()
                messages.success(request, 'User created successfully.')

        elif action == 'edit' and user_id:
            if not username:
                messages.error(request, 'Username is required.')
            else:
                existing_user = conn.execute(
                    'SELECT id FROM auth_user WHERE username=? AND id!=?',
                    (username, user_id),
                ).fetchone()
                if existing_user:
                    messages.error(request, 'That username is already in use.')
                else:
                    first_name, last_name = _split_full_name(full_name or username)
                    if password:
                        conn.execute('''
                            UPDATE auth_user
                            SET username=?, first_name=?, last_name=?, is_superuser=?, is_staff=1, password=?
                            WHERE id=?
                        ''', (
                            username,
                            first_name,
                            last_name,
                            1 if role_label == 'Admin' else 0,
                            make_password(password),
                            user_id,
                        ))
                    else:
                        conn.execute('''
                            UPDATE auth_user
                            SET username=?, first_name=?, last_name=?, is_superuser=?, is_staff=1
                            WHERE id=?
                        ''', (
                            username,
                            first_name,
                            last_name,
                            1 if role_label == 'Admin' else 0,
                            user_id,
                        ))
                    role_row = conn.execute(
                        'SELECT id, permissions FROM rps_userrole WHERE user_id=?',
                        (user_id,),
                    ).fetchone()
                    permissions_text = ''
                    if role_row and role_label != 'Admin':
                        permissions_text = role_row['permissions'] or ''
                    if role_row:
                        conn.execute('''
                            UPDATE rps_userrole
                            SET role=?, is_active=1, updated_at=?, permissions=?
                            WHERE id=?
                        ''', (
                            role_label.lower(),
                            now,
                            permissions_text,
                            role_row['id'],
                        ))
                    else:
                        conn.execute('''
                            INSERT INTO rps_userrole
                            (role, is_active, created_at, updated_at, user_id, require_password_change, permissions)
                            VALUES (?, 1, ?, ?, ?, 0, ?)
                        ''', (role_label.lower(), now, now, user_id, permissions_text))
                    conn.commit()
                    messages.success(request, 'User updated successfully.')

        elif action == 'delete' and user_id:
            user_row = conn.execute(
                'SELECT username FROM auth_user WHERE id=?',
                (user_id,),
            ).fetchone()
            if not user_row:
                messages.error(request, 'User not found.')
            elif user_row['username'].lower() == 'admin':
                messages.error(request, 'The default admin account cannot be deleted.')
            else:
                conn.execute('DELETE FROM rps_userrole WHERE user_id=?', (user_id,))
                conn.execute('DELETE FROM auth_user WHERE id=?', (user_id,))
                conn.commit()
                messages.success(request, 'User deleted successfully.')

        conn.close()
        return redirect('portal:user_manage')

    user_rows = conn.execute('''
        SELECT u.id, u.username, u.first_name, u.last_name, u.is_active,
               COALESCE(ur.role, 'user') AS role,
               COALESCE(ur.permissions, '') AS permissions
        FROM auth_user u
        LEFT JOIN rps_userrole ur ON ur.user_id = u.id
        WHERE LOWER(COALESCE(ur.role, 'user')) != 'teacher'
        ORDER BY LOWER(u.username)
    ''').fetchall()

    users = []
    for row in user_rows:
        raw_role = (row['role'] or 'user').strip().lower()
        full_name = ' '.join(part for part in [row['first_name'], row['last_name']] if part).strip()
        users.append({
            'id': row['id'],
            'username': row['username'],
            'full_name': full_name or row['username'],
            'role': 'Admin' if raw_role == 'admin' else 'User',
            'permissions': (
                AVAILABLE_PERMISSIONS
                if raw_role == 'admin'
                else [item.strip() for item in (row['permissions'] or '').split(',') if item.strip()]
            ),
            'is_active': bool(row['is_active']),
        })

    context = {
        'teacher': request.teacher,
        'users': users,
        'available_permissions': AVAILABLE_PERMISSIONS,
        'active_term': active_term,
        'active_page': 'user_manage',
    }
    conn.close()
    return render(request, 'portal/teacher/user_manage.html', context)
