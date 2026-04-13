"""
Shared keyword extraction utility used by trend sources.
"""
import re

_STOP = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "are", "was", "were", "be", "been", "has", "have", "had",
    "it", "its", "by", "as", "with", "from", "that", "this", "but",
    "not", "what", "how", "who", "which", "will", "can", "may", "new",
    "says", "said", "after", "over", "more", "than", "up", "down",
}

_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def extract_keywords(text: str, limit: int = 15) -> list[str]:
    words = _WORD_RE.findall(text.lower())
    seen: set[str] = set()
    result = []
    for w in words:
        if w not in _STOP and w not in seen:
            seen.add(w)
            result.append(w)
    return result[:limit]
