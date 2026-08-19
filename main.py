from reader.pdf_reader import extract_pages
from reader.segmenter import create_segments
from reader.tts import KokoroTTS
from pathlib import Path
from reader.audio_player import AudioPlayer

PDF_PATH = "pdfs/introduction_to_the_new_mainframe.pdf"

def run_player(segments):

    player = AudioPlayer(segments)

    print()
    print("PDF Reader")
    print("----------------")
    print("p = play")
    print("space = pause/resume")
    print("n = next")
    print("b = previous")
    print("s = stop")
    print("q = quit")
    print()

    while True:

        command = input("> ").strip().lower()

        if command == "p":

            player.play()

        elif command == "space":

            if player.is_paused:
                player.resume()
            else:
                player.pause()

        elif command == "n":

            player.next()

        elif command == "b":

            player.previous()

        elif command == "s":

            player.stop()

        elif command == "q":

            player.stop()

            break

def main():

    pages = extract_pages(PDF_PATH)

    pages = extract_pages(PDF_PATH)

    START_PAGE = 35

    segments = create_segments(pages[START_PAGE - 1:START_PAGE + 4])

    print(
        f"Created "
        f"{len(segments)} segments."
    )

    segments = segments[:20]

    tts = KokoroTTS()

    for segment in segments:

        if Path(segment.audio_path).exists():
            print(f"Using cached segment {segment.id:05}")
            continue

        print(f"Generating segment {segment.id:05} from page {segment.page}")
        
        tts.generate(
            segment.text,
            segment.audio_path
        )
        
    # -------------------------
    # Player
    # -------------------------

    player = AudioPlayer(
        segments
    )

    player.play()

    segment = player.get_current_segment()

    if segment:
        print(segment.page)
        print("\n")
        print(segment.text)

    def restart(self):
        if self.current_segment is None:
            return

        pygame.mixer.music.stop()

        self.play()

    def is_playing(self) -> bool:
        return (
            pygame.mixer.music.get_busy()
            and not self.is_paused
        )

    input(
        "Press Enter to exit..."
    )

if __name__ == "__main__":
    main()
