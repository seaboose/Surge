"use strict";
// The main process supplies a native-picker destination and worker-produced HTML.
// Renderer requests can supply neither a filesystem path nor report bytes.
const fs = require("node:fs/promises");
const path = require("node:path");
const { randomUUID, createHash } = require("node:crypto");

async function checkedParent(destination) {
  if (
    typeof destination !== "string" ||
    !path.isAbsolute(destination) ||
    path.extname(destination).toLowerCase() !== ".html" ||
    destination.includes("\0")
  )
    throw new Error("Choose a new .html report file.");
  const absolute = path.resolve(destination);
  const basename = path.basename(absolute);
  if (
    /[<>:"|?*\x00-\x1f]/.test(basename) ||
    /[. ]$/.test(basename) ||
    /^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(basename)
  )
    throw new Error(
      "Choose an ordinary report filename without reserved characters.",
    );
  let parent = path.dirname(absolute);
  while (true) {
    const info = await fs.lstat(parent);
    if (!info.isDirectory() || info.isSymbolicLink())
      throw new Error(
        "Report folders must be ordinary directories, not links.",
      );
    const next = path.dirname(parent);
    if (next === parent) break;
    parent = next;
  }
  const containing = path.dirname(absolute);
  const resolved = await fs.realpath(containing);
  const compare = (value) =>
    process.platform === "win32" ? value.toLowerCase() : value;
  if (compare(resolved) !== compare(containing))
    throw new Error("The report destination resolves through a linked folder.");
  return absolute;
}

async function saveInvestigationExport(destination, html) {
  if (
    typeof html !== "string" ||
    Buffer.byteLength(html, "utf8") > 4 * 1024 * 1024 ||
    !/^<!doctype html>/i.test(html)
  )
    throw new Error(
      "The generated investigation report is invalid or too large.",
    );
  const target = await checkedParent(destination);
  const temporary = path.join(
    path.dirname(target),
    ".surge-report-" + randomUUID() + ".tmp",
  );
  let handle;
  let owned = false;
  try {
    handle = await fs.open(temporary, "wx", 0o600);
    owned = true;
    await handle.writeFile(html, "utf8");
    await handle.sync();
    await handle.close();
    handle = null;
    await checkedParent(target);
    // Linking publishes fully written bytes and cannot replace an existing file.
    await fs.link(temporary, target);
    return {
      saved: true,
      filename: path.basename(target),
      bytes: Buffer.byteLength(html, "utf8"),
      sha256: createHash("sha256").update(html, "utf8").digest("hex"),
      message:
        "Investigation report exported. The saved revision and original evidence are unchanged.",
    };
  } catch (error) {
    if (error.code === "EEXIST")
      throw new Error(
        "That file already exists. Choose a new report filename.",
      );
    if (["EPERM", "ENOTSUP", "EOPNOTSUPP", "EXDEV"].includes(error.code))
      throw new Error(
        "This folder cannot publish a report safely without overwriting. Choose another local folder.",
      );
    throw error;
  } finally {
    if (handle) await handle.close().catch(() => {});
    if (owned) await fs.unlink(temporary).catch(() => {});
  }
}

module.exports = { saveInvestigationExport };
