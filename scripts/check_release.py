"""Check the publishable source tree for local paths and accidental credentials."""

import json
import re
from release_files import ROOT, source_files

failures = []
count = 0
patterns = [
    re.compile(r"(?i)[a-z]:[/\\]+Users[/\\]+[^/\\\s]+"),
    re.compile(r"/[U]sers/[^/\s]+/"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
for path in source_files():
    count += 1
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        continue
    for pattern in patterns:
        if pattern.search(text):
            failures.append(f"{path.relative_to(ROOT)}: local path or credential pattern")
package = json.loads((ROOT / "desktop/package.json").read_text())
for name, version in {**package["dependencies"], **package["devDependencies"]}.items():
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        failures.append(f"Unpinned dependency: {name}")
if failures:
    raise SystemExit("\n".join(failures))
print(
    f"Checked {count} source files. No local user paths or credential patterns found; dependencies are pinned."
)
