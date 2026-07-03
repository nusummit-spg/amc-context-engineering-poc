"""Parser registry. ingestion/pipeline.py calls get_parser(filepath)."""
from ingestion.parsers.base import BaseParser, ParsedSection
from ingestion.parsers.pdf import PDFParser
from ingestion.parsers.docx import DOCXParser
from ingestion.parsers.pptx import PPTXParser
from ingestion.parsers.excel import ExcelParser
from ingestion.parsers.email import EmailParser
from ingestion.parsers.text import TextParser

_PARSERS = [PDFParser(), DOCXParser(), PPTXParser(), ExcelParser(), EmailParser(), TextParser()]


def get_parser(filepath: str) -> BaseParser | None:
    for parser in _PARSERS:
        if parser.can_handle(filepath):
            return parser
    return None


__all__ = ["BaseParser", "ParsedSection", "get_parser"]