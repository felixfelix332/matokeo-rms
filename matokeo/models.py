from django.db import models


class School(models.Model):
    name = models.CharField(max_length=200)
    abbreviation = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    website = models.CharField(max_length=200, blank=True)
    principal_name = models.CharField(max_length=200, blank=True)
    logo = models.CharField(max_length=100, blank=True)

    class Meta:
        managed = False
        db_table = 'rms_school'

    def __str__(self):
        return self.name


class AcademicSession(models.Model):
    session_name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, db_column='school_id')

    class Meta:
        managed = False
        db_table = 'rms_academicsession'

    def __str__(self):
        return self.session_name


class Term(models.Model):
    TERM_CHOICES = [('1', 'Term 1'), ('2', 'Term 2'), ('3', 'Term 3')]
    term = models.CharField(max_length=1, choices=TERM_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, db_column='session_id')

    class Meta:
        managed = False
        db_table = 'rms_term'

    def __str__(self):
        return f'{self.session.session_name} - Term {self.term}'

    @property
    def display_name(self):
        return f'Term {self.term}'


class SchoolClass(models.Model):
    name = models.CharField(max_length=100)
    level = models.CharField(max_length=50)
    school = models.ForeignKey(School, on_delete=models.CASCADE, db_column='school_id')

    class Meta:
        managed = False
        db_table = 'rms_schoolclass'
        ordering = ['name']

    def __str__(self):
        return self.name


class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    school = models.ForeignKey(School, on_delete=models.CASCADE, db_column='school_id')

    class Meta:
        managed = False
        db_table = 'rms_subject'
        ordering = ['name']

    def __str__(self):
        return self.name


class Student(models.Model):
    admission_number = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10)
    parent_name = models.CharField(max_length=200, blank=True)
    parent_phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    class_field = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, db_column='class_field_id')
    school = models.ForeignKey(School, on_delete=models.CASCADE, db_column='school_id')
    image = models.CharField(max_length=100, blank=True)

    class Meta:
        managed = False
        db_table = 'rms_student'
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return ' '.join(p for p in parts if p)


class Score(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, db_column='student_id')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_column='subject_id')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, db_column='term_id')
    continuous_assessment = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    test_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    exam_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    total_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    grade = models.CharField(max_length=2, blank=True)
    comment = models.TextField(blank=True)
    component_scores = models.TextField(blank=True)

    class Meta:
        managed = False
        db_table = 'rms_score'

    def __str__(self):
        return f'{self.student} - {self.subject}: {self.total_score}'


class ResultSheet(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, db_column='student_id')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, db_column='term_id')
    total_subjects = models.IntegerField()
    total_score = models.DecimalField(max_digits=8, decimal_places=2)
    average_score = models.DecimalField(max_digits=5, decimal_places=2)
    position = models.IntegerField()
    form_teacher_remark = models.TextField(blank=True)
    principal_remark = models.TextField(blank=True)
    generated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'rms_resultsheet'

    def __str__(self):
        return f'{self.student} - Position {self.position}'


class AttendanceEntry(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, db_column='student_id')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, db_column='term_id')
    date = models.DateField()
    status = models.CharField(max_length=1)
    remark = models.TextField(blank=True)

    class Meta:
        managed = False
        db_table = 'rms_attendanceentry'

    def __str__(self):
        return f'{self.student} - {self.date}: {self.status}'


class FeePayment(models.Model):
    receipt_number = models.CharField(max_length=50)
    admission_number = models.CharField(max_length=50)
    learner_name = models.CharField(max_length=200)
    class_name = models.CharField(max_length=100)
    payment_term = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50)
    reference_code = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, db_column='student_id', null=True)
    school = models.ForeignKey(School, on_delete=models.CASCADE, db_column='school_id')
    entry_type = models.CharField(max_length=50, blank=True)
    payment_status = models.CharField(max_length=50, blank=True)

    class Meta:
        managed = False
        db_table = 'rms_feepayment'

    def __str__(self):
        return f'{self.receipt_number} - {self.learner_name}'
