import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('httprint', ROOT / 'httprint.py')
httprint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(httprint)


@pytest.mark.parametrize('markdown', [True, False])
def test_text_conversion_creates_pdf(tmp_path, monkeypatch, markdown):
    monkeypatch.syspath_prepend(str(ROOT))
    source = tmp_path / 'text.txt'
    source.write_text('# Title\n\n**Bold** and 中文\n\n- Item\n', encoding='utf-8')
    output = tmp_path / 'text.pdf'
    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    assert handler.convert_txt_to_pdf(str(source), str(output), markdown=markdown) == (True, None)
    assert output.read_bytes().startswith(b'%PDF-')


@pytest.mark.skipif(not shutil.which('pdftotext'), reason='pdftotext unavailable')
@pytest.mark.parametrize('markdown,expected', [(True, 'Title'), (False, '# Title')])
def test_markdown_option_controls_printed_text(tmp_path, monkeypatch, markdown, expected):
    monkeypatch.syspath_prepend(str(ROOT))
    source = tmp_path / 'text.txt'
    source.write_text('# Title\n\n**Bold** <script>alert(1)</script>\n', encoding='utf-8')
    output = tmp_path / 'text.pdf'
    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    assert handler.convert_txt_to_pdf(str(source), str(output), markdown=markdown) == (True, None)
    result = subprocess.run(['pdftotext', str(output), '-'], capture_output=True, text=True, check=True)
    assert result.stdout.splitlines()[0] == expected
    assert '<script>alert(1)</script>' in result.stdout
    assert ('**Bold**' in result.stdout) is (not markdown)


def test_markdown_tables_and_long_code_paginate(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    source = tmp_path / 'text.txt'
    source.write_text(
        '# 中文标题\n\n> 引用\n\n1. first\n2. second\n\n'
        '| 名称 | 数量 |\n| --- | --- |\n| 测试 | 2 |\n\n'
        '```\n' + '    long code & <tag>\n' * 150 + '```\n', encoding='utf-8',
    )
    output = tmp_path / 'text.pdf'
    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    assert handler.convert_txt_to_pdf(str(source), str(output)) == (True, None)
    assert output.read_bytes().count(b'/Type /Page\n') > 1


def test_conversion_reports_missing_source(tmp_path):
    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    success, error = handler.convert_txt_to_pdf(str(tmp_path / 'missing.txt'), str(tmp_path / 'out.pdf'))
    assert success is False
    assert 'missing.txt' in error
