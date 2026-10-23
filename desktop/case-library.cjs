"use strict";
const fs = require("node:fs/promises");
const path = require("node:path");
const { randomUUID } = require("node:crypto");

function caseName(name) {
  if (
    typeof name !== "string" ||
    !name.trim() ||
    name.trim().length > 100 ||
    /[\x00-\x1f\x7f]/.test(name)
  )
    throw new Error(
      "Enter a case name of 1–100 characters without control characters.",
    );
  return name.trim();
}
async function copyCase(source, destination) {
  const input = await fs.open(source, "r");
  let output,
    created = false;
  try {
    if (!(await input.stat()).isFile()) throw new Error("Choose a case file.");
    output = await fs.open(destination, "wx");
    created = true;
    const buffer = Buffer.alloc(64 * 1024);
    let total = 0;
    for (;;) {
      const { bytesRead } = await input.read(buffer, 0, buffer.length, null);
      if (!bytesRead) break;
      total += bytesRead;
      if (total > 64 * 1024 * 1024) throw new Error("Case exceeds 64 MiB.");
      let offset = 0;
      while (offset < bytesRead)
        offset += (await output.write(buffer, offset, bytesRead - offset))
          .bytesWritten;
    }
  } catch (error) {
    if (output) {
      await output.close();
      output = null;
    }
    if (created) await fs.unlink(destination).catch(() => {});
    throw error;
  } finally {
    await input.close();
    if (output) await output.close();
  }
}
class CaseLibrary {
  constructor(root, call) {
    this.root = root;
    this.call = call;
  }
  async init() {
    await fs.mkdir(this.root, { recursive: true });
    if ((await fs.lstat(this.root)).isSymbolicLink())
      throw new Error("Case library must be a local directory, not a link.");
  }
  async entry(id) {
    if (
      typeof id !== "string" ||
      !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(id)
    )
      throw new Error("Invalid case identifier.");
    await this.init();
    const dir = path.join(this.root, id);
    const stat = await fs.lstat(dir);
    if (!stat.isDirectory() || stat.isSymbolicLink())
      throw new Error("Invalid library entry.");
    for (const name of ["case.json", "metadata.json"]) {
      const s = await fs.lstat(path.join(dir, name));
      if (!s.isFile() || s.isSymbolicLink() || s.nlink !== 1)
        throw new Error("Linked library files are not supported.");
    }
    if ((await fs.stat(path.join(dir, "metadata.json"))).size > 4096)
      throw new Error("Invalid case metadata.");
    const meta = JSON.parse(
      await fs.readFile(path.join(dir, "metadata.json"), "utf8"),
    );
    caseName(meta.name);
    if (meta.id !== id || typeof meta.created !== "string")
      throw new Error("Invalid case metadata.");
    return {
      dir,
      file: path.join(dir, "case.json"),
      meta: { id, name: meta.name, created: meta.created },
    };
  }
  async list() {
    await this.init();
    const entries = [],
      unavailable = [];
    for (const item of await fs.readdir(this.root, { withFileTypes: true })) {
      if (item.name.startsWith(".")) continue;
      try {
        entries.push((await this.entry(item.name)).meta);
      } catch {
        unavailable.push(item.name);
      }
    }
    entries.sort((a, b) => b.created.localeCompare(a.created));
    return { entries, unavailable: unavailable.length };
  }
  async create(name, write) {
    name = caseName(name);
    await this.init();
    const id = randomUUID(),
      staging = path.join(this.root, `.pending-${id}`),
      final = path.join(this.root, id);
    await fs.mkdir(staging);
    try {
      await write(path.join(staging, "case.json"));
      const meta = { id, name, created: new Date().toISOString() };
      await fs.writeFile(
        path.join(staging, "metadata.json"),
        JSON.stringify(meta),
        { flag: "wx" },
      );
      await fs.rename(staging, final);
      return { entry: meta, message: "Case saved to the local library." };
    } catch (error) {
      // Staging contains only files created by this operation, never source evidence.
      await fs.rm(staging, { recursive: true, force: true }).catch(() => {});
      throw error;
    }
  }
  async save(name, revision) {
    return this.create(name, (file) =>
      this.call("library_snapshot", { path: file, revision }),
    );
  }
  async open(id) {
    const e = await this.entry(id);
    const state = await this.call("open", { path: e.file });
    return { ...state, library_case: { id: e.meta.id, name: e.meta.name } };
  }
  async rename(id, name) {
    name = caseName(name);
    const e = await this.entry(id),
      tmp = path.join(e.dir, `.name-${randomUUID()}`);
    try {
      await fs.writeFile(tmp, JSON.stringify({ ...e.meta, name }), {
        flag: "wx",
      });
      await fs.rename(tmp, path.join(e.dir, "metadata.json"));
    } finally {
      await fs.unlink(tmp).catch(() => {});
    }
    return { message: "Case renamed." };
  }
  async delete(id) {
    const e = await this.entry(id);
    if (
      (await fs.readdir(e.dir)).some(
        (n) => !["case.json", "metadata.json"].includes(n),
      )
    )
      throw new Error(
        "Case folder contains unexpected files; deletion canceled.",
      );
    const removed = path.join(this.root, `.deleted-${id}-${randomUUID()}`);
    await fs.rename(e.dir, removed);
    try {
      await fs.unlink(path.join(removed, "case.json"));
      await fs.unlink(path.join(removed, "metadata.json"));
      await fs.rmdir(removed);
    } catch {
      return {
        message:
          "Case removed from the library; local cleanup is incomplete. Original evidence is unchanged.",
      };
    }
    return {
      message:
        "Case deleted. Original evidence and external files are unchanged.",
    };
  }
  async import(source, name) {
    return this.create(name, async (file) => {
      await copyCase(source, file);
      await this.call("library_verify", { path: file });
    });
  }
  async export(id, destination) {
    const e = await this.entry(id);
    await copyCase(e.file, destination);
    try {
      await this.call("library_verify", { path: destination });
    } catch (error) {
      await fs.unlink(destination).catch(() => {});
      throw error;
    }
    return {
      message: "Portable case exported. The library copy is unchanged.",
    };
  }
}
module.exports = { CaseLibrary, caseName };
