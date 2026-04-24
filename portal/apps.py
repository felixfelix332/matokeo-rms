from django.apps import AppConfig


class PortalConfig(AppConfig):
    name = 'portal'

    def ready(self):
        try:
            from django.template import engines

            engine = engines['django'].engine
            library = 'portal.templatetags.teacher_extras'
            if library not in engine.builtins:
                engine.builtins.append(library)
        except Exception:
            # Template engine may not be fully initialized in every context.
            pass
