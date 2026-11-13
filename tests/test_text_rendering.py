"""Extraction and cue offsets checked against Qt, not stripped HTML strings."""
import os
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QGuiApplication, QTextDocument, QTextCursor
from reader.content_blocks import ContentBlock
from reader.cue_mapping import map_cues
from reader.epub_reader import _extract_document, extract_blocks
from reader.segmenter import create_segments, create_segments_from_blocks
from reader.models import TextCue
from tests.test_epub_extraction import REAL_BOOK


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def blocks(self, markup):
        blocks = []
        _extract_document(None, 'chapter.xhtml', ET.fromstring(markup), blocks, None)
        return blocks

    def assert_rendered(self, segment):
        doc = QTextDocument()
        if segment.html:
            doc.setHtml(segment.html)
        else:
            doc.setPlainText(segment.text)
        self.assertEqual(segment.text, doc.toPlainText())
        return doc

    def test_nested_lists_and_quotes_are_not_narrated_twice(self):
        blocks = self.blocks('<body><blockquote><p>A quotation.</p></blockquote>'
                             '<ol><li><p>Parent</p><ul><li>Child</li></ul>Tail</li></ol>'
                             '<div>Direct <b>text</b><p>A paragraph.</p>After.</div></body>')
        self.assertEqual(['A quotation.', '1. Parent', '• Child', 'Tail',
                          'Direct text', 'A paragraph.', 'After.'],
                         [b.display_text for b in blocks])

    def test_inline_whitespace_and_breaks_survive_rendering(self):
        blocks = self.blocks('<body><p> Before <i> emphasis </i> after.<br/>Next line.</p>'
                             '<p>A\u2009B\u2003\u2003C &amp; D.</p>'
                             '<p><b>  Trimmed  </b> end.</p></body>')
        segment = create_segments_from_blocks(blocks)[0]
        self.assertIn('Before emphasis after.\nNext line.', segment.text)
        self.assert_rendered(segment)

    def test_preformatted_lines_survive(self):
        segment = create_segments_from_blocks(self.blocks('<body><pre>First\n  Second</pre></body>'))[0]
        self.assertEqual('First\n  Second', segment.text)
        self.assert_rendered(segment)

    def test_aside_preserves_definition_paragraphs(self):
        blocks = self.blocks('<body><aside><p>DEFINITION 5.2</p>'
                             '<p>A derivation is leftmost.</p></aside></body>')
        self.assertEqual(['DEFINITION 5.2', 'A derivation is leftmost.'],
                         [b.display_text for b in blocks])

    def test_plain_documents_do_not_interpret_markup_or_collapse_newlines(self):
        segment = create_segments([{'page':1,'text':'Use <variable> & <b>literally</b>.\n\nSecond paragraph.'}])[0]
        self.assertEqual('', segment.html)
        self.assert_rendered(segment)

    def test_standalone_pagebreak_is_applied(self):
        blocks = self.blocks('<body xmlns:epub="http://www.idpf.org/2007/ops">'
                             '<p>Before.</p><span epub:type="pagebreak" title="42"/>'
                             '<p>After.</p></body>')
        self.assertEqual([None,'42'], [b.page_label for b in blocks])

    def test_math_semantics_does_not_repeat_annotations(self):
        blocks = self.blocks('<body><math xmlns="http://www.w3.org/1998/Math/MathML">'
            '<semantics><mfenced><mi>x</mi><mi>y</mi></mfenced>'
            '<annotation encoding="application/x-tex">duplicate</annotation></semantics>'
            '</math></body>')
        self.assertEqual('(x,y)', blocks[0].display_text)

    def test_images_are_not_silently_dropped(self):
        blocks = self.blocks('<body><p>See <img src="fig.png" alt="diagram"/> here.</p>'
                             '<p><img src="eq.png"/></p></body>')
        self.assertEqual(['See diagram here.','[Image]'],[b.display_text for b in blocks])

    def test_spoken_equation_and_unicode_cues_select_correct_display_ranges(self):
        blocks = [ContentBlock('a', display_text='😀 First\u2009sentence.', display_html='😀 First\u2009sentence.'),
                  ContentBlock('b', display_text='n ≥ 0', display_html='n ≥ 0',
                               spoken_text='n is greater than or equal to zero.'),
                  ContentBlock('c', display_text='First sentence.', display_html='First sentence.')]
        segment = create_segments_from_blocks(blocks)[0]
        segment.cues = [TextCue('😀 First sentence.',0,1),
                        TextCue('n is greater than or equal to zero.',1,2),
                        TextCue('First sentence.',2,3)]
        doc = self.assert_rendered(segment)
        offsets = map_cues(segment)
        self.assertEqual(3,len(offsets))
        selected = []
        for cue,start,end in offsets:
            cursor = QTextCursor(doc); cursor.setPosition(start)
            cursor.setPosition(end,QTextCursor.KeepAnchor)
            selected.append(cursor.selectedText())
        self.assertEqual([b.display_text for b in blocks],selected)

    def test_multiblock_cue_maps_across_different_separator_lengths(self):
        blocks = [ContentBlock('a',display_text='First.',display_html='First.'),
                  ContentBlock('b',display_text='Second.',display_html='Second.')]
        segment = create_segments_from_blocks(blocks)[0]
        segment.cues = [TextCue('First. Second.',0,1)]
        offsets = map_cues(segment)
        self.assertEqual((0,len(segment.text)),offsets[0][1:])

    @unittest.skipUnless(REAL_BOOK.exists(),'reference book unavailable')
    def test_every_reference_book_segment_matches_qt(self):
        for segment in create_segments_from_blocks(extract_blocks(str(REAL_BOOK))):
            with self.subTest(source=segment.source_ids):
                self.assert_rendered(segment)

    def test_unparseable_chapter_fails_instead_of_silently_skipping_it(self):
        from tests.test_epub_extraction import build_epub
        with tempfile.TemporaryDirectory() as root:
            path=build_epub(Path(root)/'book.epub')
            with patch('reader.epub_reader._parse_document',return_value=None):
                with self.assertRaisesRegex(ValueError,'Cannot parse'):
                    extract_blocks(str(path))


class ReaderPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        from PySide6.QtCore import QUrl, QObject
        from PySide6.QtQml import QQmlApplicationEngine
        from reader.viewmodel.app_viewmodel import AppViewModel
        from reader.paths import resource_path
        with patch('reader.viewmodel.book_list_model.get_recent_books',return_value=[]):
            self.vm = AppViewModel()
        self.vm.timer.stop()
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty('vm',self.vm)
        qml_url = QUrl.fromLocalFile(str(resource_path('qml'))).toString()
        qml = f'''import QtQuick
import QtQuick.Controls
import "{qml_url}"
ApplicationWindow {{ width: 900; height: 700; visible: true
ReaderPage {{ anchors.fill: parent; shown: true }} }}'''
        self.engine.loadData(qml.encode(),QUrl('file:///tmp/reader-test.qml'))
        self.assertTrue(self.engine.rootObjects())
        self.window = self.engine.rootObjects()[0]
        self.body = self.window.findChild(QObject,'readerBody')

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication,QEvent
        self.window.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.vm.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def show(self, text, html=''):
        self.vm._segment_text=text; self.vm._segment_html=html
        self.vm.segmentChanged.emit()
        self.app.processEvents()

    def selected(self):
        return self.body.property('selectedText').replace('\u2029','\n').replace('\u2028','\n')

    def test_switching_both_directions_preserves_literal_text(self):
        from PySide6.QtCore import QMetaObject
        for i in range(2):
            self.show('Rich text.','<p>Rich <b>text.</b></p>')
            QMetaObject.invokeMethod(self.body,'selectAll')
            self.assertEqual('Rich text.', self.selected())
            literal='Use <b>literal tags</b>.\n\nSecond paragraph.'
            self.show(literal)
            QMetaObject.invokeMethod(self.body,'selectAll')
            self.assertEqual(literal,self.selected())

    def test_qml_selection_uses_utf16_and_preserves_rich_math(self):
        blocks=[ContentBlock('a',display_text='😀 Before.',display_html='😀 Before.'),
                ContentBlock('b',display_text='a2n ≥ 0',display_html='a<sup>2n</sup> ≥ 0')]
        segment=create_segments_from_blocks(blocks)[0]
        segment.cues=[TextCue('a2n ≥ 0',0,1)]
        self.show(segment.text,segment.html)
        cue,start,end=map_cues(segment)[0]
        self.vm._highlight_start=start; self.vm._highlight_end=end
        self.vm.highlightChanged.emit();self.app.processEvents()
        self.assertEqual('a2n ≥ 0',self.selected())
        self.vm._set_cue_offsets(map_cues(segment))
        self.assertIs(cue,self.vm._cue_at_offset(start+1))


if __name__ == "__main__":
    unittest.main()
