# Third-Party Notices

This file lists the direct dependencies declared in `requirements.txt`, the speech model weights downloaded at runtime, and the additional language and phonemizer packages explicitly bundled by `BookTTSReader.spec`. Licenses are recorded from the installed package metadata under `.venv/lib/python3.12/site-packages/*.dist-info` where available, or marked `unverified` when no license metadata is present locally in `.dist-info`.

| Name | What it is used for | License | Upstream URL |
| --- | --- | --- | --- |
| PySide6 (`6.11.2`) | Qt 6 QML desktop user interface, application loop, and settings storage | `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | https://pyside.org |
| PyMuPDF (`1.28.2`) | PDF text and layout extraction, document metadata, and fallback EPUB reading | `Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License` | https://github.com/pymupdf/pymupdf |
| kokoro (`0.9.4`) | Neural text-to-speech inference pipeline (`KModel` and `KPipeline`) | `Apache-2.0` | https://github.com/hexgrad/kokoro |
| misaki[en] (`0.9.4`) | Grapheme-to-phoneme (G2P) conversion for English text in the Kokoro TTS pipeline | `Apache-2.0` | https://github.com/hexgrad/misaki |
| numpy (`2.5.2`) | Concatenating and handling synthesized audio sample arrays | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | https://github.com/numpy/numpy |
| pygame (`2.6.1`) | Audio playback mixer for synthesized WAV segments | `LGPL` | https://github.com/pygame/pygame |
| soundfile (`0.14.0`) | Writing synthesized audio buffers to WAV files on disk (via libsndfile) | `BSD-3-Clause` | https://github.com/bastibe/python-soundfile |
| Kokoro-82M (`hexgrad/Kokoro-82M`) | Pretrained 82M-parameter text-to-speech model weights and voice embeddings downloaded from Hugging Face | `Apache-2.0` (per the Hugging Face model card) | https://huggingface.co/hexgrad/Kokoro-82M |
| en_core_web_sm (`3.8.0`) | Bundled spaCy English pipeline used by `misaki[en]` for tokenization and part-of-speech tagging | `MIT` (model package; underlying data sources include OntoNotes 5, ClearNLP, and WordNet 3.0 per `LICENSES_SOURCES`) | https://spacy.io/models/en#en_core_web_sm |
| espeak-ng (via `espeakng-loader` `0.2.4`) | Bundled shared library (`libespeak-ng`) and phoneme data used as the out-of-vocabulary phonemization fallback | `GPL-3.0-or-later` (espeak-ng upstream; not confirmed from local package metadata) | https://github.com/thewh1teagle/espeakng-loader / https://github.com/espeak-ng/espeak-ng |
