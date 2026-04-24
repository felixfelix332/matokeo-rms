import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render

from .selectors_template_editor import get_school, serialize_school
from .services.template_editor_state import (
    DEFAULT_TEMPLATE_NAME,
    list_template_editor_templates,
    load_template_editor_state,
    save_template_editor_state,
)
from .services.template_preview import (
    build_combined_preview_variants,
    build_layout_sections,
    build_preview_state,
    build_preview_sections,
    get_default_selected_models,
)
from .views import _build_school_shell_context


REMOVAL_MESSAGE = "Template Editor has been removed from this project."

SECTION_5_CUSTOMIZE = {
    "title": "Skills Development and Behaviourial Attributes",
    "models": {
        "model_1": {
            "rating_title": "Keys To Rating",
            "ratings": [
                {"value": 1, "label": "Very Poor"},
                {"value": 2, "label": "Poor"},
                {"value": 3, "label": "Fair"},
                {"value": 4, "label": "Good"},
                {"value": 5, "label": "Excellent"},
            ],
            "categories": [
                {
                    "key": "affective_traits",
                    "label": "AFFECTIVE TRAITS",
                    "side": "left",
                    "items": [
                        {"label": "Attentiveness", "rating": 3},
                        {"label": "Attitude of School work", "rating": 4},
                        {"label": "Cooperation with others", "rating": 3},
                        {"label": "Emotion Stability", "rating": 5},
                        {"label": "Health", "rating": 1},
                        {"label": "Leadership", "rating": 4},
                        {"label": "Attendance", "rating": 4},
                        {"label": "Neatness", "rating": 4},
                        {"label": "Perseverance", "rating": 5},
                        {"label": "Politeness", "rating": 1},
                        {"label": "Punctuality", "rating": 3},
                        {"label": "Speaking / Writing", "rating": 3},
                    ],
                },
                {
                    "key": "psychomotor_skills",
                    "label": "PSYCHOMOTOR SKILLS",
                    "side": "right",
                    "items": [
                        {"label": "Drawing & Painting", "rating": 2},
                        {"label": "Handling of Tools", "rating": 2},
                        {"label": "Games", "rating": 5},
                        {"label": "Handwriting", "rating": 2},
                        {"label": "Music", "rating": 4},
                        {"label": "Verbal Fluency", "rating": 3},
                    ],
                },
            ],
        },
        "model_2": {
            "rating_title": "Keys to Rating on Skills Development and Behaviourial Attributes",
            "ratings": [
                {"value": 5, "label": "Excellent"},
                {"value": 4, "label": "High Level"},
                {"value": 3, "label": "Acceptable Level"},
                {"value": 2, "label": "Minimal Level"},
                {"value": 1, "label": "No Trial"},
            ],
            "categories": [
                {
                    "key": "personal_development",
                    "label": "PERSONAL DEV.",
                    "items": [
                        {"label": "Obedience", "point": 4},
                        {"label": "Honesty", "point": 4},
                        {"label": "Self Control", "point": 5},
                        {"label": "Self-Reliance", "point": 3},
                        {"label": "Initiative", "point": 2},
                    ],
                },
                {
                    "key": "responsibility",
                    "label": "SENSE OF RESPONSIBILITY",
                    "items": [
                        {"label": "Punctuality", "point": 3},
                        {"label": "Neatness", "point": 4},
                        {"label": "Perseverance", "point": 3},
                        {"label": "Attendance", "point": 2},
                        {"label": "Attentiveness", "point": 1},
                    ],
                },
                {
                    "key": "social_development",
                    "label": "SOCIAL DEV.",
                    "items": [
                        {"label": "Politeness", "point": 4},
                        {"label": "Consideration for others", "point": 2},
                        {"label": "Sociability", "point": 4},
                        {"label": "Promptness", "point": 5},
                        {"label": "Sense of Value", "point": 5},
                    ],
                },
                {
                    "key": "psychomotor_development",
                    "label": "PSYCHOMOTOR DEV.",
                    "items": [
                        {"label": "Reading & Writing", "point": 1},
                        {"label": "Verbal Communication", "point": 2},
                        {"label": "Sports & Games", "point": 1},
                        {"label": "Inquisitiveness", "point": 2},
                        {"label": "Dexterity", "point": 5},
                    ],
                },
            ],
        },
        "model_3": {
            "rating_title": "Keys To Rating",
            "ratings": [
                {"value": 1, "label": "Not Yet"},
                {"value": 2, "label": "Some of the Time"},
                {"value": 3, "label": "Most of the Time"},
                {"value": 4, "label": "All of the Time"},
            ],
            "categories": [
                {
                    "key": "academic_skills",
                    "label": "ACADEMIC SKILLS",
                    "side": "left",
                    "items": [
                        {"label": "Can sound letter A to Z", "rating": 3},
                        {"label": "Able to rote count from 1 to 10", "rating": 4},
                        {"label": "Able to identify numbers from 1 to 10", "rating": 4},
                        {"label": "Can colour given objects", "rating": 4},
                        {"label": "Pupils can sound letter A to J", "rating": 3},
                        {"label": "Able to put blocks in and out of a box", "rating": 1},
                    ],
                },
                {
                    "key": "social_courtesy",
                    "label": "DEVELOPMENT OF SOCIAL SKILLS AND COURTESY",
                    "side": "left",
                    "items": [
                        {"label": "Greeting people", "rating": 4},
                        {
                            "label": "Use of magic words (Thank You, Excuse me, Please, Sorry)",
                            "rating": 2,
                        },
                        {"label": "Conduct with a visitor", "rating": 2},
                        {"label": "Speaking to a group", "rating": 3},
                        {"label": "Behaviour on outing", "rating": 2},
                        {"label": "Helping out", "rating": 4},
                        {"label": "Table manners and use of eating utensils", "rating": 2},
                    ],
                },
                {
                    "key": "emotional_development",
                    "label": "EMOTIONAL DEVELOPMENT",
                    "side": "left",
                    "items": [
                        {"label": "Independent of parent", "rating": 3},
                        {"label": "Independent of teacher", "rating": 3},
                        {"label": "Can cope with class activities", "rating": 4},
                    ],
                },
                {
                    "key": "music_art_story",
                    "label": "MUSIC/ART/STORY SKILLS",
                    "side": "left",
                    "items": [
                        {"label": "Can look at pictures in several books", "rating": 1},
                        {
                            "label": "Participates in simple group activities e.g. dancing, clapping, singing",
                            "rating": 2,
                        },
                        {"label": "Able to repeat rhymes, alphabets, numbers", "rating": 2},
                    ],
                },
                {
                    "key": "motor_skills",
                    "label": "MOTOR SKILLS",
                    "side": "right",
                    "items": [
                        {"label": "Picks up toys he/she has dropped", "rating": 3},
                        {"label": "Can hold a crayon with good tensile grip", "rating": 3},
                        {
                            "label": "Can turn pages of a book 2 or 3 pages at a time",
                            "rating": 4,
                        },
                        {"label": "Can group objects", "rating": 3},
                        {"label": "Able to roll a ball in imitation of an adult", "rating": 4},
                        {"label": "Can pick up an object without dropping", "rating": 2},
                    ],
                },
                {
                    "key": "care_of_self",
                    "label": "EXERCISE FOR THE CARE OF SELF",
                    "side": "right",
                    "items": [
                        {"label": "Dries hands", "rating": 4},
                        {"label": "Coughs with hand over mouth", "rating": 4},
                        {"label": "Sneezes with hand over mouth", "rating": 4},
                        {"label": "Yawns with hand over mouth", "rating": 4},
                        {"label": "Washes hands", "rating": 4},
                    ],
                },
                {
                    "key": "self_help",
                    "label": "SELF-HELP SKILLS",
                    "side": "right",
                    "items": [
                        {
                            "label": "Can hold a cup with two hands and drinks without assistance",
                            "rating": 1,
                        },
                        {"label": "Can indicate toilet needs", "rating": 3},
                        {"label": "Can hold out arms and legs for dressing", "rating": 2},
                        {"label": "Able to use spoon without spilling", "rating": 2},
                    ],
                },
                {
                    "key": "social_play",
                    "label": "SOCIAL AND PLAY SKILLS",
                    "side": "right",
                    "items": [
                        {"label": "Responds to his/her name often", "rating": 3},
                        {"label": "Can imitate simple actions", "rating": 4},
                        {"label": "Able to play by him/herself", "rating": 4},
                        {"label": "Helps put things away", "rating": 3},
                        {"label": "Can refer to him/herself by name", "rating": 3},
                    ],
                },
                {
                    "key": "understanding_language",
                    "label": "UNDERSTANDING LANGUAGE",
                    "side": "right",
                    "items": [
                        {"label": "Can imitate sounds", "rating": 4},
                        {"label": "Responds to different sounds made", "rating": 3},
                        {
                            "label": "Responds to simple direction accompanied by gestures",
                            "rating": 4,
                        },
                        {
                            "label": "Able to responds to specific words by showing what was named",
                            "rating": 4,
                        },
                        {
                            "label": "Can look at pictures in a book, pointing to or naming objects",
                            "rating": 4,
                        },
                        {"label": "Listens to and follows directions", "rating": 2},
                    ],
                },
            ],
        },
    },
}


