"""A minimal stand-in for an OpenAI-compatible vision client.

Records every chat.completions.create call and returns canned text, so the
markitdown-ocr plugin path can be tested without a running oMLX server.
"""

from types import SimpleNamespace


class FakeVisionClient:
    def __init__(self, reply: str = "FAKE_OCR_TEXT") -> None:
        self.reply = reply
        self.calls: list[dict] = []
        self._chat = SimpleNamespace(completions=self._Completions(self))

    class _Completions:
        def __init__(self, parent: "FakeVisionClient") -> None:
            self._parent = parent

        def create(self, **kwargs) -> SimpleNamespace:
            self._parent.calls.append(kwargs)
            message = SimpleNamespace(content=self._parent.reply)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    @property
    def chat(self):
        return self._chat
