from accounts.template_registry import TEMPLATE_SECTION_REGISTRY


LEGACY_MODEL_ALIASES = {
    "section_3": {
        "model_9": "model_8",
    },
}


def _is_model_available(section_key, model_key, model_def, selected_models=None):
    if not model_def["enabled"]:
        return False

    selected_models = selected_models or {}

    if section_key == "section_2" and model_key == "model_10":
        selected_section3_model = _normalize_model_choice(
            "section_3",
            selected_models.get("section_3"),
            selected_models,
        )
        return selected_section3_model != "model_3"

    return True


def _normalize_model_choice(section_key, requested_model, selected_models=None):
    section_def = TEMPLATE_SECTION_REGISTRY[section_key]
    models = section_def["models"]
    selected_models = selected_models or {}
    requested_model = LEGACY_MODEL_ALIASES.get(section_key, {}).get(requested_model, requested_model)

    if requested_model in models and _is_model_available(
        section_key,
        requested_model,
        models[requested_model],
        selected_models,
    ):
        return requested_model

    default_model = section_def["default_model"]
    if _is_model_available(section_key, default_model, models[default_model], selected_models):
        return default_model

    for model_key, model_def in models.items():
        if _is_model_available(section_key, model_key, model_def, selected_models):
            return model_key

    return default_model


def get_default_selected_models():
    return {
        section_key: section_def["default_model"]
        for section_key, section_def in TEMPLATE_SECTION_REGISTRY.items()
    }


def normalize_selected_models(selected_models):
    normalized = {}
    for section_key in TEMPLATE_SECTION_REGISTRY:
        context_selected_models = {**selected_models, **normalized}
        normalized[section_key] = _normalize_model_choice(
            section_key,
            selected_models.get(section_key),
            context_selected_models,
        )
    return normalized


def _is_section2_customize_locked(selected_models):
    selected_section3_model = _normalize_model_choice(
        "section_3",
        selected_models.get("section_3"),
        selected_models,
    )
    return selected_section3_model == "model_3"


def _can_customize_model(section_key, model_def, selected_models):
    if not model_def.get("customize_mode"):
        return False

    if section_key == "section_2" and _is_section2_customize_locked(selected_models):
        return False

    return True


def _get_preview_template_name(section_key, model_key, model_def, selected_models):
    combined_preview_templates = model_def.get("combined_preview_templates", {})
    selected_models_normalized = normalize_selected_models(selected_models)

    for dependency_key, template_name in combined_preview_templates.items():
        dependency_section, dependency_model = dependency_key.split(":", 1)
        if selected_models_normalized.get(dependency_section) == dependency_model:
            return template_name

    return model_def["preview_template"]


def build_layout_sections(selected_models):
    normalized_models = normalize_selected_models(selected_models)
    layout_sections = []

    for index, (section_key, section_def) in enumerate(TEMPLATE_SECTION_REGISTRY.items(), start=1):
        selected_model = normalized_models[section_key]
        selected_model_def = section_def["models"][selected_model]
        enabled_models = [
            {
                "key": model_key,
                "name": model_def["label"],
                "available": True,
                "can_customize": _can_customize_model(section_key, model_def, selected_models),
                "customize_mode": model_def.get("customize_mode", ""),
            }
            for model_key, model_def in section_def["models"].items()
            if _is_model_available(section_key, model_key, model_def, normalized_models)
        ]

        layout_sections.append(
            {
                "key": section_key,
                "index": index,
                "title": section_def["title"],
                "model": selected_model_def["label"],
                "selected_model": selected_model,
                "models": enabled_models,
                "has_available_model": bool(enabled_models),
                "can_customize": _can_customize_model(section_key, selected_model_def, selected_models),
                "customize_mode": selected_model_def.get("customize_mode", ""),
                "show_extra_toggle": section_def.get("show_extra_toggle", False),
                "extra_enabled": section_def.get("extra_enabled", False),
            }
        )

    return layout_sections


def build_preview_sections(selected_models):
    normalized_models = normalize_selected_models(selected_models)
    preview_sections = []

    for section_key, section_def in TEMPLATE_SECTION_REGISTRY.items():
        selected_model = normalized_models[section_key]
        variants = []

        for model_key, model_def in section_def["models"].items():
            if not _is_model_available(section_key, model_key, model_def, normalized_models):
                continue
            variants.append(
                {
                    "key": model_key,
                    "label": model_def["label"],
                    "template_name": _get_preview_template_name(section_key, model_key, model_def, selected_models),
                    "is_active": model_key == selected_model,
                }
            )

        preview_sections.append(
            {
                "key": section_key,
                "title": section_def["title"],
                "selected_model": selected_model,
                "variants": variants,
            }
        )

    return preview_sections


def build_combined_preview_variants(selected_models):
    normalized_models = normalize_selected_models(selected_models)
    section_def = TEMPLATE_SECTION_REGISTRY["section_2"]
    variants = []
    combined_selected_models = dict(normalized_models)
    combined_selected_models["section_3"] = "model_3"

    for model_key, model_def in section_def["models"].items():
        if not _is_model_available("section_2", model_key, model_def, combined_selected_models):
            continue
        variants.append(
            {
                "key": model_key,
                "label": model_def["label"],
                "template_name": _get_preview_template_name(
                    "section_2",
                    model_key,
                    model_def,
                    combined_selected_models,
                ),
                "is_active": model_key == normalized_models["section_2"],
            }
        )

    return variants


def build_preview_state(selected_models):
    normalized_models = normalize_selected_models(selected_models)
    return {
        "selected_models": normalized_models,
        "is_combined_section2_section3": normalized_models.get("section_3") == "model_3",
    }
