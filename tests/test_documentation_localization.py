from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_russian_user_docs_match_english_doc_set():
    pairs = [
        ("docs/SETTINGS.md", "docs/SETTINGS.ru.md"),
        ("docs/ACTIONS.md", "docs/ACTIONS.ru.md"),
        ("docs/EXAMPLES.md", "docs/EXAMPLES.ru.md"),
        ("docs/TESTING.md", "docs/TESTING.ru.md"),
        ("docs/CONTROL_PANELS.md", "docs/CONTROL_PANELS.ru.md"),
    ]

    for english, russian in pairs:
        assert (ROOT / english).is_file(), english
        assert (ROOT / russian).is_file(), russian


def test_russian_readme_links_russian_examples_testing_and_control_panel_guides():
    readme = _read("README.ru.md")

    assert "docs/EXAMPLES.ru.md" in readme
    assert "docs/TESTING.ru.md" in readme
    assert "docs/CONTROL_PANELS.ru.md" in readme


def test_english_readme_links_control_panel_guide_and_beta_roadmap():
    readme = _read("README.md")

    assert "docs/CONTROL_PANELS.md" in readme
    assert "0.6.0b1" in readme
    assert "Widget" in readme
    assert "planned" in readme.lower()


def test_each_new_user_guide_links_to_other_language():
    examples_en = _read("docs/EXAMPLES.md")
    testing_en = _read("docs/TESTING.md")

    assert "EXAMPLES.ru.md" in examples_en
    assert "TESTING.ru.md" in testing_en

    control_en = _read("docs/CONTROL_PANELS.md")
    control_ru = _read("docs/CONTROL_PANELS.ru.md")
    assert "CONTROL_PANELS.ru.md" in control_en
    assert "CONTROL_PANELS.md" in control_ru


def test_control_panel_guides_document_actual_b1_safety_and_lifecycle():
    en = _read("docs/CONTROL_PANELS.md").lower()
    ru = _read("docs/CONTROL_PANELS.ru.md").lower()

    for marker in (
        "existing matrix room",
        "allowlist",
        "one panel",
        "30-second",
        "same sender",
        "needs_repair",
        "repair",
        "yaml",
        "debounce",
        "outage",
        "widget",
    ):
        assert marker in en, marker

    for marker in (
        "существующ",
        "allowlist",
        "одна панель",
        "30 секунд",
        "тот же отправитель",
        "needs_repair",
        "восстанов",
        "yaml",
        "debounce",
        "недоступ",
        "widget",
    ):
        assert marker in ru, marker


def test_examples_cover_low_risk_and_dangerous_control_panel_actions():
    en = _read("docs/EXAMPLES.md").lower()
    ru = _read("docs/EXAMPLES.ru.md").lower()

    for marker in ("garage", "alarm", "light", "confirmation_required"):
        assert marker in en, marker
    for marker in ("гараж", "сигнализац", "свет", "confirmation_required"):
        assert marker in ru, marker
