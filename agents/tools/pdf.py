"""chak's Pdf, confined to a set of directories."""
from __future__ import annotations

import functools
import json
from pathlib import Path

from chak.tools.std import Pdf as _ChakPdf

import docindex


def _ensure_docindex_loaded() -> None:
    """Load docindex on first use here if nothing else in this process already
    has (agent_service.py's pill scoping and app.py's citation resolver do the
    same lazy load — a plain question with no attached pill may reach this
    tool before either of those runs).
    """
    if docindex.all_records():
        return
    from workrepo import local_repo_path
    try:
        docindex.init(local_repo_path())
    except Exception:
        pass


class Pdf(_ChakPdf):
    """chak's Pdf, read-only and confined to the directories it is given.

    chak's FileSystem has ``workdir`` and ``allowed_dirs``; its Pdf has neither —
    it takes a path and reads it wherever it is, and an ``http(s)`` source is
    fetched over the network. That gap matters here because this repo is
    committed and pushed: a figure lifted out of a PDF elsewhere on the disk
    becomes a line in a client's profile and leaves the machine.

    A scope of several directories rather than one root, because the real unit of
    work needs exactly two: the client's own folder, and ``products/`` for the
    guideline that says whether their numbers qualify. A single root can express
    only one of those, and the root that contains both is the whole repo — which
    hands over every other borrower's documents to answer a question about one.

    Only the boundary is added. Every method is wrapped at the bottom of this
    module from whatever chak exposes, so nothing is enumerated by hand and a
    method added upstream arrives already confined.

    The class name is deliberate: NativeObjectTool prefixes tool names with the
    lowercased class name, so the model still sees ``pdf-*``.
    """

    def __init__(self, *scope: str | Path, base: str | Path,
                 mode: str = "r"):
        """Args: the folders documents may be read from, and the base for
        relative paths.

        Two independent settings, which is why ``base`` is named for what it does
        rather than for a root the scope sits under — it need not: a scope folder
        outside ``base`` is perfectly readable, by absolute path. ``base`` only
        answers "what does a relative path mean", and it exists because the
        agents get their paths from git, which reports them repo-relative.

        One base, not one per scope folder. Trying each in turn would accept more
        of what a model writes, but a path that resolves under two of them
        silently means whichever was tried first — ask for ``README.md``, get the
        client's copy instead of the repo's. A refusal the model can read and
        correct beats a document it read and believed.

        An empty scope means everything under ``base``.

        ``mode`` is passed through to chak's Pdf: ``"r"`` (default) hides
        ``schema``/``fill``; ``"rw"`` exposes them for form-filling agents.
        Either way ``_check`` blocks remote URLs and confines paths to the
        scope.
        """
        super().__init__(mode=mode)
        self._base = Path(base).resolve()
        self._allowed = [Path(s).resolve() for s in scope] or [self._base]

    def _check(self, source: str) -> str:
        """The one gate. Returns a path inside an allowed directory, or raises."""
        src = str(source)
        if src.startswith(("http://", "https://")):
            raise PermissionError(f"'{src}' is remote; only local files can be read.")

        # Relative against the one base; absolute taken as given. Either way the
        # result has to land inside the scope, which is the only question asked.
        p = Path(src).expanduser()
        found = (p if p.is_absolute() else self._base / p).resolve()

        if not any(found.is_relative_to(d) for d in self._allowed):
            readable = ", ".join(str(d) for d in self._allowed)
            raise PermissionError(
                f"'{source}' is not a readable document. Readable: {readable} "
                f"(relative paths resolve against {self._base})"
            )
        return str(found)

    @functools.wraps(_ChakPdf.render_page)
    def render_page(self, source: str, page: int, dpi: int | None = None,
                    output_path: str | None = None) -> str:
        # output_path is dropped rather than confined. Confining it would leave
        # the client's own folder as a legal target — and that folder is
        # committed and pushed, so an honoured path means PNGs littered into
        # someone's loan file. chak's default puts the render in a temp dir,
        # which is where a throwaway image belongs.
        return _ChakPdf.render_page(self, self._check(source), page, dpi, None)

    @functools.wraps(_ChakPdf.search)
    def search(self, source: str, query: str, max_results: int = 20,
               context_chars: int = 220) -> str:
        # A direct read never touches the RAG tool, so nothing upstream ever
        # attaches a doc_id — yet the system prompt still requires a citation
        # for every eligibility claim. Without a real one here the model is
        # left to invent one to satisfy that rule, which is exactly what
        # produced a citation the UI could not resolve. search's own page
        # number is already the real PDF physical page (no locate.py
        # guesswork needed); only the doc_id half was missing.
        local_path = self._check(source)
        raw = _ChakPdf.search(self, local_path, query, max_results, context_chars)
        return self._with_match_citations(local_path, raw)

    # Additive, not a replacement — search.__doc__ above was just set to
    # chak's own docstring by functools.wraps, so this describes only what
    # this file adds on top of it.
    search.__doc__ = (search.__doc__ or "") + (
        "\n\nWhen a result includes a \"citation\" field, it is a ready "
        "mai://<doc_id>/<page> link for that exact match — copy it verbatim "
        "as the citation for any claim sourced from that result. If a result "
        "has no \"citation\" field, do not invent one; state the finding "
        "without a citation link."
    )

    @functools.wraps(_ChakPdf.read_pages)
    def read_pages(self, source: str, start_page: int, end_page: int,
                   format: str = "markdown", max_chars: int | None = None) -> str:
        # Same gap as search, over a page range instead of a single match —
        # the model reads full page content here (this was the actual source
        # of the terminal-83..96 "no citation" report: search found nothing
        # conclusive, then a read_pages call is what the answer was really
        # grounded in), so it needs the same per-page citation the model can
        # copy verbatim instead of inventing.
        local_path = self._check(source)
        raw = _ChakPdf.read_pages(self, local_path, start_page, end_page, format, max_chars)
        return self._with_page_citations(local_path, raw, format)

    read_pages.__doc__ = (read_pages.__doc__ or "") + (
        "\n\nEach page comes with a ready mai://<doc_id>/<page> citation — see "
        "the \"citation\" field per page (json format) or the trailing "
        "\"Page citations:\" list (other formats). Copy the link for whichever "
        "page a claim actually came from; do not invent one."
    )

    @functools.wraps(_ChakPdf.schema)
    def schema(self, source: str) -> str:
        # Confined identically to the read methods — the source PDF must be a
        # local file inside the scope, never a URL.
        return _ChakPdf.schema(self, self._check(source))

    @functools.wraps(_ChakPdf.fill)
    def fill(self, source: str, data, output_path: str | None = None) -> str:
        # Both the input form and the output path must be local files inside
        # the scope.  _check blocks URLs and confines paths, so the filler can
        # never exfiltrate data to a remote endpoint or write outside the root.
        src = self._check(source)
        out = self._check(output_path) if output_path else output_path
        return _ChakPdf.fill(self, src, data, out)

    @functools.wraps(_ChakPdf.read_all)
    def read_all(self, source: str, format: str = "markdown",
                 max_chars: int | None = None) -> str:
        local_path = self._check(source)
        raw = _ChakPdf.read_all(self, local_path, format, max_chars)
        return self._with_page_citations(local_path, raw, format)

    read_all.__doc__ = (read_all.__doc__ or "") + (
        "\n\nEach page comes with a ready mai://<doc_id>/<page> citation in "
        "the trailing \"Page citations:\" list. Copy the link for whichever "
        "page a claim actually came from; do not invent one."
    )

    def _with_match_citations(self, local_path: str, raw: str) -> str:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return raw
        results = data.get("results")
        if not isinstance(results, list):
            return raw
        doc_id = self._doc_id_for(local_path)
        if not doc_id:
            return raw
        data["doc_id"] = doc_id
        for index, item in enumerate(results, start=1):
            page = item.get("page") if isinstance(item, dict) else None
            if page:
                item["citation"] = f"[[{index}]](mai://{doc_id}/{page})"
        return json.dumps(data, ensure_ascii=False)

    def _with_page_citations(self, local_path: str, raw: str, format: str) -> str:
        doc_id = self._doc_id_for(local_path)
        if not doc_id:
            return raw
        if format == "json":
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                return raw
            pages = data.get("pages")
            if not isinstance(pages, list):
                return raw
            data["doc_id"] = doc_id
            for item in pages:
                page = item.get("page") if isinstance(item, dict) else None
                if page:
                    item["citation"] = f"[[{page}]](mai://{doc_id}/{page})"
            return json.dumps(data, ensure_ascii=False)

        # Text formats: chak's own header is one pretty-printed JSON block,
        # separated from the page content by a blank line — see
        # chak/tools/std/pdf.py::read_pages/read_all.
        header_str, sep, content = raw.partition("\n\n")
        if not sep:
            return raw
        try:
            header = json.loads(header_str)
        except (TypeError, ValueError):
            return raw
        page_range = self._page_range_from_header(header)
        if not page_range:
            return raw
        start, end = page_range
        header["doc_id"] = doc_id
        citations = "\n".join(
            f"Page {p}: [[{p}]](mai://{doc_id}/{p})" for p in range(start, end + 1)
        )
        return (
            f"{json.dumps(header, ensure_ascii=False, indent=2)}\n\n{content}"
            f"\n\nPage citations:\n{citations}"
        )

    @staticmethod
    def _page_range_from_header(header: dict) -> tuple[int, int] | None:
        """read_pages headers carry start_page/end_page; read_all's carries
        only a total page count under "pages" — normalize both to a range."""
        start, end = header.get("start_page"), header.get("end_page")
        if not (isinstance(start, int) and isinstance(end, int)):
            total = header.get("pages")
            if not isinstance(total, int) or total < 1:
                return None
            start, end = 1, total
        if start > end:
            return None
        return start, end

    def _doc_id_for(self, local_path: str) -> str | None:
        """Resolve an already-confined absolute path back to its doc_id via
        docindex — the same identity RAG citations and the frontend's
        citation-link resolver use, so a link built here opens the same way.

        Every current caller passes ``base=`` the repo root (see agents/qa.py,
        agents/clerk.py), which is what docindex indexes
        against — so ``self._base`` is the right anchor for the repo-relative
        path docindex expects.
        """
        try:
            repo_rel = Path(local_path).resolve().relative_to(self._base).as_posix()
        except ValueError:
            return None
        _ensure_docindex_loaded()
        rec = docindex.lookup_path(repo_rel)
        return rec.get("doc_id") if rec else None


def _confined(name: str):
    """Wrap one parent method so its source argument passes through _check.

    ``functools.wraps`` carries the parent's docstring and signature over, which
    is what the tool schema is built from — so the model sees chak's own
    documentation rather than a copy of it that drifts.
    """
    parent = getattr(_ChakPdf, name)

    @functools.wraps(parent)
    def guard(self, source: str, *args, **kwargs):
        return parent(self, self._check(source), *args, **kwargs)

    return guard


# Take the method list from chak instead of writing it out here: a hand-kept
# list is a list that goes stale, and a method that slips past _check is not a
# lesser bug for being an omission.
# Wrap every method chak's Pdf can expose (both read-only and read-write
# modes) so a method that slips past _check is never an omission.  Methods
# already overridden explicitly above (schema, fill, read_pages, etc.) are
# skipped; the rest get the generic _confined guard.
for _name in _ChakPdf(mode="rw").__available__():
    if _name not in Pdf.__dict__:
        setattr(Pdf, _name, _confined(_name))
