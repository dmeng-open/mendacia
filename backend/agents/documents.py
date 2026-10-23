import re
import unicodedata

from engine.schema import EvidenceDoc

_DELIMITER = re.compile(r"<(?=\s*/?\s*document)", re.IGNORECASE)


def quote_document(doc: EvidenceDoc) -> str:
    text = "".join(ch for ch in f"{doc.title}\n{doc.body}" if unicodedata.category(ch) != "Cf")
    quoted = _DELIMITER.sub("&lt;", text)
    return f'<document id="{doc.id}" source="{doc.source}">\n{quoted}\n</document>'
