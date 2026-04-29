class SchoolDataRouter:
    SCHOOL_MODELS = {
        'rms_school', 'rms_academicsession', 'rms_term',
        'rms_schoolclass', 'rms_subject', 'rms_student',
        'rms_score', 'rms_resultsheet', 'rms_attendanceentry',
        'rms_feepayment',
        'rms_teacher', 'rms_teacher_assigned_subjects',
        'rps_schoolbranding',
        'rms_studentattribute', 'rps_studentattribute',
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
