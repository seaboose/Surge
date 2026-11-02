"""Literal case-insensitive matches mapped back to the original displayed text."""


def match_spans(text, query):
    needle = query.casefold()
    if not needle:
        return []
    folded = []
    positions = []
    for index, char in enumerate(text):
        part = char.casefold()
        folded.append(part)
        positions.extend([index] * len(part))
    haystack = "".join(folded)
    spans = []
    offset = 0
    while (found := haystack.find(needle, offset)) != -1:
        end = found + len(needle)
        span = (positions[found], positions[end - 1] + 1)
        # Case folding can expand one character (ß -> ss); count that character once.
        if not spans or span[0] >= spans[-1][1]:
            spans.append(span)
        offset = end
    return spans
