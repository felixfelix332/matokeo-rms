import json
from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.utils import OperationalError
from django.db.models import Avg, Count, Q, Sum, Max, Min
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import (
    AcademicSession, AttendanceEntry, FeePayment, ResultSheet,
    School, SchoolClass, Score, Student, Subject, Term,
)

def _get_school_id(request):
    return request.session.get('school_id', 5)


def _get_school(school_id):
    return School.objects.using('school_data').filter(id=school_id).first()


def _get_classes(school_id):
    return SchoolClass.objects.using('school_data').filter(school_id=school_id).order_by('name')


def _get_subjects(school_id):
    return Subject.objects.using('school_data').filter(school_id=school_id, is_active=True).order_by('name')


def _get_terms(school_id):
    return Term.objects.using('school_data').filter(
        session__school_id=school_id
    ).select_related('session').order_by('-session__start_date', '-term')


def _get_active_term(school_id):
    return Term.objects.using('school_data').filter(
        session__school_id=school_id, is_active=True
    ).select_related('session').first()


@login_required
def dashboard(request):
    try:
        school_id = _get_school_id(request)
        school = _get_school(school_id)
        students = Student.objects.using('school_data').filter(school_id=school_id)
        total_students = students.count()
        active_students = students.filter(is_active=True).count()
        male_count = students.filter(gender='M', is_active=True).count()
        female_count = students.filter(gender='F', is_active=True).count()
        classes = _get_classes(school_id)
        subjects = _get_subjects(school_id)
        terms = _get_terms(school_id)
        active_term = _get_active_term(school_id)

        class_distribution = []
        for sc in classes:
            count = students.filter(class_field=sc, is_active=True).count()
            if count > 0:
                class_distribution.append({'name': sc.name, 'count': count})

        grade_dist = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0}
        if active_term:
            scores = Score.objects.using('school_data').filter(term=active_term)
            for s in scores:
                g = (s.grade or '').upper().strip()
                if g in grade_dist:
                    grade_dist[g] += 1

        subject_averages = []
        if active_term:
            for subj in subjects:
                avg = Score.objects.using('school_data').filter(
                    term=active_term, subject=subj, total_score__isnull=False
                ).aggregate(avg=Avg('total_score'))['avg']
                if avg is not None:
                    subject_averages.append({'name': subj.name, 'avg': round(float(avg), 1)})

        recent_payments = FeePayment.objects.using('school_data').filter(
            school_id=school_id
        ).order_by('-payment_date')[:5]

        total_fees_collected = FeePayment.objects.using('school_data').filter(
            school_id=school_id, payment_status='active'
        ).aggregate(total=Sum('amount'))['total'] or 0

        attendance_count = 0
        if active_term:
            attendance_count = AttendanceEntry.objects.using('school_data').filter(
                term=active_term
            ).count()

        top_results = []
        if active_term:
            top_results = list(
                ResultSheet.objects.using('school_data').filter(
                    term=active_term
                ).select_related('student', 'student__class_field').order_by('position')[:10]
            )

        context = {
            'active_page': 'dashboard',
            'school': school,
            'total_students': total_students,
            'active_students': active_students,
            'male_count': male_count,
            'female_count': female_count,
            'total_classes': classes.count(),
            'total_subjects': subjects.count(),
            'total_terms': terms.count(),
            'active_term': active_term,
            'class_distribution': json.dumps(class_distribution),
            'grade_distribution': json.dumps(grade_dist),
            'subject_averages': json.dumps(subject_averages),
            'recent_payments': recent_payments,
            'total_fees_collected': total_fees_collected,
            'attendance_count': attendance_count,
            'top_results': top_results,
        }
        return render(request, 'portal/dashboard.html', context)
    except OperationalError:
        messages.info(
            request,
            'The dashboard is not available yet while the setup pages are still being built.',
        )
        return redirect('accounts:add_school')


