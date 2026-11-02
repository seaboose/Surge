"use strict";
// Runs only against a caller-created owned fixture directory; no product hooks.
const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const [
  root,
  python,
  helper,
  libraryRoot,
  phase,
  source,
  stateFile,
  exportFile,
] = process.argv.slice(2);
const { CaseLibrary } = require(path.join(root, "desktop", "case-library.cjs"));
const call = async (method, args) => {
  const run = spawnSync(python, ["-B", helper, root, method, args.path], {
    encoding: "utf8",
    timeout: 10000,
    maxBuffer: 256 * 1024,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
  });
  if (run.error || run.status !== 0)
    throw run.error || Error(run.stderr || "reader failed");
  return JSON.parse(run.stdout);
};
async function main() {
  const library = new CaseLibrary(libraryRoot, call);
  if (phase === "seed") {
    const saved = await library.import(source, "Owned café 東京");
    await fs.writeFile(stateFile, JSON.stringify(saved.entry), { flag: "wx" });
    assert.equal((await library.list()).entries.length, 1);
    return {
      entry: saved.entry,
      opened: await library.open(saved.entry.id),
      checks: 2,
    };
  }
  const original = JSON.parse(await fs.readFile(stateFile, "utf8"));
  if (phase === "inspect") {
    const entries = (await library.list()).entries;
    assert.equal(entries.length, 1);
    assert.equal(entries[0].id, original.id);
    return {
      entry: entries[0],
      opened: await library.open(original.id),
      checks: 2,
    };
  }
  assert.equal(phase, "exercise");
  const evidence = await fs.readFile((await library.entry(original.id)).file);
  const originalInput = await fs.readFile(source);
  await library.rename(original.id, "Reviewed café 東京");
  assert.deepEqual(
    await fs.readFile((await library.entry(original.id)).file),
    evidence,
  );
  await library.export(original.id, exportFile);
  assert.deepEqual(await fs.readFile(exportFile), evidence);
  await assert.rejects(
    library.export(original.id, exportFile),
    (error) => error.code === "EEXIST",
  );
  assert.deepEqual(await fs.readFile(exportFile), evidence);
  const imported = await library.import(exportFile, "Temporary import");
  assert.notEqual(imported.entry.id, original.id);
  await library.delete(imported.entry.id);
  assert.deepEqual(await fs.readFile(exportFile), evidence);
  const changed = JSON.parse(evidence.toString("utf8"));
  changed.payload.current.text = changed.payload.current.text.replace(
    '"reading":0',
    '"reading":999',
  );
  assert.notEqual(
    changed.payload.current.text,
    JSON.parse(evidence).payload.current.text,
  );
  const invalid = path.join(path.dirname(source), "modified.case.json");
  await fs.writeFile(invalid, JSON.stringify(changed), { flag: "wx" });
  await assert.rejects(library.import(invalid, "Must be refused"), /integrity/);
  const entries = (await library.list()).entries;
  assert.equal(entries.length, 1);
  assert.equal(entries[0].id, original.id);
  assert.equal(entries[0].name, "Reviewed café 東京");
  assert.deepEqual(
    await fs.readFile((await library.entry(original.id)).file),
    evidence,
  );
  assert.deepEqual(await fs.readFile(source), originalInput);
  assert.deepEqual(await fs.readFile(exportFile), evidence);
  return {
    entry: entries[0],
    opened: await library.open(original.id),
    checks: 14,
  };
}
main()
  .then((result) => console.log(JSON.stringify(result)))
  .catch((error) => {
    console.error(error.stack || String(error));
    process.exitCode = 1;
  });
