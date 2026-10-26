# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================
"""Initialization module for parsers package."""


from app.ingestion.parsers.base import ParserRegistry
from app.ingestion.parsers.csv import CsvParser
from app.ingestion.parsers.docx import DocxParser
from app.ingestion.parsers.email import EmlParser, MsgParser
from app.ingestion.parsers.excel import ExcelParser
from app.ingestion.parsers.pdf import PdfParser
from app.ingestion.parsers.pptx import PptxParser
from app.ingestion.parsers.text import MarkdownParser, PlainTextParser


def build_registry() -> ParserRegistry:
    """Build registry.

    Returns:
        ParserRegistry: Resulting ParserRegistry instance.
    """
    registry = ParserRegistry()
    for parser in (
        PdfParser(), DocxParser(), PptxParser(), MsgParser(), EmlParser(),
        ExcelParser(), CsvParser(), MarkdownParser(), PlainTextParser(),
    ):
        registry.register(parser)
    return registry
