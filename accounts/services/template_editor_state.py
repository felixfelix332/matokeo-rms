import json
from copy import deepcopy

from django.conf import settings
from django.utils.text import slugify

from accounts.services.template_preview import get_default_selected_models, normalize_selected_models


RESULT_TEMPLATE_AUTO = "Auto"
DEFAULT_TEMPLATE_NAME = "Nursery (Default)"
PRIMARY_TEMPLATE_NAME = "Primary (Default)"
JUNIOR_SECONDARY_TEMPLATE_NAME = "Junior Secondary (Default)"
DEFAULT_THEME_COLOR = "#d4147a"
BUILT_IN_TEMPLATE_NAMES = [
    DEFAULT_TEMPLATE_NAME,
    PRIMARY_TEMPLATE_NAME,
    JUNIOR_SECONDARY_TEMPLATE_NAME,
]
_TEMPLATE_NAME_ALIASES = {
    "auto": RESULT_TEMPLATE_AUTO,
    "nursery": DEFAULT_TEMPLATE_NAME,
    "nursery default": DEFAULT_TEMPLATE_NAME,
    "nursery (default)": DEFAULT_TEMPLATE_NAME,
    "primary": PRIMARY_TEMPLATE_NAME,
    "primary default": PRIMARY_TEMPLATE_NAME,
    "primary (default)": PRIMARY_TEMPLATE_NAME,
    "secondary": JUNIOR_SECONDARY_TEMPLATE_NAME,
    "secondary default": JUNIOR_SECONDARY_TEMPLATE_NAME,
    "secondary (default)": JUNIOR_SECONDARY_TEMPLATE_NAME,
    "junior secondary": JUNIOR_SECONDARY_TEMPLATE_NAME,
    "junior secondary default": JUNIOR_SECONDARY_TEMPLATE_NAME,
    "junior secondary (default)": JUNIOR_SECONDARY_TEMPLATE_NAME,
}


def normalize_template_name(template_name, allow_auto=False):
    """Keep built-in template names canonical so defaults cannot be duplicated."""
    raw_name = " ".join(str(template_name or "").strip().split())
    if not raw_name:
        return RESULT_TEMPLATE_AUTO if allow_auto else DEFAULT_TEMPLATE_NAME

    normalized = _TEMPLATE_NAME_ALIASES.get(raw_name.lower())
    if normalized == RESULT_TEMPLATE_AUTO and not allow_auto:
        return DEFAULT_TEMPLATE_NAME
    if normalized:
        return normalized

    for built_in_name in BUILT_IN_TEMPLATE_NAMES:
        if raw_name.lower() == built_in_name.lower():
            return built_in_name

    return raw_name[:120]


def list_result_template_choices(school_id=None):
    template_names = list_template_editor_templates(school_id) if school_id is not None else list(BUILT_IN_TEMPLATE_NAMES)
    return [RESULT_TEMPLATE_AUTO, *template_names]