@login_required
def student_list(request):
    school_id = _get_school_id(request)
    students = Student.objects.using('school_data').filter(
        school_id=school_id
    ).select_related('class_field')

    search = request.GET.get('search', '').strip()
    class_filter = request.GET.get('class', '')
    gender_filter = request.GET.get('gender', '')
    status_filter = request.GET.get('status', '')

    if search:
        students = students.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(middle_name__icontains=search) |
            Q(admission_number__icontains=search)
        )
    if class_filter:
        students = students.filter(class_field_id=class_filter)
    if gender_filter:
        students = students.filter(gender=gender_filter)
    if status_filter == 'active':
        students = students.filter(is_active=True)
    elif status_filter == 'inactive':
        students = students.filter(is_active=False)

    students = students.order_by('class_field__name', 'first_name', 'last_name')

    context = {
        'active_page': 'students',
        'students': students,
        'classes': _get_classes(school_id),
        'search': search,
        'class_filter': class_filter,
        'gender_filter': gender_filter,
        'status_filter': status_filter,
        'total_count': students.count(),
    }
    return render(request, 'portal/students.html', context)


@login_required
def student_detail(request, pk):
    school_id = _get_school_id(request)
    student = get_object_or_404(Student.objects.using('school_data'), pk=pk, school_id=school_id)
    terms = _get_terms(school_id)

    # All scores
    scores = Score.objects.using('school_data').filter(
        student=student
    ).select_related('subject', 'term', 'term__session').order_by('-term__session__start_date', '-term__term', 'subject__name')

    # Result sheets
    results = ResultSheet.objects.using('school_data').filter(
        student=student
    ).select_related('term', 'term__session').order_by('-term__session__start_date', '-term__term')

    # Attendance
    attendance = AttendanceEntry.objects.using('school_data').filter(
        student=student
    ).select_related('term').order_by('-date')

    # Fee payments
    fees = FeePayment.objects.using('school_data').filter(
        student=student
    ).order_by('-payment_date')

    # Score trend data
    score_trend = []
    for t in terms:
        avg = Score.objects.using('school_data').filter(
            student=student, term=t, total_score__isnull=False
        ).aggregate(avg=Avg('total_score'))['avg']
        if avg is not None:
            score_trend.append({
                'term': f'{t.session.session_name} T{t.term}',
                'avg': round(float(avg), 1)
            })
    score_trend.reverse()

    context = {
        'active_page': 'students',
        'student': student,
        'scores': scores,
        'results': results,
        'attendance': attendance,
        'fees': fees,
        'score_trend': json.dumps(score_trend),
    }
    return render(request, 'portal/student_detail.html', context)


@login_required
def scores_view(request):
    school_id = _get_school_id(request)
    terms = _get_terms(school_id)
    classes = _get_classes(school_id)
    subjects = _get_subjects(school_id)

    term_id = request.GET.get('term', '')
    class_id = request.GET.get('class', '')
    subject_id = request.GET.get('subject', '')

    scores = Score.objects.using('school_data').filter(
        student__school_id=school_id
    ).select_related('student', 'student__class_field', 'subject', 'term', 'term__session')

    if term_id:
        scores = scores.filter(term_id=term_id)
    else:
        active = _get_active_term(school_id)
        if active:
            scores = scores.filter(term=active)
            term_id = str(active.id)

    if class_id:
        scores = scores.filter(student__class_field_id=class_id)
    if subject_id:
        scores = scores.filter(subject_id=subject_id)

    scores = scores.order_by('student__class_field__name', 'student__first_name', 'subject__name')

    context = {
        'active_page': 'scores',
        'scores': scores[:500],
        'terms': terms,
        'classes': classes,
        'subjects': subjects,
        'term_id': term_id,
        'class_id': class_id,
        'subject_id': subject_id,
        'total_count': scores.count(),
    }
    return render(request, 'portal/scores.html', context)


@login_required
def results_view(request):
    school_id = _get_school_id(request)
    terms = _get_terms(school_id)
    classes = _get_classes(school_id)

    term_id = request.GET.get('term', '')
    class_id = request.GET.get('class', '')

    results = ResultSheet.objects.using('school_data').filter(
        student__school_id=school_id
    ).select_related('student', 'student__class_field', 'term', 'term__session')

    if term_id:
        results = results.filter(term_id=term_id)
    else:
        active = _get_active_term(school_id)
        if active:
            results = results.filter(term=active)
            term_id = str(active.id)

    if class_id:
        results = results.filter(student__class_field_id=class_id)

    results = results.order_by('position')

    context = {
        'active_page': 'results',
        'results': results,
        'terms': terms,
        'classes': classes,
        'term_id': term_id,
        'class_id': class_id,
        'total_count': results.count(),
    }
    return render(request, 'portal/results.html', context)


