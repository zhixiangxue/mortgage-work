"""Local page-location helpers for RAG evidence.

This ports the production-tested locate algorithm from rag-service, but replaces
rag-service's DB/S3/PDF_FILES_DIR lookup with Mortgage Work's local docindex.
The authoritative files live in the managed work repo, so page location is a
local file operation used internally by RAG result formatting.
"""
from __future__ import annotations

import html
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Optional


def normalize_text(text: str) -> str:
    """Normalize text for fuzzy matching.

    Ported from zag.utils.page_inference.normalize_text used by rag-service.
    Removes HTML/Markdown formatting, normalizes Unicode, collapses whitespace,
    and preserves word spacing for robust fuzzy matching.
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fuzzy_find_start(
    signature: str,
    haystack: str,
    start_from: int = 0,
    threshold: float = 0.80,
    max_search_range: int | None = None,
) -> Optional[int]:
    """Find the start position of signature in haystack using fuzzy matching.

    Ported from zag.utils.page_inference.fuzzy_find_start. Strategy:
    1. exact quick signature match with verification;
    2. sliding-window fuzzy match on original text;
    3. sliding-window fuzzy match on normalized text.
    """
    if not signature or len(signature) < 10:
        return None

    haystack_len = len(haystack)
    search_end = haystack_len if max_search_range is None else min(haystack_len, start_from + max_search_range)

    quick_sig = signature[:min(50, len(signature))]
    if len(quick_sig) >= 10:
        pos = haystack.find(quick_sig, start_from)
        if pos != -1 and pos < search_end:
            end_pos = min(pos + len(signature), haystack_len)
            candidate = haystack[pos:end_pos]
            score = SequenceMatcher(None, signature, candidate).ratio()
            if score >= threshold:
                return pos

    best_pos = None
    best_score = threshold
    sig_len = len(signature)
    step = max(200, sig_len // 2)

    for pos in range(start_from, search_end, step):
        window_end = min(pos + sig_len * 2, haystack_len)
        window = haystack[pos:window_end]
        idx = window.find(quick_sig)
        if idx != -1:
            candidate = window[idx:idx + sig_len]
            score = SequenceMatcher(None, signature, candidate).ratio()
            if score > best_score:
                best_score = score
                best_pos = pos + idx
                if score > 0.95:
                    return best_pos

    if best_pos is not None:
        return best_pos

    norm_signature = normalize_text(signature)
    norm_sig_len = len(norm_signature)
    if norm_sig_len < 10:
        return None

    norm_quick_sig = norm_signature[:min(50, norm_sig_len)]
    best_pos = None
    best_score = threshold

    for pos in range(start_from, search_end, step):
        window_end = min(pos + sig_len * 3, haystack_len)
        window = haystack[pos:window_end]
        norm_window = normalize_text(window)
        idx = norm_window.find(norm_quick_sig)
        if idx == -1:
            continue
        compare_end = min(idx + norm_sig_len, len(norm_window))
        candidate = norm_window[idx:compare_end]
        score = SequenceMatcher(None, norm_signature, candidate).ratio()
        if score > best_score:
            best_score = score
            best_pos = pos
            if score > 0.95:
                break

    return best_pos


def _extract_pdf_text_and_positions(file_path: str):
    """Extract normalized text and page character positions from a local PDF.

    Ported from rag-service documents.py. Returns ``(full_text,
    page_positions)`` or None for scanned/unreadable PDFs.
    """
    try:
        import fitz

        doc = fitz.open(file_path)
        full_text = ""
        page_positions = []
        current = 0
        try:
            for page in doc:
                norm = normalize_text(page.get_text())
                page_start = current
                page_end = current + len(norm)
                page_positions.append((page_start, page_end, page.number + 1))
                full_text += ("\n" if full_text else "") + norm
                current = page_end + 1

                # Same scanned-PDF early bail-out as rag-service.
                if page.number == 2 and len(full_text) / 3 < 50:
                    return None
        finally:
            doc.close()

        return full_text, page_positions
    except Exception:
        return None


def _search_in_text(
    full_text: str,
    page_positions: list,
    text_start: str,
    text_end: str | None,
) -> tuple[list[int] | None, bool]:
    """Search for text_start/text_end inside pre-extracted full text.

    Ported from rag-service documents.py. Returns ``(page_numbers, found)``.
    """
    norm_start = normalize_text(text_start)
    norm_end = normalize_text(text_end) if text_end else None

    start_pos = fuzzy_find_start(norm_start, full_text, start_from=0, threshold=0.85)
    if start_pos is None:
        return None, False

    # Reject ambiguous matches: returning the first duplicate would likely be wrong.
    duplicate = fuzzy_find_start(
        norm_start,
        full_text,
        start_from=start_pos + 1,
        threshold=0.85,
    )
    if duplicate is not None:
        return None, False

    if norm_end:
        found_end = fuzzy_find_start(
            norm_end,
            full_text,
            start_from=start_pos + len(norm_start),
            threshold=0.85,
            max_search_range=100_000,
        )
        end_pos = (found_end + len(norm_end)) if found_end is not None else (start_pos + len(norm_start))
    else:
        end_pos = start_pos + len(norm_start)

    pages = sorted(
        pn for ps, pe, pn in page_positions
        if not (end_pos <= ps or start_pos >= pe)
    )
    if not pages:
        return [], False

    # Reject implausibly wide spans — likely a false-positive start match.
    if len(pages) > 10:
        return None, False

    return pages, True


def _ensure_docindex_loaded() -> None:
    try:
        import docindex
        if docindex.all_records():
            return
        from workrepo import local_repo_path
        docindex.init(local_repo_path())
    except Exception:
        return


def _paths_for_doc(doc_id: str) -> list[Path]:
    if not doc_id:
        return []
    try:
        import docindex
        _ensure_docindex_loaded()
        records = docindex.lookup(doc_id)
    except Exception:
        return []
    paths: list[Path] = []
    for rec in records:
        raw = rec.get("abs_path") or rec.get("path")
        if not raw:
            continue
        path = Path(str(raw))
        if path.is_file():
            paths.append(path)
    return paths


def _anchors_from_content(content: str) -> tuple[str, str | None]:
    """Build locate anchors from a RAG evidence chunk.

    The production endpoint receives text_start/text_end from callers. Here the
    caller is the RAG tool, so derive stable anchors from the chunk itself.
    """
    text = normalize_text(content)
    if len(text) <= 500:
        return text, None
    return text[:500], text[-300:]


def _htmlish_lines(content: str) -> list[str]:
    text = html.unescape(unicodedata.normalize("NFKC", content or ""))
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" |-•`\t")
        if len(line) >= 8:
            lines.append(line)
    return lines


def _phrase_candidates(content: str) -> list[str]:
    """Return stable short phrases for table-like RAG chunks.

    RAG table chunks often preserve logical row order, while PDF text extraction
    may emit table cells in a visual order. Whole-span matching can fail even
    though many individual cell values are present on the right page. This
    fallback keeps locate local and evidence-based without trusting service page
    metadata.
    """
    seen: set[str] = set()
    phrases: list[str] = []
    for line in _htmlish_lines(content):
        pieces = re.split(r"(?:\s+-\s+|[;。；])", line)
        for piece in pieces:
            phrase = normalize_text(piece)
            if not (10 <= len(phrase) <= 180):
                continue
            # Very short labels such as "Credit" are too ambiguous on matrices.
            if len(phrase.split()) < 2 and len(phrase) < 18:
                continue
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            phrases.append(phrase)
    return phrases[:80]


def _locate_by_page_phrase_score(full_text: str, page_positions: list, content: str) -> int:
    phrases = _phrase_candidates(content)
    if not phrases:
        return 0

    best_page = 0
    best_score = 0
    second_score = 0
    for page_start, page_end, page_num in page_positions:
        page_text = full_text[page_start:page_end]
        score = 0
        hits = 0
        for phrase in phrases:
            if phrase in page_text:
                score += len(phrase)
                hits += 1
                continue
            if len(phrase) >= 40 and fuzzy_find_start(phrase, page_text, threshold=0.88) is not None:
                score += len(phrase)
                hits += 1
        if hits >= 2 and score > best_score:
            second_score = best_score
            best_score = score
            best_page = int(page_num)
        elif score > second_score:
            second_score = score

    if best_score < 40:
        return 0
    if second_score and best_score < second_score * 1.2:
        return 0
    return best_page


@lru_cache(maxsize=256)
def _cached_pdf_entry(path_str: str, mtime_ns: int, size: int):
    # mtime_ns and size are part of the cache key so edits invalidate entries.
    return _extract_pdf_text_and_positions(path_str)


def _pdf_entry(path: Path):
    try:
        stat = path.stat()
    except OSError:
        return None
    return _cached_pdf_entry(str(path), stat.st_mtime_ns, stat.st_size)


def locate_pdf_page(doc_id: str, content: str) -> int:
    """Return the first local PDF page containing a RAG evidence snippet.

    Uses the rag-service production locate algorithm against local work-repo
    PDFs resolved through docindex. Returns 0 when the page cannot be located;
    callers must treat 0 as "page unavailable", never fabricate a page.
    """
    text_start, text_end = _anchors_from_content(content)
    if not text_start or len(text_start.strip()) < 10:
        return 0

    for path in _paths_for_doc(doc_id):
        if path.suffix.lower() != ".pdf":
            continue
        entry = _pdf_entry(path)
        if entry is None:
            continue
        full_text, page_positions = entry
        pages, found = _search_in_text(full_text, page_positions, text_start, text_end)
        if found and pages:
            return int(pages[0])
        page = _locate_by_page_phrase_score(full_text, page_positions, content)
        if page:
            return page
    return 0
