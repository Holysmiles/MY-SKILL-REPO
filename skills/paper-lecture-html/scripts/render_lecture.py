"""Render a lecture JSON document as a self-contained, offline HTML file."""

import argparse
import base64
import html
import json
import mimetypes
from pathlib import Path
import re
import sys


SKILL_ROOT = Path(__file__).resolve().parents[1]


def escape(value):
    return html.escape(str(value), quote=True)


def source_note(block):
    source = block.get('source')
    return f'<p class="source">{escape(source)}</p>' if source else ''


def embed_image(path):
    mime = mimetypes.guess_type(str(path))[0]
    if mime not in {'image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/svg+xml'}:
        raise ValueError(f'Unsupported image type at {path}')
    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'data:{mime};base64,{encoded}'


def render_block(block, base_dir):
    kind = block['type']
    if kind == 'paragraph':
        content = f'<p>{escape(block["text"])}</p>'
    elif kind == 'callout':
        style = block.get('kind', 'insight')
        if style not in {'question', 'insight', 'evidence', 'caution'}:
            raise ValueError(f'Unknown callout kind {style}')
        title = f'<strong>{escape(block["title"])}</strong>' if block.get('title') else ''
        content = f'<aside class="callout {style}">{title}<p>{escape(block["text"])}</p></aside>'
    elif kind == 'list':
        items = ''.join(f'<li>{escape(item)}</li>' for item in block['items'])
        content = f'<ul>{items}</ul>'
    elif kind == 'equation':
        content = (
            f'<div class="equation" data-tex="{escape(block["latex"])}"></div>'
            f'<p class="meaning">{escape(block["meaning"])}</p>'
            f'<details class="math-source"><summary>查看公式源码</summary>'
            f'<pre>{escape(block["latex"])}</pre></details>'
        )
    elif kind == 'figure':
        image_path = (base_dir / block['src']).resolve()
        image_uri = embed_image(image_path)
        pins = []
        notes = []
        for mark in block.get('marks', []):
            x, y = float(mark['x']), float(mark['y'])
            if not (0 <= x <= 100 and 0 <= y <= 100):
                raise ValueError('Figure annotation coordinates must be percentages from 0 to 100')
            pins.append(
                f'<span class="pin" style="left:{x}%;top:{y}%" '
                f'title="{escape(mark["text"])}">{escape(mark["label"])}</span>'
            )
            notes.append(f'<li><b>{escape(mark["label"])}</b> {escape(mark["text"])}</li>')
        content = (
            f'<figure><div class="figure-image"><img src="{image_uri}" '
            f'alt="{escape(block["alt"])}">{"".join(pins)}'
            f'<button type="button" class="figure-open">放大图片</button></div>'
            f'<figcaption>{escape(block["caption"])}</figcaption>'
            f'<ul class="annotations">{"".join(notes)}</ul></figure>'
        )
    elif kind == 'table':
        columns, rows = block['columns'], block['rows']
        if not columns or any(len(row) != len(columns) for row in rows):
            raise ValueError('A table needs columns and equally sized rows')
        head = ''.join(f'<th scope="col">{escape(column)}</th>' for column in columns)
        body = ''.join('<tr>' + ''.join(f'<td>{escape(cell)}</td>' for cell in row) + '</tr>' for row in rows)
        caption = f'<caption>{escape(block["caption"])}</caption>' if block.get('caption') else ''
        content = f'<div class="table-wrap"><table>{caption}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    elif kind == 'flow':
        steps = ''.join(f'<li>{escape(step)}</li>' for step in block['steps'])
        content = f'<ol class="flow">{steps}</ol>'
        if block.get('caption'):
            content += f'<p class="source">{escape(block["caption"])}</p>'
    elif kind == 'details':
        inner = ''.join(render_block(child, base_dir) for child in block['blocks'])
        content = f'<details class="derivation"><summary>{escape(block["summary"])}</summary>{inner}</details>'
    else:
        raise ValueError(f'Unsupported block type {kind}')
    return content + source_note(block)


def offline_math():
    root = SKILL_ROOT / 'assets/katex'
    css = (root / 'katex.min.css').read_text(encoding='utf-8')
    css = re.sub(r',url\([^)]*\) format\("(?:woff|truetype)"\)', '', css)

    def font_url(match):
        font = root / match.group(1)
        data = base64.b64encode(font.read_bytes()).decode('ascii')
        return f'url(data:font/woff2;base64,{data})'

    css = re.sub(r'url\((fonts/[^)]+\.woff2)\)', font_url, css)
    if 'url(fonts/' in css:
        raise ValueError('Some math font URLs were not embedded')
    script = (root / 'katex.min.js').read_text(encoding='utf-8')
    script = re.sub(r'(?i)</script', r'<\/script', script)
    return css, script


def render_document(data, base_dir):
    if not data.get('title') or not data.get('sections'):
        raise ValueError('A lecture needs a title and at least one section')
    navigation, sections, ids = [], [], set()
    for index, section in enumerate(data['sections'], 1):
        section_id = section['id']
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', section_id) or section_id in ids:
            raise ValueError(f'Invalid or duplicate section id {section_id}')
        ids.add(section_id)
        navigation.append(f'<a href="#{section_id}"><span>{index:02d}</span>{escape(section["title"])}</a>')
        question = f'<p class="section-question">{escape(section["question"])}</p>' if section.get('question') else ''
        body = ''.join(render_block(block, base_dir) for block in section['blocks'])
        sections.append(
            f'<section id="{section_id}" class="lecture-section">'
            f'<div class="section-number">{index:02d}</div><h2>{escape(section["title"])}</h2>'
            f'{question}{body}</section>'
        )
    math_css, math_script = offline_math()
    replacements = {
        'TITLE': escape(data['title']),
        'SUBTITLE': escape(data.get('subtitle', '')),
        'AUDIENCE': escape(data.get('audience', '')),
        'SOURCE': escape(data.get('source', '')),
        'NAVIGATION': ''.join(navigation),
        'SECTIONS': ''.join(sections),
        'MATH_CSS': math_css,
        'MATH_SCRIPT': math_script,
    }
    template = (SKILL_ROOT / 'assets/lecture.html').read_text(encoding='utf-8')
    return re.sub(r'\{\{([A-Z_]+)\}\}', lambda match: replacements[match.group(1)], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding='utf-8-sig'))
        document = render_document(data, args.input.resolve().parent)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + '.tmp')
        temporary.write_text(document, encoding='utf-8')
        temporary.replace(args.output)
    except (KeyError, ValueError, OSError, TypeError) as error:
        print(f'Lecture rendering failed — {error}', file=sys.stderr)
        return 1
    print(str(args.output.resolve()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
