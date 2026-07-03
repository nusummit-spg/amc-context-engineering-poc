"""
Email parser — handles .msg (Outlook) and .eml files if any surface in the
corpus (e.g. analyst email threads). Uses extract-msg for real .msg structure;
falls back to plain-text read for .eml.
"""
from typing import List

from ingestion.parsers.base import BaseParser, ParsedSection


class EmailParser(BaseParser):
    supported_extensions = [".msg", ".eml"]

    def parse(self, filepath: str) -> List[ParsedSection]:
        if filepath.lower().endswith(".msg"):
            return self._parse_msg(filepath)
        return self._parse_eml(filepath)

    def _parse_msg(self, filepath: str) -> List[ParsedSection]:
        try:
            import extract_msg
        except ImportError:
            print("[email parser] extract-msg not installed, falling back to raw read")
            return self._raw_fallback(filepath)

        msg = extract_msg.Message(filepath)
        heading = msg.subject or "email"
        body = msg.body or ""
        metadata = {"sender": msg.sender, "date": str(msg.date)}
        return [
            ParsedSection(
                heading=heading, text=body, source_file=filepath,
                route_hint="unstructured", metadata=metadata,
            )
        ] if body.strip() else []

    def _parse_eml(self, filepath: str) -> List[ParsedSection]:
        import email
        from email import policy

        with open(filepath, "rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        body = msg.get_body(preferencelist=("plain",))
        text = body.get_content() if body else ""
        return [
            ParsedSection(
                heading=msg.get("Subject", "email"), text=text, source_file=filepath,
                route_hint="unstructured",
                metadata={"sender": msg.get("From"), "date": msg.get("Date")},
            )
        ] if text.strip() else []

    def _raw_fallback(self, filepath: str) -> List[ParsedSection]:
        with open(filepath, "r", errors="ignore") as f:
            text = f.read()
        return [
            ParsedSection(heading="email", text=text, source_file=filepath, route_hint="unstructured")
        ] if text.strip() else []