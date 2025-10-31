import importlib.util
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "httprint.py"
    spec = importlib.util.spec_from_file_location("httprint", mod_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader, "cannot load module spec"
    spec.loader.exec_module(mod)
    return mod


def test_api_version_string():
    httprint = _load_module()
    assert isinstance(httprint.API_VERSION, str)
    assert httprint.API_VERSION.count('.') >= 1


def test_pdf_pages_regex_matches_integer():
    httprint = _load_module()
    sample = 'Title: x\nPages: 12\nCreator: y\n'
    found = httprint.re_pages.findall(sample)
    assert found and found[0] == '12'


def test_custom_exception_carries_message_and_status():
    httprint = _load_module()
    err = httprint.HTTPrintBaseException('boom', status=418)
    assert err.message == 'boom'
    assert err.status == 418
    # Ensure it is still an Exception
    assert isinstance(err, Exception)


def test_print_cmd_contains_expected_placeholders():
    httprint = _load_module()
    cmd = httprint.PRINT_CMD
    # The command template should expose expected keys
    for key in ('copies', 'sides', 'media'):
        assert f"%({key})s" in cmd