def _require_school_access(request, school_id):
    if not request.user.is_authenticated and not request.session.get("teacher_id"):
        return None, redirect("accounts:login")
    school = get_school(school_id)
    if not school:
        messages.error(request, "That school could not be found.")
        return None, redirect("accounts:add_school")
    request.session["school_id"] = int(school.id)
    request.session["school_name"] = school.name
    return school, None


def _read_selected_models(request, template_state=None):
    selected_models = get_default_selected_models()
    saved_models = (template_state or {}).get("selected_models", {})

    for section_key in selected_models:
        value = (saved_models.get(section_key) or "").strip().lower()
        if value:
            selected_models[section_key] = value

    for section_key in selected_models:
        value = (request.GET.get(section_key) or "").strip().lower()
        if value:
            selected_models[section_key] = value

    return selected_models


def _build_other_settings(template_state):
    theme_color = (template_state or {}).get("theme_color") or "#d4147a"
    return [
        {"key": "theme_color", "label": "Theme Color", "type": "color", "value": theme_color},
        {"key": "grade", "label": "Grade", "type": "edit"},
        {"key": "remarks", "label": "Remarks", "type": "edit"},
        {"key": "class_teacher_comments", "label": "Class Teacher's Comments", "type": "edit"},
        {"key": "headteacher_comments", "label": "Headteacher's Comments", "type": "edit"},
        {"key": "director_comments", "label": "Director's Comments", "type": "edit"},
        {"key": "promotion_status", "label": "Promotion Status", "type": "edit"},
        {"key": "student_position", "label": "Student's Position", "type": "edit"},
        {"key": "score_color", "label": "Score Color", "type": "edit"},
        {"key": "stamp", "label": "Stamp", "type": "edit"},
        {"key": "result_title", "label": "Result Title", "type": "edit"},
        {"key": "footer_text", "label": "Footer Text", "type": "edit"},
        {"key": "background_image", "label": "Background Image", "type": "edit"},
        {"key": "student_data_preferences", "label": "Student Data Preferences", "type": "edit"},
        {"label": "Jumbotron Header Background", "type": "check", "checked": True},
        {"label": "Autofill Attributes / Skills", "type": "check", "checked": True},
    ]


