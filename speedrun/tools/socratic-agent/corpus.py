"""Parses speedrun/ai/source_material.md into retrievable chunks.

Reuses the exact same corpus ai-cardgen already cites chunk IDs from
(kc-01..kc-14) - this agent's "traces to a named source" claim points at
the same provenance chain, not a new one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SOURCE_PATH = Path(__file__).parent.parent.parent / "ai" / "source_material.md"

CHUNK_HEADER_RE = re.compile(r"^## (kc-\d+): (.+)$", re.MULTILINE)


@dataclass
class Chunk:
    chunk_id: str
    title: str
    text: str


def load_chunks() -> list[Chunk]:
    raw = SOURCE_PATH.read_text(encoding="utf-8")
    headers = list(CHUNK_HEADER_RE.finditer(raw))
    chunks = []
    for i, match in enumerate(headers):
        chunk_id, title = match.group(1), match.group(2)
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(raw)
        text = raw[start:end].strip()
        chunks.append(Chunk(chunk_id=chunk_id, title=title, text=text))
    return chunks
