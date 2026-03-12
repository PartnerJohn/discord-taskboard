import logging
import os
from dataclasses import dataclass, field

import anthropic

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


@dataclass
class CommentaryEngine:
    model: str = "claude-sonnet-4-6"
    _client: anthropic.AsyncAnthropic | None = field(default=None, repr=False)
    _conversation: list[dict] = field(default_factory=list, repr=False)
    max_history: int = 20

    def __post_init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            self._client = anthropic.AsyncAnthropic(api_key=api_key)

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
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=self._conversation,
            )
            text = response.content[0].text
            self._conversation.append({"role": "assistant", "content": text})
            return text
        except Exception as e:
            logger.error("Commentary generation failed: %s", e)
            return "Uh, sorry chat, I just blanked for a second there. What were we talking about?"
