import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

import reader.tts as tts_module
from reader.tts import KOKORO_REPO_ID, KOKORO_REVISION, KokoroTTS


class TestModelPin(unittest.TestCase):
    def test_constants_defined(self):
        self.assertEqual(KOKORO_REPO_ID, "hexgrad/Kokoro-82M")
        self.assertEqual(
            KOKORO_REVISION, "f3ff3571791e39611d31c381e3a41a3af07b4987"
        )

    @patch("reader.tts.sf.write")
    @patch("reader.tts.KPipeline")
    @patch("reader.tts.KModel")
    @patch("reader.tts.hf_hub_download")
    def test_downloads_use_pinned_revision_and_preserve_voice_name(
        self, mock_hf_download, mock_kmodel_cls, mock_kpipeline_cls, mock_sf_write
    ):
        mock_kmodel_cls.MODEL_NAMES = {KOKORO_REPO_ID: "kokoro-v1_0.pth"}

        def fake_download(repo_id, filename, revision=None, **kwargs):
            return f"/fake/cache/{filename}"

        mock_hf_download.side_effect = fake_download

        mock_model_instance = MagicMock()
        mock_model_instance.to.return_value = mock_model_instance
        mock_model_instance.eval.return_value = mock_model_instance
        mock_kmodel_cls.return_value = mock_model_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.return_value = [
            ("Hello world", "həˈloʊ wɜːld", np.zeros(2400, dtype=np.float32))
        ]
        mock_kpipeline_cls.return_value = mock_pipeline_instance

        def fake_sf_write(target, audio, sample_rate):
            Path(target).write_bytes(b"RIFFfakewav")

        mock_sf_write.side_effect = fake_sf_write

        tts = KokoroTTS(voice="af_heart", speed=1.2, lang_code="a")

        self.assertEqual(tts.voice, "af_heart")

        with tempfile.TemporaryDirectory() as tmp:
            out_wav = Path(tmp) / "out.wav"
            cues = tts.generate("Hello world", str(out_wav))

        self.assertEqual(tts.voice, "af_heart")
        self.assertEqual(len(cues), 1)

        self.assertGreaterEqual(mock_hf_download.call_count, 3)
        for call in mock_hf_download.call_args_list:
            _, kwargs = call
            self.assertEqual(kwargs.get("repo_id"), KOKORO_REPO_ID)
            self.assertEqual(kwargs.get("revision"), KOKORO_REVISION)

        downloaded_filenames = [
            call.kwargs.get("filename") for call in mock_hf_download.call_args_list
        ]
        self.assertIn("config.json", downloaded_filenames)
        self.assertIn("kokoro-v1_0.pth", downloaded_filenames)
        self.assertIn("voices/af_heart.pt", downloaded_filenames)

        mock_kmodel_cls.assert_called_once_with(
            repo_id=KOKORO_REPO_ID,
            config="/fake/cache/config.json",
            model="/fake/cache/kokoro-v1_0.pth",
        )
        mock_model_instance.to.assert_called_once()
        mock_model_instance.eval.assert_called_once()

        mock_kpipeline_cls.assert_called_once_with(
            lang_code="a",
            repo_id=KOKORO_REPO_ID,
            model=mock_model_instance,
        )

        mock_pipeline_instance.assert_called_once_with(
            "Hello world",
            voice="/fake/cache/voices/af_heart.pt",
            speed=1.2,
        )


if __name__ == "__main__":
    unittest.main()
