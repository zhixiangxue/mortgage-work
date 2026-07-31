"""Tools the agents share.

An agent is a goal plus the means to pursue it. These are the means — kept out
of the agents so a capability is defined once and every agent that needs it gets
the same one, with the same boundaries.

Everything here is read-only and confined to the work repo. Writing is never a
tool: the agents that produce files have exactly one path they own, and their
own code puts the bytes there. A model that cannot write cannot write to the
wrong place.

TODO: richer media. A loan file arrives as whatever the borrower had to hand —
scans, phone photos of a paystub, a voicemail, a recorded call. PDF text
extraction covers the documents that were born digital and nothing else. The
gap is real: a photographed W-2 is currently a filename and no facts.
"""
from .filesystem import FileSystem
from .git import Git
from .pdf import Pdf

__all__ = ["FileSystem", "Git", "Pdf"]
