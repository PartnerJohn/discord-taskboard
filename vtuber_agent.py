#!/usr/bin/env python3
"""
VTuber AI Streaming Agent
Automated VTuber that discusses current events with a Live2D avatar.

Environment variables (all optional depending on backend):
    ANTHROPIC_API_KEY       - Anthropic API key (for Claude backend)
    LLM_BASE_URL            - OpenAI-compatible API URL (for local models)
    OBS_WS_PASSWORD         - OBS WebSocket password

LLM backends:
    --provider ollama       - Ollama (default, localhost:11434)
    --provider lmstudio     - LM Studio (localhost:1234)
    --provider llamacpp     - llama.cpp server (localhost:8080)
    --provider vllm         - vLLM (localhost:8000)
    --provider anthropic    - Anthropic Claude API
    --base-url URL          - Any OpenAI-compatible endpoint

Required external software:
    - OBS Studio with obs-websocket plugin (v5+)
    - VTube Studio with API enabled (port 8001)
    - ffplay (from ffmpeg) for audio playback

Usage:
    python vtuber_agent.py --provider ollama --model llama3.1
    python vtuber_agent.py --provider lmstudio
    python vtuber_agent.py --base-url http://localhost:5000/v1 --model my-model
    python vtuber_agent.py --provider anthropic --model claude-sonnet-4-6
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field

from vtuber.news import NewsFetcher
from vtuber.commentary import CommentaryEngine
from vtuber.tts import TTSEngine
from vtuber.vtube_studio import VTubeStudioController
from vtuber.obs_controller import OBSController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("vtuber_agent")


@dataclass
class VTuberAgent:
    """Main orchestrator for the AI VTuber streaming agent."""

    # Component configuration
    voice: str = "en-US-AriaNeural"
    topic_interval: int = 180  # seconds between new topics
    obs_host: str = "localhost"
    obs_port: int = 4455
    vts_host: str = "localhost"
    vts_port: int = 8001

    # LLM configuration
    llm_provider: str = ""
    llm_model: str = ""
    llm_base_url: str = ""

    # Components
    news: NewsFetcher = field(default_factory=NewsFetcher)
    commentary: CommentaryEngine = field(default=None)
    tts: TTSEngine = field(default=None)
    vtube: VTubeStudioController = field(default=None)
    obs: OBSController = field(default=None)

    # State
    _running: bool = False
    _speech_counter: int = 0

    def __post_init__(self):
        if self.commentary is None:
            self.commentary = CommentaryEngine(
                model=self.llm_model,
                provider=self.llm_provider,
                base_url=self.llm_base_url,
            )
        if self.tts is None:
            self.tts = TTSEngine(voice=self.voice)
        if self.vtube is None:
            self.vtube = VTubeStudioController(host=self.vts_host, port=self.vts_port)
        if self.obs is None:
            self.obs = OBSController(
                host=self.obs_host,
                port=self.obs_port,
                password=os.environ.get("OBS_WS_PASSWORD", ""),
            )

    async def start(self):
        """Initialize all connections and start the streaming loop."""
        logger.info("Starting VTuber AI Agent...")

        # Connect to OBS
        try:
            self.obs.connect()
            logger.info("OBS connected")
            if not self.obs.is_streaming():
                logger.info("OBS is not streaming — start streaming from OBS when ready")
        except Exception as e:
            logger.warning("OBS not available (%s) — running without OBS control", e)
            self.obs = None

        # Connect to VTube Studio
        try:
            await self.vtube.connect()
            logger.info("VTube Studio connected")
        except Exception as e:
            logger.warning("VTube Studio not available (%s) — running without avatar control", e)
            self.vtube = None

        self._running = True
        logger.info("VTuber Agent is live! Topic interval: %ds", self.topic_interval)

        # Run the main loop
        await self._main_loop()

    async def stop(self):
        """Gracefully shut down the agent."""
        logger.info("Shutting down VTuber Agent...")
        self._running = False
        if self.vtube:
            await self.vtube.disconnect()
        if self.obs:
            self.obs.disconnect()

    async def _main_loop(self):
        """Main streaming loop — fetch news, generate commentary, speak."""
        while self._running:
            try:
                await self._do_topic_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in main loop: %s", e)
                await asyncio.sleep(10)

            # Wait before next topic
            for _ in range(self.topic_interval):
                if not self._running:
                    break
                await asyncio.sleep(1)

    async def _do_topic_cycle(self):
        """Single cycle: fetch news, generate commentary, speak it."""
        logger.info("Fetching current events...")
        news_summary = await self.news.get_topics_summary(max_items=8)

        logger.info("Generating commentary...")
        commentary = await self.commentary.generate_commentary(news_summary)
        logger.info("Commentary: %s", commentary[:100] + "...")

        await self._speak(commentary)

    async def _speak(self, text: str):
        """Convert text to speech, play audio, and animate avatar."""
        self._speech_counter += 1
        filename = f"speech_{self._speech_counter}.mp3"

        logger.info("Generating TTS audio...")
        result = await self.tts.synthesize_with_timestamps(text, filename)
        audio_path = result["audio_path"]
        timestamps = result["timestamps"]

        # Play audio and animate mouth simultaneously
        tasks = [TTSEngine.play_audio(audio_path)]
        if self.vtube and timestamps:
            tasks.append(self._animate_lip_sync(timestamps))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _animate_lip_sync(self, timestamps: list[dict]):
        """Animate the Live2D model's mouth based on word timestamps."""
        if not self.vtube:
            return

        start = time.monotonic()
        for ts in timestamps:
            # Wait until this word's timestamp
            target = ts["offset"] / 10_000_000  # convert 100ns ticks to seconds
            elapsed = time.monotonic() - start
            if target > elapsed:
                await asyncio.sleep(target - elapsed)

            # Open mouth for word duration
            duration_s = ts["duration"] / 10_000_000
            try:
                await self.vtube.set_parameter("MouthOpen", 0.7)
                await asyncio.sleep(max(duration_s * 0.6, 0.05))
                await self.vtube.set_parameter("MouthOpen", 0.1)
                await asyncio.sleep(max(duration_s * 0.3, 0.02))
            except Exception:
                pass

        # Close mouth when done
        try:
            await self.vtube.set_parameter("MouthOpen", 0.0)
        except Exception:
            pass

    async def respond_to_chat(self, username: str, message: str):
        """Handle a chat message — generate response and speak it."""
        response = await self.commentary.respond_to_chat(username, message)
        await self._speak(response)
        return response


