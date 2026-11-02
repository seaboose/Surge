"use strict";

// This child only touches the harness-owned fixture passed by its parent. All
// fault injection stays here; production library code has no testing hooks.
const fs = require("node:fs/promises");
const path = require("node:path");
const { createHash } = require("node:crypto");
const { CaseLibrary } = require("./case-library.cjs");

const original = Object.fromEntries(
  [
    "readFile",
    "writeFile",
    "open",
    "rename",
    "link",
    "rm",
    "unlink",
    "rmdir",
  ].map((key) => [key, fs[key].bind(fs)]),
);
const sha256 = (data) => createHash("sha256").update(data).digest("hex");
const fail = (code, message) => Object.assign(new Error(message), { code });

async function main() {
  const config = JSON.parse(await original.readFile(process.argv[2], "utf8"));
  const root = path.resolve(config.fixture);
  const inFixture = (file) => {
    const relative = path.relative(root, path.resolve(String(file)));
    if (
      relative === ".." ||
      relative.startsWith(`..${path.sep}`) ||
      path.isAbsolute(relative)
    )
      throw new Error(
        "Fault injection refused a path outside its owned fixture.",
      );
  };
  const emitted = new Set();
  const event = (name) => {
    emitted.add(name);
    process.send?.({ type: "injection", name });
  };
  const pause = async (name) => {
    event(name);
    await new Promise((resolve, reject) => {
      process.send({ type: "boundary", name }, (error) => {
        if (error) reject(error);
      });
      // Deliberately never resolve: the parent terminates only this child after
      // receiving the persistence marker. The IPC handle keeps the child alive.
    });
  };
  const fault = config.scenario.fault;
  const kind = config.scenario.kind;
  const call = async (method, args) => {
    inFixture(args.path);
    if (method === "library_snapshot") {
      if (fault === "snapshot-error" || fault === "snapshot-cleanup-error") {
        await fs.writeFile(args.path, config.valid.slice(0, 128), {
          flag: "wx",
        });
        event("snapshot-partial-ENOSPC");
        throw fail("ENOSPC", "Owned simulated snapshot write failure.");
      }
      await fs.writeFile(args.path, config.valid, { flag: "wx" });
      if (fault === "kill-snapshot") await pause("snapshot-written");
      return { saved: true };
    }
    const bytes = await fs.readFile(args.path);
    if (method === "library_verify" && fault === "kill-validation")
      await pause("verification-read-before-acceptance");
    if (
      method === "library_verify" &&
      ["verify-error", "verify-cleanup-error"].includes(fault)
    ) {
      event("verification-rejected");
      throw fail("EINVAL", "Owned simulated verification rejection.");
    }
    if (!bytes.equals(Buffer.from(config.valid)))
      throw fail(
        "EINVAL",
        "Owned fixture evidence failed exact-byte validation.",
      );
    return { verified: true, evidence_hash: sha256(bytes) };
  };
  const library = new CaseLibrary(path.join(root, "cases"), call);

  if (config.mode === "inspect") {
    const listed = await library.list();
    const opened = {};
    for (const entry of listed.entries) {
      try {
        opened[entry.id] = { ok: true, result: await library.open(entry.id) };
      } catch (error) {
        opened[entry.id] = {
          ok: false,
          error: error.message,
          code: error.code || null,
        };
      }
    }
    let recovery = null;
    if (config.recoverRename) {
      recovery = {};
      for (const [label, action] of [
        ["open", () => library.open(config.targetId)],
        ["rename", () => library.rename(config.targetId, "Recovered name")],
        ["delete", () => library.delete(config.targetId)],
      ]) {
        try {
          recovery[label] = { ok: true, result: await action() };
        } catch (error) {
          recovery[label] = {
            ok: false,
            error: error.message,
            code: error.code || null,
          };
        }
      }
      recovery.after = await library.list();
    }
    return { inspection: true, listed, opened, recovery };
  }

  fs.writeFile = async (file, data, options) => {
    inFixture(file);
    const base = path.basename(String(file));
    if (
      fault === "metadata-permission" &&
      base === "metadata.json" &&
      String(file).includes(".pending-")
    ) {
      event("metadata-EACCES");
      throw fail("EACCES", "Owned simulated metadata permission failure.");
    }
    if (
      base.startsWith(".name-") &&
      ["rename-partial", "kill-rename-partial"].includes(fault)
    ) {
      await original.writeFile(file, String(data).slice(0, 7), options);
      if (fault === "kill-rename-partial")
        await pause("rename-partial-temp-written");
      event("rename-temp-ENOSPC");
      throw fail("ENOSPC", "Owned simulated rename metadata write failure.");
    }
    return original.writeFile(file, data, options);
  };

  fs.open = async (file, flags, mode) => {
    inFixture(file);
    const handle = await original.open(file, flags, mode);
    if (flags !== "wx") return handle;
    const write = handle.write.bind(handle);
    const close = handle.close.bind(handle);
    let writeInjected = false;
    let closeInjected = false;
    handle.write = async (buffer, offset, length, position) => {
      if (fault === "zero-write") {
        if (!writeInjected) event("zero-byte-write");
        writeInjected = true;
        return { bytesWritten: 0, buffer };
      }
      if (fault === "short-write") {
        if (!writeInjected) event("short-byte-write");
        writeInjected = true;
        return write(buffer, offset, Math.min(length, 257), position);
      }
      if (!writeInjected && ["partial-write", "kill-copy"].includes(fault)) {
        writeInjected = true;
        const result = await write(
          buffer,
          offset,
          Math.min(length, 128),
          position,
        );
        if (fault === "kill-copy") await pause("partial-copy-persisted");
        event("partial-copy-ENOSPC");
        throw fail("ENOSPC", "Owned simulated partial copy failure.");
      }
      return write(buffer, offset, length, position);
    };
    handle.close = async () => {
      await close();
      if (fault === "close-error" && !closeInjected) {
        closeInjected = true;
        event("output-close-EIO");
        throw fail("EIO", "Owned simulated output close failure.");
      }
    };
    return handle;
  };

  const publication = async (name, operation) => {
    if (fault === "publish-error") {
      event(`${name}-EACCES`);
      throw fail("EACCES", "Owned simulated publication permission failure.");
    }
    if (fault === "kill-prepublish") await pause(`${name}-before`);
    if (fault === "destination-race") {
      await original.writeFile(config.destination, config.existing, {
        flag: "wx",
      });
      event("destination-created-immediately-before-publication");
    }
    const result = await operation();
    if (fault === "kill-postpublish") await pause(`${name}-after`);
    return result;
  };
  fs.rename = async (from, to) => {
    inFixture(from);
    inFixture(to);
    const base = path.basename(String(from));
    if (base.startsWith(".pending-"))
      return publication("case-publication", () => original.rename(from, to));
    if (base.startsWith(".name-"))
      return publication("name-publication", () => original.rename(from, to));
    if (path.basename(String(to)).startsWith(".deleted-"))
      return publication("delete-publication", () => original.rename(from, to));
    return original.rename(from, to);
  };
  fs.link = async (from, to) => {
    inFixture(from);
    inFixture(to);
    if (
      kind === "export" &&
      path.resolve(String(to)) === path.resolve(config.destination)
    )
      return publication("export-publication", () => original.link(from, to));
    return original.link(from, to);
  };
  for (const method of ["rm", "unlink", "rmdir"]) {
    fs[method] = async (file, ...args) => {
      inFixture(file);
      const relative = path.relative(root, String(file));
      if (
        (fault === "snapshot-cleanup-error" &&
          relative.includes(".pending-")) ||
        (["export-cleanup-error", "verify-cleanup-error"].includes(fault) &&
          relative.includes(".surge-export-")) ||
        (fault === "delete-cleanup-error" && relative.includes(".deleted-"))
      ) {
        event(`${kind}-cleanup-EACCES`);
        throw fail("EACCES", "Owned simulated cleanup permission failure.");
      }
      return original[method](file, ...args);
    };
  }

  try {
    let result;
    if (kind === "save") result = await library.save("New case", 1);
    else if (kind === "import")
      result = await library.import(config.source, "New case");
    else if (kind === "rename")
      result = await library.rename(config.targetId, "New name");
    else if (kind === "export")
      result = await library.export(config.targetId, config.destination);
    else if (kind === "delete") result = await library.delete(config.targetId);
    else if (kind === "corruption") result = await library.list();
    else throw new Error(`Unknown owned operation: ${kind}`);
    return { ok: true, result, injections: [...emitted] };
  } catch (error) {
    return {
      ok: false,
      error: error.message,
      code: error.code || null,
      injections: [...emitted],
    };
  }
}

main()
  .then((result) => {
    process.send?.({ type: "result", result });
    process.disconnect?.();
  })
  .catch((error) => {
    console.error(error.stack || error);
    process.exitCode = 2;
    process.disconnect?.();
  });
