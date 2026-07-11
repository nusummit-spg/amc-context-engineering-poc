"""WS2 — Email parsers: .msg via extract-msg, .eml via stdlib. Thread unwinding:
each reply in a quoted thread becomes its own section (newest first)."""
import email
import email.policy
import re
from pathlib import Path

from app.ingestion.parsers.base import BaseParser
from app.schemas.documents import Document, DocumentType, Section

# Common reply-separators used to unwind a quoted thread.
_THREAD_SPLIT_RE = re.compile(
    r"(?:^-{3,}\s*Original Message\s*-{3,}$|^On .{5,120} wrote:$|^From:\s.+$)",
    re.MULTILINE,
)


def _split_thread(body: str) -> list[str]:
    parts = _THREAD_SPLIT_RE.split(body)
    return [p.strip() for p in parts if p and p.strip()]


def _build_document(path: Path, headers: dict, body: str) -> Document:
    parts = _split_thread(body)
    sections = [
        Section(
            title=f"Message {i + 1}" if i else (headers.get("subject") or "Message"),
            text=part,
            order=i,
            metadata={"thread_position": i},
        )
        for i, part in enumerate(parts)
    ]
    return Document(
        filename=path.name,
        doc_type=DocumentType.EMAIL,
        title=headers.get("subject") or path.stem,
        author=headers.get("from"),
        source_path=str(path),
        sections=sections or [Section(text=body, order=0)],
        metadata=headers,
    )


class MsgParser(BaseParser):
    extensions = (".msg",)

    def parse(self, path: Path) -> Document:
        import extract_msg

        msg = extract_msg.Message(str(path))
        headers = {
            "from": msg.sender or "",
            "to": msg.to or "",
            "subject": msg.subject or "",
            "date": str(msg.date or ""),
        }
        body = msg.body or ""
        msg.close()
        return _build_document(path, headers, body)


class EmlParser(BaseParser):
    extensions = (".eml",)

    def parse(self, path: Path) -> Document:
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=email.policy.default)
        headers = {
            "from": str(msg.get("From", "")),
            "to": str(msg.get("To", "")),
            "subject": str(msg.get("Subject", "")),
            "date": str(msg.get("Date", "")),
        }
        body_part = msg.get_body(preferencelist=("plain", "html"))
        body = body_part.get_content() if body_part else ""
        return _build_document(path, headers, body)
