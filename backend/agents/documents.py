import unicodedata

from engine.schema import EvidenceDoc

_BLANKS = frozenset({0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x2800, 0x3164, 0xFFA0})
_ESCAPES = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;"})


def invisible(ch: str) -> bool:
    cp = ord(ch)
    return (
        unicodedata.category(ch) == "Cf"
        or cp in _BLANKS
        or 0x180B <= cp <= 0x180F
        or 0xFE00 <= cp <= 0xFE0F
        or 0xE0000 <= cp <= 0xE0FFF
    )


def plain(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", text) if not invisible(ch))


def quote_document(doc: EvidenceDoc) -> str:
    quoted = plain(f"{doc.title}\n{doc.body}").translate(_ESCAPES)
    return f'<document id="{doc.id}" source="{doc.source}">\n{quoted}\n</document>'
