#!/usr/bin/env python3
"""Convert the HTML review docs in .docs/ to .docx for import into Google Docs.

Upload the output to Drive and open it with Google Docs. Headings arrive as real
Google Docs heading styles, so the outline pane and Insert > Table of contents work.

Usage: scripts/docs-to-docx.py [source.html ...]   (default: every .docs/*.html)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / ".docs"
OUT = DOCS / "build"

# Google Docs native metrics, so an imported doc matches one typed in Docs.
BODY_FONT = "Arial"
MONO_FONT = "Roboto Mono"
HEADING_INK = "202124"
ACCENT = "1155CC"
CODE_FILL = "F6F8FA"
INLINE_CODE_FILL = "F1F3F4"
FIGURE_FILL = "F8F9FA"
TABLE_HEAD_FILL = "EEF2F8"
RULE = "D9D9D9"


# --------------------------------------------------------------------------
# HTML preprocessing
# --------------------------------------------------------------------------


def find_matching_div(html: str, start: int) -> int:
    """Return the index just past the </div> closing the <div at `start`."""
    depth = 0
    for m in re.finditer(r"<(/?)div\b[^>]*>", html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return start + m.end()
    raise ValueError(f"unbalanced <div> at offset {start}")


def flatten_chips(block: str) -> str:
    """Render a flex chip diagram as one readable line; flexbox does not survive docx."""
    tokens = re.findall(r'<span class="(chip|arrow)">(.*?)</span>', block, flags=re.S)
    parts: list[str] = []
    for kind, inner in tokens:
        if kind == "arrow":
            parts.append("&rarr;")
            continue
        sub = re.search(r"(.*?)<small>(.*?)</small>", inner, flags=re.S)
        label = f"{sub.group(1).strip()} ({sub.group(2).strip()})" if sub else inner.strip()
        if parts and parts[-1] != "&rarr;":
            parts.append("&middot;")
        parts.append(label)
    return "<p>" + " ".join(parts) + "</p>"


def rewrite_figures(html: str) -> str:
    """Turn .figure callouts into blockquotes so they read as set-off blocks in Docs."""
    while (m := re.search(r'<div class="figure">', html)) is not None:
        end = find_matching_div(html, m.start())
        inner = html[m.end() : end - len("</div>")]
        if 'class="chips"' in inner:
            chips_start = inner.index('<div class="chips">')
            chips_end = find_matching_div(inner, chips_start)
            inner = (
                inner[:chips_start]
                + flatten_chips(inner[chips_start:chips_end])
                + inner[chips_end:]
            )
        inner = re.sub(r'<div class="edge">(.*?)</div>', r"<p>\1</p>", inner, flags=re.S)
        if "<p>" not in inner:
            inner = f"<p>{inner.strip()}</p>"
        html = html[: m.start()] + f"<blockquote>{inner}</blockquote>" + html[end:]
    return html


def preprocess(html: str) -> str:
    # The <title> metadata and the body <h1> both render, producing a doubled title.
    html = re.sub(r"<title>.*?</title>", "", html, flags=re.S)
    html = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    return rewrite_figures(html)


# --------------------------------------------------------------------------
# Reference .docx
# --------------------------------------------------------------------------


def style_block(styles: str, style_id: str) -> re.Match[str] | None:
    for m in re.finditer(r"<w:style\b[^>]*>(?:(?!</w:style>).)*</w:style>", styles, re.S):
        if re.search(rf'w:styleId="{style_id}"', m.group(0)):
            return m
    return None


def replace_style(
    styles: str, style_id: str, fn: Callable[[str], str], seed: str | None = None
) -> str:
    """Patch a style in place, seeding it first if pandoc only synthesises it on write."""
    m = style_block(styles, style_id)
    if m is None:
        if seed is None:
            raise KeyError(style_id)
        return styles.replace("</w:styles>", fn(seed) + "</w:styles>")
    return styles[: m.start()] + fn(m.group(0)) + styles[m.end() :]


def set_run_props(block: str, props: str) -> str:
    """Replace a style's <w:rPr> body, dropping theme colours and fonts."""
    if "<w:rPr>" in block:
        return re.sub(r"<w:rPr>.*?</w:rPr>", f"<w:rPr>{props}</w:rPr>", block, flags=re.S)
    return block.replace("</w:style>", f"<w:rPr>{props}</w:rPr></w:style>")


