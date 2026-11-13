# Book TTS Reader

Listen to your PDF, EPUB, and plain-text books with a local neural voice and synchronized highlighting.

Book TTS Reader is a desktop application that reads PDF and EPUB books aloud using the Kokoro-82M neural text-to-speech model. It operates completely offline after an initial download of the speech model and voice weights, displaying the book text with synchronized word and line highlighting while tracking reading progress across sessions. It is built for anyone who wants to listen to books, papers, textbooks, or pasted passages locally on their computer without cloud accounts or subscriptions.

Downloads and an interactive audio sample are available at [https://pdf-reader.assemani.com](https://pdf-reader.assemani.com) and on the [GitHub Releases](https://github.com/HADIASSEMANI/text-to-speech-pdf-reader/releases) page.

## Highlights

- **Structured EPUB reading**: Reads EPUB XHTML content documents in spine order using the Python standard library, preserving headings, lists, superscripts, subscripts, MathML equations, and printed page numbers from `epub:type="pagebreak"` anchors. Falls back to PyMuPDF plain-text extraction only if an EPUB cannot be parsed structurally.
- **PDF layout filtering**: Extracts positioned text blocks with PyMuPDF and automatically filters out running headers, footers, page numbers, and terminal sections (such as appendices, references, bibliography, works cited, and index), with optional toggles in Settings to read footnotes, figure captions, and sidebars.
- **Synchronized highlighting and click-to-read**: Highlights the active passage in real time as it is spoken and scrolls to keep it in view. Click any sentence or passage in the reader to jump straight to that spot and start listening.
- **Resume to the second**: Saves your reading position in a local SQLite database every 5 seconds during playback and whenever playback pauses, stops, or closes. Progress is stored using a durable anchor (cache ID, document source ID, page number, and text excerpt) so your place survives application restarts, re-segmentation, and changes to voice or speed. Newly added books automatically start at the first detected chapter when available.
- **Voice and speed per open book**: Synthesizes 24 kHz audio locally with Kokoro-82M (`hexgrad/Kokoro-82M`). Choose between bundled voice presets (`af_heart`, `af_bella`, `am_adam`) and adjust narration speed from `0.50x` to `2.00x` (default `0.85x`). Applying a new voice or speed re-keys the open book while keeping your reading position; audio for the new setting is prepared as you reach each passage, while previously generated audio stays cached.
- **Paste text to read**: Open `.pdf`, `.epub`, and `.txt` files, or use **Paste Text** in the library to paste or type any passage. Pasted texts are saved as UTF-8 `.txt` files in your library so you can resume them later.
- **15-second skip across segments**: Skip forward or backward by 15 seconds (`-15s` / `+15s`), carrying any time overflow seamlessly across segment boundaries while preserving whether playback is playing or paused.
- **Chapter, page, and segment navigation**: Jump to any chapter from the **Chapters** dropdown or to any page number using the **Page** spin box (which stops playback and waits for you to press **Play**). Step through passages with **Previous** and **Next** while keeping the current play or pause state.
- **Audio preloading and managed cache**: Preloads upcoming segments in the background while you listen and writes WAV audio and JSON cue files atomically to disk. The audio cache enforces a configurable size limit (`256 MB` to `8192 MB`, default `1024 MB` / `1 GB`) using least-recently-used cleanup, and includes a **Clear cache** button in Settings to delete generated audio on demand without losing your library or saved positions.
- **Accessible controls and keyboard navigation**: Provides `Accessible.name` and `Accessible.description` labels across UI controls for screen readers, responsive layouts down to a `420x460` minimum window size, adjustable reader text size (`14 px` to `32 px`, default `18 px`), and keyboard shortcuts for common actions.

## Download and install

Prebuilt packages are published on the [download page](https://pdf-reader.assemani.com) and on [GitHub Releases](https://github.com/HADIASSEMANI/text-to-speech-pdf-reader/releases).

| Platform | Package | Architecture & Requirements | Installation & Signing Notes |
| --- | --- | --- | --- |
| **macOS** | `BookTTSReader-<version>.dmg` | Apple silicon (`arm64`, M1 or later), macOS 12.0+. On Intel Macs, run from source. | Open the `.dmg` disk image and drag **Book TTS Reader.app** to `/Applications`. Signed with a Developer ID certificate (hardened runtime) and notarized by Apple. |
| **Windows** | `BookTTSReader-Setup-<version>.exe` | Windows 10 / 11 (64-bit `x64compatible`). | Runs a per-user install into `%LOCALAPPDATA%\Programs\BookTTSReader` without administrator privileges. Not yet code-signed; if Microsoft Defender SmartScreen prompts on first run, click **More info** and then **Run anyway**. |
| **From source** | Repository clone | Python 3.12 on Linux, macOS (Apple silicon or Intel), or Windows. | Create a virtual environment, install `requirements.txt`, and run `python main.py` (see [Run from source](#run-from-source)). |

**SHA-256 checksums**: Every GitHub release publishes a `SHA256SUMS.txt` file alongside the `.dmg` and `.exe` installers so you can verify your download before running it.

## Getting started

1. **Open a book or paste text**: On the **Your Library** screen, click **Open Book** (or press `Ctrl+O` / `Cmd+O`) to select a `.pdf`, `.epub`, or `.txt` file, or click **Paste Text** to enter a title and paste text to read aloud.
2. **Start listening**: Once the book opens on the reader screen, press **Play** (or press `Space`) to start narration. If a passage is being synthesized for the first time, an inline progress strip shows preparation progress with **Cancel** and **Try again** controls while keeping the text readable on screen.
3. **Navigate the book**:
   - Click any sentence in the passage to seek directly to that point and begin reading.
   - Use **Previous** and **Next** (or `Left` / `Right` arrow keys) to move between passages, or **-15s** and **+15s** (or `Shift+Left` / `Shift+Right`) to skip 15 seconds backward or forward.
   - Use the **Chapters** dropdown to jump to a chapter, or use the **Page** spin box (`Ctrl+L` / `Cmd+L`) to jump to a specific page.
   - Press `?` or `F1` on the reader screen to view the **Keyboard shortcuts** dialog.
4. **Change voice, speed, and layout preferences**: Click **Settings** to adjust **Text size**, **Voice** (`af_heart`, `af_bella`, `am_adam`), **Narration speed** (`0.50x` to `2.00x`), **Audio cache limit**, or the **What gets read** switches (**Read footnotes**, **Read figure captions**, **Read sidebars**). Click **Done** (or press `Escape`) to return.
5. **Resume anytime**: Click **Library** (or press `Escape`) to close the book and return to **Your Library**, or quit the application. Your position is saved automatically in `reader.db` and resumes from where you left off (stepping back 3 seconds when resuming mid-passage so you rejoin cleanly).

## Privacy and network use

Your books and pasted texts never leave your computer. The application contains no telemetry, analytics, or cloud services.

The only network access performed by the application is a one-time download from Hugging Face (`hexgrad/Kokoro-82M`, pinned to revision `f3ff3571791e39611d31c381e3a41a3af07b4987`) to fetch the Kokoro model configuration, model weights, and selected voice files when they are not already present in the local Hugging Face cache. Once downloaded, synthesis runs completely offline.

## Where data is stored

Book TTS Reader stores its data in a per-user application data directory (`BookTTSReader`):

- **Windows**: `%LOCALAPPDATA%\BookTTSReader`
- **macOS**: `~/Library/Application Support/BookTTSReader`
- **Linux**: `$XDG_DATA_HOME/BookTTSReader` (or `~/.local/share/BookTTSReader` if `XDG_DATA_HOME` is unset)

Inside this directory:

- `reader.db`: SQLite database storing the library list and per-book reading progress anchors.
- `cache/`: Generated WAV audio segments and JSON timing cue files, managed up to the configured cache size limit and removable at any time with Clear cache in Settings.
- `pasted-texts/`: Plain-text files created through the paste-text dialog.

Downloaded Hugging Face model and voice files are stored in the standard Hugging Face cache directory (`~/.cache/huggingface/hub` unless overridden by `HF_HOME` or `HUGGINGFACE_HUB_CACHE`). Application preferences (voice, speed, cache size limit, and layout filter toggles) are stored via Qt `QSettings` under the organization `BookTTS` and application `BookTTSReader`.

## Run from source

Requires Python 3.12. From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

On Windows, activate the virtual environment with `.venv\Scripts\activate`.

By default, running `python main.py` from source clears the generated audio cache when the application exits. Set `BOOKTTS_KEEP_CACHE=1` in the environment to keep cached audio across development runs.

## How it works

Book TTS Reader processes documents through a modular pipeline from source file to audio playback and persistence:

1. **Extraction (`reader/pdf_reader.py`, `reader/epub_reader.py`, `reader/text_source.py`, `reader/document_reader.py`)**:
   - For PDFs, `pdf_reader.py` extracts positioned text blocks and font sizes from each page with PyMuPDF.
   - For EPUBs, `epub_reader.py` parses the archive's XHTML content documents in spine order using the Python standard library and produces `ContentBlock` records (`reader/content_blocks.py`) that keep displayed text, HTML markup, spoken text (including verbalized MathML equations), printed page labels, and document source IDs together.
   - For pasted or plain text, `text_source.py` reads UTF-8 text files.
2. **Layout filtering and chapter detection (`reader/layout_filter.py`, `reader/chapter_finder.py`)**:
   - PDF blocks are classified to skip repeated running headers/footers, isolated page numbers, and terminal sections, while applying user toggles for footnotes, figure captions, and sidebars.
   - For newly opened books, `chapter_finder.py` and document table-of-contents metadata locate the first chapter.
3. **Cleaning, chunking, and segmentation (`reader/text_cleaner.py`, `reader/chunker.py`, `reader/segmenter.py`, `reader/cache.py`)**:
   - Text is normalized and grouped into narration `Segment` objects (`reader/models.py`) up to 1,500 characters without splitting structured content blocks. Each segment is assigned a deterministic cache ID derived from `NARRATION_VERSION`, voice, speed, and spoken text.
4. **Speech synthesis and cue mapping (`reader/tts.py`, `reader/cue_mapping.py`)**:
   - `KokoroTTS` runs the Kokoro-82M pipeline on a background worker thread, writing 24 kHz `.wav` audio and `.json` grapheme timing cues atomically to `cache/`.
   - `cue_mapping.py` maps spoken cue timings onto UTF-16 character offsets in the displayed text so highlighting and click-to-read stay aligned with rich-text formatting.
5. **Playback, controller, and UI (`reader/audio_player.py`, `reader/controller.py`, `reader/viewmodel/app_viewmodel.py`, `qml/`, `main.py`)**:
   - `AudioPlayer` decodes WAV files with `soundfile` and plays them through `pygame.mixer` with frame-accurate seeking and monotonic clock tracking.
   - `ReaderController` (constructed by `reader/book_loader.py`) owns `PlaybackState`, segment transitions, 15-second relative seeking across segments, background preloading, and LRU cache cleanup.
   - `AppViewModel` exposes properties, slots, and signals to the Qt 6 QML interface (`qml/`) launched by `main.py`. (An earlier QWidget interface remains in `reader/ui/` behind `main_widgets.py`.)
6. **Persistence (`reader/database.py`, `reader/progress.py`, `reader/settings.py`)**:
   - `database.py` manages schema migrations in `reader.db` via `PRAGMA user_version`, `progress.py` stores and resolves `ProgressAnchor` records, and `settings.py` persists user preferences through `QSettings`.

## Development

Use the project virtual environment (`.venv`) for all checks and tests so that PySide6, PyMuPDF, Kokoro, and audio dependencies are available.

Run syntax/bytecode compilation checks:

```bash
.venv/bin/python -m compileall -q main.py reader
```

Run the unit test suite:

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

Optional real-book EPUB extraction tests in `tests/test_epub_extraction.py` are skipped by default and run when the `BOOKTTS_REAL_EPUB` environment variable points to the reference EPUB file.

When changing extraction, cleaning, chunking, or segmentation behavior, review and update the golden narration fixtures recorded in `tests/fixtures/golden/` (verified by `tests/test_pipeline_golden.py`):

```bash
.venv/bin/python -m tools.baseline --text --update-golden
```

## Building releases

Packaged builds are configured with PyInstaller (`BookTTSReader.spec`) and automated in `.github/workflows/release.yml`.

### 1. Bundle the application with PyInstaller

Install the project dependencies, PyInstaller, and the bundled spaCy English model (`en_core_web_sm`), then run PyInstaller with `BookTTSReader.spec`:

```bash
python -m pip install -r requirements.txt pyinstaller
python -m pip install --no-deps "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl#sha256=1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
pyinstaller --noconfirm BookTTSReader.spec
```

This produces `dist/BookTTSReader/` (and `dist/Book TTS Reader.app` on macOS). You can set `APP_VERSION` in the environment before running PyInstaller to stamp the release version (defaults to `0.1.0`).

### 2. Windows installer (Inno Setup)

On Windows, compile `installer/BookTTSReader.iss` using Inno Setup (`ISCC.exe`) after building `dist/BookTTSReader`:

```powershell
ISCC.exe "/DMyAppVersion=0.1.0" "/Oinstaller-output" "installer/BookTTSReader.iss"
```

This creates `installer-output/BookTTSReader-Setup-<version>.exe`.

### 3. macOS signing and notarization

On macOS, signed releases use a Developer ID Application certificate, hardened runtime entitlements (`packaging/macos/entitlements.plist`), `notarytool`, and `stapler`:

1. Set `MACOS_CODESIGN_IDENTITY` and `MACOS_ENTITLEMENTS_FILE=packaging/macos/entitlements.plist` when running `pyinstaller --noconfirm BookTTSReader.spec` (or sign the `.app` bundle with `codesign --options runtime`), then verify the bundle:
   ```bash
   codesign --verify --deep --strict --verbose=2 "dist/Book TTS Reader.app"
   ```
2. Stage `dist/Book TTS Reader.app` and an `/Applications` symlink into a folder, then create a compressed `.dmg` with `hdiutil`:
   ```bash
   hdiutil create -volname "Book TTS Reader" -srcfolder <staging-dir> -ov -format UDZO "BookTTSReader-<version>.dmg"
   ```
3. Sign the `.dmg`, submit it for notarization with `xcrun notarytool`, and staple the ticket with `xcrun stapler`:
   ```bash
   codesign --force --sign "<Developer ID Application identity>" --timestamp "BookTTSReader-<version>.dmg"
   codesign --verify --strict "BookTTSReader-<version>.dmg"
   xcrun notarytool submit "BookTTSReader-<version>.dmg" --apple-id "<apple-id>" --team-id "<team-id>" --password "<app-specific-password>" --wait
   xcrun stapler staple "BookTTSReader-<version>.dmg"
   xcrun stapler validate "BookTTSReader-<version>.dmg"
   ```

## Troubleshooting

- **First-run model download requires an internet connection**: The first time you open a book or switch to a voice that has not been downloaded yet, Book TTS Reader downloads the Kokoro-82M model weights (`config.json` and model checkpoint) and voice file (`voices/<voice>.pt`) from Hugging Face (`hexgrad/Kokoro-82M`). If you are offline on first run, book loading or preparation will fail with an error dialog or preparation banner. Connect to the internet once to complete the download; all subsequent runs with cached voices work offline.
- **macOS Gatekeeper and architecture requirements**: Official release `.dmg` builds are signed and notarized for Apple silicon (`arm64`, M1 or later) on macOS 12.0+. If you build an unsigned `.app` locally or download an unsigned artifact, macOS Gatekeeper may block it until you allow it in **System Settings > Privacy & Security**. On Intel Macs, run the application from source.
- **Windows SmartScreen warning**: The Windows installer (`BookTTSReader-Setup-<version>.exe`) is not yet code-signed, so Microsoft Defender SmartScreen may show a "Windows protected your PC" prompt on first launch. Verify the installer against `SHA256SUMS.txt` from the release page, then click **More info** and **Run anyway**.
- **Clearing or resizing the audio cache**: If generated audio takes up too much disk space or you want to force segments to regenerate, open **Settings** and click **Clear cache** next to **Stored audio**, or lower the **Audio cache limit** (`256 MB` to `8192 MB`). Clearing the cache removes only generated `.wav` and `.json` files in `cache/`; your library and reading progress in `reader.db` are preserved.

## Security

To report a security vulnerability, please send a private email to hadi@assemani.com rather than opening a public issue.

## Contributing

Issues and pull requests are welcome at [HADIASSEMANI/text-to-speech-pdf-reader](https://github.com/HADIASSEMANI/text-to-speech-pdf-reader).

Before submitting a pull request:

1. Run bytecode compilation and the full unit test suite in the project virtual environment:
   ```bash
   .venv/bin/python -m compileall -q main.py reader
   .venv/bin/python -m unittest discover -s tests -t .
   ```
2. Add focused regression tests when changing extraction, chunking, navigation, or progress behavior.
3. If your change intentionally alters what the reader narrates or how passages are segmented, update the golden text fixtures and include the reviewed diff:
   ```bash
   .venv/bin/python -m tools.baseline --text --update-golden
   ```

## License

Book TTS Reader is authored by Hadi Assemani and published under the **GNU Affero General Public License v3.0 (AGPL-3.0)**; see [LICENSE](LICENSE) for the full text. The project is licensed under AGPL-3.0 because it depends on PyMuPDF, which is distributed under the AGPL-3.0 license.

### Third-party notices and acknowledgements

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the full list of direct dependencies, runtime model weights, bundled packages, and their licenses. Book TTS Reader is built with:

- [Kokoro](https://github.com/hexgrad/kokoro) and [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (with [misaki](https://github.com/hexgrad/misaki), `en_core_web_sm`, and `espeak-ng`) for local neural text-to-speech synthesis and grapheme-to-phoneme conversion.
- [PyMuPDF](https://github.com/pymupdf/pymupdf) for PDF text and layout extraction, document metadata, and fallback EPUB reading.
- [PySide6 / Qt 6](https://pyside.org) for the QML desktop user interface, application loop, and settings storage.
- [pygame](https://github.com/pygame/pygame), [soundfile](https://github.com/bastibe/python-soundfile), and [NumPy](https://github.com/numpy/numpy) for audio buffer handling, WAV file output, and mixer playback.
