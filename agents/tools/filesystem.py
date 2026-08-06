"""chak's FileSystem, narrowed to a set of directories."""
from __future__ import annotations

from pathlib import Path

from chak.tools.std import FileSystem as _ChakFS

# Which tool owns a file read_file cannot decode. PDFs are Pdf's, everything
# else is Reader's — see tools/reader.py for why that split exists.
_PDF_HINT = ("use the pdf-* tools instead: pdf-metadata first, then "
             "pdf-search / pdf-read_pages (or pdf-read_all for a short one)")
_READER_HINT = ("use reader-read instead — it converts images (transcribed by a "
                "vision model), Word, Excel, PowerPoint, archives and other "
                "binary formats into Markdown")


class FileSystem(_ChakFS):
    """chak's FileSystem, restricted to the directories it is given.

    chak already has ``workdir`` and ``allowed_dirs`` — but ``workdir`` is both
    where relative paths are measured from *and* a granted root, and the
    constructor adds it to the allowed list. So the one arrangement wanted here
    cannot be expressed: paths written the way git reports them, repo-relative,
    while only two subtrees are actually readable. Passing the repo as workdir
    grants the repo; passing the client folder makes ``products/...`` unwritable
    as a path.

    Splitting the two settles it. The base is where paths are measured from and
    nothing more; the allowed set is what may be opened.
    """

    def __init__(self, *scope: str | Path, base: str | Path, mode: str = "r"):
        """Args: the folders that may be read, and the base for relative paths.

        ``base`` is named for what it does, not for a root the scope sits under —
        it need not: a scope folder outside ``base`` is readable by absolute path.
        It exists only because relative paths have to mean something, and the
        agents write theirs the way git reports them, repo-relative.

        An empty scope means everything under ``base``.
        """
        anchor = Path(base).resolve()
        allowed = [Path(s).resolve() for s in scope] or [anchor]
        super().__init__(workdir=str(anchor),
                         allowed_dirs=[str(d) for d in allowed], mode=mode)
        # The parent put the base in the allowed list, which would hand over the
        # whole tree these folders happen to share — the repo, when they are a
        # client and products/. Replacing it is the entire point of subclassing:
        # everything else, including the _resolve every method funnels through,
        # already does the right thing once _allowed says what it means.
        self._allowed = allowed

    def read_file(self, path: str, offset: int = 1, limit: int = 250) -> str:
        """Read a TEXT file and return its content with line numbers.

        Output format: "LINE_NUM→ line content" for every line returned.
        Use offset + limit to page through large files (max ~128K chars).

        Text only. For a PDF use the pdf-* tools; for an image, Word/Excel/
        PowerPoint document, archive or any other binary file use reader-read,
        which converts them to Markdown.

        Args:
            path:   File path (absolute or relative to workdir).
            offset: First line to return, 1-based (default 1).
            limit:  Maximum number of lines to return (default 250).

        Returns:
            Numbered file content, or an error string.
        """
        out = super().read_file(path, offset, limit)
        # chak answers a non-UTF-8 file with "Cannot read binary file", which is
        # true and useless: a model that reads it concludes the content is
        # unreachable and says so to the user — that is exactly how a dropped
        # paystub photo became "sorry, I can't view images". The bytes are
        # readable, just not by this tool, so the refusal carries the way on.
        if isinstance(out, str) and out.startswith("Error: Cannot read binary file"):
            is_pdf = Path(str(path)).suffix.lower() == ".pdf"
            return (f"Error: {Path(str(path)).name} is not a text file, so read_file "
                    f"cannot read it — {_PDF_HINT if is_pdf else _READER_HINT}.")
        return out
