"""Structured EPUB extraction.

The previous path handed the file to PyMuPDF and asked for plain text. That
renders the book and gives back flat lines, so headings, paragraphs, list
structure, superscripts and every equation arrive already flattened — an
``<mtable>`` of five production rules comes out as ``1. S->AB.2. A->aaA.``
and there is nothing downstream that can put it back.

An EPUB is XHTML in a zip, so the structure is simply there to be read. This
module reads the content documents in spine order and produces
``ContentBlock`` values that keep it.

Only the standard library is used. An EPUB content document is well-formed
XML by specification, so ElementTree is enough, and the reader ships as a
packaged build where every extra dependency has to be bundled.
"""

import posixpath
import re
import zipfile
from copy import deepcopy
from xml.etree import ElementTree

from reader.content_blocks import (
    EQUATION,
    FIGURE,
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    ContentBlock,
)


CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
XHTML_NS = "http://www.w3.org/1999/xhtml"
MATHML_NS = "http://www.w3.org/1998/Math/MathML"
EPUB_NS = "http://www.idpf.org/2007/ops"

CONTAINER_PATH = "META-INF/container.xml"

MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


class EpubLimitError(ValueError):
    """An EPUB exceeds the safe uncompressed read limits."""


class _EpubArchive(zipfile.ZipFile):
    """Keep one byte budget for all member reads in this archive."""

    def __init__(self, path):
        super().__init__(path)
        self._total_bytes_read = 0

    def read_member(self, path: str) -> bytes:
        info = self.getinfo(path)
        if info.file_size > MAX_MEMBER_BYTES:
            raise EpubLimitError(
                f"EPUB member {path!r} exceeds the {MAX_MEMBER_BYTES}-byte "
                "uncompressed member limit."
            )

        chunks = []
        member_bytes = 0
        with self.open(info) as source:
            while True:
                # Probe at most one byte beyond either budget, even when
                # the member's declared size understates its actual size.
                size = min(
                    64 * 1024,
                    MAX_MEMBER_BYTES - member_bytes + 1,
                    MAX_TOTAL_BYTES - self._total_bytes_read + 1,
                )
                chunk = source.read(size)
                if not chunk:
                    break
                member_bytes += len(chunk)
                self._total_bytes_read += len(chunk)
                if member_bytes > MAX_MEMBER_BYTES:
                    raise EpubLimitError(
                        f"EPUB member {path!r} exceeds the {MAX_MEMBER_BYTES}-byte "
                        "uncompressed member limit."
                    )
                if self._total_bytes_read > MAX_TOTAL_BYTES:
                    raise EpubLimitError(
                        f"EPUB exceeds the {MAX_TOTAL_BYTES}-byte total "
                        f"uncompressed read limit while reading {path!r}."
                    )
                chunks.append(chunk)
        return b"".join(chunks)


HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

BLOCK_TAGS = {"p", "li", "blockquote", "figcaption", "dd", "dt", "pre"}

# Inline elements whose emphasis is worth keeping in the displayed markup.
EMPHASIS_TAGS = {"i": "i", "em": "i", "b": "b", "strong": "b"}

