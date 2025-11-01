import importlib.util
from pathlib import Path

import pytest


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "httprint.py"
    spec = importlib.util.spec_from_file_location("httprint", mod_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader, "cannot load module spec"
    spec.loader.exec_module(mod)
    return mod


httprint = _load_module()


@pytest.mark.parametrize(
    "pages,total,expected",
    [
        (None, 0, None),
        ("", 5, None),
        ("3", 5, "3"),
        ("1-3,5", 6, "1-3,5"),
        (" 2 - 4 ", 10, "2-4"),
    ],
)
def test_normalize_page_ranges_valid(pages, total, expected):
    assert httprint.normalize_page_ranges(pages, total) == expected


@pytest.mark.parametrize(
    "pages,total,error",
    [
        ("0", 5, "page numbers must be >= 1"),
        ("a", 5, "page numbers must be numeric"),
        ("2-b", 5, "page ranges must be numeric"),
        ("5", 4, "page number out of bounds"),
        ("3-2", 5, "range start cannot exceed end"),
        ("1-10", 5, "page range exceeds document length"),
        ("1", 0, "unknown document page count"),
    ],
)
def test_normalize_page_ranges_invalid(pages, total, error):
    with pytest.raises(ValueError) as exc:
        httprint.normalize_page_ranges(pages, total)
    assert error in str(exc.value)
