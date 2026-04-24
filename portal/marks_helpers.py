"""
Helpers for reading/writing scores with component-based assessment schemes.
Talks directly to school_data.sqlite3 for the assessment structure tables.
"""
import json
import sqlite3
from django.conf import settings


def _db():
    return str(settings.DATABASES['school_data']['NAME'])


def get_terms_for_school(school_id):
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT t.id, t.term, t.is_active, s.session_name, s.id as session_id
        FROM portal_term t
        JOIN portal_academicsession s ON s.id = t.session_id
        WHERE s.school_id = ?
        ORDER BY s.start_date DESC, t.term DESC
    ''', (school_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_scheme_for_term(term_id):
    """Get the assessment scheme and its components for a given term."""
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    row = conn.execute('''
        SELECT tas.scheme_id, s.name as scheme_name
        FROM rps_termassessmentscheme tas
        JOIN rps_assessmentscheme s ON s.id = tas.scheme_id
        WHERE tas.term_id = ?
    ''', (term_id,)).fetchone()
    if not row:
        conn.close()
        return None, []
    scheme = dict(row)
    components = conn.execute('''
        SELECT id, code, label, max_score, input_max_score, input_mode, period, component_kind, "order"
        FROM rps_assessmentcomponent
        WHERE scheme_id = ?
        ORDER BY "order"
    ''', (scheme['scheme_id'],)).fetchall()
    conn.close()
    return scheme, [dict(c) for c in components]


def get_subjects_for_class(class_id, school_id):
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT csa.subject_id, s.name as subject_name
        FROM rps_classsubjectallocation csa
        JOIN portal_subject s ON s.id = csa.subject_id
        WHERE csa.school_class_id = ? AND s.school_id = ?
        ORDER BY csa.display_order, s.name
    ''', (class_id, school_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_students_for_class(class_id, school_id):
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT id, admission_number, first_name, last_name, middle_name, gender
        FROM portal_student
        WHERE class_field_id = ? AND school_id = ? AND is_active = 1
        ORDER BY first_name, last_name
    ''', (class_id, school_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_scores_for_entry(term_id, class_id, subject_id, school_id):
    """
    Get existing scores for a class+subject+term.
    Returns dict keyed by student_id -> {score row + parsed component_scores}
    """
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT ps.id, ps.student_id, ps.total_score, ps.grade, ps.component_scores,
               ps.continuous_assessment, ps.test_score, ps.exam_score
        FROM portal_score ps
        JOIN portal_student st ON st.id = ps.student_id
        WHERE ps.term_id = ? AND ps.subject_id = ? AND st.class_field_id = ? AND st.school_id = ?
    ''', (term_id, subject_id, class_id, school_id)).fetchall()
    conn.close()

    result = {}
    for r in rows:
        d = dict(r)
        try:
            d['_components'] = json.loads(d['component_scores'] or '{}')
        except (json.JSONDecodeError, TypeError):
            d['_components'] = {}
        result[d['student_id']] = d
    return result


def compute_grade(score):
    """
    CBC (Competency-Based Curriculum) grading system.
    Returns (grade_label, points) tuple.
    EE1=8pts (80-100), EE2=7pts (70-79), ME1=6pts (60-69), ME2=5pts (50-59),
    AE1=4pts (40-49), AE2=3pts (30-39), BE1=2pts (20-29), BE2=1pt (0-19).
    """
    # Contributor extension point:
    # Replace this hardcoded scale with configurable grading profiles before
    # adding more country-specific grading rules.
    if score is None:
        return '', 0
    s = float(score)
    if s >= 80:
        return 'EE1', 8
    if s >= 70:
        return 'EE2', 7
    if s >= 60:
        return 'ME1', 6
    if s >= 50:
        return 'ME2', 5
    if s >= 40:
        return 'AE1', 4
    if s >= 30:
        return 'AE2', 3
    if s >= 20:
        return 'BE1', 2
    return 'BE2', 1


def save_scores(term_id, subject_id, class_id, components, student_marks, school_id):
    """
    Save/update scores for all students.
    student_marks: dict of student_id -> {component_id: value, ...}
    components: list of component dicts from get_scheme_for_term
    """
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row

    existing = get_scores_for_entry(term_id, class_id, subject_id, school_id)

    for student_id_str, comp_values in student_marks.items():
        student_id = int(student_id_str)

        # Build component_scores JSON
        component_scores = {}
        total = 0.0
        has_any = False
        for comp in components:
            key = f'component_{comp["id"]}'
            val = comp_values.get(str(comp['id']))
            if val is not None and val != '':
                try:
                    fval = float(val)
                    # Clamp to max_score
                    max_s = comp.get('input_max_score') or comp['max_score']
                    fval = max(0, min(fval, float(max_s)))
                    component_scores[key] = fval
                    total += fval
                    has_any = True
                except (ValueError, TypeError):
                    pass
            else:
                # Keep existing value if any
                if student_id in existing:
                    old_val = existing[student_id]['_components'].get(key)
                    if old_val is not None:
                        component_scores[key] = old_val
                        total += float(old_val)
                        has_any = True

        if not has_any:
            continue

        # For percentage-mode schemes, average across entered components
        entered_count = len(component_scores)
        if entered_count > 0:
            # Check if all components use percentage mode
            all_percentage = all(
                c.get('input_mode') == 'percentage' for c in components
            )
            if all_percentage and entered_count > 0:
                # Average of entered percentage scores
                total_score = round(sum(component_scores.values()) / entered_count, 2)
            else:
                total_score = round(total, 2)
        else:
            total_score = 0

        grade, points = compute_grade(total_score)
        comp_json = json.dumps(component_scores)

        if student_id in existing:
            # Update both tables
            score_id = existing[student_id]['id']
            conn.execute('''
                UPDATE portal_score
                SET total_score = ?, grade = ?, component_scores = ?,
                    exam_score = ?
                WHERE id = ?
            ''', (total_score, grade, comp_json, total_score, score_id))
            conn.execute('''
                UPDATE rps_score
                SET total_score = ?, grade = ?, component_scores = ?,
                    exam_score = ?
                WHERE id = ?
            ''', (total_score, grade, comp_json, total_score, score_id))
        else:
            # Insert into both tables
            conn.execute('''
                INSERT INTO portal_score
                (student_id, subject_id, term_id, continuous_assessment, test_score,
                 exam_score, total_score, grade, comment, component_scores)
                VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, '', ?)
            ''', (student_id, subject_id, term_id, total_score, total_score, grade, comp_json))
            last_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.execute('''
                INSERT INTO rps_score
                (id, student_id, subject_id, term_id, continuous_assessment, test_score,
                 exam_score, total_score, grade, comment, component_scores,
                 created_at, updated_at, teacher_id)
                VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, '', ?,
                        datetime('now'), datetime('now'), NULL)
            ''', (last_id, student_id, subject_id, term_id, total_score, total_score, grade, comp_json))

    conn.commit()
    conn.close()
    return True
