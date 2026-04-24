from django import template


register = template.Library()


def _get_rating(values, index):
    try:
        return values[int(index)]
    except (TypeError, ValueError, IndexError):
        return ''


@register.filter
def get_affective(student, index):
    return _get_rating(getattr(student, 'affective_ratings', []), index)


@register.filter
def get_psychomotor(student, index):
    return _get_rating(getattr(student, 'psychomotor_ratings', []), index)
