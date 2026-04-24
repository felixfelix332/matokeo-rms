from portal.models import School


def _media_url(relative_path):
    from django.conf import settings

    if not relative_path:
        return ""
    normalized = str(relative_path).replace("\\", "/")
    if normalized.startswith(("http://", "https://", "/")):
        return normalized
    return f"{settings.MEDIA_URL.rstrip('/')}/{normalized.lstrip('/')}"


def get_school(school_id):
    return (
        School.objects.using("school_data")
        .filter(id=school_id)
        .first()
    )


def serialize_school(school):
    logo_path = getattr(school, "logo", "") or ""
    abbreviation = getattr(school, "abbreviation", "") or "SCH"
    return {
        "id": school.id,
        "name": school.name,
        "abbreviation": abbreviation,
        "email": getattr(school, "email", "") or "",
        "phone": getattr(school, "phone", "") or "",
        "address": getattr(school, "address", "") or "",
        "website": getattr(school, "website", "") or "",
        "principal_name": getattr(school, "principal_name", "") or "",
        "logo": logo_path,
        "logo_url": _media_url(logo_path),
    }
