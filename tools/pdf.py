"""chak's Pdf, confined to a set of directories."""
from __future__ import annotations

import functools
from pathlib import Path

from chak.tools.std import Pdf as _ChakPdf


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

    def __init__(self, *scope: str | Path, base: str | Path):
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
        """
        super().__init__(mode="r")
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
for _name in _ChakPdf(mode="r").__available__():
    if _name not in Pdf.__dict__:
        setattr(Pdf, _name, _confined(_name))
