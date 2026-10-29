"""Peak-preserving chart geometry and record identity, independent of Tk."""

from dataclasses import dataclass, replace

BASE_Y = 82


@dataclass(frozen=True)
class Point:
    row: int
    field: str
    score: float
    x: int
    y: float
    count: int = 1


def x_for_row(row, count, width):
    return 58 + round((row - 1) * max(width - 80, 1) / max(count - 1, 1))


def signal(record):
    return max(record["scores"], key=record["scores"].get) if record["scores"] else None


def points(records, width, threshold):
    buckets = {}
    for record in records:
        field = signal(record)
        if field is None:
            continue  # Missing data is never drawn as a zero.
        score = record["scores"][field]
        x = x_for_row(record["row"], len(records), width)
        point = Point(record["row"], field, score, x, BASE_Y - min(score / threshold, 2) * 28)
        old = buckets.get(x)
        if old:
            # Compare uncapped scores, so two tall peaks do not become false ties.
            point = replace(point if score > old.score else old, count=old.count + 1)
        buckets[x] = point
    return list(buckets.values())


def hit(points, x, y, radius=6):
    """Choose only a nearby point/bar, never a label or arbitrary empty space."""
    if y < 20 or y > BASE_Y + radius:
        return None
    candidates = []
    for point in points:
        dy = max(point.y - y, y - BASE_Y, 0)
        distance = (point.x - x) ** 2 + dy**2
        if distance <= radius**2:
            candidates.append((distance, abs(point.y - y), point.row, point))
    return min(candidates, key=lambda value: value[:3])[3] if candidates else None
