import asyncio
import importlib.util
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from playwright import async_api
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application, RequestHandler

import url_preview
from url_preview import fit_pdf_to_portrait_a4


spec = importlib.util.spec_from_file_location(
    'httprint', Path(__file__).resolve().parents[1] / 'httprint.py',
)
httprint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(httprint)


class TestUrlPreview(AsyncHTTPTestCase):
    def get_app(self):
        self.cfg = SimpleNamespace(**httprint.DEFAULT_CONFIG)
        self.render = AsyncMock(return_value=b'%PDF-1.4\n')
        self.capacity = asyncio.Semaphore(2)
        return Application([
            (r'/api/url-preview', httprint.UrlPreviewHandler, {
                'cfg': self.cfg,
                'render': self.render,
                'capacity': self.capacity,
            }),
        ])

    def preview(self, body):
        return self.fetch('/api/url-preview', method='POST', body=body,
                          headers={'Content-Type': 'application/json'})

    def test_default_config_previews_pdf_without_using_print_queue(self):
        response = self.preview('{"url": "https://example.com/article"}')
        assert response.code == 200
        assert response.headers['Content-Type'] == 'application/pdf'
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.body == b'%PDF-1.4\n'
        self.render.assert_awaited_once_with(
            'https://example.com/article', include_images=True, reader_mode=True,
        )

    def test_false_requests_pdf_without_html_images(self):
        response = self.preview('{"url": "https://example.com", "include_images": false}')
        assert response.code == 200
        self.render.assert_awaited_once_with(
            'https://example.com', include_images=False, reader_mode=True,
        )

    def test_false_requests_original_layout(self):
        response = self.preview('{"url": "https://example.com", "reader_mode": false}')
        assert response.code == 200
        self.render.assert_awaited_once_with(
            'https://example.com', include_images=True, reader_mode=False,
        )

    def test_rejects_non_boolean_reader_mode(self):
        response = self.preview('{"url": "https://example.com", "reader_mode": "false"}')
        assert response.code == 400
        self.render.assert_not_called()

    def test_rejects_non_boolean_include_images_option(self):
        response = self.preview('{"url": "https://example.com", "include_images": "false"}')
        assert response.code == 400
        self.render.assert_not_called()

    def test_rejects_empty_urls_and_non_http_schemes(self):
        for body in ('{}', '{"url": " "}', '{"url": "file:///etc/passwd"}'):
            assert self.preview(body).code == 400
        self.render.assert_not_called()

    def test_rejects_local_addresses_and_embedded_credentials(self):
        for url in ('http://127.0.0.1', 'http://[::1]', 'http://localhost',
                    'http://printer.local', 'https://user:pass@example.com'):
            assert self.preview('{"url": "%s"}' % url).code == 400
        self.render.assert_not_called()

    def test_render_failure_returns_readable_error(self):
        self.render.side_effect = httprint.UrlPreviewError('网页加载超时。', 504)
        response = self.preview('{"url": "https://example.com"}')
        assert response.code == 504
        assert json.loads(response.body)['message'] == '网页加载超时。'

    def test_busy_renderer_rejects_additional_preview(self):
        async def occupy_capacity():
            await self.capacity.acquire()
            await self.capacity.acquire()

        self.io_loop.run_sync(occupy_capacity)
        assert self.preview('{"url": "https://example.com"}').code == 429
        self.render.assert_not_called()


class FixedHeaderPage(RequestHandler):
    def get(self):
        self.write("""
            <style>
                .banner { position: fixed; top: 0; left: 0; width: 100%;
                          line-height: 60px; background: white; }
                section + section { break-before: page; }
            </style>
            <div class="banner">Site navigation</div>
            <section>First page body</section>
            <section>Second page body</section>
        """)


class TestOriginalPrintLayout(AsyncHTTPTestCase):
    def get_app(self):
        return Application([(r'/', FixedHeaderPage)])

    @gen_test(timeout=35)
    async def test_fixed_top_banner_prints_only_once(self):
        async with async_api.async_playwright() as playwright:
            if not Path(playwright.chromium.executable_path).is_file():
                pytest.skip('Playwright Chromium is not installed')

        pdf = await url_preview.render_url_pdf(self.get_url('/'), reader_mode=False)
        first, second = (page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        assert 'Site navigation' in first
        assert 'First page body' in first
        assert 'Second page body' in second
        assert 'Site navigation' not in second


@pytest.fixture
def browser_page(monkeypatch):
    page = SimpleNamespace(
        goto=AsyncMock(return_value=SimpleNamespace(ok=True)),
        emulate_media=AsyncMock(),
        evaluate=AsyncMock(return_value=None),
        locator=Mock(return_value=SimpleNamespace(evaluate_all=AsyncMock())),
        pdf=AsyncMock(),
    )
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    browser = MagicMock(new_context=AsyncMock(return_value=context))
    chromium = SimpleNamespace(launch=AsyncMock(return_value=browser))
    playwright = MagicMock()
    playwright.__aenter__.return_value = SimpleNamespace(chromium=chromium)
    monkeypatch.setattr(async_api, 'async_playwright', lambda: playwright)
    monkeypatch.setattr(url_preview, 'fit_pdf_to_portrait_a4', lambda pdf: pdf)
    return page, context


@pytest.mark.parametrize('include_images', [True, False])
def test_reader_fallback_can_return_large_pdf(browser_page, include_images):
    page, _ = browser_page
    pdf = bytes(32 * 1024 * 1024 + 1)
    page.pdf.return_value = pdf
    preview = asyncio.run(url_preview.render_url_pdf('https://example.com', include_images=include_images))

    assert preview == pdf
    page.pdf.assert_awaited_once()
    if include_images:
        page.locator.assert_not_called()
    else:
        page.locator.assert_called_once_with('img')
        page.locator.return_value.evaluate_all.assert_awaited_once()


def test_reader_mode_prints_extracted_article_in_a_separate_document(browser_page):
    page, context = browser_page
    page.evaluate.return_value = {'title': 'Title <1>', 'content': '<p>Article body</p>'}
    reader = SimpleNamespace(set_content=AsyncMock(), pdf=AsyncMock(return_value=b'reader PDF'))
    context.new_page.side_effect = [page, reader]

    assert asyncio.run(url_preview.render_url_pdf('https://example.com')) == b'reader PDF'
    html = reader.set_content.await_args.args[0]
    assert '<h1>Title &lt;1&gt;</h1>' in html
    assert '<p>Article body</p>' in html
    page.pdf.assert_not_awaited()


def test_reader_mode_false_prints_original_document(browser_page):
    page, _ = browser_page
    page.pdf.return_value = b'original PDF'

    assert asyncio.run(url_preview.render_url_pdf('https://example.com', reader_mode=False)) == b'original PDF'
    page.evaluate.assert_awaited_once_with(url_preview.ORIGINAL_PRINT_LAYOUT_SCRIPT)


def test_fits_portrait_and_landscape_pages_to_portrait_a4():
    source = BytesIO()
    canvas = Canvas(source, pagesize=(612, 792))
    canvas.drawString(30, 50, 'Portrait')
    canvas.showPage()
    canvas.setPageSize((792, 612))
    canvas.drawString(700, 50, 'Landscape')
    canvas.save()

    pages = PdfReader(BytesIO(fit_pdf_to_portrait_a4(source.getvalue()))).pages

    assert len(pages) == 2
    for page, content in zip(pages, ('Portrait', 'Landscape')):
        assert float(page.mediabox.width) == pytest.approx(595.276, abs=0.01)
        assert float(page.mediabox.height) == pytest.approx(841.89, abs=0.01)
        assert content in page.extract_text()
