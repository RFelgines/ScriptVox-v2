class EpubParsingError(Exception):
    def __init__(self, path: str, cause: Exception) -> None:
        super().__init__(f"Failed to parse EPUB at {path!r}: {cause}")
        self.path = path
        self.cause = cause


class LLMParsingError(Exception):
    pass
