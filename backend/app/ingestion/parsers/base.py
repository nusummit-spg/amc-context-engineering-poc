# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS2 — Parser interface. Each parser converts one file format into the unified Document schema."""
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.documents import Document


class BaseParser(ABC):
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def parse(self, path: Path) -> Document:
        ...


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}

    def register(self, parser: BaseParser) -> None:
        for ext in parser.extensions:
            self._parsers[ext.lower()] = parser

    def get(self, path: Path) -> BaseParser:
        ext = path.suffix.lower()
        if ext not in self._parsers:
            raise ValueError(f"No parser registered for extension {ext!r}")
        return self._parsers[ext]

    def supported_extensions(self) -> list[str]:
        return sorted(self._parsers.keys())
