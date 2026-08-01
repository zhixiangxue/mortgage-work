"""fyle behind one tool: any file in, LLM-ready Markdown out.

A loan file arrives as whatever the borrower had to hand — a Word letter of
explanation, an Excel rent roll, a phone photo of a paystub, a zip from an
underwriter. FileSystem reads text and Pdf reads PDFs; everything else used to
be a filename and no facts. fyle (a sibling local package, like chak) closes
that gap: 180+ formats to clean Markdown, 100% local.

Three of fyle's behaviours are wrong for this repo, and this wrapper exists
precisely to correct them:

*PDFs are refused.* fyle reads them, but chak's Pdf reads them far better —
metadata/search/read_pages navigation, complex-table vision rescue, form-field
awareness. Two PDF paths would mean the model picks the worse one at random,
so this tool answers ``.pdf`` with directions instead of content.

*Images are transcribed, not base64'd.* fyle hands an image back as a
``data:`` URL — honest, but a tool result is text in the context window, and
50KB of base64 is noise the model cannot see through. A vision model turns
the pixels into the words on them, which is the content a photographed W-2
actually carries. No vision model configured → an honest refusal, never a blob.

*Archives never unpack into the repo.* fyle extracts next to the archive as a
side effect, and next to the archive here means inside a client folder that
is committed and pushed. The archive is copied to a temp dir first, so the
extraction lands there; the temp dir joins the readable scope so the listed
files can be read by a follow-up call.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import tempfile
from pathlib import Path

import fyle

# Everything fyle routes to its image reader (fyle.accepts()["image"]).
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
# Everything fyle routes to its archive reader — the ones with the
# extract-next-to-the-file side effect this wrapper redirects to temp.
_ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2", ".txz"}
# Transcription lives behind fyle's [audio] / [video] extras (~90 MB of native
# wheels plus a Whisper download). Without them fyle raises; a loan officer's
# voicemail must not take a whole turn down, so those are answered in words.
_AV_EXTS = {".mp3", ".m4a", ".wav", ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm"}

# Inline data: URLs (docx/pptx/html embed images this way). The model can't
# read pixels out of base64 text; a placeholder says what was there instead
# of spending kilotokens saying nothing.
_DATA_URL_MD = re.compile(r"!\[([^\]]*)\]\(data:[^)]*\)")

_VISION_SYSTEM = (
    "You are a precise document transcriber. You are shown one image from a "
    "mortgage loan file — usually a photographed or scanned document such as a "
    "paystub, W-2, bank statement, ID, or letter."
)
_VISION_USER = (
    "Transcribe this image faithfully as Markdown. Capture every legible value "
    "with its label; use pipe tables for tabular regions. Mark anything "
    "unreadable as [illegible] — never guess a number. If the image is not a "
    "document, describe concretely what it shows instead."
)

_UNSET = object()


class Reader:
    """Read-only, confined to the directories it is given — same boundary
    contract as tools/pdf.py, same reasons. The class name is the tool prefix:
    the model sees ``reader-read``.
    """

    def __init__(self, *scope: str | Path, base: str | Path,
                 vision: str | None = None, vision_api_key: str | None = None):
        """Args: the folders files may be read from, the base for relative
        paths, and the vision model that turns images into text.

        ``vision`` is a chak model URI (e.g. ``openai/gpt-4o``) — the agents
        pass the model they already run on. Absent or broken, image reads
        degrade to a refusal instead of failing the tool call.
        """
        self._base = Path(base).resolve()
        self._allowed = [Path(s).resolve() for s in scope] or [self._base]
        self._vision = vision
        self._vision_api_key = vision_api_key
        self._vision_cache = _UNSET  # resolved provider, or None once tried

    def __available__(self) -> frozenset[str]:
        return frozenset({"read"})

    def _check(self, source: str) -> Path:
        """The one gate — a path inside an allowed directory, or a refusal."""
        src = str(source)
        if src.startswith(("http://", "https://")):
            raise PermissionError(f"'{src}' is remote; only local files can be read.")
        p = Path(src).expanduser()
        found = (p if p.is_absolute() else self._base / p).resolve()
        if not any(found.is_relative_to(d) for d in self._allowed):
            readable = ", ".join(str(d) for d in self._allowed)
            raise PermissionError(
                f"'{source}' is not a readable file. Readable: {readable} "
                f"(relative paths resolve against {self._base})"
            )
        if not found.is_file():
            raise FileNotFoundError(f"no such file: {source}")
        return found

    def read(self, source: str, max_chars: int | None = None) -> str:
        """Read any non-PDF file as clean Markdown: Word, Excel, PowerPoint,
        CSV, HTML, images, archives, and 150+ text/code/config formats.

        Args:
            source: File path, relative to the working directory (or absolute).
            max_chars: Optional cap on the returned Markdown; content beyond
                it is cut with an explicit truncation note.

        Returns:
            Markdown — a short header (filename, format, size), then the
            content. Images come back transcribed by a vision model. Archives
            are unpacked to a temporary folder and return a manifest; pass a
            listed path back to this tool to read an extracted file. For PDFs
            use the pdf-* tools instead (metadata first, then read_pages).
        """
        path = self._check(source)
        ext = path.suffix.lower()

        # PDF: refuse with directions. Guidance the model can follow beats a
        # second-rate extraction it would trust.
        if ext == ".pdf" or _head(path).startswith(b"%PDF-"):
            return (f"{path.name} is a PDF — this tool does not read PDFs. "
                    f"Use the pdf-* tools: pdf-metadata first, then pdf-search / "
                    f"pdf-read_pages (or pdf-read_all for short documents).")

        if ext in _IMAGE_EXTS:
            return self._read_image(path)
        if ext in _ARCHIVE_EXTS:
            return self._read_archive(path)

        if ext in _AV_EXTS:
            return self._read_av(path)

        doc = fyle.open(path)
        text = _DATA_URL_MD.sub(r"[embedded image: \1 — not extracted]", str(doc))
        return _truncate(text, max_chars)

    # ── images: pixels → words ──

    def _read_image(self, path: Path) -> str:
        provider = self._vision_provider()
        size_kb = path.stat().st_size // 1024
        if provider is None:
            return (f"{path.name} is an image ({size_kb} KB) and no vision model is "
                    f"available to read it — report to the user that this file's "
                    f"content could not be read, rather than guessing at it.")
        mime = "image/png" if path.suffix.lower() == ".png" else \
               "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
        data_uri = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

        from chak.message import HumanMessage, SystemMessage  # noqa: PLC0415
        try:
            resp = provider.send(messages=[
                SystemMessage(content=_VISION_SYSTEM),
                HumanMessage(content=[
                    {"type": "text", "text": _VISION_USER},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ]),
            ], stream=False)
            text = (getattr(resp, "content", "") or "").strip()
        except Exception as error:  # noqa: BLE001 — degrade, never fail the call
            return (f"{path.name} is an image ({size_kb} KB); the vision model "
                    f"failed to read it ({error}). Tell the user this file could "
                    f"not be read rather than guessing.")
        return (f"[{path.name}: image, transcribed from the pixels by a vision "
                f"model. Values below are what the model could read; treat "
                f"[illegible] as unknown, not zero.]\n\n{_strip_fences(text)}")

    def _vision_provider(self):
        """Resolve once, cache forever — including the None of a failed setup.
        Mirrors chak Pdf's own vision plumbing (its provider cache is private,
        so this stays a parallel four-liner rather than a reach-in)."""
        if self._vision_cache is not _UNSET:
            return self._vision_cache
        provider = None
        if self._vision:
            try:
                from chak.providers import create_provider  # noqa: PLC0415
                from chak.providers.types import ProviderCategory  # noqa: PLC0415
                from chak.utils.uri import parse as parse_uri  # noqa: PLC0415
                parsed = parse_uri(self._vision)
                key = self._vision_api_key or os.getenv(f"{parsed['provider'].upper()}_API_KEY")
                if key:
                    config = {"api_key": key, "model": parsed["model"]}
                    if parsed.get("base_url"):
                        config["base_url"] = parsed["base_url"]
                    provider = create_provider(parsed["provider"], config, ProviderCategory.LLM)
            except Exception:  # noqa: BLE001 — no vision beats no tool
                provider = None
        self._vision_cache = provider
        return provider

    # ── audio / video: transcription, or an honest "not installed" ──

    def _read_av(self, path: Path) -> str:
        """Transcribe locally when the extra is present, say so plainly when not.

        The missing-extra case is a deployment fact, not a bad file: raising
        would surface as a failed tool call the model retries, where a sentence
        it can read ends the matter and reaches the user intact.
        """
        size_kb = path.stat().st_size // 1024
        try:
            return str(fyle.open(path))
        except Exception as error:  # noqa: BLE001 — fyle raises ParseError here
            note = str(error)
            if "faster-whisper" in note or "optional extra" in note:
                return (f"{path.name} is a recording ({size_kb} KB) and local "
                        f"transcription is not installed on this machine, so its "
                        f"content cannot be read. Tell the user the recording "
                        f"could not be transcribed — do not guess at what it says.")
            return (f"{path.name} could not be transcribed ({note}). Report that "
                    f"to the user rather than guessing at the content.")

    # ── archives: extraction redirected out of the repo ──

    def _read_archive(self, path: Path) -> str:
        # Copy first: fyle extracts to a sibling of the archive, and the
        # archive's real siblings are a client's committed documents.
        tmp = Path(tempfile.mkdtemp(prefix="mw-archive-"))
        staged = tmp / path.name
        shutil.copy2(path, staged)
        doc = fyle.open(staged)
        # The extraction landed under tmp; make it readable so the manifest's
        # paths work when the model passes one back.
        self._allowed.append(tmp)
        return (str(doc) + "\n\nRead any listed file by passing "
                "'<the Extracted to: folder>/<path>' back to this tool.")


def _strip_fences(text: str) -> str:
    """Drop a ```-fence wrapped around a whole transcription.

    Models fence Markdown even when asked for Markdown. Left in, the fence
    turns a table the next reader could parse into a literal code block.
    """
    lines = text.strip().splitlines()
    while lines and lines[0].strip().startswith("```"):
        lines.pop(0)
    while lines and lines[-1].strip().startswith("```"):
        lines.pop()
    return "\n".join(lines).strip()


def _head(path: Path, n: int = 8) -> bytes:
    try:
        with path.open("rb") as fh:
            return fh.read(n)
    except OSError:
        return b""


def _truncate(text: str, max_chars: int | None) -> str:
    if max_chars is None or max_chars <= 0 or len(text) <= max_chars:
        return text
    return (text[:max_chars]
            + f"\n\n[truncated at {max_chars} chars of {len(text)} — call again "
              f"with a larger max_chars for the rest]")
