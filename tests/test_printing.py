import configparser
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "httprint.py"
    spec = importlib.util.spec_from_file_location("httprint", mod_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader, "cannot load module spec"
    spec.loader.exec_module(mod)
    return mod


httprint = _load_module()


def test_print_file_includes_page_ranges(tmp_path):
    pdf_path = tmp_path / "1234-20240101000000.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    cfg = configparser.ConfigParser()
    cfg['print'] = {
        'name': 'sample.pdf',
        'date': '20240101000000',
        'copies': '1',
        'sides': 'two-sided-long-edge',
        'media': 'A4',
        'color': 'False',
    }
    with open(pdf_path.with_suffix(pdf_path.suffix + '.info'), 'w') as fh:
        cfg.write(fh)

    captured = {}

    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    handler.cfg = SimpleNamespace(
        print_cmd='lp -n %(copies)s -o sides=%(sides)s -o media=%(media)s',
        demo=False,
        archive=False,
        archive_dir=str(tmp_path),
    )

    def fake_run(cmd, fname, callback=None):
        captured['cmd'] = cmd
        captured['fname'] = fname

    handler.run_subprocess = fake_run

    handler.print_file(str(pdf_path), page_ranges='2-3')

    assert captured['fname'] == str(pdf_path)
    assert '-o' in captured['cmd']
    assert 'page-ranges=2-3' in captured['cmd']
    assert captured['cmd'][-1] == str(pdf_path)


def test_print_file_respects_double_sided_flag(tmp_path):
    pdf_path = tmp_path / "5678-20240101000000.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    cfg = configparser.ConfigParser()
    cfg['print'] = {
        'name': 'sample.pdf',
        'date': '20240101000000',
        'copies': '1',
        'sides': 'one-sided',
        'media': 'A4',
        'color': 'False',
        'double_sided': 'false',
    }
    with open(pdf_path.with_suffix(pdf_path.suffix + '.info'), 'w') as fh:
        cfg.write(fh)

    captured = {}

    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    handler.cfg = SimpleNamespace(
        print_cmd='lp -n %(copies)s -o sides=%(sides)s -o media=%(media)s',
        demo=False,
        archive=False,
        archive_dir=str(tmp_path),
    )

    def fake_run(cmd, fname, callback=None):
        captured['cmd'] = cmd

    handler.run_subprocess = fake_run

    handler.print_file(str(pdf_path))

    assert any('sides=one-sided' in part for part in captured['cmd'])
