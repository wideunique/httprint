"""Render Markdown tokens using the existing ReportLab PDF stack."""

from html import escape

import mistune
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


def inline_markup(tokens):
    """Translate supported inline formatting and escape all user markup."""
    parts = []
    for token in tokens:
        kind = token['type']
        content = inline_markup(token.get('children', []))
        if kind in ('strong', 'emphasis', 'strikethrough'):
            tag = {'strong': 'b', 'emphasis': 'i', 'strikethrough': 'strike'}[kind]
            parts.append(f'<{tag}>{content}</{tag}>')
        elif kind == 'codespan':
            parts.append('<font backColor="#eeeeee">' + escape(token['raw']) + '</font>')
        elif kind in ('softbreak', 'linebreak'):
            parts.append('<br/>')
        elif kind == 'link':
            parts.append(content + ' (' + escape(token['attrs']['url']) + ')')
        elif kind == 'image':
            parts.append('[Image: ' + content + ']')
        else:
            parts.append(escape(token['raw']) if 'raw' in token else content)
    return ''.join(parts)


def render_markdown_pdf(text, output_pdf, font_name):
    """Build paginated Markdown without fetching images or executing HTML."""
    if font_name != 'Helvetica':
        # System CJK fonts may have no separate bold/italic face.
        pdfmetrics.registerFontFamily(
            font_name, normal=font_name, bold=font_name,
            italic=font_name, boldItalic=font_name,
        )
    style = ParagraphStyle(
        'Markdown', fontName=font_name, fontSize=10, leading=15,
        spaceAfter=7, wordWrap='CJK',
    )
    document = SimpleDocTemplate(
        output_pdf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    parser = mistune.create_markdown(renderer='ast', plugins=['table', 'strikethrough'])
    story = []

    def paragraph(markup, indent=0, **overrides):
        current_style = ParagraphStyle(
            'Block', parent=style, leftIndent=indent * 14, **overrides,
        )
        story.append(Paragraph(markup or '&#160;', current_style))

    def blocks(tokens, indent=0):
        for token in tokens:
            kind = token['type']
            children = token.get('children', [])
            if kind in ('paragraph', 'block_text'):
                paragraph(inline_markup(children), indent)
            elif kind == 'heading':
                level = token['attrs']['level']
                size = max(11, 22 - level * 2)
                paragraph(inline_markup(children), indent, fontSize=size,
                          leading=size * 1.4, spaceBefore=10)
            elif kind == 'list':
                attrs = token['attrs']
                start = attrs.get('start', 1)
                for index, item in enumerate(children, start):
                    marker = f'{index}.' if attrs['ordered'] else '\u2022'
                    item_blocks = item.get('children', [])
                    if item_blocks and item_blocks[0]['type'] in ('paragraph', 'block_text'):
                        paragraph(marker + ' ' + inline_markup(item_blocks[0]['children']), indent + 1)
                        blocks(item_blocks[1:], indent + 1)
                    else:
                        paragraph(marker, indent + 1)
                        blocks(item_blocks, indent + 1)
            elif kind == 'block_quote':
                blocks(children, indent + 1)
            elif kind == 'block_code':
                # One paragraph per code line permits splitting tall code blocks.
                for line in token['raw'].expandtabs(4).splitlines():
                    markup = escape(line).replace(' ', '&#160;')
                    paragraph(markup, indent, backColor=colors.HexColor('#eeeeee'),
                              fontSize=9, leading=12, spaceAfter=0)
                story.append(Spacer(1, 7))
            elif kind == 'thematic_break':
                story.append(HRFlowable(width='100%', spaceBefore=7, spaceAfter=7))
            elif kind == 'block_html':
                paragraph(escape(token['raw']).replace('\n', '<br/>'), indent)
            elif kind == 'table':
                rows = []
                for section in children:
                    section_rows = [section] if section['type'] == 'table_head' else section['children']
                    for row in section_rows:
                        rows.append([
                            Paragraph(inline_markup(cell['children']), style)
                            for cell in row['children']
                        ])
                if rows:
                    width = document.width - indent * 14
                    table = Table(rows, colWidths=[width / len(rows[0])] * len(rows[0]),
                                  repeatRows=1, hAlign='LEFT', splitInRow=1)
                    table.setStyle(TableStyle([
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eeeeee')),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ]))
                    story.extend([table, Spacer(1, 7)])
            elif children:
                blocks(children, indent)

    blocks(parser(text))
    document.build(story or [Paragraph('&#160;', style)])
