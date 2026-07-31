"""chak's FileSystem, narrowed to a set of directories."""
from __future__ import annotations

from pathlib import Path

from chak.tools.std import FileSystem as _ChakFS


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