def template_editor_view(request, school_id):
    school, redirect_response = _require_school_access(request, school_id)
    if redirect_response:
        return redirect_response
    selected_template = (request.GET.get("template") or DEFAULT_TEMPLATE_NAME).strip() or DEFAULT_TEMPLATE_NAME

    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON payload."}, status=400)

        selected_template = (payload.get("template_name") or selected_template).strip() or DEFAULT_TEMPLATE_NAME
        saved_state = save_template_editor_state(
            school.id,
            selected_template,
            payload.get("state") or {},
        )
        return JsonResponse({"ok": True, "state": saved_state})

    active_tab = (request.GET.get("tab") or "layout").strip().lower()
    if active_tab not in {"layout", "other"}:
        active_tab = "layout"
    school_data = serialize_school(school)
    template_options = list_template_editor_templates(school.id)
    if selected_template not in template_options:
        selected_template = DEFAULT_TEMPLATE_NAME
    template_state = load_template_editor_state(school.id, selected_template)
    selected_models = _read_selected_models(request, template_state)
    template_state["selected_models"] = selected_models
    section_1_saved = template_state.get("customizations", {}).get("section_1_model_3", {})
    context = {
        **_build_school_shell_context(school_data, active_key="template"),
        "removal_message": REMOVAL_MESSAGE,
        "current_year": 2026,
        "active_tab": active_tab,
        "template_options": template_options,
        "selected_template": selected_template,
        "preview_enabled": True,
        "preview_disabled_reason": "",
        "selected_models": selected_models,
        "template_editor_state": template_state,
        "layout_sections": build_layout_sections(selected_models),
        "preview_sections": build_preview_sections(selected_models),
        "combined_section_2_variants": build_combined_preview_variants(selected_models),
        "preview_state": build_preview_state(selected_models),
        "section_1_model_3_customize": {
            "title": "School Details 2",
            "school_name": section_1_saved.get("school_name") or "ÉCOLE INTERNATIONALE HISGRACE",
            "other_details": section_1_saved.get("other_details") or "(PRIMAIRE)\nRue Williams, Île Victoria, Lagos\nDevise : Sa Grâce suffit\nelgracezb@gmail.com",
        },
        "section_2_customize": {
            "title": "Student Details",
            "defaults": {
                "name": "John Doe Essien",
                "date_of_birth": "02/12/1992",
                "sex": "MALE",
                "class_name": "",
                "admission_no": "HG123",
            },
        },
        "section_3_customize": {
            "title": "Result Headers",
            "model_meta": {
                "model_1": {
                    "subtitle": "Mostly used by Nigerian Users",
                    "show_grading_button": True,
                },
                "model_2": {
                    "subtitle": "Mostly used by Cameroonian Users",
                    "show_grading_button": False,
                },
                "model_3": {
                    "subtitle": "Mostly used by Sierra Leonean Users",
                    "show_grading_button": False,
                },
                "model_4": {
                    "subtitle": "Mostly used by Ugandan Users",
                    "show_grading_button": True,
                    "grading_button_label": "Division",
                    "grading_modal": "division",
                },
                "model_5": {
                    "subtitle": "Mostly used by Ugandan Users",
                    "show_grading_button": False,
                },
                "model_6": {
                    "subtitle": "Mostly used by Nigerian Users",
                    "show_grading_button": True,
                },
                "model_7": {
                    "subtitle": "Mostly used by Ugandan Users",
                    "show_grading_button": True,
                    "grading_button_label": "Division",
                    "grading_modal": "division",
                },
                "model_8": {
                    "subtitle": "Mostly used by Nigerian Users",
                    "show_grading_button": True,
                },
            },
            "headers": [
                {"key": "ca", "label": "CONTINUOUS ASSESSMENT (CA)", "score_obtainable": "20", "columns": "1", "models": ["model_1", "model_2"]},
                {"key": "coef", "label": "COEF.", "score_obtainable": "", "columns": "", "models": ["model_2"]},
                {"key": "marks_average", "label": "MARKS AVERAGE", "score_obtainable": "20", "columns": "", "models": ["model_2"]},
                {"key": "competences_developed", "label": "COMPETENCES DEVELOPED", "score_obtainable": "", "columns": "", "models": ["model_2"]},
                {"key": "attendance", "label": "ATTENDANCE", "score_obtainable": "10", "columns": "", "models": ["model_2"]},
                {"key": "class_work", "label": "CLASS WORK", "score_obtainable": "10", "columns": "", "models": ["model_2"]},
                {"key": "home_work", "label": "HOME WORK", "score_obtainable": "10", "columns": "", "models": ["model_2"]},
                {"key": "assignment", "label": "ASSIGNMENT", "score_obtainable": "10", "columns": "", "models": ["model_2"]},
                {"key": "activities", "label": "ACTIVITIES", "score_obtainable": "10", "columns": "", "models": ["model_2"]},
                {"key": "assessment", "label": "ASSESSMENT", "score_obtainable": "10", "columns": "", "models": ["model_2"]},
                {"key": "project", "label": "PROJECT", "score_obtainable": "10", "columns": "", "models": ["model_2"]},
                {"key": "exam", "label": "EXAMINATION", "score_obtainable": "60", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "total_score", "label": "TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "cum_total_score", "label": "CUM. TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "percentage", "label": "PERCENTAGE", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "position_in_subject", "label": "POSITION IN SUBJECT", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "class_average", "label": "CLASS AVERAGE", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "remarks", "label": "REMARKS", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "sign", "label": "SIGN.", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "subject_teacher", "label": "SUBJECT TEACHER", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "grade", "label": "GRADE", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "class_highest", "label": "CLASS HIGHEST", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "class_lowest", "label": "CLASS LOWEST", "score_obtainable": "", "columns": "", "models": ["model_1", "model_2"]},
                {"key": "ca", "label": "CONTINUOUS ASSESSMENT (CA)", "score_obtainable": "20", "columns": "1", "models": ["model_4"]},
                {"key": "total_score", "label": "TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "exam", "label": "EXAMINATION", "score_obtainable": "60", "columns": "", "models": ["model_4"]},
                {"key": "cum_total_score", "label": "CUM. TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "percentage", "label": "PERCENTAGE", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "position_in_subject", "label": "POSITION IN SUBJECT", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "class_average", "label": "CLASS AVERAGE", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "remarks", "label": "REMARKS", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "sign", "label": "SIGN.", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "subject_teacher", "label": "SUBJECT TEACHER", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "grade", "label": "GRADE", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "class_highest", "label": "CLASS HIGHEST", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "class_lowest", "label": "CLASS LOWEST", "score_obtainable": "", "columns": "", "models": ["model_4"]},
                {"key": "ca", "label": "CHAPTER (CA)", "score_obtainable": "20", "columns": "1", "models": ["model_5"]},
                {"key": "average", "label": "AVERAGE", "score_obtainable": "", "columns": "", "models": ["model_5"]},
                {"key": "position_in_subject", "label": "POSITION IN SUBJECT", "score_obtainable": "", "columns": "", "models": ["model_5"]},
                {"key": "class_average", "label": "CLASS AVERAGE", "score_obtainable": "", "columns": "", "models": ["model_5"]},
                {"key": "descriptor", "label": "DESCRIPTOR", "score_obtainable": "", "columns": "", "models": ["model_5"]},
                {"key": "sign", "label": "SIGN.", "score_obtainable": "", "columns": "", "models": ["model_5"]},
                {"key": "subject_teacher", "label": "SUBJECT TEACHER", "score_obtainable": "", "columns": "", "models": ["model_5"]},
                {"key": "identifier", "label": "IDENTIFIER", "score_obtainable": "", "columns": "", "models": ["model_5"]},
                {"key": "class_highest", "label": "CLASS HIGHEST", "score_obtainable": "", "columns": "", "models": ["model_5"]},
                {"key": "class_lowest", "label": "CLASS LOWEST", "score_obtainable": "", "columns": "", "models": ["model_5"]},
                {"key": "ca", "label": "CONTINUOUS ASSESSMENT (CA)", "score_obtainable": "20", "columns": "1", "models": ["model_6"]},
                {"key": "attendance", "label": "ATTENDANCE", "score_obtainable": "10", "columns": "", "models": ["model_6"]},
                {"key": "class_work", "label": "CLASS WORK", "score_obtainable": "10", "columns": "", "models": ["model_6"]},
                {"key": "home_work", "label": "HOME WORK", "score_obtainable": "10", "columns": "", "models": ["model_6"]},
                {"key": "assignment", "label": "ASSIGNMENT", "score_obtainable": "10", "columns": "", "models": ["model_6"]},
                {"key": "activities", "label": "ACTIVITIES", "score_obtainable": "10", "columns": "", "models": ["model_6"]},
                {"key": "assessment", "label": "ASSESSMENT", "score_obtainable": "10", "columns": "", "models": ["model_6"]},
                {"key": "project", "label": "PROJECT", "score_obtainable": "10", "columns": "", "models": ["model_6"]},
                {"key": "percentage", "label": "PERCENTAGE", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "exam", "label": "EXAMINATION", "score_obtainable": "60", "columns": "", "models": ["model_6"]},
                {"key": "position_in_subject", "label": "POSITION IN SUBJECT", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "total_score", "label": "TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "class_average", "label": "CLASS AVERAGE", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "remarks", "label": "REMARKS", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "cum_total_score", "label": "CUM. TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "sign", "label": "SIGN.", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "subject_teacher", "label": "SUBJECT TEACHER", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "grade", "label": "GRADE", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "class_highest", "label": "CLASS HIGHEST", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "class_lowest", "label": "CLASS LOWEST", "score_obtainable": "", "columns": "", "models": ["model_6"]},
                {"key": "bot_exams", "label": "B. O. T. EXAMS", "score_obtainable": "10", "columns": "", "models": ["model_7"]},
                {"key": "midterm_exams", "label": "MID-TERM EXAMS", "score_obtainable": "10", "columns": "", "models": ["model_7"]},
                {"key": "average", "label": "AVERAGE", "score_obtainable": "", "columns": "", "models": ["model_7"]},
                {"key": "end_of_term_exams", "label": "END OF TERM EXAMS", "score_obtainable": "60", "columns": "", "models": ["model_7"]},
                {"key": "position_in_subject", "label": "POSITION IN SUBJECT", "score_obtainable": "", "columns": "", "models": ["model_7"]},
                {"key": "total_score", "label": "TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_7"]},
                {"key": "remarks", "label": "REMARKS", "score_obtainable": "", "columns": "", "models": ["model_7"]},
                {"key": "sign", "label": "SIGN.", "score_obtainable": "", "columns": "", "models": ["model_7"]},
                {"key": "subject_teacher", "label": "SUBJECT TEACHER", "score_obtainable": "", "columns": "", "models": ["model_7"]},
                {"key": "grade", "label": "GRADE", "score_obtainable": "", "columns": "", "models": ["model_7"]},
                {"key": "ca", "label": "CONTINUOUS ASSESSMENT (CA)", "score_obtainable": "20", "columns": "1", "models": ["model_8"]},
                {"key": "unit", "label": "UNIT", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "attendance", "label": "ATTENDANCE", "score_obtainable": "10", "columns": "", "models": ["model_8"]},
                {"key": "class_work", "label": "CLASS WORK", "score_obtainable": "10", "columns": "", "models": ["model_8"]},
                {"key": "home_work", "label": "HOME WORK", "score_obtainable": "10", "columns": "", "models": ["model_8"]},
                {"key": "assignment", "label": "ASSIGNMENT", "score_obtainable": "10", "columns": "", "models": ["model_8"]},
                {"key": "activities", "label": "ACTIVITIES", "score_obtainable": "10", "columns": "", "models": ["model_8"]},
                {"key": "assessment", "label": "ASSESSMENT", "score_obtainable": "10", "columns": "", "models": ["model_8"]},
                {"key": "project", "label": "PROJECT", "score_obtainable": "10", "columns": "", "models": ["model_8"]},
                {"key": "exam", "label": "EXAMINATION", "score_obtainable": "60", "columns": "", "models": ["model_8"]},
                {"key": "total_score", "label": "TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "cum_total_score", "label": "CUM. TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "percentage", "label": "PERCENTAGE", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "position_in_subject", "label": "POSITION IN SUBJECT", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "class_average", "label": "CLASS AVERAGE", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "remarks", "label": "REMARKS", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "point", "label": "POINT", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "sign", "label": "SIGN.", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "subject_teacher", "label": "SUBJECT TEACHER", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "grade", "label": "GRADE", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "class_highest", "label": "CLASS HIGHEST", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "class_lowest", "label": "CLASS LOWEST", "score_obtainable": "", "columns": "", "models": ["model_8"]},
                {"key": "max", "label": "MAX", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "test", "label": "TEST", "score_obtainable": "30", "columns": "3", "models": ["model_3"]},
                {"key": "percentage", "label": "PERCENTAGE", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "position_in_subject", "label": "POSITION IN SUBJECT", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "total_score", "label": "TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "class_average", "label": "CLASS AVERAGE", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "mean", "label": "MEAN", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "remarks", "label": "REMARKS", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "cum_total_score", "label": "CUM. TOTAL SCORE", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "sign", "label": "SIGN.", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "subject_teacher", "label": "SUBJECT TEACHER", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "grade", "label": "GRADE", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "class_highest", "label": "CLASS HIGHEST", "score_obtainable": "", "columns": "", "models": ["model_3"]},
                {"key": "class_lowest", "label": "CLASS LOWEST", "score_obtainable": "", "columns": "", "models": ["model_3"]},
            ],
            "model_configs": {
                "model_1": {
                    "visibility": {
                        "ca": True,
                        "exam": True,
                        "total_score": True,
                        "cum_total_score": True,
                        "percentage": True,
                        "position_in_subject": True,
                        "class_average": True,
                        "remarks": True,
                        "sign": True,
                        "subject_teacher": False,
                        "grade": False,
                        "class_highest": False,
                        "class_lowest": False,
                    },
                    "scores": {
                        "ca": "30",
                        "exam": "60",
                    },
                    "columns": {
                        "ca": "3",
                    },
                },
                "model_2": {
                    "visibility": {
                        "ca": True,
                        "coef": True,
                        "marks_average": True,
                        "competences_developed": False,
                        "attendance": False,
                        "class_work": False,
                        "home_work": False,
                        "assignment": False,
                        "activities": False,
                        "assessment": False,
                        "project": False,
                        "exam": True,
                        "total_score": True,
                        "cum_total_score": True,
                        "percentage": True,
                        "position_in_subject": True,
                        "class_average": True,
                        "remarks": True,
                        "sign": True,
                        "subject_teacher": False,
                        "grade": False,
                        "class_highest": False,
                        "class_lowest": False,
                    },
                    "scores": {
                        "ca": "20",
                        "marks_average": "20",
                        "attendance": "10",
                        "class_work": "10",
                        "home_work": "10",
                        "assignment": "10",
                        "activities": "10",
                        "assessment": "10",
                        "project": "10",
                        "exam": "60",
                    },
                    "columns": {
                        "ca": "1",
                    },
                },
                "model_3": {
                    "visibility": {
                        "max": True,
                        "test": True,
                        "percentage": True,
                        "position_in_subject": True,
                        "total_score": True,
                        "class_average": True,
                        "mean": False,
                        "remarks": True,
                        "cum_total_score": True,
                        "sign": True,
                        "subject_teacher": False,
                        "grade": False,
                        "class_highest": False,
                        "class_lowest": False,
                    },
                    "scores": {
                        "test": "30",
                    },
                    "columns": {
                        "test": "1",
                    },
                },
                "model_4": {
                    "visibility": {
                        "ca": True,
                        "exam": True,
                        "total_score": True,
                        "cum_total_score": True,
                        "percentage": True,
                        "position_in_subject": True,
                        "class_average": True,
                        "remarks": True,
                        "sign": True,
                        "subject_teacher": False,
                        "grade": False,
                        "class_highest": False,
                        "class_lowest": False,
                    },
                    "scores": {
                        "ca": "20",
                        "exam": "60",
                    },
                    "columns": {
                        "ca": "1",
                    },
                },
                "model_5": {
                    "visibility": {
                        "ca": True,
                        "average": True,
                        "position_in_subject": True,
                        "class_average": True,
                        "descriptor": True,
                        "sign": True,
                        "subject_teacher": False,
                        "identifier": False,
                        "class_highest": False,
                        "class_lowest": False,
                    },
                    "scores": {
                        "ca": "20",
                    },
                    "columns": {
                        "ca": "1",
                    },
                },
                "model_6": {
                    "visibility": {
                        "ca": True,
                        "attendance": False,
                        "class_work": False,
                        "home_work": False,
                        "assignment": False,
                        "activities": False,
                        "assessment": False,
                        "project": False,
                        "percentage": True,
                        "exam": True,
                        "position_in_subject": True,
                        "total_score": True,
                        "class_average": True,
                        "remarks": True,
                        "cum_total_score": True,
                        "sign": True,
                        "subject_teacher": False,
                        "grade": False,
                        "class_highest": False,
                        "class_lowest": False,
                    },
                    "scores": {
                        "ca": "20",
                        "attendance": "10",
                        "class_work": "10",
                        "home_work": "10",
                        "assignment": "10",
                        "activities": "10",
                        "assessment": "10",
                        "project": "10",
                        "exam": "60",
                    },
                    "columns": {
                        "ca": "1",
                    },
                },
                "model_7": {
                    "visibility": {
                        "bot_exams": True,
                        "midterm_exams": True,
                        "average": True,
                        "end_of_term_exams": True,
                        "position_in_subject": True,
                        "total_score": True,
                        "remarks": True,
                        "sign": True,
                        "subject_teacher": False,
                        "grade": False,
                    },
                    "scores": {
                        "bot_exams": "10",
                        "midterm_exams": "10",
                        "end_of_term_exams": "60",
                    },
                    "columns": {},
                },
                "model_8": {
                    "visibility": {
                        "ca": True,
                        "unit": True,
                        "attendance": False,
                        "class_work": False,
                        "home_work": False,
                        "assignment": False,
                        "activities": False,
                        "assessment": False,
                        "project": False,
                        "exam": True,
                        "total_score": True,
                        "cum_total_score": True,
                        "percentage": True,
                        "position_in_subject": True,
                        "class_average": True,
                        "remarks": True,
                        "point": True,
                        "sign": True,
                        "subject_teacher": False,
                        "grade": False,
                        "class_highest": False,
                        "class_lowest": False,
                    },
                    "scores": {
                        "ca": "20",
                        "attendance": "10",
                        "class_work": "10",
                        "home_work": "10",
                        "assignment": "10",
                        "activities": "10",
                        "assessment": "10",
                        "project": "10",
                        "exam": "60",
                    },
                    "columns": {
                        "ca": "1",
                    },
                },
            },
        },
        "section_5_customize": SECTION_5_CUSTOMIZE,
        "other_settings": _build_other_settings(template_state),
    }
    return render(request, "accounts/template_editor_disabled.html", context)
