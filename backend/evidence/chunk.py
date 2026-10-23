import re
from dataclasses import dataclass

from engine.schema import EvidenceDoc, Id, Unlock

CHUNKER_VERSION = "chunk-1"
MAX_TOKENS = 500
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    document_id: Id
    ordinal: int
    title: str
    source: Id
    text: str
    unlocked_by: tuple[Id, ...]


def approx_tokens(text: str) -> int:
    return -(-len(text.split()) * 4 // 3)


def _pieces(paragraph: str) -> list[str]:
    if approx_tokens(paragraph) <= MAX_TOKENS:
        return [paragraph]
    step = MAX_TOKENS * 3 // 4
    out: list[str] = []
    for sentence in SENTENCE_END.split(paragraph):
        words = sentence.split()
        if approx_tokens(sentence) <= MAX_TOKENS:
            out.append(sentence)
        else:
            out += [" ".join(words[i : i + step]) for i in range(0, len(words), step)]
    return out


def chunk_document(doc: EvidenceDoc) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", doc.body) if p.strip()]
    packed: list[str] = []
    for piece in (q for p in paragraphs for q in _pieces(p)):
        if packed and approx_tokens(f"{packed[-1]}\n\n{piece}") <= MAX_TOKENS:
            packed[-1] = f"{packed[-1]}\n\n{piece}"
        else:
            packed.append(piece)
    unlocked_by = doc.visibility.unlocked_by if isinstance(doc.visibility, Unlock) else ()
    return [
        Chunk(doc.id, ordinal, doc.title, doc.source, text, unlocked_by)
        for ordinal, text in enumerate(packed or [""])
    ]
