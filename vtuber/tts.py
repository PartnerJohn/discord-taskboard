import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TTSEngine:
    voice: str = "en-US-AriaNeural"
    rate: str = "+10%"
    volume: str = "+0%"
    output_dir: str = ""

    def __post_init__(self):
        if not self.output_dir:
            self.output_dir = tempfile.mkdtemp(prefix="vtuber_tts_")

    async def synthesize(self, text: str, filename: str = "speech.mp3") -> str:
        """Generate speech audio from text using edge-tts. Returns path to audio file."""
        import edge_tts

        output_path = os.path.join(self.output_dir, filename)

        communicate = edge_tts.Communicate(
            text,
            self.voice,
            rate=self.rate,
            volume=self.volume,
        )
        await communicate.save(output_path)
        logger.info("TTS audio saved to %s", output_path)
        return output_path

    async def synthesize_with_timestamps(self, text: str, filename: str = "speech.mp3") -> dict:
        """Generate speech with word-level timestamps for lip sync."""
        import edge_tts

        output_path = os.path.join(self.output_dir, filename)
        timestamps = []

        communicate = edge_tts.Communicate(
            text,
            self.voice,
            rate=self.rate,
            volume=self.volume,
        )

        with open(output_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    timestamps.append({
                        "text": chunk["text"],
                        "offset": chunk["offset"],
                        "duration": chunk["duration"],
                    })

        return {"audio_path": output_path, "timestamps": timestamps}

    @staticmethod
    async def play_audio(path: str):
        """Play audio file through default system audio output."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except FileNotFoundError:
            logger.error("ffplay not found. Install ffmpeg to play audio.")
            raise

    @staticmethod
    def list_voices():
        """Return common edge-tts voice options."""
        return [
            "en-US-AriaNeural",       # Female, natural
            "en-US-GuyNeural",        # Male, natural
            "en-US-JennyNeural",      # Female, warm
            "en-GB-SoniaNeural",      # British female
            "en-AU-NatashaNeural",    # Australian female
            "ja-JP-NanamiNeural",     # Japanese female
        ]
