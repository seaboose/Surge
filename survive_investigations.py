"""Versioned analyst narratives with immutable, source-bound evidence snapshots.

This module never writes recordings or changes detector inputs. Author names
are local, operator-supplied labels; hashes provide consistency, not attestation.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid

from survive_capture import LAB

SCHEMA = "survive-investigation-v1"
SECTIONS = ("question", "observations", "hypothesis", "conclusion", "next_steps")
MAX_REVISIONS = 256
MAX_EVIDENCE = 32
MAX_RECORDINGS = 8
MAX_DOCUMENT = 384 * 1024
MAX_HISTORY_BYTES = 16 * 1024 * 1024
MAX_INVESTIGATIONS = 256
ID = re.compile(r"^[a-f0-9]{32}$")
EVIDENCE_ID = re.compile(r"^E([1-9][0-9]?)$")
HASH = re.compile(r"^[a-f0-9]{64}$")
REVISION_FILE = re.compile(r"^([0-9]{4})\.json$")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _display_number(value):
    """Round report prose only; raw snapshots keep every recorded digit."""
    if type(value) not in (int, float) or not math.isfinite(value):
        return "Unavailable"
    return f"{value:.3f}"


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate investigation field")
        result[key] = value
    return result


def _json(raw):
    def reject(value):
        raise ValueError("Nonfinite investigation number")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=reject)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Investigation data is unreadable or truncated") from exc


def _identifier(value, label="investigation"):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid " + label + " identifier")
    return value


def _revision(value):
    if type(value) is not int or not 1 <= value <= MAX_REVISIONS:
        raise ValueError("Invalid investigation revision")
    return value


def _text(value, maximum, label, required=False):
    if (not isinstance(value, str) or len(value) > maximum or
            any(ord(c) < 32 and c not in "\n\t" for c in value) or
            any(0xD800 <= ord(c) <= 0xDFFF for c in value) or
            required and not value.strip()):
        raise ValueError(f"{label} must contain {'1–' if required else 'at most '}{maximum} readable characters")
    return value


def _directory(path, create=False):
    path = Path(path).absolute()
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if (part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400
                or not stat.S_ISDIR(info.st_mode)):
            raise ValueError("Investigation directories must be local directories without links")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise FileNotFoundError("Investigation directory is unavailable")
    return path.resolve()


def _read(path, limit=MAX_DOCUMENT):
    _directory(path.parent)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("Investigation evidence cannot follow file links")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("Investigation file changed while opening")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Investigation file exceeds its size bound")
    return raw


def _publish(folder, revision, value):
    """An exclusive hard-link publication cannot replace a winning revision."""
    folder = _directory(folder)
    raw = _encoded(value)
    if len(raw) > MAX_DOCUMENT:
        raise ValueError("Investigation exceeds its 384 KiB revision bound")
    history_bytes = 0
    for index, entry in enumerate(folder.iterdir()):
        if index > MAX_REVISIONS + 32:
            raise ValueError("Investigation folder exceeds its entry bound")
        if REVISION_FILE.fullmatch(entry.name):
            info = entry.lstat()
            if (not stat.S_ISREG(info.st_mode) or entry.is_symlink()
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                raise ValueError("Investigation history cannot follow links")
            history_bytes += info.st_size
    if history_bytes + len(raw) > MAX_HISTORY_BYTES:
        raise ValueError("Investigation reached its 16 MiB history bound; previous revisions remain unchanged")
    pending = folder / (".pending-" + uuid.uuid4().hex)
    target = folder / (f"{revision:04d}.json")
    try:
        with pending.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(pending, target, follow_symlinks=False)
        except FileExistsError as exc:
            raise ValueError("Investigation changed in another window. Reload before saving; your text was not saved.") from exc
        except OSError as exc:
            raise ValueError("This folder cannot safely publish an exclusive revision; previous revisions are unchanged.") from exc
    finally:
        try:
            pending.unlink()
        except FileNotFoundError:
            pass
    return raw


def _validate_card(card, ordinal):
    fields = {"evidence_id", "added_utc", "added_by", "recording_id", "session_id", "seq", "time_s",
              "constraint_id", "capture", "raw_record", "interval_start_record", "constraint", "fingerprints"}
    if not isinstance(card, dict) or set(card) != fields or card["evidence_id"] != "E" + str(ordinal):
        raise ValueError("Invalid evidence card or sequence")
    _identifier(card["recording_id"], "recording")
    _text(card["added_utc"], 80, "Evidence timestamp", True)
    _text(card["added_by"], 80, "Evidence author", True)
    if (type(card["seq"]) is not int or not 0 <= card["seq"] < 10000 or
            type(card["time_s"]) not in (int, float) or not math.isfinite(card["time_s"]) or card["time_s"] < 0):
        raise ValueError("Invalid evidence selection")
    if not isinstance(card["session_id"], str) or not re.fullmatch(r"[a-fA-F0-9]{32}", card["session_id"]):
        raise ValueError("Invalid evidence session")
    raw = card["raw_record"]
    if (not isinstance(raw, dict) or len(raw) != 31 or raw.get("schema") != "survive-v3" or
            raw.get("seq") != card["seq"] or raw.get("session_id") != card["session_id"] or
            raw.get("elapsed_s") != card["time_s"]):
        raise ValueError("Evidence snapshot differs from its selection")
    for row in (raw, card["interval_start_record"]):
        if row is not None and (not isinstance(row, dict) or any(type(row.get(key)) not in (int, float) or not math.isfinite(row[key]) for key in ("x_cm", "y_cm", "elapsed_s"))):
            raise ValueError("Invalid evidence coordinates or clock")
    if not isinstance(card["capture"], dict) or card["capture"].get("recording_id") != card["recording_id"]:
        raise ValueError("Invalid capture snapshot")
    constraint = card["constraint"]
    if card["constraint_id"] is None:
        if constraint is not None or card["interval_start_record"] is not None:
            raise ValueError("Unexpected interval snapshot")
    elif (not isinstance(card["constraint_id"], str) or len(card["constraint_id"]) > 160 or
          not isinstance(constraint, dict) or constraint.get("event_id") != card["constraint_id"] or
          constraint.get("end_seq") != card["seq"] or not isinstance(card["interval_start_record"], dict) or
          card["interval_start_record"].get("seq") != constraint.get("start_seq")):
        raise ValueError("Invalid constraint snapshot")
    prints = card["fingerprints"]
    if not isinstance(prints, dict) or set(prints) != {"manifest_sha256", "files_sha256", "analysis_inputs_sha256", "snapshot_sha256"}:
        raise ValueError("Invalid pinned evidence fingerprints")
    if not all(isinstance(prints[key], str) and HASH.fullmatch(prints[key]) for key in ("manifest_sha256", "snapshot_sha256")):
        raise ValueError("Invalid evidence fingerprint")
    names = {"source.jsonl", "receipts.jsonl", "profile.json", "policy.json", "started.json", "surge.jsonl", "analysis.json"}
    if (not isinstance(prints["files_sha256"], dict) or not {"source.jsonl", "profile.json", "policy.json"} <= set(prints["files_sha256"]) or
            set(prints["files_sha256"]) - names or not isinstance(prints["analysis_inputs_sha256"], dict) or
            len(prints["analysis_inputs_sha256"]) > 16):
        raise ValueError("Invalid pinned file inventory")
    if any(not isinstance(v, str) or not HASH.fullmatch(v) for values in (prints["files_sha256"], prints["analysis_inputs_sha256"]) for v in values.values()):
        raise ValueError("Invalid pinned file fingerprint")
    material = {key: card[key] for key in ("capture", "raw_record", "interval_start_record", "constraint")}
    if _hash(_encoded(material)) != prints["snapshot_sha256"]:
        raise ValueError("Evidence snapshot was modified")


def _validate_document(doc):
    fields = {"schema", "investigation_id", "revision", "previous_sha256", "title", "author", "created_utc",
              "updated_utc", "status", "change_reason", "sections", "evidence"}
    if not isinstance(doc, dict) or set(doc) != fields or doc.get("schema") != SCHEMA:
        raise ValueError("Unsupported investigation document")
    _identifier(doc["investigation_id"])
    _revision(doc["revision"])
    if doc["previous_sha256"] is not None and (not isinstance(doc["previous_sha256"], str) or not HASH.fullmatch(doc["previous_sha256"])):
        raise ValueError("Invalid revision predecessor")
    _text(doc["title"], 120, "Title", True)
    _text(doc["author"], 80, "Author", True)
    _text(doc["change_reason"], 500, "Change reason", True)
    _text(doc["created_utc"], 80, "Creation timestamp", True)
    _text(doc["updated_utc"], 80, "Revision timestamp", True)
    if not isinstance(doc["status"], str) or doc["status"] not in {"draft", "reviewed"}:
        raise ValueError("Choose draft or reviewed")
    if not isinstance(doc["sections"], dict) or set(doc["sections"]) != set(SECTIONS):
        raise ValueError("Provide the five investigation sections")
    for key, value in doc["sections"].items():
        _text(value, 4000, key)
    if not isinstance(doc["evidence"], list) or len(doc["evidence"]) > MAX_EVIDENCE:
        raise ValueError("An investigation supports at most 32 evidence cards")
    for index, card in enumerate(doc["evidence"], 1):
        _validate_card(card, index)
    if len({card["recording_id"] for card in doc["evidence"]}) > MAX_RECORDINGS:
        raise ValueError("An investigation supports at most 8 distinct recordings")
    available = {card["evidence_id"] for card in doc["evidence"]}
    references = set(re.findall(r"\[(E[0-9]+)\]", "\n".join(doc["sections"].values())))
    if references - available:
        raise ValueError("Unresolved evidence reference: " + ", ".join(sorted(references - available)))
    if doc["status"] == "reviewed" and (not available or not doc["sections"]["conclusion"].strip()):
        raise ValueError("Reviewed investigations need evidence and a written conclusion")


class InvestigationManager:
    def __init__(self, capture, root=None):
        self.capture = capture
        self.root = _directory(Path(root) if root is not None else LAB / "Saved/Investigations", create=True)

    def _folder(self, investigation_id):
        return self.root / _identifier(investigation_id)

    def _revision_numbers(self, investigation_id):
        _directory(self.root)
        folder = _directory(self._folder(investigation_id))
        numbers = []
        for index, entry in enumerate(folder.iterdir()):
            if index > MAX_REVISIONS + 32:
                raise ValueError("Investigation folder exceeds its entry bound")
            match = REVISION_FILE.fullmatch(entry.name)
            if match:
                numbers.append(int(match.group(1)))
        numbers.sort()
        if not numbers or numbers != list(range(1, len(numbers) + 1)) or len(numbers) > MAX_REVISIONS:
            raise ValueError("Investigation revision chain is incomplete or exceeds its bound")
        return folder, numbers

    def _chain(self, investigation_id):
        folder, numbers = self._revision_numbers(investigation_id)
        chain = []
        previous = None
        created = None
        previous_cards = []
        history_bytes = 0
        for number in numbers:
            raw = _read(folder / f"{number:04d}.json")
            history_bytes += len(raw)
            if history_bytes > MAX_HISTORY_BYTES:
                raise ValueError("Investigation exceeds its 16 MiB history bound")
            doc = _json(raw)
            _validate_document(doc)
            if doc["revision"] != number or doc["investigation_id"] != investigation_id or doc["previous_sha256"] != previous:
                raise ValueError("Investigation revision chain changed")
            if created is not None and doc["created_utc"] != created:
                raise ValueError("Investigation creation identity changed")
            if doc["evidence"][:len(previous_cards)] != previous_cards:
                raise ValueError("Previously attached evidence changed across revisions")
            previous = _hash(raw)
            created = doc["created_utc"]
            previous_cards = doc["evidence"]
            chain.append((doc, previous))
        return chain

    def list(self):
        _directory(self.root)
        investigations, unavailable = [], []
        count = 0
        for index, folder in enumerate(self.root.iterdir()):
            if index >= MAX_INVESTIGATIONS + 32:
                raise ValueError("Investigation inventory exceeds its bound")
            if not ID.fullmatch(folder.name):
                continue
            count += 1
            if count > MAX_INVESTIGATIONS:
                raise ValueError("This workspace supports at most 256 investigations")
            try:
                directory, revisions = self._revision_numbers(folder.name)
                doc = _json(_read(directory / f"{revisions[-1]:04d}.json"))
                _validate_document(doc)
                if doc["investigation_id"] != folder.name or doc["revision"] != revisions[-1]:
                    raise ValueError("Investigation metadata identity differs")
                investigations.append({key: doc[key] for key in ("investigation_id", "revision", "title", "author", "created_utc", "updated_utc", "status")}
                                      | {"evidence_count": len(doc["evidence"]), "history_verified": False})
            except (ValueError, OSError, TypeError) as exc:
                unavailable.append({"investigation_id": folder.name, "error": "Retained investigation is unavailable: " + type(exc).__name__})
        investigations.sort(key=lambda item: item["updated_utc"], reverse=True)
        return {"investigations": investigations, "unavailable": unavailable}

    def create(self, title, author):
        _text(title, 120, "Title", True)
        _text(author, 80, "Author", True)
        inventory = self.list()
        if len(inventory["investigations"]) + len(inventory["unavailable"]) >= MAX_INVESTIGATIONS:
            raise ValueError("This workspace reached its 256-investigation bound")
        identifier = uuid.uuid4().hex
        folder = self._folder(identifier)
        folder.mkdir(exist_ok=False)
        now = _now()
        doc = {"schema": SCHEMA, "investigation_id": identifier, "revision": 1, "previous_sha256": None,
               "title": title, "author": author, "created_utc": now, "updated_utc": now,
               "status": "draft", "change_reason": "Created investigation", "sections": {key: "" for key in SECTIONS}, "evidence": []}
        _validate_document(doc)
        _publish(folder, 1, doc)
        return self.open(identifier)

    def _read_source(self, recording_id):
        directory = _directory(Path(self.capture.recording_root) / _identifier(recording_id, "recording"))
        manifest_raw = _read(directory / "manifest.json", 128 * 1024)
        manifest = _json(manifest_raw)
        opened = self.capture.open(recording_id)
        capture = opened["capture"]
        if capture["state"] not in {"complete", "stopped", "failed"}:
            raise ValueError("Finish recording before attaching evidence")
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files_sha256"), dict):
            raise ValueError("Source manifest is unavailable")
        raw = _read(directory / "source.jsonl", 4 * 1024 * 1024)
        if _hash(raw) != manifest["files_sha256"].get("source.jsonl"):
            raise ValueError("Recording changed while selecting evidence")
        rows = [_json(line) for line in raw.splitlines()[:capture["records"]]]
        if len(rows) != capture["records"]:
            raise ValueError("Source record inventory differs from its manifest")
        constraints = []
        if capture["analysis_state"] == "complete":
            analysis_raw = _read(directory / "analysis.json", 16 * 1024 * 1024)
            if _hash(analysis_raw) != manifest["files_sha256"].get("analysis.json"):
                raise ValueError("Analysis changed while selecting evidence")
            constraints = _json(analysis_raw)["constraints"]
        if _read(directory / "manifest.json", 128 * 1024) != manifest_raw:
            raise ValueError("Recording manifest changed while selecting evidence")
        fields = ("recording_id", "session_id", "profile_id", "source_sha256", "profile_sha256", "completion", "analysis_state",
                  "records", "bytes", "created_utc", "state", "authenticity", "provenance")
        facts = {key: capture.get(key) for key in fields}
        facts["health"] = {key: (capture.get("health") or {}).get(key) for key in ("sequence_gaps", "parse_errors", "pending_bytes")}
        return {"capture": facts, "rows": rows, "constraints": constraints,
                "manifest_sha256": _hash(manifest_raw), "files_sha256": manifest["files_sha256"],
                "analysis_inputs_sha256": manifest["analysis_inputs_sha256"], "replay": opened}

    @staticmethod
    def _material(source, seq, constraint_id):
        if type(seq) is not int or not 0 <= seq < len(source["rows"]):
            raise ValueError("Selected source record is unavailable")
        raw = source["rows"][seq]
        constraint, start = None, None
        if constraint_id is not None:
            _text(constraint_id, 160, "Constraint identifier", True)
            matches = [item for item in source["constraints"] if item.get("event_id") == constraint_id]
            if len(matches) != 1 or matches[0].get("end_seq") != seq:
                raise ValueError("Constraint does not belong to the selected source record")
            constraint = matches[0]
            start_seq = constraint.get("start_seq")
            if type(start_seq) is not int or not 0 <= start_seq < len(source["rows"]):
                raise ValueError("Constraint interval start is unavailable")
            start = source["rows"][start_seq]
        return {"capture": source["capture"], "raw_record": raw, "interval_start_record": start, "constraint": constraint}

    def _verify(self, doc):
        loaded = {}
        results = []
        counts = {key: 0 for key in ("verified", "missing", "changed", "unavailable")}
        for card in doc["evidence"]:
            rid = card["recording_id"]
            if rid not in loaded:
                try:
                    directory = Path(self.capture.recording_root) / rid
                    _directory(directory)
                    raw_manifest = _read(directory / "manifest.json", 128 * 1024)
                    loaded[rid] = (self._read_source(rid), _hash(raw_manifest), None)
                except FileNotFoundError:
                    loaded[rid] = (None, None, ("missing", "Original recording files are missing; the pinned snapshot is retained."))
                except (ValueError, OSError, KeyError, TypeError):
                    # Distinguish changed retained bytes from a current adapter
                    # incompatibility without exposing filesystem paths.
                    try:
                        digest = _hash(_read(Path(self.capture.recording_root) / rid / "manifest.json", 128 * 1024))
                    except (ValueError, OSError):
                        digest = None
                    loaded[rid] = (None, digest, ("unavailable", "Original evidence cannot currently be verified; the pinned snapshot is retained."))
            source, manifest_digest, failure = loaded[rid]
            state, message = "verified", "Pinned recording, analysis and selected evidence match current verified bytes."
            pins = card["fingerprints"]
            if manifest_digest is not None and manifest_digest != pins["manifest_sha256"]:
                state, message = "changed", "The original recording manifest differs from this pinned revision."
            elif failure:
                state, message = failure
                if state != "missing":
                    try:
                        directory = Path(self.capture.recording_root) / rid
                        if any(_hash(_read(directory / name, 16 * 1024 * 1024)) != digest for name, digest in pins["files_sha256"].items()):
                            state, message = "changed", "Retained source or analysis bytes differ from this pinned revision."
                    except FileNotFoundError:
                        state, message = "missing", "Original recording files are missing; the pinned snapshot is retained."
                    except (ValueError, OSError):
                        pass
            else:
                try:
                    material = self._material(source, card["seq"], card["constraint_id"])
                    if (source["files_sha256"] != pins["files_sha256"] or source["analysis_inputs_sha256"] != pins["analysis_inputs_sha256"] or
                            _hash(_encoded(material)) != pins["snapshot_sha256"]):
                        state, message = "changed", "Source facts, analysis version or selected evidence differs from this pinned revision."
                except (ValueError, TypeError, KeyError):
                    state, message = "changed", "The selected source interval no longer matches its pinned snapshot."
            counts[state] += 1
            results.append({"evidence_id": card["evidence_id"], "state": state, "message": message})
        valid = bool(doc["evidence"]) and counts["verified"] == len(doc["evidence"])
        return {"checked_utc": _now(), "state": "verified" if not doc["evidence"] or valid else "attention",
                "items": results, "counts": counts, "review_valid": doc["status"] == "reviewed" and valid}

    def open(self, investigation_id, revision=None):
        chain = self._chain(_identifier(investigation_id))
        latest = len(chain)
        selected = latest if revision is None else _revision(revision)
        if selected > latest:
            raise ValueError("Investigation revision is unavailable")
        doc = copy.deepcopy(chain[selected - 1][0])
        verification = self._verify(doc)
        doc["history"] = [{key: item[key] for key in ("revision", "author", "updated_utc", "change_reason", "status")} for item, _ in chain]
        return {"document": doc, "verification": verification, "latest_revision": latest}

    def _next(self, investigation_id, expected_revision):
        _revision(expected_revision)
        chain = self._chain(_identifier(investigation_id))
        if len(chain) != expected_revision:
            raise ValueError("Investigation changed in another window. Reload before saving; your text was not saved.")
        if expected_revision >= MAX_REVISIONS:
            raise ValueError("Investigation reached its 256-revision bound; preserve this report and create a new investigation")
        doc = copy.deepcopy(chain[-1][0])
        doc["revision"] += 1
        doc["previous_sha256"] = chain[-1][1]
        doc["updated_utc"] = _now()
        return doc

    def save(self, investigation_id, expected_revision, title, author, change_reason, status, sections):
        doc = self._next(investigation_id, expected_revision)
        doc.update(title=title, author=author, change_reason=change_reason, status=status, sections=copy.deepcopy(sections))
        _validate_document(doc)
        if status == "reviewed" and self._verify(doc)["state"] != "verified":
            raise ValueError("Resolve missing, changed or unavailable evidence before marking this revision reviewed")
        _publish(self._folder(investigation_id), doc["revision"], doc)
        return self.open(investigation_id, doc["revision"])

    def attach(self, investigation_id, expected_revision, recording_id, seq, constraint_id, author, change_reason):
        doc = self._next(investigation_id, expected_revision)
        _text(author, 80, "Author", True)
        _text(change_reason, 500, "Change reason", True)
        _identifier(recording_id, "recording")
        if len(doc["evidence"]) >= MAX_EVIDENCE:
            raise ValueError("An investigation supports at most 32 evidence cards")
        if len({item["recording_id"] for item in doc["evidence"]} | {recording_id}) > MAX_RECORDINGS:
            raise ValueError("An investigation supports at most 8 distinct recordings")
        if any(item["recording_id"] == recording_id and item["seq"] == seq and item["constraint_id"] == constraint_id for item in doc["evidence"]):
            raise ValueError("This exact evidence selection is already attached")
        source = self._read_source(recording_id)
        material = self._material(source, seq, constraint_id)
        card = {"evidence_id": "E" + str(len(doc["evidence"]) + 1), "added_utc": doc["updated_utc"], "added_by": author,
                "recording_id": recording_id, "session_id": material["raw_record"]["session_id"], "seq": seq,
                "time_s": material["raw_record"]["elapsed_s"], "constraint_id": constraint_id, **material,
                "fingerprints": {key: source[key] for key in ("manifest_sha256", "files_sha256", "analysis_inputs_sha256")}
                }
        card["fingerprints"]["snapshot_sha256"] = _hash(_encoded(material))
        doc["evidence"].append(card)
        doc.update(author=author, change_reason=change_reason, status="draft")
        _validate_document(doc)
        _publish(self._folder(investigation_id), doc["revision"], doc)
        return self.open(investigation_id, doc["revision"])

    def resolve(self, investigation_id, evidence_id, revision=None):
        if not isinstance(evidence_id, str) or not EVIDENCE_ID.fullmatch(evidence_id):
            raise ValueError("Invalid evidence reference")
        opened = self.open(investigation_id, revision)
        doc = opened["document"]
        matches = [card for card in doc["evidence"] if card["evidence_id"] == evidence_id]
        if not matches:
            raise ValueError("Evidence reference does not exist in this revision")
        state = next(item for item in opened["verification"]["items"] if item["evidence_id"] == evidence_id)
        if state["state"] != "verified":
            raise ValueError(state["message"] + " Live replay navigation is unavailable.")
        card = matches[0]
        # Deliver the same verified replay rather than ask the renderer to make
        # a second open request that could select a newly replaced source.
        source = self._read_source(card["recording_id"])
        material = self._material(source, card["seq"], card["constraint_id"])
        pins = card["fingerprints"]
        if (source["manifest_sha256"] != pins["manifest_sha256"] or
                source["files_sha256"] != pins["files_sha256"] or
                source["analysis_inputs_sha256"] != pins["analysis_inputs_sha256"] or
                _hash(_encoded(material)) != pins["snapshot_sha256"]):
            raise ValueError("Evidence changed during resolution; replay navigation is unavailable")
        replay = copy.deepcopy(source["replay"])
        if not any(row.get("seq") == card["seq"] for row in replay["records"]):
            replay["records"].append(copy.deepcopy(material["raw_record"]))
        if material["constraint"] is not None and not any(item.get("event_id") == card["constraint_id"] for item in replay["view"]["constraints"]):
            replay["view"]["constraints"].append(copy.deepcopy(material["constraint"]))
        return {key: card[key] for key in ("recording_id", "seq", "constraint_id", "time_s", "evidence_id")} | {
            "investigation_id": investigation_id, "revision": doc["revision"], "replay": replay,
            "raw_record": copy.deepcopy(material["raw_record"]), "constraint": copy.deepcopy(material["constraint"])}

    def export(self, investigation_id, revision=None):
        opened = self.open(investigation_id, revision)
        doc, verification = opened["document"], opened["verification"]
        doc["history"] = [item for item in doc["history"] if item["revision"] <= doc["revision"]]
        payload = {"schema": "survive-investigation-export-v1", "exported_utc": _now(), **opened,
                   "limits": ["Analyst text and Reviewed are operator assertions, not detector verdicts or authenticated authorship.",
                              "Local unsigned hashes establish consistency, not client attestation.",
                              "Snapshots preserve selected evidence, not the complete original recording. Reproduction requires the referenced original recording and analysis version.",
                              "Verification describes export time. Later source changes are not reflected in this static report.",
                              "No finding does not establish human input or legitimate play. Unknown coverage is not a clean result."]}
        structured = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
        escape = lambda value: html.escape(str(value), quote=True)
        sections = []
        for name in SECTIONS:
            body = escape(doc["sections"][name])
            body = re.sub(r"\[(E[0-9]+)\]", lambda m: '<a href="#' + m.group(1) + '">[' + m.group(1) + ']</a>', body)
            sections.append('<section><h2>' + escape(name.replace("_", " ").title()) + '</h2><div class="narrative">' + (body or "Not supplied.") + '</div></section>')
        cards = []
        for card in doc["evidence"]:
            state = next(item for item in verification["items"] if item["evidence_id"] == card["evidence_id"])
            constraint = card["constraint"]
            details = '<p>Recorded event: ' + escape(card["raw_record"].get("event")) + ' · ' + _display_number(card["time_s"]) + ' s · sequence ' + str(card["seq"]) + '</p>'
            if constraint:
                details += '<p>Rule: ' + escape(constraint.get("constraint")) + ' · outcome: ' + escape(constraint.get("status")) + '</p>'
                details += '<p>Observed ' + _display_number(constraint.get("observed")) + ' / allowed ' + _display_number(constraint.get("allowed")) + ' ' + escape(constraint.get("unit")) + ' · coverage: ' + escape(constraint.get("coverage")) + '</p>'
            details += '<p>Summary numbers are rounded to 3 decimal places; exact original values remain in the records and structured appendix.</p>'
            if constraint:
                start = card["interval_start_record"]
                end = card["raw_record"]
                dx, dy = end["x_cm"] - start["x_cm"], end["y_cm"] - start["y_cm"]
                norm = max(abs(dx), abs(dy), 1)
                ex, ey = 150 + 90 * dx / norm, 100 - 70 * dy / norm
                details += f'<svg viewBox="0 0 300 200" role="img" aria-label="Selected interval endpoint displacement, not a reconstructed path"><line x1="150" y1="100" x2="{ex:.3f}" y2="{ey:.3f}" stroke="#087b8c" stroke-width="3"/><circle cx="150" cy="100" r="5" fill="#222"/><circle cx="{ex:.3f}" cy="{ey:.3f}" r="5" fill="#087b8c"/></svg><p>Interval endpoint displacement; this line does not establish the path between samples.</p>'
            cards.append('<section class="evidence" id="' + card["evidence_id"] + '"><h2>' + card["evidence_id"] + ' — measured evidence snapshot</h2><p><strong>' + escape(state["state"].upper()) + '</strong>: ' + escape(state["message"]) + '</p>' + details + '<p>Recording ' + escape(card["recording_id"]) + ' · session ' + escape(card["session_id"]) + '</p><p>Completion: ' + escape(card["capture"].get("completion") or "partial / unavailable") + '; analysis: ' + escape(card["capture"].get("analysis_state")) + '</p><details><summary>Exact records, rule and fingerprints</summary><pre>' + escape(json.dumps(card, ensure_ascii=False, indent=2, allow_nan=False)) + '</pre></details></section>')
        history = ''.join('<tr>' + ''.join('<td>' + escape(item[key]) + '</td>' for key in ("revision", "updated_utc", "author", "status", "change_reason")) + '</tr>' for item in doc["history"] if item["revision"] <= doc["revision"])
        output = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'"><title>' + escape(doc["title"]) + '</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:1000px;margin:36px auto;padding:0 24px;color:#182832;background:#fff}h1,h2{line-height:1.2}section{margin:24px 0;padding:16px;border:1px solid #bfcbd0;border-radius:6px}.narrative{white-space:pre-wrap;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #cdd5d9;text-align:left}svg{width:260px;max-width:100%;height:170px;background:#f2f6f7}.warning{padding:12px;background:#fff0d5}a{color:#075f87}@media print{body{margin:0;max-width:none}section{break-inside:avoid}details>pre{display:block}svg{height:110px}}</style></head><body><h1>' + escape(doc["title"]) + '</h1><p>Surge investigation · revision ' + str(doc["revision"]) + ' · ' + escape(doc["status"].upper()) + '</p><p>Author label: ' + escape(doc["author"]) + ' · saved ' + escape(doc["updated_utc"]) + '</p><p class="warning">Evidence verification: ' + escape(verification["state"]) + '. Reviewed means analyst review, not proof of legitimate play. ' + ("A previously reviewed revision now requires attention. " if doc["status"] == "reviewed" and not verification["review_valid"] else "") + 'Facts below are pinned snapshots; analyst narrative is separate.</p><h2>Analyst narrative</h2>' + ''.join(sections) + '<h2>Evidence appendix</h2>' + (''.join(cards) or '<p>No evidence attached.</p>') + '<h2>Revision history through this export</h2><table><thead><tr><th>Revision</th><th>Time</th><th>Author label</th><th>Status</th><th>Reason</th></tr></thead><tbody>' + history + '</tbody></table><h2>Scope and limitations</h2><ul>' + ''.join('<li>' + escape(item) + '</li>' for item in payload["limits"]) + '</ul><details><summary>Structured export with exact evidence snapshots</summary><pre id="surge-investigation-json">' + escape(structured) + '</pre></details></body></html>'
        return {"html": output, "json": structured, "filename": "surge-investigation-" + investigation_id + "-r" + str(doc["revision"]) + ".html", **opened}
