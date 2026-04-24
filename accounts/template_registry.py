from collections import OrderedDict


# Contributor extension point:
# Add report-card section models here first, then add the matching preview template.
# Keep section coordination explicit so one model does not silently replace another
# section's source of truth.
TEMPLATE_SECTION_REGISTRY = OrderedDict(
    [
        (
            "section_1",
            {
                "title": "Section 1 (School Details)",
                "default_model": "model_2",
                "show_extra_toggle": False,
                "extra_enabled": False,
                "models": OrderedDict(
                    [
                        (
                            "model_1",
                            {
                                "label": "Model 1",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_1/model_1.html",
                            },
                        ),
                        (
                            "model_2",
                            {
                                "label": "Model 2",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_1/model_2.html",
                            },
                        ),
                        (
                            "model_3",
                            {
                                "label": "Model 3",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_1/model_3.html",
                                "customize_mode": "section1_model3",
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "section_2",
            {
                "title": "Section 2 (Student Details)",
                "default_model": "model_1",
                "show_extra_toggle": False,
                "extra_enabled": False,
                "models": OrderedDict(
                    [
                        (
                            "model_1",
                            {
                                "label": "Model 1",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_1.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_1.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                        (
                            "model_2",
                            {
                                "label": "Model 2",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_2.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_2.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                        (
                            "model_3",
                            {
                                "label": "Model 3",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_3.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_3.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                        (
                            "model_4",
                            {
                                "label": "Model 4",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_4.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_4.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                        (
                            "model_5",
                            {
                                "label": "Model 5",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_5.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_5.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                        (
                            "model_6",
                            {
                                "label": "Model 6",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_6.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_6.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                        (
                            "model_7",
                            {
                                "label": "Model 7",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_7.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_7.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                        (
                            "model_8",
                            {
                                "label": "Model 8",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_8.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_8.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                        (
                            "model_9",
                            {
                                "label": "Model 9",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_9.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_9.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                        (
                            "model_10",
                            {
                                "label": "Model 10",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_2/model_10.html",
                                "combined_preview_templates": {
                                    "section_3:model_3": "accounts/template_editor/combined/section_2_with_section_3_model_3/model_10.html",
                                },
                                "customize_mode": "section2_student_details",
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "section_3",
            {
                "title": "Section 3 (Academic Performance)",
                "default_model": "model_1",
                "show_extra_toggle": True,
                "extra_enabled": True,
                "models": OrderedDict(
                    [
                        (
                            "model_1",
                            {
                                "label": "Model 1",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_3/model_1.html",
                                "customize_mode": "section3_headers",
                            },
                        ),
                        (
                            "model_2",
                            {
                                "label": "Model 2",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_3/model_2.html",
                                "customize_mode": "section3_headers",
                            },
                        ),
                        (
                            "model_3",
                            {
                                "label": "Model 3",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_3/model_3.html",
                                "customize_mode": "section3_headers",
                            },
                        ),
                        (
                            "model_4",
                            {
                                "label": "Model 4",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_3/model_4.html",
                                "customize_mode": "section3_headers",
                            },
                        ),
                        (
                            "model_5",
                            {
                                "label": "Model 5",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_3/model_5.html",
                                "customize_mode": "section3_headers",
                            },
                        ),
                        (
                            "model_6",
                            {
                                "label": "Model 6",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_3/model_6.html",
                                "customize_mode": "section3_headers",
                            },
                        ),
                        (
                            "model_7",
                            {
                                "label": "Model 7",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_3/model_7.html",
                                "customize_mode": "section3_headers",
                            },
                        ),
                        (
                            "model_8",
                            {
                                "label": "Model 8",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_3/model_8.html",
                                "customize_mode": "section3_headers",
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "section_4",
            {
                "title": "Section 4 (Grade)",
                "default_model": "model_1",
                "show_extra_toggle": False,
                "extra_enabled": False,
                "models": OrderedDict(
                    [
                        (
                            "none",
                            {
                                "label": "None",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_4/none.html",
                            },
                        ),
                        (
                            "model_1",
                            {
                                "label": "Model 1",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_4/model_1.html",
                            },
                        ),
                        (
                            "model_2",
                            {
                                "label": "Model 2",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_4/model_2.html",
                            },
                        ),
                        (
                            "model_3",
                            {
                                "label": "Model 3",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_4/model_3.html",
                            },
                        ),
                        (
                            "model_4",
                            {
                                "label": "Model 4",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_4/model_4.html",
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "section_5",
            {
                "title": "Section 5 (Attributes/Skills)",
                "default_model": "model_3",
                "show_extra_toggle": False,
                "extra_enabled": False,
                "models": OrderedDict(
                    [
                        (
                            "none",
                            {
                                "label": "None",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_5/none.html",
                            },
                        ),
                        (
                            "model_1",
                            {
                                "label": "Model 1",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_5/model_1.html",
                                "customize_mode": "section5_skills",
                            },
                        ),
                        (
                            "model_2",
                            {
                                "label": "Model 2",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_5/model_2.html",
                                "customize_mode": "section5_skills",
                            },
                        ),
                        (
                            "model_3",
                            {
                                "label": "Model 3",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_5/model_3.html",
                                "customize_mode": "section5_skills",
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "section_6",
            {
                "title": "Section 6 (Comment)",
                "default_model": "model_1",
                "show_extra_toggle": False,
                "extra_enabled": False,
                "models": OrderedDict(
                    [
                        (
                            "none",
                            {
                                "label": "None",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_6/none.html",
                            },
                        ),
                        (
                            "model_1",
                            {
                                "label": "Model 1",
                                "enabled": True,
                                "preview_template": "accounts/template_editor/sections/section_6/model_1.html",
                            },
                        ),
                    ]
                ),
            },
        ),
    ]
)
