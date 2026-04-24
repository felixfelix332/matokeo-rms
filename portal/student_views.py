import json
from functools import wraps

from django.db.models import Avg
from django.shortcuts import redirect, render

from .models import AttendanceEntry, FeePayment, ResultSheet, Score, Student, Term


def student_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        student_data = request.session.get('student_user')
        if not student_data:
            return redirect('accounts:student_login')
        request.student_data = student_data
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_school_id(request):
    student_data = request.session.get('student_user') or {}
    return request.session.get('school_id') or student_data.get('school_id') or 5


def _get_terms(school_id):
    return Term.objects.using('school_data').filter(
        session__school_id=school_id
    ).select_related('session').order_by('-session__start_date', '-term')


def _get_active_term(school_id):
    return Term.objects.using('school_data').filter(
        session__school_id=school_id, is_active=True
    ).select_related('session').first()


@student_required
def student_portal(request):
    sd = request.student_data
    student_id = sd['id']
    school_id = _get_school_id(request)

    student = Student.objects.using('school_data').filter(
        id=student_id,
        school_id=school_id,
    ).select_related('class_field').first()
    if not student:
        request.session.flush()
        return redirect('accounts:student_login')

    active_term = _get_active_term(school_id)
    terms = _get_terms(school_id)

    # Current term scores
    current_scores = []
    if active_term:
        current_scores = list(
            Score.objects.using('school_data').filter(
                student_id=student_id, term=active_term
            ).select_related('subject').order_by('subject__name')
        )

    # Current result sheet
    current_result = None
    if active_term:
        current_result = ResultSheet.objects.using('school_data').filter(
            student_id=student_id, term=active_term
        ).select_related('term', 'term__session').first()

    # All result sheets
    all_results = list(
        ResultSheet.objects.using('school_data').filter(
            student_id=student_id
        ).select_related('term', 'term__session').order_by('-term__session__start_date', '-term__term')
    )

    # Attendance
    attendance = list(
        AttendanceEntry.objects.using('school_data').filter(
            student_id=student_id
        ).select_related('term').order_by('-date')
    )

    present = sum(1 for a in attendance if a.status == 'P')
    absent = sum(1 for a in attendance if a.status == 'A')
    total_att = len(attendance)
    att_rate = round((present / total_att * 100), 1) if total_att > 0 else 0

    # Fee payments
    fees = list(
        FeePayment.objects.using('school_data').filter(
            student_id=student_id
        ).order_by('-payment_date')
    )

    # Score trend
    score_trend = []
    for t in terms:
        avg = Score.objects.using('school_data').filter(
            student_id=student_id, term=t, total_score__isnull=False
        ).aggregate(avg=Avg('total_score'))['avg']
        if avg is not None:
            score_trend.append({
                'term': f'{t.session.session_name} T{t.term}',
                'avg': round(float(avg), 1)
            })
    score_trend.reverse()

    context = {
        'student': student,
        'active_term': active_term,
        'current_scores': current_scores,
        'current_result': current_result,
        'all_results': all_results,
        'attendance': attendance[:50],
        'present_count': present,
        'absent_count': absent,
        'attendance_rate': att_rate,
        'fees': fees,
        'score_trend': json.dumps(score_trend),
        'active_page': 'my_portal',
    }
    return render(request, 'portal/student_portal/dashboard.html', context)
