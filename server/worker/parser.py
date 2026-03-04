"""
Document text extraction module.

Supports:
  - PDF  (.pdf)   via pdfminer.six
  - PPTX (.pptx)  via python-pptx
  - DOCX (.docx)  via python-docx
"""

import io
import logging

logger = logging.getLogger(__name__)


def extract_text(content: bytes, file_name: str) -> str:
    """
    Dispatch to the correct extractor based on file extension.

    Args:
        content:   Raw bytes of the document file.
        file_name: Original file name (used to determine format).

    Returns:
        Extracted plain-text string.

    Raises:
        ValueError: If the file format is not supported.
    """
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(content)
    elif lower.endswith(".pptx"):
        return _extract_pptx(content)
    elif lower.endswith(".docx"):
        return _extract_docx(content)
    else:
        raise ValueError(f"Unsupported file format: '{file_name}'")


# ── PDF ───────────────────────────────────────────────────────────────────────

def _extract_pdf(content: bytes) -> str:
    from pdfminer.high_level import extract_text_to_fp
    from pdfminer.layout import LAParams

    output = io.StringIO()
    extract_text_to_fp(
        io.BytesIO(content),
        output,
        laparams=LAParams(),
        output_type="text",
        codec="utf-8",
    )
    return output.getvalue().strip()


# ── PPTX ──────────────────────────────────────────────────────────────────────

def _extract_pptx(content: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(content))
    lines = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = " ".join(run.text for run in para.runs).strip()
                    if line:
                        lines.append(line)
    return "\n".join(lines)


# ── DOCX ──────────────────────────────────────────────────────────────────────

def _extract_docx(content: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(content))
    return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
