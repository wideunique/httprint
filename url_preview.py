"""Render web pages as A4 PDFs using Chromium."""

import asyncio
from html import escape
from io import BytesIO
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


RENDER_TIMEOUT = 30
A4_WIDTH = 210 * 72 / 25.4
A4_HEIGHT = 297 * 72 / 25.4
READABILITY_JS = (Path(__file__).with_name('vendor') / 'readability' / 'Readability.js').read_text(
    encoding='utf-8',
)
READABILITY_SCRIPT = '(includeImages) => {\nconst module = undefined;\n' + READABILITY_JS + """
    return new Readability(document.cloneNode(true), {
        serializer: article => {
            for (const element of article.querySelectorAll(
                'base, embed, form, iframe, link, meta, object, script, style'
            )) {
                element.remove();
            }
            for (const image of article.querySelectorAll('img')) {
                if (includeImages) {
                    image.loading = 'eager';
                } else {
                    image.remove();
                }
            }
            return article.innerHTML;
        }
    }).parse();
}
"""

ORIGINAL_PRINT_LAYOUT_SCRIPT = """() => {
    const { clientWidth, clientHeight } = document.documentElement;
    const topBars = Array.from(document.querySelectorAll('body *')).filter(element => {
        if (getComputedStyle(element).position !== 'fixed') {
            return false;
        }
        const { top, width, height } = element.getBoundingClientRect();
        return Math.abs(top) <= 1 && width >= clientWidth / 2 &&
            height > 0 && height <= clientHeight / 3;
    });
    // Chromium repeats fixed boxes on each printed page. Keep top bars in flow.
    for (const bar of topBars) {
        bar.style.setProperty('position', 'relative', 'important');
        bar.style.setProperty('inset', 'auto', 'important');
    }
}"""


class UrlPreviewError(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def validate_preview_url(value):
    if not isinstance(value, str):
        raise ValueError('URL must be a string')
    value = value.strip()
    if len(value) > 4096 or '\\' in value or any(ord(char) < 33 for char in value):
        raise ValueError('invalid URL characters or length')

    parts = urlsplit(value)
    if (parts.scheme not in ('http', 'https') or not parts.hostname
            or parts.username is not None or '%' in parts.netloc or parts.port == 0):
        raise ValueError('expected an HTTP(S) URL without credentials')

    host = parts.hostname.rstrip('.')
    try:
        address = ip_address(host)
    except ValueError:
        if '.' not in host or host.endswith(('.local', '.localhost', '.internal')):
            raise ValueError('expected a public hostname') from None
    else:
        if not address.is_global or address.is_multicast or address.is_reserved:
            raise ValueError('expected a public address')
    return urlunsplit(parts)


async def render_url_pdf(url, *, include_images=True, reader_mode=True):
    try:
        from playwright.async_api import Error, TimeoutError as BrowserTimeout, async_playwright
        from pypdf.errors import PdfReadError
    except ImportError:
        raise UrlPreviewError('服务器尚未安装网页预览依赖。', 503) from None

    async def capture(playwright):
        try:
            browser = await playwright.chromium.launch(channel='chromium', chromium_sandbox=True)
        except BrowserTimeout:
            raise
        except Error:
            raise UrlPreviewError('服务器无法启动 Chromium，请检查安装和沙箱配置。', 503) from None

        async with browser:
            context = await browser.new_context(accept_downloads=False, service_workers='block')
            page = await context.new_page()
            response = await page.goto(url, wait_until='load')
            if response is None or not response.ok:
                raise UrlPreviewError('目标网页无法访问，请检查网址和网页响应。', 502)
            article = await page.evaluate(READABILITY_SCRIPT, include_images) if reader_mode else None
            if article:
                page = await context.new_page()
                await page.set_content(reader_html(article), wait_until='load')
            else:
                if not include_images:
                    await page.locator('img').evaluate_all(
                        """images => {
                            for (const image of images) {
                                image.style.setProperty('display', 'none', 'important');
                            }
                        }"""
                    )
                await page.emulate_media(media='print')
                await page.evaluate(ORIGINAL_PRINT_LAYOUT_SCRIPT)
            pdf = await page.pdf(format='A4', prefer_css_page_size=False, print_background=True)

        return await asyncio.to_thread(fit_pdf_to_portrait_a4, pdf)

    async with async_playwright() as playwright:
        try:
            return await asyncio.wait_for(capture(playwright), timeout=RENDER_TIMEOUT)
        except (asyncio.TimeoutError, BrowserTimeout):
            raise UrlPreviewError('网页加载或生成 PDF 超时。', 504) from None
        except (Error, PdfReadError):
            raise UrlPreviewError('无法加载网页或生成 PDF，请检查网址和服务器的网络连接。', 502) from None


def reader_html(article):
    title = escape(article.get('title') or '')
    byline = escape(article.get('byline') or '')
    lang = escape(article.get('lang') or '')
    direction = 'rtl' if article.get('dir') == 'rtl' else 'ltr'
    heading = f'<h1>{title}</h1>' if title else ''
    author = f'<p class="byline">{byline}</p>' if byline else ''
    return f"""<!doctype html>
<html lang="{lang}" dir="{direction}">
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; img-src http: https: data:; style-src 'unsafe-inline';
               base-uri 'none'; form-action 'none'">
<title>{title}</title>
<style>
  @page {{ size: A4 portrait; margin: 16mm 18mm; }}
  body {{ margin: 0; color: #181818; font: 11.5pt/1.6 Georgia, "Noto Serif CJK SC", serif;
          overflow-wrap: anywhere; }}
  h1, h2, h3, h4, h5, h6 {{ line-height: 1.3; break-after: avoid; }}
  h1 {{ font-size: 23pt; margin: 0 0 0.5em; }}
  .byline {{ color: #555; margin: 0 0 1.5em; }}
  p {{ margin: 0 0 0.85em; orphans: 3; widows: 3; }}
  a {{ color: inherit; }}
  figure {{ margin: 1em 0; break-inside: avoid; }}
  img, svg, video {{ max-width: 100%; max-height: 90mm; height: auto; object-fit: contain; }}
  blockquote {{ margin-inline: 0; padding-inline-start: 1em; border-inline-start: 2px solid #bbb; }}
  pre {{ white-space: pre-wrap; }}
  table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
  th, td {{ padding: 0.3em; border: 1px solid #bbb; }}
  tr {{ break-inside: avoid; }}
</style>
<main>{heading}{author}{article['content']}</main>
</html>"""


def fit_pdf_to_portrait_a4(pdf):
    """Fit each page without cropping, including CSS-selected landscape pages."""
    from pypdf import PdfReader, PdfWriter, Transformation

    reader = PdfReader(BytesIO(pdf))
    writer = PdfWriter()
    if reader.metadata:
        writer.add_metadata(reader.metadata)
    for original in reader.pages:
        if original.rotation:
            original.transfer_rotation_to_content()
        box = original.mediabox
        width, height = float(box.width), float(box.height)
        scale = min(A4_WIDTH / width, A4_HEIGHT / height)
        transform = Transformation().translate(-float(box.left), -float(box.bottom))
        transform = transform.scale(scale).translate(
            (A4_WIDTH - width * scale) / 2, (A4_HEIGHT - height * scale) / 2,
        )
        page = writer.add_blank_page(width=A4_WIDTH, height=A4_HEIGHT)
        page.merge_transformed_page(original, transform)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
