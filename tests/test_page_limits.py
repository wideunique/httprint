import importlib.util
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import tornado.web
from tornado.testing import AsyncHTTPTestCase


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('httprint', ROOT / 'httprint.py')
httprint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(httprint)


class TestConfiguredPageLimit(AsyncHTTPTestCase):
    def setUp(self):
        self.workspace = TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        config_path = Path(self.workspace.name) / 'config.yaml'
        config_path.write_text('max_pages: 50000\n', encoding='utf-8')
        self.cfg = httprint.load_config(str(config_path))
        self.cfg.queue_dir = self.workspace.name
        super().setUp()

    def get_app(self):
        params = {'cfg': self.cfg, 'logger': logging.getLogger()}
        return tornado.web.Application(
            [('/api/upload', httprint.UploadHandler, params),
             ('/', httprint.TemplateHandler, params)],
            template_path=str(ROOT / 'dist'),
        )

    def upload(self, pages, copies, filename='test.pdf', markdown=None):
        markdown_field = '' if markdown is None else (
            '--boundary\r\n'
            'Content-Disposition: form-data; name="markdown"\r\n\r\n'
            f'{markdown}\r\n'
        )
        body = (
            markdown_field +
            '--boundary\r\n'
            'Content-Disposition: form-data; name="copies"\r\n\r\n'
            f'{copies}\r\n'
            '--boundary\r\n'
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            'Content-Type: application/pdf\r\n\r\n'
            '%PDF-1.4\n\r\n'
            '--boundary--\r\n'
        )
        process = Mock(returncode=0)
        process.communicate.return_value = (f'Pages: {pages}\n'.encode(), None)
        with patch.object(httprint.subprocess, 'Popen', return_value=process), \
                patch.object(httprint.UploadHandler, 'print_file') as print_file:
            response = self.fetch(
                '/api/upload', method='POST', body=body,
                headers={'Content-Type': 'multipart/form-data; boundary=boundary'},
            )
        return response, print_file

    def test_page_uses_configured_limit(self):
        response = self.fetch('/')
        assert response.code == 200
        html = response.body.decode()
        assert 'id="copies" min="1" max="50000"' in html
        assert '打印份数：1-50000 份' in html
        assert '最大页数 50000 页' in html

    def test_query_cannot_override_configured_limit(self):
        response = self.fetch('/?max_pages=7')
        assert response.code == 200
        assert 'id="copies" min="1" max="50000"' in response.body.decode()

    def test_copies_at_configured_limit_are_printed(self):
        response, print_file = self.upload(pages=1, copies=50000)
        assert response.code == 200
        print_file.assert_called_once()

    def test_copies_above_configured_limit_are_rejected(self):
        response, print_file = self.upload(pages=1, copies=50001)
        assert response.code == 400
        print_file.assert_not_called()

    def test_total_pages_at_configured_limit_are_printed(self):
        response, print_file = self.upload(pages=25000, copies=2)
        assert response.code == 200
        print_file.assert_called_once()

    def test_total_pages_above_configured_limit_are_rejected(self):
        response, print_file = self.upload(pages=25001, copies=2)
        assert response.code == 400
        assert json.loads(response.body)['message'] == 'too many pages to print (50002)'
        print_file.assert_not_called()
        assert list(Path(self.workspace.name).glob('*.pdf*')) == []

    def test_text_defaults_to_markdown(self):
        with patch.object(httprint.UploadHandler, 'convert_txt_to_pdf',
                          return_value=(True, None)) as convert:
            response, _ = self.upload(1, 1, filename='text.txt')
        assert response.code == 200
        assert convert.call_args.kwargs == {'markdown': True}

    def test_text_upload_converts_and_prints_pdf(self):
        response, print_file = self.upload(1, 1, filename='text.txt')
        assert response.code == 200
        print_file.assert_called_once()
        output = Path(print_file.call_args.args[0])
        assert output.read_bytes().startswith(b'%PDF-')

    def test_text_page_has_markdown_enabled(self):
        response = self.fetch('/')
        assert response.code == 200
        assert 'id="markdown" checked' in response.body.decode()

    def test_text_can_disable_markdown(self):
        with patch.object(httprint.UploadHandler, 'convert_txt_to_pdf',
                          return_value=(True, None)) as convert:
            response, _ = self.upload(1, 1, filename='text.txt', markdown='false')
        assert response.code == 200
        assert convert.call_args.kwargs == {'markdown': False}

    def test_invalid_markdown_option_is_rejected(self):
        response, print_file = self.upload(1, 1, filename='text.txt', markdown='invalid')
        assert response.code == 400
        assert json.loads(response.body)['message'] == 'invalid value for markdown'
        print_file.assert_not_called()
