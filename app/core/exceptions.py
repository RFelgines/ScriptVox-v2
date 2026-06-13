class EpubParsingError(Exception):
    def __init__(self, path: str, cause: Exception) -> None:
        super().__init__(f"Failed to parse EPUB at {path!r}: {cause}")
        self.path = path
        self.cause = cause


class LLMParsingError(Exception):
    def __init__(self, raw_response: str, cause: Exception) -> None:
        import logging
        super().__init__(f"LLM response parsing failed: {cause}")
        logging.getLogger(__name__).error("LLM raw response:\n%s", raw_response)
        self.raw_response = raw_response
        self.cause = cause
