"""The chat app's AI forms. Job prompts live in `charie/prompts/`."""

from pydantic import BaseModel, ConfigDict, Field


class ChatTitle(BaseModel):
    """Form for the name_chat job. Titles label a chat; labels are text."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(description="A short title for the chat, 2 to 6 words, no digits.")
