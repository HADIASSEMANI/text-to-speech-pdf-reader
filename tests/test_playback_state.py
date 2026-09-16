"""Playback, resume and seeking behaviour, without an audio device.

ReaderController is exercised against a stand-in player so these run
anywhere: the point is the state machine and the arithmetic, not pygame.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reader.models import Segment


class FakePlayer:
    """Just enough AudioPlayer to drive the controller.

    Mirrors the one behaviour that caused the resume bug: ``stop()`` resets
    the position to zero, so anything that saves after stopping saves zero.
    """

    def __init__(self, segments, start_index=0):
        self.segments = segments
        self.current_index = start_index
        self.current_segment = None
        self.is_paused = False
        self.position = 0.0
        self.duration = 30.0
        self._playing = False
        self.shutdown_called = False

    def play(self):
        self.current_segment = self.segments[self.current_index]
        self.position = 0.0
        self.is_paused = False
        self._playing = True

    def pause(self):
        self.is_paused = True
        self._playing = False

    def resume(self):
        self.is_paused = False
        self._playing = True

    def stop(self):
        self.position = 0.0
        self.is_paused = False
        self._playing = False

    def seek(self, seconds):
        self.position = max(0.0, min(seconds, self.duration))

    def get_playback_position(self):
        return self.position

    def get_duration(self):
        return self.duration if self.current_segment is not None else 0.0

    def is_playing(self):
        return self._playing and not self.is_paused

    def shutdown(self):
        self.shutdown_called = True


class FakeTTS:
    def __init__(self, voice="af_heart", speed=0.85):
        self.voice = voice
        self.speed = speed

    def load_cues(self, audio_path):
        return []

    def generate(self, text, output_path, on_progress=None):
        Path(output_path).write_bytes(b"")
        return []


class ControllerTestCase(unittest.TestCase):
    """Builds a controller over real (empty) cache files in a temp directory."""

    SEGMENT_COUNT = 4

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        root = Path(self.directory.name)

        self.database = root / "reader.db"

        patcher = patch("reader.database.DATABASE_PATH", self.database)
        patcher.start()
        self.addCleanup(patcher.stop)

        from reader.database import initialize_database

        initialize_database()

        with self._connection() as connection:
            connection.execute(
                "INSERT INTO books (path, title) VALUES ('/tmp/book.pdf', 'Book')"
            )
            connection.commit()

        self.segments = []

        for index in range(self.SEGMENT_COUNT):
            audio = root / f"segment{index}.wav"
            audio.write_bytes(b"")

            self.segments.append(
                Segment(
                    id=index + 1,
                    page=index + 1,
                    text=f"Passage number {index}. It has two sentences.",
                    cache_id=f"cache{index}",
                    audio_path=str(audio),
                    generated=False,
                )
            )

        self.player_patcher = patch(
            "reader.controller.AudioPlayer",
            FakePlayer,
        )
        self.player_patcher.start()
        self.addCleanup(self.player_patcher.stop)

    @staticmethod
    def _connection():
        from reader.database import get_connection

        return get_connection()

    def make_controller(self, **kwargs):
        from reader.controller import ReaderController

        controller = ReaderController(
            segments=self.segments,
            tts=FakeTTS(),
            book_id=1,
            **kwargs,
        )

        # Every segment has a cache file, so durations are known without a
        # real decoder. 30 seconds each keeps the seek arithmetic readable.
        for segment in self.segments:
            controller._duration_cache[segment.audio_path] = 30.0

        return controller

    def saved_row(self):
        with self._connection() as connection:
            return connection.execute(
                "SELECT * FROM books WHERE id = 1"
            ).fetchone()


class ResumeTests(ControllerTestCase):
    def test_position_is_saved_before_the_player_is_stopped(self):
        """The library-return bug: stop() zeroes the offset, so save first."""
        controller = self.make_controller()

        controller.play()
        controller.player.position = 8.2

        controller.shutdown()

        row = self.saved_row()

        self.assertAlmostEqual(8.2, row["playback_position"], places=2)

    def test_stopping_saves_the_live_position(self):
        controller = self.make_controller()

        controller.play()
        controller.player.position = 12.5

        controller.stop()

        self.assertAlmostEqual(
            12.5,
            self.saved_row()["playback_position"],
            places=2,
        )

    def test_pausing_saves_the_position(self):
        controller = self.make_controller()

        controller.play()
        controller.player.position = 4.0
        controller.pause()

        self.assertAlmostEqual(
            4.0,
            self.saved_row()["playback_position"],
            places=2,
        )

    def test_an_anchor_is_written_with_the_position(self):
        controller = self.make_controller()

        controller.play()
        controller.player.position = 6.0
        controller.save_position(force=True)

        row = self.saved_row()

        self.assertEqual("cache0", row["anchor_cache_id"])
        self.assertEqual(1, row["anchor_page"])
        self.assertIn("Passage number 0", row["anchor_text"])

    def test_saved_position_is_restored_with_a_short_rewind(self):
        controller = self.make_controller(start_position=20.0, resume_rewind=3.0)

        self.assertAlmostEqual(17.0, controller.pending_seek)

        controller.play()

        self.assertAlmostEqual(17.0, controller.player.get_playback_position())

    def test_periodic_saves_are_throttled(self):
        controller = self.make_controller()

        controller.play()
        controller.player.position = 3.0
        controller.save_position(force=True)

        controller.player.position = 9.0
        controller.save_position()

        self.assertAlmostEqual(
            3.0,
            self.saved_row()["playback_position"],
            places=2,
            msg="an unforced save inside the interval should not write",
        )


class ResumeResolutionTests(ControllerTestCase):
    def _progress(self, **kwargs):
        from reader.progress import BookProgress, ProgressAnchor

        defaults = {
            "id": 1,
            "path": "/tmp/book.pdf",
            "title": "Book",
            "current_segment": 0,
            "playback_position": 0.0,
            "anchor": ProgressAnchor(),
        }
        defaults.update(kwargs)

        return BookProgress(**defaults)

    def test_matching_cache_id_restores_the_exact_offset(self):
        from reader.progress import ProgressAnchor, resolve_resume_point

        progress = self._progress(
            current_segment=0,
            playback_position=17.5,
            anchor=ProgressAnchor(cache_id="cache2", page=3, text="anything"),
        )

        index, position = resolve_resume_point(progress, self.segments)

        self.assertEqual(2, index)
        self.assertAlmostEqual(17.5, position)

    def test_resegmented_book_is_found_by_its_text(self):
        """Voice or chunking changed, so the cache id is gone but text remains."""
        from reader.progress import ProgressAnchor, resolve_resume_point

        progress = self._progress(
            current_segment=99,
            playback_position=17.5,
            anchor=ProgressAnchor(
                cache_id="a-cache-id-that-no-longer-exists",
                page=3,
                text="Passage number 2.",
            ),
        )

        index, position = resolve_resume_point(progress, self.segments)

        self.assertEqual(2, index)
        self.assertEqual(
            0.0,
            position,
            "seconds are meaningless once the audio has been re-rendered",
        )

    def test_page_anchor_is_used_when_the_text_has_changed(self):
        from reader.progress import ProgressAnchor, resolve_resume_point

        progress = self._progress(
            anchor=ProgressAnchor(cache_id="gone", page=3, text="not present"),
        )

        index, _position = resolve_resume_point(progress, self.segments)

        self.assertEqual(2, index)

    def test_out_of_range_index_falls_back_to_the_start(self):
        from reader.progress import resolve_resume_point

        index, position = resolve_resume_point(
            self._progress(current_segment=500),
            self.segments,
        )

        self.assertEqual((0, 0.0), (index, position))


class StateMachineTests(ControllerTestCase):
    def test_playing_and_the_transport_flag_agree(self):
        from reader.controller import PlaybackState

        controller = self.make_controller()

        self.assertIs(PlaybackState.STOPPED, controller.state)
        self.assertFalse(controller.running)

        controller.play()

        self.assertIs(PlaybackState.PLAYING, controller.state)
        self.assertTrue(controller.running)

        controller.pause()

        self.assertIs(PlaybackState.PAUSED, controller.state)
        self.assertFalse(controller.running)
        self.assertTrue(controller.player.is_paused)

    def test_next_while_playing_keeps_playing(self):
        """The reported defect: navigation started audio but read as paused."""
        from reader.controller import PlaybackState

        controller = self.make_controller()

        controller.play()
        controller.next()

        self.assertEqual(1, controller.get_current_index())
        self.assertIs(PlaybackState.PLAYING, controller.state)
        self.assertTrue(controller.running)
        self.assertTrue(controller.player.is_playing())

    def test_next_while_paused_stays_paused_and_silent(self):
        from reader.controller import PlaybackState

        controller = self.make_controller()

        controller.play()
        controller.pause()
        controller.next()

        self.assertEqual(1, controller.get_current_index())
        self.assertIs(PlaybackState.PAUSED, controller.state)
        self.assertFalse(controller.running)
        self.assertFalse(controller.player.is_playing())

    def test_previous_restarts_the_passage_when_well_into_it(self):
        controller = self.make_controller()

        controller.play()
        controller.next()
        controller.player.position = 12.0

        controller.previous()

        self.assertEqual(
            1,
            controller.get_current_index(),
            "previous should restart the current passage first",
        )

    def test_previous_at_the_start_moves_back(self):
        controller = self.make_controller()

        controller.play()
        controller.next()
        controller.player.position = 1.0

        controller.previous()

        self.assertEqual(0, controller.get_current_index())

    def test_page_jump_stops_playback(self):
        from reader.controller import PlaybackState

        controller = self.make_controller()

        controller.play()

        self.assertEqual(3, controller.go_to_page(3))
        self.assertIs(PlaybackState.STOPPED, controller.state)
        self.assertFalse(controller.player.is_playing())

    def test_end_of_book_finishes_rather_than_looping(self):
        from reader.controller import PlaybackState

        controller = self.make_controller(start_index=self.SEGMENT_COUNT - 1)

        controller.play()
        controller.next()

        self.assertIs(PlaybackState.FINISHED, controller.state)
        self.assertFalse(controller.running)


class CrossSegmentSeekTests(ControllerTestCase):
    def test_forward_overflow_carries_into_the_next_passage(self):
        controller = self.make_controller()

        controller.play()
        controller.player.position = 25.0

        controller.seek_relative(15)

        self.assertEqual(1, controller.get_current_index())
        self.assertAlmostEqual(10.0, controller.player.get_playback_position())

    def test_backward_underflow_carries_into_the_previous_passage(self):
        controller = self.make_controller(start_index=2)

        controller.play()
        controller.player.position = 5.0

        controller.seek_relative(-15)

        self.assertEqual(1, controller.get_current_index())
        self.assertAlmostEqual(20.0, controller.player.get_playback_position())

    def test_seeking_across_more_than_one_passage(self):
        controller = self.make_controller()

        controller.play()
        controller.player.position = 20.0

        controller.seek_relative(45)

        self.assertEqual(2, controller.get_current_index())
        self.assertAlmostEqual(5.0, controller.player.get_playback_position())

    def test_seeking_back_from_the_first_passage_clamps_to_its_start(self):
        controller = self.make_controller()

        controller.play()
        controller.player.position = 4.0

        controller.seek_relative(-15)

        self.assertEqual(0, controller.get_current_index())
        self.assertAlmostEqual(0.0, controller.player.get_playback_position())

    def test_a_cross_segment_seek_preserves_a_paused_transport(self):
        from reader.controller import PlaybackState

        controller = self.make_controller()

        controller.play()
        controller.player.position = 25.0
        controller.pause()

        controller.seek_relative(15)

        self.assertEqual(1, controller.get_current_index())
        self.assertIs(PlaybackState.PAUSED, controller.state)
        self.assertFalse(controller.player.is_playing())

    def test_a_cross_segment_seek_preserves_a_playing_transport(self):
        from reader.controller import PlaybackState

        controller = self.make_controller()

        controller.play()
        controller.player.position = 25.0

        controller.seek_relative(15)

        self.assertIs(PlaybackState.PLAYING, controller.state)
        self.assertTrue(controller.player.is_playing())

    def test_seeking_past_the_end_of_the_book_finishes(self):
        from reader.controller import PlaybackState

        controller = self.make_controller(start_index=self.SEGMENT_COUNT - 1)

        controller.play()
        controller.player.position = 25.0

        controller.seek_relative(15)

        self.assertIs(PlaybackState.FINISHED, controller.state)


class CueLoadingTests(ControllerTestCase):
    """Highlighting and click-to-read both depend on cues being loaded.

    A segment whose audio is already cached arrives marked generated, so the
    readiness check can return true without ever reading the cue file. When
    that happened the passage played with no highlight and clicking the text
    did nothing.
    """

    class CuedTTS(FakeTTS):
        def load_cues(self, audio_path):
            from reader.models import TextCue

            return [
                TextCue(text="The first sentence.", start=0.0, end=5.0),
                TextCue(text="The second sentence.", start=5.0, end=12.0),
            ]

    def make_cued_controller(self):
        from reader.controller import ReaderController

        # Exactly what create_segments does for a passage already in cache.
        for segment in self.segments:
            segment.generated = True
            segment.cues = []

        controller = ReaderController(
            segments=self.segments,
            tts=self.CuedTTS(),
            book_id=1,
        )

        for segment in self.segments:
            controller._duration_cache[segment.audio_path] = 30.0

        return controller

    def test_playing_a_cached_passage_loads_its_cues(self):
        controller = self.make_cued_controller()

        self.assertEqual([], controller.get_current_segment().cues)

        controller.play()

        self.assertEqual(
            2,
            len(controller.get_current_segment().cues),
            "a cached passage played without loading its cues",
        )

    def test_the_cue_under_the_playhead_is_found(self):
        controller = self.make_cued_controller()

        controller.play()
        controller.player.position = 7.0

        cue = controller.get_current_cue()

        self.assertIsNotNone(cue, "no cue covers the playhead")
        self.assertEqual("The second sentence.", cue.text)

    def test_cues_are_available_before_playback_starts(self):
        """Clicking into a passage must work without pressing play first."""
        controller = self.make_cued_controller()

        controller.player.current_index = 1
        controller.player.current_segment = self.segments[1]

        self.assertIsNotNone(controller.get_current_cue())

    def test_moving_to_a_new_passage_loads_that_passage_cues(self):
        controller = self.make_cued_controller()

        controller.play()
        controller.next()

        self.assertEqual(2, len(controller.get_current_segment().cues))


class ResponsiveShutdownTests(ControllerTestCase):
    """Closing a book must not wait for synthesis that is already running."""

    class SlowTTS(FakeTTS):
        def __init__(self):
            super().__init__()
            self.started = __import__("threading").Event()

        def generate(self, text, output_path, on_progress=None):
            import time

            self.started.set()
            time.sleep(1.5)

            Path(output_path).write_bytes(b"")

            return []

    def _controller_with_generation_in_flight(self):
        from reader.controller import ReaderController

        tts = self.SlowTTS()

        # Remove the cache files so the segments really have to be generated.
        for segment in self.segments:
            Path(segment.audio_path).unlink()

        controller = ReaderController(
            segments=self.segments,
            tts=tts,
            book_id=1,
        )

        controller.play()

        self.assertTrue(
            tts.started.wait(timeout=5),
            "synthesis never started",
        )

        return controller

    def test_closing_a_book_returns_immediately(self):
        import time

        controller = self._controller_with_generation_in_flight()

        started = time.monotonic()

        controller.shutdown()

        elapsed = time.monotonic() - started

        self.assertLess(
            elapsed,
            0.5,
            f"closing the book blocked for {elapsed:.2f}s on synthesis",
        )

    def test_closing_a_book_still_saves_the_position(self):
        controller = self._controller_with_generation_in_flight()

        controller.shutdown()

        row = self.saved_row()

        self.assertEqual("cache0", row["anchor_cache_id"])

    def test_queued_work_is_abandoned_rather_than_finished(self):
        controller = self._controller_with_generation_in_flight()

        controller.preload_upcoming()

        controller.cancel_pending_generation()

        self.assertLessEqual(
            len(controller.generating),
            1,
            "only the passage already being synthesized may survive",
        )


class NarrationSettingsTests(ControllerTestCase):
    def test_changing_speed_rekeys_every_segment(self):
        controller = self.make_controller()

        before = [segment.cache_id for segment in controller.segments]

        self.assertTrue(controller.apply_narration_settings("af_heart", 1.25))

        after = [segment.cache_id for segment in controller.segments]

        self.assertNotEqual(before, after)
        self.assertEqual(len(set(after)), len(after), "cache ids must be distinct")
        self.assertEqual(1.25, controller.tts.speed)

    def _precache(self, voice: str, speed: float):
        """Make the audio for these settings already exist.

        Without this the new passage is synthesized in the background and the
        assertion races the worker. Warm audio is also the normal case: it is
        what happens when the listener switches back to a voice they used
        before.
        """
        from reader.cache import create_cache_id
        from reader.paths import cache_dir

        for segment in self.segments:
            cache_id = create_cache_id(segment.text, voice, speed)

            path = cache_dir() / f"{cache_id}.wav"
            path.write_bytes(b"")

            self.addCleanup(path.unlink, True)

    def test_changing_speed_keeps_the_place_as_a_fraction(self):
        self._precache("af_heart", 1.25)

        controller = self.make_controller()

        controller.play()
        controller.player.position = 15.0  # half of a 30 second passage

        controller.apply_narration_settings("af_heart", 1.25)

        self.assertEqual(0, controller.get_current_index())

        # Half of the re-rendered passage, less the second of lead-in that
        # stops the listener landing mid-word.
        self.assertAlmostEqual(
            14.0,
            controller.player.get_playback_position(),
            places=2,
        )

    def test_applying_the_same_settings_does_nothing(self):
        controller = self.make_controller()

        self.assertFalse(
            controller.apply_narration_settings("af_heart", 0.85)
        )

    def test_a_settings_change_while_paused_stays_paused(self):
        from reader.controller import PlaybackState

        controller = self.make_controller()

        controller.play()
        controller.pause()

        controller.apply_narration_settings("am_adam", 0.85)

        self.assertIs(PlaybackState.PAUSED, controller.state)
        self.assertFalse(controller.running)


if __name__ == "__main__":
    unittest.main()