def parse_args():
    parser = argparse.ArgumentParser(description="VTuber AI Streaming Agent")
    # LLM backend
    parser.add_argument("--provider", default="",
                        help="LLM provider: ollama, lmstudio, llamacpp, vllm, anthropic (default: auto-detect)")
    parser.add_argument("--model", default="",
                        help="Model name (default: auto per provider, e.g. llama3.1 for Ollama)")
    parser.add_argument("--base-url", default="",
                        help="OpenAI-compatible API base URL (overrides --provider)")

    # Streaming config
    parser.add_argument("--voice", default="en-US-AriaNeural",
                        help="Edge TTS voice (default: en-US-AriaNeural)")
    parser.add_argument("--interval", type=int, default=180,
                        help="Seconds between new topics (default: 180)")
    parser.add_argument("--obs-host", default="localhost")
    parser.add_argument("--obs-port", type=int, default=4455)
    parser.add_argument("--vts-host", default="localhost")
    parser.add_argument("--vts-port", type=int, default=8001)
    parser.add_argument("--list-voices", action="store_true",
                        help="List available TTS voices and exit")
    return parser.parse_args()


async def run(args):
    agent = VTuberAgent(
        voice=args.voice,
        topic_interval=args.interval,
        obs_host=args.obs_host,
        obs_port=args.obs_port,
        vts_host=args.vts_host,
        vts_port=args.vts_port,
        llm_provider=args.provider,
        llm_model=args.model,
        llm_base_url=args.base_url,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(agent.stop()))

    await agent.start()


def main():
    args = parse_args()

    if args.list_voices:
        print("Available voices:")
        for v in TTSEngine.list_voices():
            print(f"  {v}")
        return

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
