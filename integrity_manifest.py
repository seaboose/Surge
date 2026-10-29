"""Validate versioned coverage declarations; fingerprints do not authenticate them."""

import re

SCHEMA = "surge-integrity-manifest-v1"
FIELDS = {
    "schema",
    "architecture",
    "descriptor_version",
    "module_sha256",
    "module_size",
    "image_size",
    "relocation_policy",
    "executable_bytes",
    "checked_bytes",
    "excluded_bytes",
    "ranges",
    "executable_ranges",
    "exclusions",
}


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid integrity manifest dimension.")
    return value


def spans(entries, image_size, maximum, excluded=False):
    if not isinstance(entries, list) or len(entries) > maximum:
        raise ValueError("Integrity manifest span count exceeds its bound.")
    result = []
    keys = {"range_rva", "range_size"} | ({"reason"} if excluded else set())
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != keys:
            raise ValueError("Malformed integrity manifest span.")
        begin = integer(entry["range_rva"], 1, image_size - 1)
        size = integer(entry["range_size"], 1, image_size)
        if begin + size > image_size:
            raise ValueError("Integrity manifest span exceeds the image.")
        if excluded and entry["reason"] not in ("not_declared", "loader_fixup"):
            raise ValueError("Unsupported integrity exclusion reason.")
        result.append((begin, begin + size))
    ordered = sorted(result)
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Integrity manifest spans overlap.")
    return ordered


def validate(value, ranges=None, module_sha256=None, module_size=None):
    # Import here to share the established byte/range validator without an import cycle.
    from native_integrity import validate_manifest

    if not isinstance(value, dict) or set(value) != FIELDS or value.get("schema") != SCHEMA:
        raise ValueError("Unsupported integrity manifest.")
    if (
        value["architecture"] != "x64"
        or type(value["descriptor_version"]) is not int
        or value["descriptor_version"] != 1
        or value["relocation_policy"] != "reject"
        or not isinstance(value["module_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["module_sha256"])
    ):
        raise ValueError("Unsupported integrity architecture, version or relocation policy.")
    integer(value["module_size"], 1, 64 * 1024 * 1024)
    if module_size is not None:
        integer(module_size, 1, 64 * 1024 * 1024)
    size = integer(value["image_size"], 1, 512 * 1024 * 1024)
    declared = validate_manifest(value["ranges"])
    if (
        (ranges is not None and declared != ranges)
        or (module_sha256 is not None and value["module_sha256"] != module_sha256)
        or (module_size is not None and value["module_size"] != module_size)
    ):
        raise ValueError("Integrity manifest differs from the captured build or ranges.")
    checked = spans(
        [{k: r[k] for k in ("range_rva", "range_size")} for r in declared], size, 16
    )
    executable = spans(value["executable_ranges"], size, 32)
    excluded = spans(value["exclusions"], size, 128, excluded=True)
    if not executable:
        raise ValueError("Integrity manifest needs executable file-backed spans.")
    # Walk the partition, not merely the totals: holes, overlaps and padding outside
    # executable spans must not inflate the reported coverage.
    partition = sorted(checked + excluded)
    position = 0
    for begin, end in executable:
        cursor = begin
        while position < len(partition) and partition[position][0] < end:
            left, right = partition[position]
            if left != cursor or right > end:
                raise ValueError(
                    "Checked and excluded bytes do not partition executable spans."
                )
            cursor = right
            position += 1
        if cursor != end:
            raise ValueError("Integrity manifest leaves executable bytes unaccounted for.")
    if position != len(partition):
        raise ValueError("Integrity manifest declares bytes outside executable spans.")
    for field, parts in (
        ("executable_bytes", executable),
        ("checked_bytes", checked),
        ("excluded_bytes", excluded),
    ):
        if integer(value[field], 0, size) != sum(end - begin for begin, end in parts):
            raise ValueError("Integrity manifest byte totals differ from its spans.")
    return value


def describe(value):
    """Short evidence details after validation, without claiming whole-image coverage."""
    validate(value)
    reasons = {"not_declared": "outside declared checks", "loader_fixup": "loader fixups"}
    totals = {}
    for excluded in value["exclusions"]:
        reason = reasons[excluded["reason"]]
        totals[reason] = totals.get(reason, 0) + excluded["range_size"]
    exclusions = "; ".join(
        f"{count} bytes {reason}" for reason, count in sorted(totals.items())
    )
    return (
        f"{value['checked_bytes']}/{value['executable_bytes']} executable file-backed bytes in scope; "
        f"{value['excluded_bytes']} excluded. This is declared scope, not whole-DLL verification.\n"
        f"Excluded: {exclusions or 'none'}.\n"
        "x64 manifest v1; checked ranges with loader fixups are unsupported."
    )
