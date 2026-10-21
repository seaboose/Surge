"""Bounded, source-located import diagnostics; never include record values."""

from dataclasses import dataclass

MAX_ISSUES = 20


def label(value):
    """Keep untrusted names on one line, with explicit quoting and truncation."""
    text = str(value)
    return repr(text[:160] + ("…" if len(text) > 160 else ""))


@dataclass(frozen=True)
class ImportIssue:
    message: str
    record: int | None = None
    line: int | None = None
    column: int | None = None
    field: str | None = None

    def describe(self):
        location = []
        if self.record is not None:
            location.append(f"Record {self.record}")
        if self.line is not None:
            location.append(f"line {self.line}")
        if self.column is not None:
            location.append(f"column {self.column}")
        if self.field is not None:
            location.append(f"field {label(self.field)}")
        return " · ".join(location or ["File"]) + "\n" + self.message


class ImportFailure(ValueError):
    def __init__(self, source, issues, stopped=False):
        self.source = source
        self.issues = tuple(issues[:MAX_ISSUES])
        self.stopped = stopped
        super().__init__(self.describe())

    def describe(self):
        text = f"{label(self.source)} was not imported. No records were added.\n\n"
        text += "\n\n".join(issue.describe() for issue in self.issues)
        text += "\n\nLocations start at 1. Record numbers follow file order, not record IDs."
        text += "\nEach record shows its first problem; fixing it may reveal another."
        if self.stopped:
            text += "\nStopped after 20 problems; more may remain."
        text += "\nFix the listed problems and import the file again."
        return text


class FieldFailure(ValueError):
    def __init__(self, message, field=None):
        self.field = field
        super().__init__(message)
