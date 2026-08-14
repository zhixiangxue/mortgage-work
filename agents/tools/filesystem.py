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

# Write landing policy (rw mode only): where an interactive agent may create
# or update files.  Client data belongs under clients/<slug>/<subdir>/ — the
# client folder root itself holds client.yaml and README.md only — guidelines
# under products/, and .chak/ + .tmp/ are scratch space.  A model with a free
# hand drops updates at the repo root or into stray top-level folders, which
# is exactly the failure this policy exists to catch: rejected writes return
# a steering hint so the agent self-corrects within the same turn.
_SCRATCH_TOPS = frozenset({".chak", ".tmp"})
_CLIENT_ROOT_FILES = frozenset({"client.yaml", "README.md", "readme.md"})

_ROOT_WRITE_ERROR = (
    "Error: refusing to write outside the client/guideline folders. "
    "Client files belong under clients/<client-id>/<subdir>/ — unstructured "
    "notes and updates go to clients/<client-id>/notes/. Guideline documents "
    "go under products/. Run filesystem-list_dir on clients/ to find the "
    "right folder."
)


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

    In ``rw`` mode the class also enforces a write landing policy: files may
    only be created or updated under a client folder, products/, or scratch
    space (see _landing_error).  Only the interactive QAAgent runs this class
    in rw mode; clerk and the sub-agents use mode="r", where the policy never
    fires.
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
        self._anchor = anchor
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

    def _landing_error(self, path: str) -> str | None:
        """Return a steering error if a write would land outside the landing
        zones, else None.  Read methods are never gated — only writes."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self._anchor / p
        try:
            fp = p.resolve()
            rel = fp.relative_to(self._anchor)
        except (OSError, ValueError):
            # Unresolvable or out of scope — the parent's _resolve already
            # raises PermissionError for those, so don't double-report.
            return None
        parts = rel.parts
        if not parts:
            return _ROOT_WRITE_ERROR
        top = parts[0]
        if top == "clients":
            if len(parts) < 3:
                # clients/ itself or a stray file under it — no client folder.
                return _ROOT_WRITE_ERROR + " Write inside a specific client folder instead."
            if (len(parts) == 3 and not fp.exists()
                    and parts[2] not in _CLIENT_ROOT_FILES):
                return (
                    f"Error: clients/{parts[1]}/ is the client folder root — "
                    f"it holds client.yaml and README.md only. Put new files "
                    f"in a subdirectory instead: clients/{parts[1]}/notes/ "
                    f"for unstructured notes and updates."
                )
            return None
        if top == "products" or top in _SCRATCH_TOPS:
            return None
        return _ROOT_WRITE_ERROR

    def write_file(self, path: str, content: str = "") -> str:
        err = self._landing_error(path)
        return err if err else super().write_file(path, content)

    def create_file(self, path: str, content: str = "") -> str:
        err = self._landing_error(path)
        return err if err else super().create_file(path, content)

    def edit_file(self, path: str, old_text: str, new_text: str,
                  replace_all: bool = False) -> str:
        err = self._landing_error(path)
        return err if err else super().edit_file(path, old_text, new_text,
                                                 replace_all)

    def move(self, src: str, dst: str) -> str:
        # Gate the destination, not the source: moving a misplaced file into
        # a client folder is a legitimate way to fix an earlier mistake.
        err = self._landing_error(dst)
        return err if err else super().move(src, dst)