SKIP_TAGS = {"script", "style", "head"}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def namespace_of(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ----------------------------------------------------------------------
# text runs
# ----------------------------------------------------------------------


class RunBuilder:
    """Collects characters and the styles that apply to them.

    ``text`` and ``html`` are built from the same runs, so they always hold
    the same characters in the same order. The reader highlights by selecting
    a character range against the displayed document, and that only works
    while markup adds no characters of its own.
    """

    def __init__(self):
        self.runs: list[tuple[str, tuple[str, ...]]] = []

    def add(self, text: str, styles: tuple[str, ...] = ()):
        if text:
            self.runs.append((text, styles))

    @property
    def text(self) -> str:
        return "".join(text for text, _styles in self.runs)

    def html(self) -> str:
        parts = []

        for text, styles in self.runs:
            fragment = escape(text).replace("\n", "<br/>")

            for style in reversed(styles):
                fragment = f"<{style}>{fragment}</{style}>"

            parts.append(fragment)

        return "".join(parts)

    def normalized(self, preserve_lines=False):
        """Normalize runs once, then derive both text and markup from them.

        U+2028 marks an explicit source break, unlike XHTML indentation.
        Keep typography spaces; pre-wrap in the renderer preserves them too.
        """
        if preserve_lines:
            result = RunBuilder()
            for text, styles in self.runs:
                result.add(text.replace("\r\n", "\n").replace("\u2028", "\n"), styles)
            return result

        result = RunBuilder()
        pending_space = None
        for text, styles in self.runs:
            for character in text.replace("\r\n", "\n"):
                if character == "\u2028":
                    pending_space = None
                    result.add("\n", ())
                elif character in " \t\r\n\u00a0":
                    pending_space = styles
                else:
                    if pending_space is not None and result.runs and not result.runs[-1][0].endswith("\n"):
                        result.add(" ", pending_space)
                    pending_space = None
                    result.add(character, styles)
        # Coalesce styles without touching character positions.
        combined = RunBuilder()
        for text, styles in result.runs:
            if combined.runs and combined.runs[-1][1] == styles:
                previous, _ = combined.runs[-1]
                combined.runs[-1] = (previous + text, styles)
            else:
                combined.add(text, styles)
        return combined


def collapse(text: str) -> str:
    """Normalize prose whitespace without touching the characters themselves.

    Source whitespace is what joins text across inline elements, so runs are
    concatenated verbatim first and only collapsed here. Inserting a space
    around every element instead would split words and expressions.
    """
    return re.sub(r"[ \t\r\n ]+", " ", text).strip()


# ----------------------------------------------------------------------
# MathML to notation
# ----------------------------------------------------------------------


def render_math(element, builder: RunBuilder, styles: tuple[str, ...] = ()):
    """Render MathML as the notation a reader expects to see.

    Superscripts and subscripts map onto the tags Qt's rich text actually
    supports. An overscript — which is how this book writes a derivation
    arrow carrying its rule number — has no equivalent, so it is rendered as
    a superscript on the operator: visually close, and honest about what the
    markup can express.
    """
    name = local_name(element.tag)

    children = [
        child
        for child in element
        if namespace_of(child.tag) in ("", MATHML_NS)
    ]

    if name in ("mi", "mn", "mo", "mtext", "ms"):
        builder.add(element.text or "", styles)
        return

    if name == "mspace":
        builder.add(" ", styles)
        return

    if name in ("annotation", "annotation-xml", "mphantom"):
        return

    if name == "semantics":
        if children:
            render_math(children[0], builder, styles)
        return

    if name == "mfenced":
        builder.add(element.get("open", "("), styles)
        separators = element.get("separators", ",").replace(" ", "")
        for index, child in enumerate(children):
            if index and separators:
                builder.add(separators[min(index - 1, len(separators) - 1)], styles)
            render_math(child, builder, styles)
        builder.add(element.get("close", ")"), styles)
        return

    if name in ("math", "mrow", "mstyle", "mpadded", "menclose"):
        for child in children:
            render_math(child, builder, styles)
        return

    if name in ("msup", "msub", "mover", "munder"):
        if len(children) >= 1:
            render_math(children[0], builder, styles)

        if len(children) >= 2:
            script = "sup" if name in ("msup", "mover") else "sub"
            render_math(children[1], builder, styles + (script,))

        return

    if name in ("msubsup", "munderover"):
        if len(children) >= 1:
            render_math(children[0], builder, styles)

        if len(children) >= 2:
            render_math(children[1], builder, styles + ("sub",))

        if len(children) >= 3:
            render_math(children[2], builder, styles + ("sup",))

        return

    if name == "mfrac":
        if len(children) >= 2:
            builder.add("(", styles)
            render_math(children[0], builder, styles)
            builder.add(")/(", styles)
            render_math(children[1], builder, styles)
            builder.add(")", styles)

        return

    if name == "msqrt":
        builder.add("√(", styles)

        for child in children:
            render_math(child, builder, styles)

        builder.add(")", styles)

        return

    if name == "mtable":
        rows = [child for child in children if local_name(child.tag) == "mtr"]

        for index, row in enumerate(rows):
            if index:
                # One rule per line. This is the boundary the old extraction
                # lost, which is why five productions became one run-on line.
                builder.add("\u2028", ())

            render_math(row, builder, styles)

        return

    if name == "mtr":
        cells = [child for child in children if local_name(child.tag) == "mtd"]

        for index, cell in enumerate(cells):
            if index:
                builder.add(" ", styles)

            render_math(cell, builder, styles)

        return

    for child in children:
        render_math(child, builder, styles)


# ----------------------------------------------------------------------
# inline walking
# ----------------------------------------------------------------------


def walk_inline(
    element,
    builder: RunBuilder,
    state: dict,
    styles: tuple[str, ...] = (),
    in_math: bool = False,
):
    """Append an element's children to the builder, in source order.

    Text is taken as the source wrote it — an element's own text, then each
    child, then that child's tail. Nothing is inserted between elements,
    because a space added around every tag runs words together wrongly and
    splits expressions that were never separated.
    """
    for child in element:
        name = local_name(child.tag)

        if name in SKIP_TAGS:
            _add_prose(builder, state, child.tail or "", styles, in_math)
            continue

        if namespace_of(child.tag) == MATHML_NS or name == "math":
            before = len(builder.runs)

            render_math(child, builder, styles)

            state.setdefault("mathml", []).append(child)
            state["math_runs"] = state.get("math_runs", 0) + (
                len(builder.runs) - before
            )


        elif name == "br":
            builder.add("\u2028", ())


        elif name == "img":
            source_attribute = child.get("src")

            if source_attribute:
                state.setdefault("images", []).append(source_attribute)

            # Images must not silently vanish from the text flow.
            builder.add(child.get("alt") or "[Image]", styles)


        elif name == "span" and child.get(f"{{{EPUB_NS}}}type") == "pagebreak":
            label = child.get("title") or child.get("id", "").removeprefix("page_")

            if label:
                state["page_label"] = label


        else:
            child_styles = styles

            if name in ("sup", "sub"):
                child_styles = styles + (name,)
            elif name in EMPHASIS_TAGS:
                child_styles = styles + (EMPHASIS_TAGS[name],)

            _add_prose(builder, state, child.text or "", child_styles, in_math)

            walk_inline(child, builder, state, child_styles, in_math)


        # A tail sits outside the child, so it is prose whenever the
        # surrounding element is.
        _add_prose(builder, state, child.tail or "", styles, in_math)

    return builder


def _add_prose(
    builder: RunBuilder,
    state: dict,
    text: str,
    styles: tuple[str, ...],
    in_math: bool,
):
    """Add text, and remember how much of it was outside any equation.

    A paragraph whose only content is an equation is an equation block. One
    with a sentence around it is prose that happens to contain notation, and
    has to keep reading as prose.
    """
    if not text:
        return

    builder.add(text, styles)

    if not in_math:
        state["prose"] = state.get("prose", "") + text


def inline_content(element, state: dict) -> RunBuilder:
    builder = RunBuilder()

    _add_prose(builder, state, element.text or "", (), False)

    walk_inline(element, builder, state)

    return builder


# ----------------------------------------------------------------------
# package
# ----------------------------------------------------------------------


def _read_package(archive: _EpubArchive) -> tuple[str, list[str]]:
    """Return the OPF path and its spine, as content-document paths."""
    container = ElementTree.fromstring(archive.read_member(CONTAINER_PATH))

    rootfile = container.find(f".//{{{CONTAINER_NS}}}rootfile")

    if rootfile is None or not rootfile.get("full-path"):
        raise ValueError("This EPUB has no package document.")

    opf_path = rootfile.get("full-path")

    package = ElementTree.fromstring(archive.read_member(opf_path))

    manifest = {}

    for item in package.iter(f"{{{OPF_NS}}}item"):
        identifier = item.get("id")
        href = item.get("href")

        if identifier and href:
            manifest[identifier] = (href, item.get("media-type", ""))

    base = posixpath.dirname(opf_path)

    documents = []

    for reference in package.iter(f"{{{OPF_NS}}}itemref"):
        entry = manifest.get(reference.get("idref"))

        if entry is None:
            continue

        href, media_type = entry

        if "html" not in media_type and not href.endswith((".xhtml", ".html")):
            continue

        documents.append(posixpath.normpath(posixpath.join(base, href)))

    return opf_path, documents


def _parse_document(archive: _EpubArchive, path: str):
    data = archive.read_member(path)

    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        print(f"Could not parse {path}: {error}")
        return None


def _body_of(root):
    for element in root.iter():
        if local_name(element.tag) == "body":
            return element

    return root


# ----------------------------------------------------------------------
# extraction
# ----------------------------------------------------------------------


def extract_blocks(epub_path: str) -> list[ContentBlock]:
    """Read an EPUB into ordered content blocks.

    Documents are visited in spine order, which is the order the book is
    meant to be read in; the manifest order is not.
    """
    blocks: list[ContentBlock] = []

    with _EpubArchive(epub_path) as archive:
        _opf, documents = _read_package(archive)

        page_label = None

        for document in documents:
            try:
                root = _parse_document(archive, document)
            except KeyError as error:
                raise ValueError(f"Missing EPUB content document: {document}") from error

            if root is None:
                raise ValueError(f"Cannot parse EPUB content document: {document}")

            page_label = _extract_document(
                archive,
                document,
                _body_of(root),
                blocks,
                page_label,
            )

    return blocks


def _list_markers(body) -> dict:
    """Marker text for every list item, keyed by element identity.

    ``body.iter()`` visits elements without their parents, so an item's
    position in its list is worked out here, once, rather than guessed later.
    """
    markers = {}

    for element in body.iter():
        name = local_name(element.tag)

        if name not in ("ol", "ul"):
            continue

        items = [child for child in element if local_name(child.tag) == "li"]

        start = int(element.get("start", "1") or 1)

        for offset, item in enumerate(items):
            markers[id(item)] = (
                f"{start + offset}. " if name == "ol" else "\u2022 "
            )

    return markers


def _flow_elements(body):
    """Emit each piece of block content exactly once, in document order.

    Containers can have direct text, nested paragraphs and text after a list.
    Iterating all descendants and then using itertext on their parents repeats
    entire paragraphs. Flush direct inline content around child blocks instead.
    """
    containers = BLOCK_TAGS | set(HEADING_TAGS) | {
        "body", "section", "article", "div", "ol", "ul", "table", "thead",
        "tbody", "tfoot", "tr", "td", "th", "figure", "dl", "aside",
        "main", "header", "footer", "nav", "details", "summary", "address",
    }

    def page_label(element):
        if "pagebreak" in element.get(f"{{{EPUB_NS}}}type", "").split():
            return element.get("title") or element.get("aria-label", "").removeprefix("page ") or element.get("id", "").removeprefix("page_")
        return None

    def walk(element):
        name = local_name(element.tag)
        if name in SKIP_TAGS:
            return
        label = page_label(element)
        if label is not None:
            yield None, None, label
            return
        tag = element.tag if name in BLOCK_TAGS or name in HEADING_TAGS else "p"
        fragment = ElementTree.Element(tag, element.attrib)
        fragment.text = element.text
        first = True

        def populated(node):
            return bool((node.text or "").strip()) or len(node) > 0

        for child in element:
            child_name = local_name(child.tag)
            if child_name in containers or page_label(child) is not None:
                if populated(fragment):
                    yield fragment, element, None
                    first = False
                for nested, original, event in walk(child):
                    if name == "li" and first and nested is not None:
                        nested.tag = "li"
                        original = element
                        first = False
                    yield nested, original, event
                fragment = ElementTree.Element(tag, element.attrib if first else {})
                fragment.text = child.tail
            else:
                # Fragment nodes must not mutate the original source tree.
                fragment.append(deepcopy(child))
        if populated(fragment):
            yield fragment, element, None

    yield from walk(body)


def _extract_document(
    archive: _EpubArchive,
    document: str,
    body,
    blocks: list[ContentBlock],
    page_label: str | None,
) -> str | None:
    directory = posixpath.dirname(document)

    markers = _list_markers(body)

    for element, original, page_event in _flow_elements(body):
        if page_event is not None:
            page_label = page_event
            continue
        name = local_name(element.tag)
        state: dict = {"page_label": None}

        builder = inline_content(element, state)

        # A pagebreak anchor inside a block marks where the printed page
        # turns. The anchor sits at the start of the block in practice, so
        # the block is attributed to the new page.
        if state.get("page_label"):
            page_label = state["page_label"]

        raw = builder.text

        mathml = state.get("mathml") or []

        if name in HEADING_TAGS:
            kind = HEADING
            level = HEADING_TAGS[name]
        elif mathml and not collapse(state.get("prose", "")):
            kind = EQUATION
            level = 0
        elif name == "li":
            kind = LIST_ITEM
            level = 0
        elif state.get("images") and not collapse(raw):
            kind = FIGURE
            level = 0
        else:
            kind = PARAGRAPH
            level = 0

        builder = builder.normalized(preserve_lines=name == "pre")
        display_text = builder.text

        if kind == LIST_ITEM:
            marker = markers.get(id(original))
            markers.pop(id(original), None)
            if marker and not display_text.startswith(marker):
                builder.runs.insert(0, (marker, ()))
                display_text = builder.text

        if not display_text and not state.get("images"):
            continue

        identifier = element.get("id")

        source_id = (
            f"{document}#{identifier}"
            if identifier
            else f"{document}:{len(blocks)}"
        )

        blocks.append(
            ContentBlock(
                source_id=source_id,
                kind=kind,
                level=level,
                display_text=display_text,
                display_html=builder.html(),
                page_label=page_label,
                document=document,
                position=len(blocks),
                mathml=(
                    ElementTree.tostring(mathml[0], encoding="unicode")
                    if mathml
                    else None
                ),
                images=[
                    posixpath.normpath(posixpath.join(directory, source))
                    for source in state.get("images", [])
                ],
            )
        )

    return page_label


# ----------------------------------------------------------------------
# navigation
# ----------------------------------------------------------------------


def extract_nav(epub_path: str) -> list[tuple[int, str, str]]:
    """Read the EPUB's own table of contents.

    Returns ``(level, title, target)`` where target is a content-document
    path with an optional fragment. Chapter positions are kept as source
    targets rather than page numbers, because the printed page an EPUB
    reports is not the page a renderer would have invented.
    """
    entries: list[tuple[int, str, str]] = []

    with _EpubArchive(epub_path) as archive:
        opf_path, _documents = _read_package(archive)

        base = posixpath.dirname(opf_path)

        package = ElementTree.fromstring(archive.read_member(opf_path))

        nav_href = None
        ncx_href = None

        for item in package.iter(f"{{{OPF_NS}}}item"):
            properties = item.get("properties", "")
            href = item.get("href")

            if not href:
                continue

            if "nav" in properties.split():
                nav_href = posixpath.normpath(posixpath.join(base, href))

            if item.get("media-type") == "application/x-dtbncx+xml":
                ncx_href = posixpath.normpath(posixpath.join(base, href))

        if nav_href:
            entries = _read_nav_document(archive, nav_href)

        if not entries and ncx_href:
            entries = _read_ncx(archive, ncx_href)

    return entries


def _resolve(document: str, href: str) -> str:
    directory = posixpath.dirname(document)

    return posixpath.normpath(posixpath.join(directory, href))


def _read_nav_document(archive: _EpubArchive, path: str):
    try:
        root = _parse_document(archive, path)
    except KeyError:
        return []

    if root is None:
        return []

    for nav in root.iter():
        if local_name(nav.tag) != "nav":
            continue

        if nav.get(f"{{{EPUB_NS}}}type") != "toc":
            continue

        return _read_nav_list(nav, path)

    return []


def _read_nav_list(nav, document: str, level: int = 1):
    entries = []

    for element in nav:
        name = local_name(element.tag)

        if name in ("ol", "ul"):
            entries.extend(_read_nav_list(element, document, level))

        elif name == "li":
            for child in element:
                child_name = local_name(child.tag)

                if child_name == "a":
                    href = child.get("href")
                    title = collapse("".join(child.itertext()))

                    if href and title:
                        entries.append(
                            (level, title, _resolve(document, href))
                        )

                elif child_name in ("ol", "ul"):
                    entries.extend(
                        _read_nav_list(child, document, level + 1)
                    )

    return entries


def _read_ncx(archive: _EpubArchive, path: str):
    try:
        root = _parse_document(archive, path)
    except KeyError:
        return []

    if root is None:
        return []

    entries = []

    def walk(parent, level):
        for point in parent:
            if local_name(point.tag) != "navPoint":
                continue

            title = ""
            href = ""

            for child in point.iter():
                child_name = local_name(child.tag)

                if child_name == "text" and not title:
                    title = collapse(child.text or "")

                elif child_name == "content" and not href:
                    href = child.get("src", "")

            if title and href:
                entries.append((level, title, _resolve(path, href)))

            walk(point, level + 1)

    for nav_map in root.iter():
        if local_name(nav_map.tag) == "navMap":
            walk(nav_map, 1)
            break

    return entries
