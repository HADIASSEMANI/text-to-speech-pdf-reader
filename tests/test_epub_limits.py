"""Small EPUB fixtures exercise the uncompressed member and archive budgets."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from reader import epub_reader


CONTAINER = b'''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="book.opf"/></rootfiles></container>'''
CHAPTER = b'''<html xmlns="http://www.w3.org/1999/xhtml"><body>
<h1 id="start">Chapter One</h1><p>A <i>small</i> book.</p></body></html>'''
NAV = b'''<html xmlns="http://www.w3.org/1999/xhtml"
xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc">
<ol><li><a href="chapter.xhtml#start">Chapter One</a></li></ol>
</nav></body></html>'''
NCX = b'''<ncx><navMap><navPoint><navLabel><text>Chapter One</text></navLabel>
<content src="chapter.xhtml#start"/></navPoint></navMap></ncx>'''


class EpubLimitTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "small.epub"

    def build_epub(self, *, ncx=False, oversized=None):
        navigation = (
            '<item id="nav" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            if ncx else
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/>'
        )
        package = (
            '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
            '<item id="chapter" href="chapter.xhtml" '
            'media-type="application/xhtml+xml"/>'
            f'{navigation}</manifest><spine><itemref idref="chapter"/>'
            '</spine></package>'
        ).encode()
        members = {
            "META-INF/container.xml": CONTAINER,
            "book.opf": package,
            "chapter.xhtml": CHAPTER,
            "toc.ncx" if ncx else "nav.xhtml": NCX if ncx else NAV,
        }
        if oversized:
            members[oversized] += b" " * 2048
        with zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        return members

    def test_declared_oversized_members_are_refused_before_opening(self):
        for member in (
            "META-INF/container.xml", "book.opf", "chapter.xhtml",
            "nav.xhtml", "toc.ncx",
        ):
            with self.subTest(member=member):
                self.build_epub(ncx=member == "toc.ncx", oversized=member)
                extract = (
                    epub_reader.extract_nav if member in ("nav.xhtml", "toc.ncx")
                    else epub_reader.extract_blocks
                )
                opened = []
                original_open = zipfile.ZipFile.open

                def record_open(archive, info):
                    opened.append(info.filename)
                    return original_open(archive, info)

                with (
                    patch.object(epub_reader, "MAX_MEMBER_BYTES", 2048),
                    patch.object(epub_reader, "MAX_TOTAL_BYTES", 8192),
                    patch.object(epub_reader._EpubArchive, "open", record_open),
                    self.assertRaisesRegex(epub_reader.EpubLimitError, "member limit"),
                ):
                    extract(str(self.path))
                self.assertNotIn(member, opened)

    def test_cumulative_limit_includes_package_content_and_navigation_reads(self):
        members = self.build_epub()
        for extract, names in (
            (epub_reader.extract_blocks,
             ("META-INF/container.xml", "book.opf", "chapter.xhtml")),
            (epub_reader.extract_nav,
             ("META-INF/container.xml", "book.opf", "book.opf", "nav.xhtml")),
        ):
            total = sum(len(members[name]) for name in names)
            with (
                self.subTest(extract=extract.__name__),
                patch.object(epub_reader, "MAX_MEMBER_BYTES", 2048),
                patch.object(epub_reader, "MAX_TOTAL_BYTES", total - 1),
                self.assertRaisesRegex(epub_reader.EpubLimitError, "total.*read limit"),
            ):
                extract(str(self.path))

    def test_streamed_size_is_checked_even_when_declared_size_is_small(self):
        self.build_epub()
        with epub_reader._EpubArchive(self.path) as archive:
            # Simulate a dishonest size without writing a large ZIP member.
            source = io.BytesIO(b"x" * (64 * 1024 + 10))
            with (
                patch.object(epub_reader, "MAX_MEMBER_BYTES", 64 * 1024 + 1),
                patch.object(epub_reader, "MAX_TOTAL_BYTES", 128 * 1024),
                patch.object(archive, "open", return_value=source),
                patch.object(source, "read", wraps=source.read) as read,
                self.assertRaisesRegex(epub_reader.EpubLimitError, "member limit"),
            ):
                archive.read_member("chapter.xhtml")
            self.assertEqual([call.args[0] for call in read.call_args_list], [64 * 1024, 2])
            self.assertTrue(source.closed)

    def test_cumulative_limit_counts_actual_bytes_with_understated_sizes(self):
        self.build_epub()
        with (
            epub_reader._EpubArchive(self.path) as archive,
            patch.object(epub_reader, "MAX_MEMBER_BYTES", 2048),
            patch.object(epub_reader, "MAX_TOTAL_BYTES", 32),
        ):
            archive.getinfo("chapter.xhtml").file_size = 1
            archive.getinfo("nav.xhtml").file_size = 1
            with patch.object(archive, "open", return_value=io.BytesIO(b"x" * 20)):
                self.assertEqual(archive.read_member("chapter.xhtml"), b"x" * 20)
            source = io.BytesIO(b"y" * 20)
            with (
                patch.object(archive, "open", return_value=source),
                patch.object(source, "read", wraps=source.read) as read,
                self.assertRaisesRegex(epub_reader.EpubLimitError, "total.*read limit"),
            ):
                archive.read_member("nav.xhtml")
            read.assert_called_once_with(13)
            self.assertTrue(source.closed)

    def test_exact_limits_are_allowed_and_separate_archives_have_new_budgets(self):
        self.build_epub()
        for _ in range(2):
            with (
                epub_reader._EpubArchive(self.path) as archive,
                patch.object(epub_reader, "MAX_MEMBER_BYTES", len(CHAPTER)),
                patch.object(epub_reader, "MAX_TOTAL_BYTES", len(CHAPTER)),
            ):
                self.assertEqual(archive.read_member("chapter.xhtml"), CHAPTER)

    def test_normal_small_epub_keeps_text_markup_order_ids_and_navigation(self):
        for ncx in (False, True):
            with self.subTest(ncx=ncx):
                self.build_epub(ncx=ncx)
                with (
                    patch.object(epub_reader, "MAX_MEMBER_BYTES", 2048),
                    patch.object(epub_reader, "MAX_TOTAL_BYTES", 8192),
                ):
                    blocks = epub_reader.extract_blocks(str(self.path))
                    navigation = epub_reader.extract_nav(str(self.path))
                self.assertEqual(
                    [(block.display_text, block.display_html, block.source_id)
                     for block in blocks],
                    [("Chapter One", "Chapter One", "chapter.xhtml#start"),
                     ("A small book.", "A <i>small</i> book.", "chapter.xhtml:1")],
                )
                self.assertEqual(navigation, [(1, "Chapter One", "chapter.xhtml#start")])


if __name__ == "__main__":
    unittest.main()
