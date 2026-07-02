from app.ingestion.parsers.base import ParserRegistry
from app.ingestion.parsers.docx import DocxParser
from app.ingestion.parsers.email import EmlParser, MsgParser
from app.ingestion.parsers.excel import ExcelParser
from app.ingestion.parsers.pdf import PdfParser
from app.ingestion.parsers.pptx import PptxParser
from app.ingestion.parsers.text import MarkdownParser, PlainTextParser


def build_registry() -> ParserRegistry:
    registry = ParserRegistry()
    for parser in (
        PdfParser(), DocxParser(), PptxParser(), MsgParser(), EmlParser(),
        ExcelParser(), MarkdownParser(), PlainTextParser(),
    ):
        registry.register(parser)
    return registry