DEFAULT_OTHER_SETTINGS = {
    "grade": {
        "type": "range",
        "title": "Grade",
        "valueHeader": "Grade",
        "footerLabel": "Keys Title",
        "footerValue": "KEYS TO RATING",
        "academicColumn": "grade",
        "keyMode": "grade",
        "rows": [
            {"range": "100-70", "value": "A"},
            {"range": "60-69", "value": "B"},
            {"range": "50-59", "value": "C"},
            {"range": "45-49", "value": "D"},
            {"range": "40-44", "value": "E"},
            {"range": "0-39", "value": "F"},
        ],
    },
    "remarks": {
        "type": "range",
        "title": "Remarks",
        "valueHeader": "Remarks",
        "footerLabel": "Keys Title",
        "footerValue": "KEYS TO RATING",
        "academicColumn": "remarks",
        "keyMode": "remarks",
        "rows": [
            {"range": "100-70", "value": "EXCELLENT"},
            {"range": "60-69", "value": "VERY GOOD"},
            {"range": "50-59", "value": "GOOD"},
            {"range": "45-49", "value": "FAIR"},
            {"range": "40-44", "value": "POOR"},
            {"range": "0-39", "value": "VERY POOR"},
        ],
    },
    "class_teacher_comments": {
        "type": "comment",
        "title": "Class Teacher's Comments",
        "valueHeader": "Comment",
        "footerLabel": "Title",
        "footerValue": "Class Teacher",
        "rowKey": "class_teacher",
        "options": {"manual": False, "name": False, "comment": True, "sign": True, "date": True},
        "rows": [
            {"range": "100-70", "value": "Excellent Result"},
            {"range": "60-69", "value": "Very Good Result, Keep it up"},
            {"range": "50-59", "value": "Good, Keep improving"},
            {"range": "45-49", "value": "Add more efforts"},
            {"range": "40-44", "value": "Be attentive and put more efforts"},
            {"range": "0-39", "value": "Not too good but there is hope for you. Try again next time"},
        ],
    },
    "headteacher_comments": {
        "type": "comment",
        "title": "Headteacher's Comments",
        "valueHeader": "Comment",
        "footerLabel": "Title",
        "footerValue": "HeadTeacher",
        "rowKey": "headteacher",
        "options": {"manual": False, "name": False, "comment": True, "sign": True, "date": True},
        "rows": [
            {"range": "100-70", "value": "Excellent Result"},
            {"range": "60-69", "value": "Very Good Result, Keep it up"},
            {"range": "50-59", "value": "Good, Keep improving"},
            {"range": "45-49", "value": "Add more efforts"},
            {"range": "40-44", "value": "Be attentive and put more efforts"},
            {"range": "0-39", "value": "Not too good but there is hope for you. Try again next time"},
        ],
    },
    "director_comments": {
        "type": "comment",
        "title": "Director's Comments",
        "valueHeader": "Comment",
        "footerLabel": "Title",
        "footerValue": "Director",
        "rowKey": "director",
        "options": {"manual": False, "name": False, "comment": False, "sign": False, "date": False},
        "rows": [
            {"range": "100-70", "value": "Excellent Result"},
            {"range": "60-69", "value": "Very Good Result, Keep it up"},
            {"range": "50-59", "value": "Good, Keep improving"},
            {"range": "45-49", "value": "Add more efforts"},
            {"range": "40-44", "value": "Be attentive and put more efforts"},
            {"range": "0-39", "value": "Not too good but there is hope for you. Try again next time"},
        ],
    },
    "promotion_status": {
        "type": "range",
        "title": "Promotion Status",
        "valueHeader": "Status",
        "previewTarget": "promotion_status",
        "rows": [
            {"range": "100-50", "value": "PROMOTED TO [promote]. CONGRATULATIONS"},
            {"range": "49-40", "value": "PROMOTED ON TRIAL TO [promote]"},
            {"range": "39-0", "value": "YOU ARE ADVISED TO REPEAT [repeat]"},
        ],
    },
    "student_position": {
        "type": "position_visibility",
        "title": "Students' Position",
        "mode": "show_all",
    },
    "score_color": {
        "type": "score_color",
        "title": "Score Color",
        "rows": [
            {"range": "0-100", "color": "Black"},
        ],
    },
    "stamp": {
        "type": "image_box",
        "title": "Stamp",
        "imageData": "",
    },
    "result_title": {
        "type": "text_box",
        "title": "Result Title",
        "value": "[SESSION] [TERM] TERM REPORT SHEET",
    },
    "footer_text": {
        "type": "footer_text",
        "title": "Footer Text",
        "value": "",
        "alignment": "center",
        "color": "#111827",
    },
    "background_image": {
        "type": "background_image",
        "title": "Background Image",
        "imageData": "",
        "transparency": 50,
        "imageSize": 100,
    },
    "student_data_preferences": {
        "type": "student_data_preferences",
        "title": "Student Data Preferences",
        "fields": [
            {"key": "name", "label": "Name", "studentReports": True, "broadsheetReports": True},
            {"key": "date_of_birth", "label": "Date Of Birth", "studentReports": True, "broadsheetReports": False},
            {"key": "sex", "label": "Sex", "studentReports": True, "broadsheetReports": False},
            {"key": "class_name", "label": "Class", "studentReports": True, "broadsheetReports": False},
            {"key": "admission_no", "label": "Admission No.", "studentReports": True, "broadsheetReports": True},
            {"key": "address", "label": "Address", "studentReports": False, "broadsheetReports": False},
            {"key": "tel", "label": "Tel", "studentReports": False, "broadsheetReports": False},
            {"key": "email", "label": "Email", "studentReports": False, "broadsheetReports": False},
            {"key": "date_of_admission", "label": "Date of Admission", "studentReports": False, "broadsheetReports": False},
            {"key": "parent_guardian_name", "label": "Parent/Guardian Name", "studentReports": False, "broadsheetReports": False},
            {"key": "state_of_origin", "label": "StateOfOrigin", "studentReports": False, "broadsheetReports": False},
            {"key": "local_govt_area", "label": "Local Govt. Area", "studentReports": False, "broadsheetReports": False},
        ],
    },
}


