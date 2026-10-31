"""Read only a frozen sampled page's OCR; no image, render, title hint or other page access."""
from __future__ import annotations

import ctypes
from pathlib import Path

from archivist.templates.pages import REAL


def sampled_text(ref: str, allowed: set[str], held: set[str], pdf_path: Path,
                 width: int, height: int) -> str:
    """Equivalent word join to ocr.layer; dimensions come from manifest metadata, not an image.

    Keep the same positive pixel-box filter, at the original stored-image dimensions.
    PDFium selects only this page's text layer. No page is rendered or image opened.
    """
    match = REAL.fullmatch(ref)
    if ref not in allowed or match is None or match['issue'] not in held:
        raise PermissionError('OCR is restricted to the frozen held-out sample')
    if width <= 0 or height <= 0:
        raise ValueError('positive original image dimensions required')
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        page = pdf[int(match['page'])-1]
        text = page.get_textpage()
        words, chars = [], []
        def pixel(x, y):
            dx,dy = ctypes.c_int(),ctypes.c_int()
            raw.FPDF_PageToDevice(page.raw,0,0,width,height,0,x,y,
                                 ctypes.byref(dx),ctypes.byref(dy))
            return dx.value,dy.value
        n = text.count_chars()
        for i in range(n+1):
            char = text.get_text_range(i,1) if i<n else ' '
            if char and not char.isspace():
                chars.append((char,text.get_charbox(i)))
                continue
            if chars:
                left=min(b[0] for _,b in chars)
                bottom=min(b[1] for _,b in chars)
                right=max(b[2] for _,b in chars)
                top=max(b[3] for _,b in chars)
                (x0,y1),(x1,y0)=pixel(left,bottom),pixel(right,top)
                if x1>x0 and y1>y0:
                    words.append(''.join(c for c,_ in chars))
                chars=[]
        return ' '.join(words)
    finally:
        pdf.close()
