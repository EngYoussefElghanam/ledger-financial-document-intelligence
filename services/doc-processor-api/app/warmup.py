"""
warmup.py

Run once, at Docker BUILD time (see Dockerfile). Forces docling AND its
underlying RapidOCR engine to download and cache every model they need,
so a real container's first request doesn't have to.

IMPORTANT: just instantiating DocumentConverter() is NOT enough — RapidOCR
downloads its actual model weights (.pth files) lazily, on first real use,
not at construction time. This was confirmed the hard way: a fresh
container's first /process request triggered live downloads mid-request
instead of using pre-cached weights. So this script runs a real, tiny
conversion to force every lazy download to happen now, during the build.

Not part of the running service - never imported by app/.
"""

from pathlib import Path

from docling.document_converter import DocumentConverter

# A minimal, self-contained one-page PDF, generated inline so this script
# has no dependency on any file existing in the build context.
_MINIMAL_PDF_BYTES = (
    b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>"
    b"/MediaBox[0 0 200 100]/Contents 5 0 R>>endobj\n"
    b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"5 0 obj<</Length 44>>stream\nBT /F1 12 Tf 10 50 Td (Warmup test) Tj ET\nendstream endobj\n"
    b"xref\n0 6\n0000000000 65535 f \n"
    b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF"
)


def main() -> None:
    print("Warming up docling + RapidOCR: forcing all model downloads...")

    warmup_pdf = Path("/tmp/warmup.pdf")
    warmup_pdf.write_bytes(_MINIMAL_PDF_BYTES)

    converter = DocumentConverter()
    # The actual .convert() call is what triggers RapidOCR's lazy model
    # downloads - construction alone does not.
    converter.convert(str(warmup_pdf))

    warmup_pdf.unlink()
    print("All models downloaded and cached into the image.")


if __name__ == "__main__":
    main()