@login_required
def attendance_view(request):
    school_id = _get_school_id(request)
    terms = _get_terms(school_id)
    classes = _get_classes(school_id)

    term_id = request.GET.get('term', '')
    class_id = request.GET.get('class', '')

    entries = AttendanceEntry.objects.using('school_data').filter(
        student__school_id=school_id
    ).select_related('student', 'student__class_field', 'term', 'term__session')

    if term_id:
        entries = entries.filter(term_id=term_id)
    else:
        active = _get_active_term(school_id)
        if active:
            entries = entries.filter(term=active)
            term_id = str(active.id)

    if class_id:
        entries = entries.filter(student__class_field_id=class_id)

    entries = entries.order_by('-date', 'student__first_name')

    # Summary stats
    total_entries = entries.count()
    present_count = entries.filter(status='P').count()
    absent_count = entries.filter(status='A').count()
    late_count = entries.filter(status='L').count()

    context = {
        'active_page': 'attendance',
        'entries': entries[:500],
        'terms': terms,
        'classes': classes,
        'term_id': term_id,
        'class_id': class_id,
        'total_entries': total_entries,
        'present_count': present_count,
        'absent_count': absent_count,
        'late_count': late_count,
    }
    return render(request, 'portal/attendance.html', context)


@login_required
def fees_view(request):
    school_id = _get_school_id(request)
    payments = FeePayment.objects.using('school_data').filter(
        school_id=school_id
    ).order_by('-payment_date')

    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '').strip()

    if status_filter:
        payments = payments.filter(payment_status=status_filter)
    if search:
        payments = payments.filter(
            Q(learner_name__icontains=search) |
            Q(receipt_number__icontains=search) |
            Q(admission_number__icontains=search)
        )

    total_collected = payments.filter(payment_status='active').aggregate(
        total=Sum('amount'))['total'] or 0
    total_voided = payments.filter(payment_status='voided').aggregate(
        total=Sum('amount'))['total'] or 0

    context = {
        'active_page': 'fees',
        'payments': payments,
        'status_filter': status_filter,
        'search': search,
        'total_collected': total_collected,
        'total_voided': total_voided,
        'total_count': payments.count(),
    }
    return render(request, 'portal/fees.html', context)


@login_required
def analytics_view(request):
    school_id = _get_school_id(request)
    classes = _get_classes(school_id)
    terms = _get_terms(school_id)
    active_term = _get_active_term(school_id)

    # Class performance comparison
    class_performance = []
    term_for_analysis = active_term
    term_id = request.GET.get('term', '')
    if term_id:
        term_for_analysis = Term.objects.using('school_data').filter(id=term_id).first() or active_term

    if term_for_analysis:
        for sc in classes:
            avg = Score.objects.using('school_data').filter(
                term=term_for_analysis, student__class_field=sc, total_score__isnull=False
            ).aggregate(avg=Avg('total_score'))['avg']
            if avg is not None:
                class_performance.append({'name': sc.name, 'avg': round(float(avg), 1)})

    # Gender performance
    gender_perf = {'M': 0, 'F': 0}
    if term_for_analysis:
        for g in ['M', 'F']:
            avg = Score.objects.using('school_data').filter(
                term=term_for_analysis, student__gender=g, total_score__isnull=False
            ).aggregate(avg=Avg('total_score'))['avg']
            if avg:
                gender_perf[g] = round(float(avg), 1)

    # Subject ranking
    subject_ranking = []
    if term_for_analysis:
        for subj in _get_subjects(school_id):
            agg = Score.objects.using('school_data').filter(
                term=term_for_analysis, subject=subj, total_score__isnull=False
            ).aggregate(
                avg=Avg('total_score'),
                highest=Max('total_score'),
                lowest=Min('total_score'),
                count=Count('id')
            )
            if agg['avg'] is not None:
                subject_ranking.append({
                    'name': subj.name,
                    'avg': round(float(agg['avg']), 1),
                    'highest': float(agg['highest'] or 0),
                    'lowest': float(agg['lowest'] or 0),
                    'count': agg['count'],
                })
        subject_ranking.sort(key=lambda x: x['avg'], reverse=True)

    context = {
        'active_page': 'analytics',
        'terms': terms,
        'term_id': term_id or (str(active_term.id) if active_term else ''),
        'class_performance': json.dumps(class_performance),
        'gender_performance': json.dumps(gender_perf),
        'subject_ranking': subject_ranking,
        'subject_ranking_json': json.dumps(subject_ranking),
    }
    return render(request, 'portal/analytics.html', context)
