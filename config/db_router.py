class SchoolDataRouter:
    SCHOOL_MODELS = {
        'portal_school', 'portal_academicsession', 'portal_term',
        'portal_schoolclass', 'portal_subject', 'portal_student',
        'portal_score', 'portal_resultsheet', 'portal_attendanceentry',
        'portal_feepayment',
        'teacher_teacheruser', 'teacher_teachersubjectclass',
        'teacher_teacheruser_assigned_classes', 'teacher_teacheruser_assigned_subjects',
        'rps_schoolbranding',
        'portal_studentattribute', 'rps_studentattribute',
    }

    def db_for_read(self, model, **hints):
        if model._meta.db_table in self.SCHOOL_MODELS:
            return 'school_data'
        return 'default'

    def db_for_write(self, model, **hints):
        if model._meta.db_table in self.SCHOOL_MODELS:
            return 'school_data'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == 'school_data':
            return False
        return True
