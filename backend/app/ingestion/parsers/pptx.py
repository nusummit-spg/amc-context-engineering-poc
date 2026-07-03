"""PPTX parser — for any sector outlook / factsheet decks in the corpus."""
from typing import List
from pptx import Presentation

from ingestion.parsers.base import BaseParser, ParsedSection


class PPTXParser(BaseParser):
    supported_extensions = [".pptx"]

    def parse(self, filepath: str) -> List[ParsedSection]:
        prs = Presentation(filepath)
        sections: List[ParsedSection] = []

        for i, slide in enumerate(prs.slides, start=1):
            title = ""
            texts = []
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                frame_text = "\n".join(
                    p.text for p in shape.text_frame.paragraphs if p.text.strip()
                )
                if not frame_text:
                    continue
                if shape == slide.shapes.title:
                    title = frame_text
                else:
                    texts.append(frame_text)

            combined = "\n".join(texts).strip()
            if combined or title:
                sections.append(
                    ParsedSection(
                        heading=title or f"slide_{i}",
                        text=combined,
                        source_file=filepath,
                        route_hint="unstructured",
                        metadata={"slide_number": i},
                    )
                )
        return sections