def get_default_template_editor_state(template_name=DEFAULT_TEMPLATE_NAME):
    template_name = normalize_template_name(template_name)
    return {
        "template_name": template_name,
        "selected_models": get_default_selected_models(),
        "theme_color": DEFAULT_THEME_COLOR,
        "other_settings": deepcopy(DEFAULT_OTHER_SETTINGS),
        "customizations": {},
    }


def _state_path(school_id, template_name):
    slug = slugify(normalize_template_name(template_name)) or "default"
    return settings.MEDIA_ROOT / "template_editor" / f"school_{int(school_id)}" / f"{slug}.json"


def _legacy_state_paths(school_id, template_name):
    if normalize_template_name(template_name) != JUNIOR_SECONDARY_TEMPLATE_NAME:
        return []
    directory = settings.MEDIA_ROOT / "template_editor" / f"school_{int(school_id)}"
    return [directory / f"{slugify('Secondary (Default)')}.json"]


def _state_directory(school_id):
    return settings.MEDIA_ROOT / "template_editor" / f"school_{int(school_id)}"


def _deep_merge(base, override):
    merged = deepcopy(base)
    if not isinstance(override, dict):
        return merged

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _json_safe(value, depth=0):
    if depth > 8:
        return None
    if isinstance(value, dict):
        return {
            str(key)[:120]: _json_safe(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_json_safe(item, depth + 1) for item in value[:200]]
    if isinstance(value, str):
        return value[:300000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:2000]


def _normalize_theme_color(value):
    value = str(value or "").strip().lower()
    if len(value) == 7 and value.startswith("#"):
        hex_part = value[1:]
        if all(char in "0123456789abcdef" for char in hex_part):
            return value
    return DEFAULT_THEME_COLOR


def sanitize_template_editor_state(payload, template_name=DEFAULT_TEMPLATE_NAME):
    template_name = normalize_template_name(template_name)
    default_state = get_default_template_editor_state(template_name)
    payload = _json_safe(payload if isinstance(payload, dict) else {})
    state = _deep_merge(default_state, payload)
    state["template_name"] = template_name
    state["theme_color"] = _normalize_theme_color(state.get("theme_color"))
    state["selected_models"] = normalize_selected_models(
        _deep_merge(default_state["selected_models"], state.get("selected_models", {}))
    )
    state["other_settings"] = _deep_merge(
        default_state["other_settings"],
        state.get("other_settings", {}),
    )
    state["customizations"] = _json_safe(state.get("customizations", {})) or {}
    return state


def load_template_editor_state(school_id, template_name=DEFAULT_TEMPLATE_NAME):
    template_name = normalize_template_name(template_name)
    paths = [_state_path(school_id, template_name), *_legacy_state_paths(school_id, template_name)]
    path = next((candidate for candidate in paths if candidate.exists()), None)
    if not path:
        return get_default_template_editor_state(template_name)

    try:
        saved_state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return get_default_template_editor_state(template_name)

    return sanitize_template_editor_state(saved_state, template_name)


def save_template_editor_state(school_id, template_name, payload):
    template_name = normalize_template_name(template_name)
    state = sanitize_template_editor_state(payload, template_name)
    path = _state_path(school_id, template_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    return state


def list_template_editor_templates(school_id):
    names = list(BUILT_IN_TEMPLATE_NAMES)
    directory = _state_directory(school_id)

    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                saved_state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            name = normalize_template_name(saved_state.get("template_name"))
            if name and name not in names:
                names.append(name)

    return names
