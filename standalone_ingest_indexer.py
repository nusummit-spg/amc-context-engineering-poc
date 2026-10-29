#!/usr/bin/env python3
# ===========================================================================
# Standalone Document Ingestion and FAISS Indexer
# ===========================================================================
#
# A completely self-contained, high-performance document ingestion and vector
# indexing script designed for Google Colab (T4 GPU), Jupyter notebooks,
# or local environments.
#
# Supported Document Types:
#   - PDF (.pdf)
#   - CSV (.csv)
#   - Word (.docx, .doc)
#   - Email (.eml, .msg)
#   - Excel (.xlsx, .xls)
#   - PowerPoint (.pptx, .ppt)
#   - Text (.txt, .md, .markdown, .json, .log, .rst)
#
# Key Features:
#   - ZERO reliance on external LLM APIs (no OpenAI, Anthropic, Gemini, Groq).
#   - Downloads and runs top open-source Hugging Face embedding models
#     (Default: BAAI/bge-m3 or BAAI/bge-large-en-v1.5).
#   - Hardware-optimized for Google Colab NVIDIA Tesla T4 (16GB VRAM) with
#     FP16 half-precision and high-throughput CUDA batching.
#   - Produces standard 'index.faiss' and 'payload.json' (plus 'payloads.json').
#   - Callable directly from Python / Jupyter / Colab code cells:
#         run_indexing(input_dir=..., output_dir=...)
# ===========================================================================

from __future__ import annotations

import argparse
import csv
import email
import email.policy
import gc
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("StandaloneIndexer")


# ===========================================================================
# Data Structures
# ===========================================================================

@dataclass
class DocumentChunk:
    chunk_id: str
    vector_id: int
    document_id: str
    document_title: str
    source_filename: str
    file_path: str
    file_type: str
    page_start: int
    page_end: int
    section_locator: str
    text: str
    char_count: int
    word_count: int
    order: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# Chunking Utility (Boundary-aware, recursive text splitting)
# ===========================================================================

