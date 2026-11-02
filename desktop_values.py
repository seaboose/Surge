"""Exact display values and bounded navigation shared by desktop views."""

from array import array
import json

import record_search


def display(value):
    # Keep exact Python integers and JSON scalar types out of JavaScript numbers.
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def compact_spans(text, query):
    """Cache code-point offsets as packed integers, not Python tuple objects."""
    return array(
        "I", (offset for span in record_search.match_spans(text, query) for offset in span)
    )


def step_row(rows, row, step):
    """Select the next or previous row within the caller's ordered scope."""
    if step not in (-1, 1):
        raise ValueError("Invalid direction.")
    candidates = [r for r in rows if r > row] if step == 1 else [r for r in rows if r < row]
    return (candidates[0] if step == 1 else candidates[-1]) if candidates else None


def bounded_int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Position is outside the available range.")
    return value


def bounded_text(value, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("Search text is too long.")
    return value
