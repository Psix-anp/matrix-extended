from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_russian_user_docs_match_english_doc_set():
    pairs = [
        ("docs/SETTINGS.md", "docs/SETTINGS.ru.md"),
        ("docs/ACTIONS.md", "docs/ACTIONS.ru.md"),
        ("docs/EXAMPLES.md", "docs/EXAMPLES.ru.md"),
        ("docs/TESTING.md", "docs/TESTING.ru.md"),
    ]

    for english, russian in pairs:
        assert (ROOT / english).is_file(), english
        assert (ROOT / russian).is_file(), russian


def test_russian_readme_links_russian_examples_and_testing_guides():
    readme = (ROOT / "README.ru.md").read_text(encoding="utf-8")

    assert "docs/EXAMPLES.ru.md" in readme
    assert "docs/TESTING.ru.md" in readme


def test_each_new_user_guide_links_to_other_language():
    examples_en = (ROOT / "docs/EXAMPLES.md").read_text(encoding="utf-8")
    testing_en = (ROOT / "docs/TESTING.md").read_text(encoding="utf-8")

    assert "EXAMPLES.ru.md" in examples_en
    assert "TESTING.ru.md" in testing_en
