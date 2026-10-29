const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { saveInvestigationExport } = require("./investigation-export.cjs");
const root = path.resolve(__dirname, "../verification/temporary-test-files");
const html =
  "<!doctype html><html><body><h1>Owned investigation</h1></body></html>";
async function fixture(fn) {
  await fs.mkdir(root, { recursive: true });
  const folder = await fs.mkdtemp(path.join(root, "investigation-export-"));
  try {
    return await fn(folder);
  } finally {
    const resolved = await fs.realpath(folder);
    assert(path.relative(root, resolved).startsWith("investigation-export-"));
    assert(!path.relative(root, resolved).includes(".."));
    await fs.rm(folder, { recursive: true, force: true });
  }
}

test("report export publishes exact bytes once without overwriting existing evidence", async () =>
  fixture(async (folder) => {
    const target = path.join(folder, "report.html");
    const result = await saveInvestigationExport(target, html);
    assert.equal(result.saved, true);
    assert.equal(result.bytes, Buffer.byteLength(html));
    assert.equal(await fs.readFile(target, "utf8"), html);
    assert.deepEqual(await fs.readdir(folder), ["report.html"]);
    await assert.rejects(
      saveInvestigationExport(target, html + "changed"),
      /already exists/,
    );
    assert.equal(await fs.readFile(target, "utf8"), html);
  }));

test("report export rejects dangerous destinations and unbounded payloads before writing", async () =>
  fixture(async (folder) => {
    for (const name of [
      "capture.jsonl",
      "revision.json",
      "device:stream.html",
      "CON.html",
    ])
      await assert.rejects(
        saveInvestigationExport(path.join(folder, name), html),
      );
    await assert.rejects(saveInvestigationExport("relative.html", html));
    await assert.rejects(
      saveInvestigationExport(
        path.join(folder, "report.html"),
        "x".repeat(4 * 1024 * 1024 + 1),
      ),
    );
    assert.deepEqual(await fs.readdir(folder), []);
  }));

test("failed publication preserves destination and removes only the owned temporary file", async () =>
  fixture(async (folder) => {
    const target = path.join(folder, "report.html");
    const original = fs.link;
    try {
      fs.link = async () => {
        throw Object.assign(new Error("fixture filesystem"), {
          code: "ENOTSUP",
        });
      };
      await assert.rejects(saveInvestigationExport(target, html), /safely/);
      assert.deepEqual(await fs.readdir(folder), []);
      fs.link = async (_temporary, destination) => {
        await fs.writeFile(destination, "concurrent winner", { flag: "wx" });
        throw Object.assign(new Error("fixture race"), { code: "EEXIST" });
      };
      await assert.rejects(
        saveInvestigationExport(target, html),
        /already exists/,
      );
      assert.equal(await fs.readFile(target, "utf8"), "concurrent winner");
      assert.deepEqual(await fs.readdir(folder), ["report.html"]);
    } finally {
      fs.link = original;
    }
  }));

test("linked export folders are rejected without writing through them", async (t) =>
  fixture(async (folder) => {
    const real = path.join(folder, "real");
    await fs.mkdir(real);
    const link = path.join(folder, "linked");
    try {
      await fs.symlink(
        real,
        link,
        process.platform === "win32" ? "junction" : "dir",
      );
    } catch (error) {
      if (error.code === "EPERM") {
        t.skip("Windows link-creation permission unavailable");
        return;
      }
      throw error;
    }
    await assert.rejects(
      saveInvestigationExport(path.join(link, "report.html"), html),
      /link/,
    );
    assert.deepEqual(await fs.readdir(real), []);
  }));
