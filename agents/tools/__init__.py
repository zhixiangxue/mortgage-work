"""Tools the agents share.

An agent is a goal plus the means to pursue it. These are the means — kept out
of the agents so a capability is defined once and every agent that needs it gets
the same one, with the same boundaries.

Everything here is read-only and confined to the work repo. Writing is never a
tool: the agents that produce files have exactly one path they own, and their
own code puts the bytes there. A model that cannot write cannot write to the
wrong place.

Richer media rides Reader: a loan file arrives as whatever the borrower had to
hand — a Word letter, an Excel rent roll, a phone photo of a paystub, a zip
from an underwriter — and Reader (fyle underneath) turns any of it into
Markdown, with images transcribed through a vision model. PDFs stay with Pdf,
which navigates and reads them far better than a whole-file extraction.
"""
from .filesystem import FileSystem
from .git import Git
from .kg import KG
from .mem import Mem
from .pdf import Pdf
from .rag import RAG
from .reader import Reader

__all__ = ["FileSystem", "Git", "KG", "Mem", "Pdf", "RAG", "Reader"]