# CT_PPrBase fixes the order of its children; a consumer drops properties that
# arrive out of sequence, so paragraph properties are always emitted through this.
PPR_ORDER = (
    "keepNext",
    "keepLines",
    "pageBreakBefore",
    "numPr",
    "pBdr",
    "shd",
    "spacing",
    "ind",
    "jc",
    "outlineLvl",
)


def para_props(**parts: str) -> str:
    unknown = set(parts) - set(PPR_ORDER)
    if unknown:
        raise ValueError(f"unordered pPr children: {sorted(unknown)}")
    return "".join(parts[k] for k in PPR_ORDER if parts.get(k))


def set_para_props(block: str, props: str) -> str:
    if "<w:pPr>" in block:
        return re.sub(r"<w:pPr>.*?</w:pPr>", f"<w:pPr>{props}</w:pPr>", block, flags=re.S)
    return block.replace("</w:style>", f"<w:pPr>{props}</w:pPr></w:style>")


def heading(size_pt: float, *, rule: bool = False, outline_lvl: str = "") -> Callable[[str], str]:
    half = int(size_pt * 2)

    def apply(block: str) -> str:
        block = set_para_props(
            block,
            para_props(
                keepNext="<w:keepNext/>",
                keepLines="<w:keepLines/>",
                pBdr=(
                    '<w:pBdr><w:bottom w:val="single" w:sz="8" w:space="2"'
                    f' w:color="{ACCENT}"/></w:pBdr>'
                    if rule
                    else ""
                ),
                spacing='<w:spacing w:before="280" w:after="120"/>',
                outlineLvl=outline_lvl,
            ),
        )
        return set_run_props(
            block,
            f'<w:rFonts w:ascii="{BODY_FONT}" w:hAnsi="{BODY_FONT}" w:cs="{BODY_FONT}"/>'
            f'<w:b/><w:color w:val="{HEADING_INK}"/><w:sz w:val="{half}"/><w:szCs w:val="{half}"/>',
        )

    return apply


def patch_styles(styles: str) -> str:
    # Body text: 11pt, matching the Google Docs Normal style.
    styles = styles.replace(
        '<w:sz w:val="24" /><w:szCs w:val="24" />', '<w:sz w:val="22"/><w:szCs w:val="22"/>'
    )
    styles = re.sub(
        r'<w:sz w:val="24" />\s*<w:szCs w:val="24" />',
        '<w:sz w:val="22"/><w:szCs w:val="22"/>',
        styles,
    )

    for sid, size, rule in (
        ("Heading1", 20, False),
        ("Heading2", 16, True),
        ("Heading3", 14, False),
        ("Heading4", 12, False),
    ):
        outline = f'<w:outlineLvl w:val="{int(sid[-1]) - 1}"/>'
        styles = replace_style(styles, sid, heading(size, rule=rule, outline_lvl=outline))

    # Inline code: monospace with a light highlight.
    styles = replace_style(
        styles,
        "VerbatimChar",
        lambda b: set_run_props(
            b,
            f'<w:rFonts w:ascii="{MONO_FONT}" w:hAnsi="{MONO_FONT}"/>'
            f'<w:shd w:val="clear" w:fill="{INLINE_CODE_FILL}"/><w:sz w:val="19"/><w:szCs w:val="19"/>',
        ),
    )

    # Code blocks: shaded, boxed, and wrapping (pandoc ships wordWrap off).
    styles = replace_style(
        styles,
        "SourceCode",
        lambda b: set_run_props(
            set_para_props(
                b,
                para_props(
                    pBdr=(
                        f'<w:pBdr><w:top w:val="single" w:sz="4" w:space="4" w:color="{RULE}"/>'
                        f'<w:left w:val="single" w:sz="4" w:space="4" w:color="{RULE}"/>'
                        f'<w:bottom w:val="single" w:sz="4" w:space="4" w:color="{RULE}"/>'
                        f'<w:right w:val="single" w:sz="4" w:space="4" w:color="{RULE}"/></w:pBdr>'
                    ),
                    shd=f'<w:shd w:val="clear" w:fill="{CODE_FILL}"/>',
                    spacing='<w:spacing w:before="120" w:after="120" w:line="240" w:lineRule="auto"/>',
                ),
            ),
            f'<w:rFonts w:ascii="{MONO_FONT}" w:hAnsi="{MONO_FONT}"/><w:sz w:val="19"/><w:szCs w:val="19"/>',
        ),
        seed=(
            '<w:style w:type="paragraph" w:customStyle="1" w:styleId="SourceCode">'
            '<w:name w:val="Source Code"/><w:basedOn w:val="Normal"/>'
            '<w:link w:val="VerbatimChar"/></w:style>'
        ),
    )

    # Figure placeholders arrive as blockquotes; make them read as callouts.
    styles = replace_style(
        styles,
        "BlockText",
        lambda b: set_run_props(
            set_para_props(
                b,
                para_props(
                    pBdr=(
                        '<w:pBdr><w:left w:val="single" w:sz="18" w:space="8"'
                        f' w:color="{RULE}"/></w:pBdr>'
                    ),
                    shd=f'<w:shd w:val="clear" w:fill="{FIGURE_FILL}"/>',
                    spacing='<w:spacing w:before="160" w:after="160"/>',
                    ind='<w:ind w:left="240" w:right="0" w:firstLine="0"/>',
                ),
            ),
            '<w:i/><w:color w:val="5F6368"/>',
        ),
    )

    # pandoc's default table style draws only a header underline.
    styles = replace_style(
        styles,
        "Table",
        lambda b: re.sub(
            r"<w:tblPr>.*?</w:tblPr>",
            "<w:tblPr>"
            f'<w:tblBorders><w:top w:val="single" w:sz="4" w:color="{RULE}"/>'
            f'<w:left w:val="single" w:sz="4" w:color="{RULE}"/>'
            f'<w:bottom w:val="single" w:sz="4" w:color="{RULE}"/>'
            f'<w:right w:val="single" w:sz="4" w:color="{RULE}"/>'
            f'<w:insideH w:val="single" w:sz="4" w:color="{RULE}"/>'
            f'<w:insideV w:val="single" w:sz="4" w:color="{RULE}"/></w:tblBorders>'
            '<w:tblInd w:type="dxa" w:w="0"/>'
            '<w:tblCellMar><w:top w:type="dxa" w:w="60"/><w:left w:type="dxa" w:w="108"/>'
            '<w:bottom w:type="dxa" w:w="60"/><w:right w:type="dxa" w:w="108"/></w:tblCellMar>'
            "</w:tblPr>"
            '<w:tblStylePr w:type="firstRow"><w:rPr><w:b/></w:rPr>'
            f'<w:tcPr><w:shd w:val="clear" w:fill="{TABLE_HEAD_FILL}"/>'
            '<w:vAlign w:val="top"/></w:tcPr></w:tblStylePr>',
            b,
            flags=re.S,
        ),
    )
    return styles


