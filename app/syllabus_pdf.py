"""Standalone worker for PDF extraction limits."""

from io import BytesIO
import json
import sys

from pypdf import PdfReader, apply_configuration


def _restrict_worker() -> None:
    try:
        import resource
    except ImportError:
        return
    for limit, maximum in ((resource.RLIMIT_CPU, 5), (resource.RLIMIT_AS, 384 * 1024 * 1024)):
        try:
            _, hard = resource.getrlimit(limit)
            cap = min(hard, maximum) if hard != resource.RLIM_INFINITY else maximum
            resource.setrlimit(limit, (cap, cap))
        except (ValueError, OSError):
            pass


def extract_pdf(data: bytes) -> dict:
    limit = 6 * 1024 * 1024
    with apply_configuration(
        maximum_declared_stream_length=limit,
        array_based_stream_maximum_output_length=limit,
        zlib_maximum_output_length=limit,
        lzw_maximum_output_length=limit,
        run_length_maximum_output_length=limit,
        jbig2_maximum_output_length=limit,
        brotli_maximum_output_length=limit,
        stream_decoding_work_maximum_length=limit * 3,
    ):
        reader = PdfReader(BytesIO(data), xref_stream_maximum_entries=100_000)
        if reader.is_encrypted:
            return {"error": "This PDF is password-protected. Upload an unlocked copy or a text file."}
        if len(reader.pages) > 60:
            return {"error": "Extracting deadlines is limited to 60 PDF pages."}
        pages = []
        total = 0
        for number, page in enumerate(reader.pages, start=1):
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > limit:
                return {"error": "A PDF page is too complex to extract. Try exporting the syllabus to text."}
            text = page.extract_text()
            total += len(text)
            if total > 250_000:
                return {"error": "The PDF has too much text. Try uploading the schedule pages only."}
            if text.strip():
                pages.append((number, text))
    if not pages:
        return {"error": "No selectable text was found. Export the syllabus to text or use an OCR-processed PDF."}
    return {"pages": pages}


if __name__ == "__main__":
    _restrict_worker()
    try:
        result = extract_pdf(sys.stdin.buffer.read(4 * 1024 * 1024 + 1))
    except Exception:
        result = {"error": "This PDF could not be read. Try exporting the syllabus to a fresh PDF or text file."}
    json.dump(result, sys.stdout)