def split_text_boundary_aware(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> List[str]:
    """
    Splits text into chunks preserving paragraph and sentence boundaries.
    No LLM is needed.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    # Split by double newline (paragraphs) first
    paragraphs = text.split("\n\n")
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If a single paragraph exceeds chunk_size, split by sentences
        if len(para) > chunk_size:
            sentence_splits = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentence_splits:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if current_len + len(sentence) + 1 > chunk_size and current_chunk:
                    chunk_text = " ".join(current_chunk).strip()
                    if chunk_text:
                        chunks.append(chunk_text)
                    # Overlap handling
                    overlap_chars = 0
                    overlap_items: List[str] = []
                    for item in reversed(current_chunk):
                        if overlap_chars + len(item) <= chunk_overlap:
                            overlap_items.insert(0, item)
                            overlap_chars += len(item)
                        else:
                            break
                    current_chunk = overlap_items
                    current_len = sum(len(x) + 1 for x in current_chunk)

                current_chunk.append(sentence)
                current_len += len(sentence) + 1
        else:
            if current_len + len(para) + 2 > chunk_size and current_chunk:
                chunk_text = "\n\n".join(current_chunk).strip()
                if chunk_text:
                    chunks.append(chunk_text)
                # Overlap handling
                overlap_chars = 0
                overlap_items: List[str] = []
                for item in reversed(current_chunk):
                    if overlap_chars + len(item) <= chunk_overlap:
                        overlap_items.insert(0, item)
                        overlap_chars += len(item)
                    else:
                        break
                current_chunk = overlap_items
                current_len = sum(len(x) + 2 for x in current_chunk)

            current_chunk.append(para)
            current_len += len(para) + 2

    if current_chunk:
        chunk_text = "\n\n".join(current_chunk).strip()
        if chunk_text:
            chunks.append(chunk_text)

    return chunks


# ===========================================================================
# Multi-Format Document Extractors
# ===========================================================================

def extract_pdf(path: Path) -> List[Dict[str, Any]]:
    """
    Extracts text from PDF page-by-page.
    Prefers PyMuPDF (fitz) for speed, falls back to pypdf.
    """
    records: List[Dict[str, Any]] = []

    # 1. Try PyMuPDF
    try:
        import fitz  # PyMuPDF
        with fitz.open(str(path)) as doc:
            for page_idx, page in enumerate(doc, start=1):
                text = page.get_text() or ""
                try:
                    tabs = page.find_tables()
                    if tabs.tables:
                        for tab in tabs:
                            df_md = tab.to_markdown()
                            if df_md:
                                text += "\n\n" + df_md
                except Exception:
                    pass

                text = text.strip()
                if text:
                    records.append({
                        "text": text,
                        "page_start": page_idx,
                        "page_end": page_idx,
                        "section_locator": f"p.{page_idx}",
                        "metadata": {"total_pages": len(doc)},
                    })
        return records
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"PyMuPDF failed on {path.name}: {e}. Trying fallback...")

    # 2. Try pypdf fallback
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        num_pages = len(reader.pages)
        for page_idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                records.append({
                    "text": text,
                    "page_start": page_idx,
                    "page_end": page_idx,
                    "section_locator": f"p.{page_idx}",
                    "metadata": {"total_pages": num_pages},
                })
        return records
    except ImportError:
        logger.warning("Neither 'pymupdf' nor 'pypdf' installed. Please run: pip install pymupdf")
        return []
    except Exception as e:
        logger.error(f"Error reading PDF {path.name}: {e}")
        return []


def extract_csv(path: Path, max_rows_per_chunk: int = 25) -> List[Dict[str, Any]]:
    """
    Extracts tabular data from CSV files.
    Preserves column headers in each row-group chunk for contextual search.
    """
    records: List[Dict[str, Any]] = []
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="replace") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    return []

                clean_header = [h.strip() for h in header]
                rows: List[List[str]] = []
                row_start = 1

                for row_idx, row in enumerate(reader, start=1):
                    if not any(cell.strip() for cell in row):
                        continue
                    rows.append(row)
                    if len(rows) >= max_rows_per_chunk:
                        formatted_lines = [f"Table columns: {', '.join(clean_header)}"]
                        for r in rows:
                            row_cells = [
                                f"{clean_header[i]}: {r[i]}" if i < len(clean_header) else r[i]
                                for i in range(len(r))
                            ]
                            formatted_lines.append(" | ".join(row_cells))

                        records.append({
                            "text": "\n".join(formatted_lines),
                            "page_start": row_start,
                            "page_end": row_idx,
                            "section_locator": f"rows {row_start}-{row_idx}",
                            "metadata": {"columns": clean_header, "row_count": len(rows)},
                        })
                        rows = []
                        row_start = row_idx + 1

                if rows:
                    formatted_lines = [f"Table columns: {', '.join(clean_header)}"]
                    for r in rows:
                        row_cells = [
                            f"{clean_header[i]}: {r[i]}" if i < len(clean_header) else r[i]
                            for i in range(len(r))
                        ]
                        formatted_lines.append(" | ".join(row_cells))

                    records.append({
                        "text": "\n".join(formatted_lines),
                        "page_start": row_start,
                        "page_end": row_start + len(rows) - 1,
                        "section_locator": f"rows {row_start}-{row_start + len(rows) - 1}",
                        "metadata": {"columns": clean_header, "row_count": len(rows)},
                    })
            return records
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.error(f"Error parsing CSV {path.name}: {e}")
            break

    return records


def extract_docx(path: Path) -> List[Dict[str, Any]]:
    """
    Extracts paragraphs and tables from Word (.docx) files.
    """
    records: List[Dict[str, Any]] = []
    try:
        import docx
        doc = docx.Document(str(path))
        text_blocks: List[str] = []

        # Extract paragraphs
        for p in doc.paragraphs:
            t = p.text.strip()
            if t:
                text_blocks.append(t)

        # Extract tables
        for table_idx, table in enumerate(doc.tables, start=1):
            table_lines: List[str] = []
            for row in table.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                if any(cells):
                    table_lines.append(" | ".join(cells))
            if table_lines:
                text_blocks.append(f"[Table {table_idx}]\n" + "\n".join(table_lines))

        full_doc_text = "\n\n".join(text_blocks)
        if full_doc_text:
            records.append({
                "text": full_doc_text,
                "page_start": 1,
                "page_end": 1,
                "section_locator": "full_document",
                "metadata": {"paragraph_count": len(doc.paragraphs), "table_count": len(doc.tables)},
            })
        return records
    except ImportError:
        logger.warning("python-docx not installed. Run: pip install python-docx")
        try:
            raw = path.read_bytes()
            ascii_text = "".join(chr(b) if 32 <= b <= 126 or b in (10, 13) else " " for b in raw)
            cleaned = " ".join(ascii_text.split())
            if len(cleaned) > 100:
                return [{
                    "text": cleaned,
                    "page_start": 1,
                    "page_end": 1,
                    "section_locator": "raw_extract",
                    "metadata": {},
                }]
        except Exception:
            pass
        return []
    except Exception as e:
        logger.error(f"Error extracting DOCX {path.name}: {e}")
        return []


def extract_excel(path: Path, max_rows_per_chunk: int = 25) -> List[Dict[str, Any]]:
    """
    Extracts sheets and tabular rows from Excel (.xlsx, .xls) files.
    """
    records: List[Dict[str, Any]] = []

    # 1. Try openpyxl
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows_iter = ws.iter_rows(values_only=True)
            header_row = next(rows_iter, None)
            if not header_row:
                continue

            headers = [str(c).strip() if c is not None else f"Col_{i}" for i, c in enumerate(header_row)]
            row_batch: List[List[str]] = []
            row_start = 2

            for r_idx, r in enumerate(rows_iter, start=2):
                if not any(c is not None and str(c).strip() for c in r):
                    continue
                row_batch.append([str(c).strip() if c is not None else "" for c in r])

                if len(row_batch) >= max_rows_per_chunk:
                    lines = [f"Sheet: {sheet_name} | Columns: {', '.join(headers)}"]
                    for r_vals in row_batch:
                        cells = [
                            f"{headers[i]}: {r_vals[i]}" if i < len(headers) else r_vals[i]
                            for i in range(len(r_vals))
                        ]
                        lines.append(" | ".join(cells))

                    records.append({
                        "text": "\n".join(lines),
                        "page_start": row_start,
                        "page_end": r_idx,
                        "section_locator": f"{sheet_name}:rows_{row_start}_{r_idx}",
                        "metadata": {"sheet": sheet_name, "columns": headers},
                    })
                    row_batch = []
                    row_start = r_idx + 1

            if row_batch:
                lines = [f"Sheet: {sheet_name} | Columns: {', '.join(headers)}"]
                for r_vals in row_batch:
                    cells = [
                        f"{headers[i]}: {r_vals[i]}" if i < len(headers) else r_vals[i]
                        for i in range(len(r_vals))
                    ]
                    lines.append(" | ".join(cells))

                records.append({
                    "text": "\n".join(lines),
                    "page_start": row_start,
                    "page_end": row_start + len(row_batch) - 1,
                    "section_locator": f"{sheet_name}:rows_{row_start}_{row_start + len(row_batch) - 1}",
                    "metadata": {"sheet": sheet_name, "columns": headers},
                })
        wb.close()
        return records
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"openpyxl failed on {path.name}: {e}. Trying pandas...")

    # 2. Try pandas fallback
    try:
        import pandas as pd
        excel_file = pd.ExcelFile(path)
        for sheet in excel_file.sheet_names:
            df = excel_file.parse(sheet)
            if df.empty:
                continue
            records.append({
                "text": f"Sheet: {sheet}\n" + df.to_string(index=False),
                "page_start": 1,
                "page_end": len(df),
                "section_locator": f"{sheet}",
                "metadata": {"sheet": sheet, "rows": len(df)},
            })
        return records
    except ImportError:
        logger.warning("Neither 'openpyxl' nor 'pandas' installed for Excel. Run: pip install openpyxl")
        return []
    except Exception as e:
        logger.error(f"Error parsing Excel file {path.name}: {e}")
        return []


def extract_pptx(path: Path) -> List[Dict[str, Any]]:
    """
    Extracts slides, shapes, tables, and speaker notes from PowerPoint (.pptx).
    """
    records: List[Dict[str, Any]] = []
    try:
        from pptx import Presentation
        prs = Presentation(str(path))
        for slide_idx, slide in enumerate(prs.slides, start=1):
            slide_texts: List[str] = []

            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        t = paragraph.text.strip()
                        if t:
                            slide_texts.append(t)
                elif shape.has_table:
                    for row in shape.table.rows:
                        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                        if any(cells):
                            slide_texts.append(" | ".join(cells))

            # Include notes if available
            try:
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    notes = slide.notes_slide.notes_text_frame.text.strip()
                    if notes:
                        slide_texts.append(f"[Presenter Notes]: {notes}")
            except Exception:
                pass

            slide_body = "\n".join(slide_texts).strip()
            if slide_body:
                records.append({
                    "text": f"[Slide {slide_idx}]\n" + slide_body,
                    "page_start": slide_idx,
                    "page_end": slide_idx,
                    "section_locator": f"slide_{slide_idx}",
                    "metadata": {"slide_number": slide_idx, "total_slides": len(prs.slides)},
                })
        return records
    except ImportError:
        logger.warning("python-pptx not installed. Run: pip install python-pptx")
        return []
    except Exception as e:
        logger.error(f"Error extracting PPTX {path.name}: {e}")
        return []


def extract_email(path: Path) -> List[Dict[str, Any]]:
    """
    Extracts emails from .eml (standard RFC 822) or .msg (Outlook) files.
    """
    records: List[Dict[str, Any]] = []
    ext = path.suffix.lower()

    if ext == ".msg":
        try:
            import extract_msg
            msg = extract_msg.Message(str(path))
            header_block = (
                f"Subject: {msg.subject or ''}\n"
                f"From: {msg.sender or ''}\n"
                f"To: {msg.to or ''}\n"
                f"Date: {msg.date or ''}"
            )
            body = (msg.body or "").strip()
            text = f"{header_block}\n\n{body}"
            records.append({
                "text": text,
                "page_start": 1,
                "page_end": 1,
                "section_locator": "email_msg",
                "metadata": {
                    "subject": msg.subject,
                    "from": msg.sender,
                    "to": msg.to,
                    "date": str(msg.date),
                },
            })
            msg.close()
            return records
        except ImportError:
            logger.warning("extract-msg not installed for .msg files. Run: pip install extract-msg")
        except Exception as e:
            logger.warning(f"extract-msg failed on {path.name}: {e}")

    # Standard .eml parser
    try:
        raw_bytes = path.read_bytes()
        msg_obj = email.message_from_bytes(raw_bytes, policy=email.policy.default)
        headers = [
            f"Subject: {msg_obj.get('subject', '')}",
            f"From: {msg_obj.get('from', '')}",
            f"To: {msg_obj.get('to', '')}",
            f"Date: {msg_obj.get('date', '')}",
        ]

        body_parts: List[str] = []
        if msg_obj.is_multipart():
            for part in msg_obj.walk():
                ctype = part.get_content_type()
                cdispo = str(part.get('content-disposition', ''))
                if ctype == "text/plain" and "attachment" not in cdispo:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_parts.append(payload.decode(charset, errors="replace"))
        else:
            payload = msg_obj.get_payload(decode=True)
            if payload:
                charset = msg_obj.get_content_charset() or "utf-8"
                body_parts.append(payload.decode(charset, errors="replace"))

        body_text = "\n\n".join(body_parts).strip()
        full_text = "\n".join(headers) + "\n\n" + body_text
        records.append({
            "text": full_text,
            "page_start": 1,
            "page_end": 1,
            "section_locator": "email",
            "metadata": {
                "subject": msg_obj.get('subject', ''),
                "from": msg_obj.get('from', ''),
                "to": msg_obj.get('to', ''),
                "date": msg_obj.get('date', ''),
            },
        })
        return records
    except Exception as e:
        logger.error(f"Error parsing email {path.name}: {e}")
        return []


def extract_txt(path: Path) -> List[Dict[str, Any]]:
    """
    Extracts text from plain text formats (.txt, .md, .json, .log, .rst).
    """
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            content = path.read_text(encoding=enc).strip()
            if not content:
                return []
            return [{
                "text": content,
                "page_start": 1,
                "page_end": 1,
                "section_locator": "full_text",
                "metadata": {"char_length": len(content)},
            }]
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.error(f"Error reading text file {path.name}: {e}")
            break
    return []


# ===========================================================================
# Master Ingestion Dispatcher
# ===========================================================================

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".csv": "csv",
    ".docx": "docs",
    ".doc": "docs",
    ".eml": "email",
    ".msg": "email",
    ".xlsx": "excel",
    ".xls": "excel",
    ".pptx": "pptx",
    ".ppt": "pptx",
    ".txt": "txt",
    ".md": "txt",
    ".markdown": "txt",
    ".json": "txt",
    ".log": "txt",
    ".rst": "txt",
}

def extract_document(file_path: Path) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Dispatches file parsing according to file extension.
    Returns (file_type, raw_extracted_records).
    """
    ext = file_path.suffix.lower()
    file_type = SUPPORTED_EXTENSIONS.get(ext, "unknown")

    if file_type == "pdf":
        return file_type, extract_pdf(file_path)
    elif file_type == "csv":
        return file_type, extract_csv(file_path)
    elif file_type == "docs":
        return file_type, extract_docx(file_path)
    elif file_type == "email":
        return file_type, extract_email(file_path)
    elif file_type == "excel":
        return file_type, extract_excel(file_path)
    elif file_type == "pptx":
        return file_type, extract_pptx(file_path)
    elif file_type == "txt":
        return file_type, extract_txt(file_path)
    else:
        return file_type, []


def scan_and_chunk_corpus(
    input_dir: Path,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> List[DocumentChunk]:
    """
    Scans input directory recursively for all supported documents,
    extracts content, and splits into coherent chunks.
    """
    all_chunks: List[DocumentChunk] = []
    global_chunk_idx = 0

    files = [
        f for f in input_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    logger.info(f"Discovered {len(files)} supported document(s) in {input_dir}")

    for file_path in files:
        file_name = file_path.name
        ext = file_path.suffix.lower()
        logger.info(f"  -> Ingesting [{ext}] {file_name}...")

        file_type, extracted_sections = extract_document(file_path)
        if not extracted_sections:
            logger.warning(f"     No text extracted from {file_name}")
            continue

        doc_chunk_count = 0
        for section in extracted_sections:
            raw_text = section.get("text", "")
            page_s = section.get("page_start", 1)
            page_e = section.get("page_end", 1)
            locator = section.get("section_locator", "unknown")
            meta = section.get("metadata", {})

            # For CSV and Excel sections pre-chunked by rows
            if file_type in ("csv", "excel") and len(raw_text) <= chunk_size * 2:
                split_chunks = [raw_text]
            else:
                split_chunks = split_text_boundary_aware(
                    raw_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )

            for split_idx, chunk_text in enumerate(split_chunks):
                chunk_text = chunk_text.strip()
                if not chunk_text:
                    continue

                chunk_obj = DocumentChunk(
                    chunk_id=f"CHK_{global_chunk_idx:06d}",
                    vector_id=global_chunk_idx,
                    document_id=file_name,
                    document_title=file_path.stem,
                    source_filename=file_name,
                    file_path=str(file_path.resolve()),
                    file_type=file_type,
                    page_start=page_s,
                    page_end=page_e,
                    section_locator=f"{locator}:sub_{split_idx}" if len(split_chunks) > 1 else locator,
                    text=chunk_text,
                    char_count=len(chunk_text),
                    word_count=len(chunk_text.split()),
                    order=doc_chunk_count,
                    metadata={
                        **meta,
                        "file_size_bytes": file_path.stat().st_size,
                        "extension": ext,
                    },
                )
                all_chunks.append(chunk_obj)
                global_chunk_idx += 1
                doc_chunk_count += 1

        logger.info(f"     Extracted {doc_chunk_count} chunk(s) from {file_name}")

    logger.info(f"Ingestion complete. Total corpus chunks: {len(all_chunks)}")
    return all_chunks


# ===========================================================================
# Model Loader & Vector Embedding (Optimized for Google Colab T4 GPU)
# ===========================================================================

def get_device(requested_device: str = "auto") -> str:
    """
    Resolves compute device. Defaults to CUDA if available (e.g. Colab T4).
    """
    import torch
    if requested_device == "auto":
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"CUDA accelerator detected: {gpu_name}")
            return "cuda"
        return "cpu"
    return requested_device


def load_embedding_model(model_name: str, device: str = "auto", use_fp16: bool = True):
    """
    Downloads and initializes the Hugging Face embedding model.
    Runs in FP16 precision on T4 GPU for high throughput and reduced VRAM.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.error(
            "Missing 'sentence-transformers'. Install via:\n"
            "pip install sentence-transformers"
        )
        sys.exit(1)

    resolved_device = get_device(device)
    logger.info(f"Loading Hugging Face model '{model_name}' on {resolved_device.upper()}...")

    start_time = time.time()
    model = SentenceTransformer(model_name, device=resolved_device)

    # Enable FP16 on CUDA devices (like Google Colab Tesla T4)
    if resolved_device == "cuda" and use_fp16:
        try:
            model = model.half()
            logger.info("FP16 half-precision enabled for CUDA acceleration.")
        except Exception as e:
            logger.warning(f"Could not enable FP16: {e}. Running in standard precision.")

    load_time = time.time() - start_time
    logger.info(f"Model loaded successfully in {load_time:.2f}s.")
    return model, resolved_device


def compute_embeddings(
    model,
    texts: List[str],
    batch_size: int = 64,
    device: str = "cuda",
) -> Any:
    """
    Computes L2-normalized dense embeddings for all chunk texts.
    Returns a numpy.ndarray of shape (N, dim) with float32 type.
    """
    import numpy as np

    total_chunks = len(texts)
    logger.info(
        f"Computing dense embeddings for {total_chunks} chunks "
        f"(batch_size={batch_size}, device={device})..."
    )

    start_time = time.time()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    embeddings = embeddings.astype(np.float32)
    elapsed = time.time() - start_time
    chunks_per_sec = total_chunks / elapsed if elapsed > 0 else 0
    logger.info(
        f"Embeddings finished in {elapsed:.2f}s "
        f"({chunks_per_sec:.1f} chunks/sec). Shape: {embeddings.shape}"
    )
    return embeddings


# ===========================================================================
# FAISS Index & Payload Generation
# ===========================================================================

def build_faiss_and_payloads(
    chunks: List[DocumentChunk],
    embeddings: Any,
    output_dir: Path,
) -> Tuple[Path, Path]:
    """
    Constructs the FAISS IndexFlatIP index and serializes payload.json.
    """
    try:
        import faiss
    except ImportError:
        logger.error(
            "Missing 'faiss'. Install via:\n"
            "pip install faiss-gpu  (for Colab/CUDA) or  pip install faiss-cpu"
        )
        sys.exit(1)

    import numpy as np

    output_dir.mkdir(parents=True, exist_ok=True)
    index_file = output_dir / "index.faiss"
    payload_file = output_dir / "payload.json"
    payloads_alias = output_dir / "payloads.json"  # For broad compatibility

    num_vectors, dim = embeddings.shape
    logger.info(f"Building FAISS IndexFlatIP (dim={dim}, vectors={num_vectors})...")

    # Double check normalization for Cosine similarity
    faiss.normalize_L2(embeddings)

    # Create Inner Product index (on normalized vectors, IP == Cosine Similarity)
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    # Save FAISS index
    faiss.write_index(index, str(index_file))
    logger.info(f"  [SAVED] FAISS index written to: {index_file} ({index_file.stat().st_size:,} bytes)")

    # Construct payloads dictionary (keyed by vector ID string: "0", "1", ...)
    payload_dict: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks:
        payload_dict[str(chunk.vector_id)] = chunk.to_dict()

    # Save payload.json
    with open(payload_file, "w", encoding="utf-8") as f:
        json.dump(payload_dict, f, indent=2, ensure_ascii=False)
    logger.info(f"  [SAVED] Payload written to: {payload_file} ({payload_file.stat().st_size:,} bytes)")

    # Also save payloads.json alias
    with open(payloads_alias, "w", encoding="utf-8") as f:
        json.dump(payload_dict, f, indent=2, ensure_ascii=False)

    return index_file, payload_file


# ===========================================================================
# Interactive Verification / Query Tool
# ===========================================================================

def search_index(
    query: str,
    output_dir: Union[str, Path],
    model_name: str = "BAAI/bge-small-en-v1.5",
    top_k: int = 5,
    device: str = "auto",
):
    """
    Loads generated index.faiss and payload.json to execute a test semantic search.
    """
    try:
        import faiss
    except ImportError:
        logger.error("FAISS not installed.")
        return

    output_path = Path(output_dir).resolve()
    index_file = output_path / "index.faiss"
    payload_file = output_path / "payload.json"

    if not index_file.exists() or not payload_file.exists():
        logger.error(f"Cannot test search: Files not found in {output_path}")
        return

    logger.info(f"Loading FAISS index from {index_file}...")
    index = faiss.read_index(str(index_file))

    with open(payload_file, "r", encoding="utf-8") as f:
        payloads: Dict[str, Dict[str, Any]] = json.load(f)

    logger.info(f"Embedding query: '{query}'")
    model, resolved_device = load_embedding_model(model_name, device=device, use_fp16=False)

    query_vec = model.encode([query], normalize_embeddings=True)
    import numpy as np
    query_vec = query_vec.astype(np.float32)
    faiss.normalize_L2(query_vec)

    distances, indices = index.search(query_vec, top_k)

    print("\n" + "=" * 70)
    print(f"SEARCH RESULTS: \"{query}\"")
    print("=" * 70)

    for rank, (score, idx) in enumerate(zip(distances[0], indices[0]), start=1):
        if idx < 0 or str(idx) not in payloads:
            continue
        p = payloads[str(idx)]
        text_preview = p['text'].replace('\n', ' ')
        if len(text_preview) > 200:
            text_preview = text_preview[:200] + "..."

        print(f"[{rank}] Score: {score:.4f} | Source: {p['source_filename']} ({p['file_type'].upper()})")
        print(f"    Locator: {p['section_locator']} | Chunk ID: {p['chunk_id']}")
        print(f"    Text: \"{text_preview}\"")
        print("-" * 70)
    print()


# Alias for clean programmatic use
query_index = search_index


# ===========================================================================
# Programmatic Pipeline Runner (For Code Cells & Python scripts)
# ===========================================================================

def run_indexing(
    input_dir: Union[str, Path] = "./data",
    output_dir: Union[str, Path] = "./output",
    model_name: str = "BAAI/bge-small-en-v1.5",
    batch_size: int = 64,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    device: str = "auto",
    use_fp16: bool = True,
    test_query: Optional[str] = None,
) -> Tuple[Path, Path]:
    """
    Executes the full ingestion, embedding, and indexing pipeline.
    Directly callable from a Jupyter / Google Colab code cell:

    >>> from standalone_ingest_indexer import run_indexing
    >>> run_indexing(input_dir="/content/docs", output_dir="/content/output")
    """
    in_path = Path(input_dir).resolve()
    out_path = Path(output_dir).resolve()

    print("=" * 70)
    print("STANDALONE DOCUMENT INGESTION & FAISS INDEXER")
    print("=" * 70)
    print(f"Input Directory  : {in_path}")
    print(f"Output Directory : {out_path}")
    print(f"HF Model         : {model_name}")
    print(f"Batch Size       : {batch_size}")
    print(f"Chunk Config     : size={chunk_size}, overlap={chunk_overlap}")
    print(f"Device           : {device}")
    print("=" * 70)

    if not in_path.exists():
        raise FileNotFoundError(f"Input directory does not exist: {in_path}")

    # 1. Ingest and Chunk Documents
    chunks = scan_and_chunk_corpus(
        input_dir=in_path,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if not chunks:
        logger.warning(
            f"No supported documents or chunks found in {in_path}. "
            f"Supported extensions: {list(SUPPORTED_EXTENSIONS.keys())}"
        )
        return out_path / "index.faiss", out_path / "payload.json"

    # 2. Load Hugging Face Model
    model, resolved_device = load_embedding_model(
        model_name=model_name,
        device=device,
        use_fp16=use_fp16,
    )

    # 3. Compute Embeddings
    texts = [c.text for c in chunks]
    embeddings = compute_embeddings(
        model=model,
        texts=texts,
        batch_size=batch_size,
        device=resolved_device,
    )

    # 4. Build FAISS Index and Payload
    index_path, payload_path = build_faiss_and_payloads(
        chunks=chunks,
        embeddings=embeddings,
        output_dir=out_path,
    )

    print("\n" + "=" * 70)
    print("BUILD SUCCESSFUL!")
    print(f"  FAISS Index : {index_path}")
    print(f"  Payload     : {payload_path}")
    print(f"  Total Chunks: {len(chunks)}")
    print("=" * 70)

    # 5. Optional Test Query
    if test_query:
        search_index(
            query=test_query,
            output_dir=out_path,
            model_name=model_name,
            device=resolved_device,
        )

    return index_path, payload_path


# ===========================================================================
# CLI & Notebook Auto-Detection Entrypoint
# ===========================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Standalone Ingestion & Vector Indexer (T4 GPU optimized, No LLM required)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input-dir", "-i",
        type=str,
        default="./data",
        help="Directory containing documents to ingest (PDF, CSV, DOCX, Email, Excel, PPTX, TXT)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./output",
        help="Directory where index.faiss and payload.json will be saved",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="BAAI/bge-small-en-v1.5",
        help="Hugging Face embedding model (default: BAAI/bge-small-en-v1.5)",
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=64,
        help="Batch size for embedding calculation (64 recommended for 16GB T4 GPU)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Maximum character length per text chunk",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=150,
        help="Character overlap between consecutive chunks",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Compute device ('cuda' for Colab T4 GPU, 'cpu', or 'auto')",
    )
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Disable FP16 half-precision on GPU",
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Run an immediate semantic search test query on the built index",
    )
    # Using parse_known_args ensures safe execution inside Jupyter/Colab kernels
    args, _ = parser.parse_known_args()
    return args


def main():
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    # If only querying an existing index:
    if args.query and not input_dir.exists() and (output_dir / "index.faiss").exists():
        search_index(
            query=args.query,
            output_dir=output_dir,
            model_name=args.model,
            device=args.device,
        )
        return

    run_indexing(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        model_name=args.model,
        batch_size=args.batch_size,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        device=args.device,
        use_fp16=not args.no_fp16,
        test_query=args.query,
    )


if __name__ == "__main__":
    main()