def build_reference_docx(dest: Path) -> None:
    """Patch pandoc's default reference.docx to Google Docs' native metrics."""
    default = subprocess.run(
        ["pandoc", "--print-default-data-file", "reference.docx"],
        check=True,
        capture_output=True,
    ).stdout
    src = dest.with_suffix(".src.docx")
    src.write_bytes(default)

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                data = patch_styles(data.decode("utf-8")).encode("utf-8")
            elif item.filename == "word/theme/theme1.xml":
                text = data.decode("utf-8")
                # Aptos is not a Google Docs font; pin both theme slots to Arial.
                text = re.sub(r'typeface="Aptos Display"', f'typeface="{BODY_FONT}"', text)
                text = re.sub(r'typeface="Aptos"', f'typeface="{BODY_FONT}"', text)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    src.unlink()


# --------------------------------------------------------------------------


def convert(source: Path, reference: Path) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{source.stem}.docx"
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
        tmp.write(preprocess(source.read_text(encoding="utf-8")))
        staged = Path(tmp.name)
    try:
        subprocess.run(
            [
                "pandoc",
                str(staged),
                "--from=html",
                "--to=docx",
                f"--reference-doc={reference}",
                "--standalone",
                f"--resource-path={source.parent}",
                "-o",
                str(target),
            ],
            check=True,
        )
    finally:
        staged.unlink(missing_ok=True)
    return target


def main() -> int:
    if not shutil.which("pandoc"):
        print("pandoc not found; install it with: brew install pandoc", file=sys.stderr)
        return 1

    sources = [Path(a).resolve() for a in sys.argv[1:]] or sorted(DOCS.glob("*.html"))
    if not sources:
        print(f"no HTML docs found in {DOCS}", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    reference = OUT / "reference.docx"
    build_reference_docx(reference)

    for source in sources:
        target = convert(source, reference)
        print(f"{target.relative_to(REPO)}  ({target.stat().st_size // 1024} KB)")

    print("\nUpload to Google Drive, then right-click > Open with > Google Docs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
