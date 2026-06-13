from abc import ABC, abstractmethod


class BaseTTSProvider(ABC):
    @abstractmethod
    async def synthesise(self, text: str, voice_id: str) -> bytes: ...
