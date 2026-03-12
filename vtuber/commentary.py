import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an engaging VTuber AI streamer. Your personality is:
- Witty, curious, and opinionated (but fair)
- You speak naturally like a real streamer — casual, conversational, with personality
- You break down complex topics so anyone can understand
- You reference chat messages when responding to viewers
- Keep responses concise (2-4 paragraphs for topics, 1-2 sentences for chat replies)
- Never use markdown formatting — speak naturally as if talking out loud
- Add natural filler words occasionally ("honestly", "look", "okay so", "here's the thing")

You are currently live-streaming and discussing current events with your audience."""

# Well-known local model API base URLs
LOCAL_PRESETS = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",
    "vllm": "http://localhost:8000/v1",
    "tabby": "http://localhost:5000/v1",
    "localai": "http://localhost:8080/v1",
}


@dataclass
class CommentaryEngine:
    """LLM commentary engine supporting both Anthropic API and local models.

    For local models, uses the OpenAI-compatible chat completions API that
    Ollama, LM Studio, llama.cpp, vLLM, and others expose.

    Configuration priority:
        1. Explicit base_url → use local/OpenAI-compatible API
        2. provider preset (e.g. "ollama") → resolve to known base URL
        3. ANTHROPIC_API_KEY set → use Anthropic
        4. LLM_BASE_URL env var → use local API
        5. Fall back to Ollama on default port
    """

    model: str = ""
    provider: str = ""  # "anthropic", "ollama", "lmstudio", "llamacpp", etc.
    base_url: str = ""  # explicit OpenAI-compatible API base URL
    max_history: int = 20

    _client: object = field(default=None, repr=False)
    _backend: str = field(default="", repr=False)  # "anthropic" or "openai"
    _conversation: list[dict] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._setup_client()

    def _setup_client(self):
        # Determine backend
        if self.provider == "anthropic" or (
            not self.provider and not self.base_url and os.environ.get("ANTHROPIC_API_KEY")
        ):
            self._setup_anthropic()
        else:
            self._setup_openai_compat()

    def _setup_anthropic(self):
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set")
            return
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._backend = "anthropic"
        if not self.model:
            self.model = "claude-sonnet-4-6"
        logger.info("Using Anthropic backend, model: %s", self.model)

    def _setup_openai_compat(self):
        from openai import AsyncOpenAI

        # Resolve base URL
        url = self.base_url
        if not url and self.provider:
            url = LOCAL_PRESETS.get(self.provider, "")
        if not url:
            url = os.environ.get("LLM_BASE_URL", "")
        if not url:
            url = LOCAL_PRESETS["ollama"]  # default to Ollama

        # Default model per provider
        if not self.model:
            self.model = self._default_model_for_provider()

        self._client = AsyncOpenAI(base_url=url, api_key="not-needed")
        self._backend = "openai"
        logger.info("Using local LLM backend at %s, model: %s", url, self.model)

    def _default_model_for_provider(self) -> str:
        defaults = {
            "ollama": "llama3.1",
            "lmstudio": "loaded-model",
            "llamacpp": "default",
            "vllm": "default",
        }
        return defaults.get(self.provider, "llama3.1")

    async def generate_commentary(self, news_summary: str) -> str:
        if not self._client:
            return "Hey chat, looks like my brain isn't connected right now. Someone tell my creator to check the API key!"

        prompt = (
            f"Here are today's top news stories:\n\n{news_summary}\n\n"
            "Pick 2-3 interesting stories and give your take on them as a streamer. "
            "Be engaging and conversational. Address your audience directly."
        )
        return await self._ask(prompt)

    async def respond_to_chat(self, username: str, message: str) -> str:
        if not self._client:
            return f"Sorry {username}, my brain is offline right now!"

        prompt = f"A viewer named {username} says in chat: \"{message}\"\n\nRespond to them naturally."
        return await self._ask(prompt)

    async def transition_topic(self, new_topic: str) -> str:
        if not self._client:
            return f"Okay chat, let's talk about {new_topic}."

        prompt = (
            f"Smoothly transition to discussing this new topic: {new_topic}\n"
            "Make it feel natural, like you just thought of it or a chatter brought it up."
        )
        return await self._ask(prompt)

    async def _ask(self, user_message: str) -> str:
        self._conversation.append({"role": "user", "content": user_message})

        if len(self._conversation) > self.max_history:
            self._conversation = self._conversation[-self.max_history:]

        try:
            if self._backend == "anthropic":
                text = await self._ask_anthropic()
            else:
                text = await self._ask_openai()
            self._conversation.append({"role": "assistant", "content": text})
            return text
        except Exception as e:
            logger.error("Commentary generation failed: %s", e)
            return "Uh, sorry chat, I just blanked for a second there. What were we talking about?"

    async def _ask_anthropic(self) -> str:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=self._conversation,
        )
        return response.content[0].text

    async def _ask_openai(self) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self._conversation
        response = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=500,
            messages=messages,
        )
        return response.choices[0].message.content
