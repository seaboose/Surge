const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises"),
  os = require("node:os"),
  path = require("node:path");
const { CaseLibrary } = require("./case-library.cjs");
async function setup(t) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "surge-library-"));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const call = async (method, args) => {
    if (method === "library_snapshot") {
      assert.equal(args.revision, 1);
      await fs.writeFile(args.path, '{"evidence":"owned"}', { flag: "wx" });
    } else {
      const text = await fs.readFile(args.path, "utf8");
      assert.equal(text, '{"evidence":"owned"}');
      return { verified: true };
    }
  };
  return { dir, call, library: new CaseLibrary(path.join(dir, "cases"), call) };
}
test("save publishes independent snapshots; failure publishes nothing", async (t) => {
  const { library, call } = await setup(t);
  const a = await library.save("First", 1),
    b = await library.save("First", 1);
  assert.notEqual(a.entry.id, b.entry.id);
  assert.equal((await library.list()).entries.length, 2);
  library.call = async () => {
    throw Error("failed write");
  };
  await assert.rejects(library.save("Failure", 1), /failed write/);
  assert.equal((await library.list()).entries.length, 2);
  library.call = call;
  await assert.rejects(library.save(" ", 1));
});
test("open verifies persisted entries and rejects traversal", async (t) => {
  const { library, call } = await setup(t);
  const a = await library.save("Saved", 1);
  const restarted = new CaseLibrary(library.root, call);
  assert.deepEqual(await restarted.open(a.entry.id), {
    verified: true,
    library_case: { id: a.entry.id, name: "Saved" },
  });
  await assert.rejects(restarted.open("../evidence"), /identifier/);
  await fs.writeFile((await library.entry(a.entry.id)).file, "invalid");
  await assert.rejects(restarted.open(a.entry.id));
});
test("rename changes only the display name", async (t) => {
  const { library } = await setup(t),
    a = await library.save("Before", 1);
  const file = (await library.entry(a.entry.id)).file,
    before = await fs.readFile(file);
  await library.rename(a.entry.id, "After");
  assert.equal((await library.list()).entries[0].name, "After");
  assert.deepEqual((await library.open(a.entry.id)).library_case, {
    id: a.entry.id,
    name: "After",
  });
  assert.deepEqual(await fs.readFile(file), before);
  await assert.rejects(library.rename(a.entry.id, "x".repeat(101)));
});
test("delete preserves original evidence and other cases", async (t) => {
  const { library, dir } = await setup(t),
    a = await library.save("Delete", 1),
    b = await library.save("Keep", 1);
  const source = path.join(dir, "original.json");
  await fs.writeFile(source, "original evidence");
  await library.delete(a.entry.id);
  assert.equal(await fs.readFile(source, "utf8"), "original evidence");
  assert.deepEqual(
    (await library.list()).entries.map((x) => x.id),
    [b.entry.id],
  );
  await assert.rejects(library.open(a.entry.id));
});
test("import verifies a copy; export is portable and never overwrites", async (t) => {
  const { library, dir } = await setup(t),
    a = await library.save("Original", 1);
  const external = path.join(dir, "export.case.json");
  await library.export(a.entry.id, external);
  await assert.rejects(library.export(a.entry.id, external), /EEXIST/);
  const b = await library.import(external, "Imported");
  await library.delete(b.entry.id);
  assert.equal(await fs.readFile(external, "utf8"), '{"evidence":"owned"}');
  const bad = path.join(dir, "bad.json");
  await fs.writeFile(bad, "invalid");
  await assert.rejects(library.import(bad, "Bad"));
  assert.equal((await library.list()).entries.length, 1);
  await fs.writeFile((await library.entry(a.entry.id)).file, "invalid");
  const invalidExport = path.join(dir, "bad-export.json");
  await assert.rejects(library.export(a.entry.id, invalidExport));
  await assert.rejects(fs.stat(invalidExport));
});
test("linked managed evidence is rejected", async (t) => {
  const { library, dir } = await setup(t),
    a = await library.save("Linked", 1);
  const file = (await library.entry(a.entry.id)).file;
  await fs.link(file, path.join(dir, "external-link"));
  await assert.rejects(library.delete(a.entry.id), /Linked/);
  assert.equal((await library.list()).unavailable, 1);
});

test("unsupported exclusive export publication preserves evidence and destination", async (t) => {
  const { library, dir } = await setup(t);
  const a = await library.save("Owned source", 1);
  const source = (await library.entry(a.entry.id)).file;
  const before = await fs.readFile(source);
  const destination = path.join(dir, "unsupported.case.json");
  const link = fs.link;
  let calls = 0;
  try {
    fs.link = async (from, to) => {
      if (to !== destination) return link(from, to);
      calls++;
      throw Object.assign(new Error("Owned unsupported-link simulation."), {
        code: "ENOTSUP",
      });
    };
    await assert.rejects(
      library.export(a.entry.id, destination),
      (error) =>
        error.code === "ENOTSUP" &&
        /Choose another local folder/.test(error.message) &&
        error.cause?.code === "ENOTSUP",
    );
  } finally {
    fs.link = link;
  }
  assert.equal(calls, 1);
  await assert.rejects(fs.stat(destination), { code: "ENOENT" });
  assert.deepEqual(await fs.readFile(source), before);
  assert.deepEqual(
    (await library.list()).entries.map((entry) => entry.id),
    [a.entry.id],
  );
  assert.deepEqual(
    (await fs.readdir(dir)).filter((name) => name.startsWith(".surge-export-")),
    [],
  );
  await library.export(a.entry.id, destination);
  assert.deepEqual(await fs.readFile(destination), before);
});

for (const [code, operation] of [
  ["EPERM", "save"],
  ["EBUSY", "import"],
]) {
  test(
    `Windows ${code} publication retries preserve one ${operation} operation`,
    {
      skip: process.platform !== "win32",
    },
    async (t) => {
      const { library, dir, call } = await setup(t);
      const source = path.join(dir, "original.json");
      const bytes = '{"evidence":"owned"}';
      await fs.writeFile(source, bytes, { flag: "wx" });
      const calls = [];
      library.call = async (...args) => {
        calls.push(args[0]);
        return call(...args);
      };
      const rename = fs.rename;
      const publications = [];
      let saved;
      try {
        fs.rename = async (from, to) => {
          publications.push([from, to]);
          if (publications.length <= 2)
            throw Object.assign(
              new Error("Owned temporary publication lock."),
              { code },
            );
          return rename(from, to);
        };
        saved =
          operation === "save"
            ? await library.save("Retried", 1)
            : await library.import(source, "Retried");
      } finally {
        fs.rename = rename;
      }
      assert.equal(publications.length, 3);
      assert.ok(
        publications.every(
          ([from, to]) =>
            from === publications[0][0] && to === publications[0][1],
        ),
      );
      assert.deepEqual(calls, [
        operation === "save" ? "library_snapshot" : "library_verify",
      ]);
      assert.equal(await fs.readFile(source, "utf8"), bytes);
      assert.equal(
        await fs.readFile((await library.entry(saved.entry.id)).file, "utf8"),
        bytes,
      );
      assert.deepEqual(await fs.readdir(library.root), [saved.entry.id]);
    },
  );
}

test(
  "Windows publication retries are bounded and preserve the final failure",
  {
    skip: process.platform !== "win32",
  },
  async (t) => {
    const { library } = await setup(t);
    const rename = fs.rename;
    const failure = Object.assign(
      new Error("Owned persistent publication refusal."),
      { code: "EPERM" },
    );
    let attempts = 0;
    try {
      fs.rename = async () => {
        attempts++;
        throw failure;
      };
      await assert.rejects(
        library.save("Refused", 1),
        (error) => error === failure,
      );
    } finally {
      fs.rename = rename;
    }
    assert.equal(attempts, 5);
    assert.deepEqual(await fs.readdir(library.root), []);
  },
);

test("publication permission failures are not retried", async (t) => {
  const { library } = await setup(t);
  const rename = fs.rename;
  const failure = Object.assign(new Error("Owned permission denial."), {
    code: "EACCES",
  });
  let attempts = 0;
  try {
    fs.rename = async () => {
      attempts++;
      throw failure;
    };
    await assert.rejects(
      library.save("Denied", 1),
      (error) => error === failure,
    );
  } finally {
    fs.rename = rename;
  }
  assert.equal(attempts, 1);
  assert.deepEqual(await fs.readdir(library.root), []);
});

test(
  "Windows publication retry never replaces an intervening destination",
  {
    skip: process.platform !== "win32",
  },
  async (t) => {
    const { library } = await setup(t);
    const rename = fs.rename;
    let destination;
    let attempts = 0;
    try {
      fs.rename = async (from, to) => {
        attempts++;
        if (attempts === 1) {
          destination = to;
          await fs.mkdir(to);
          await fs.writeFile(
            path.join(to, "keep.txt"),
            "Existing destination",
            { flag: "wx" },
          );
          throw Object.assign(new Error("Owned transient publication lock."), {
            code: "EBUSY",
          });
        }
        return rename(from, to);
      };
      await assert.rejects(library.save("Cannot replace", 1));
    } finally {
      fs.rename = rename;
    }
    assert.ok(attempts >= 2 && attempts <= 5);
    assert.equal(
      await fs.readFile(path.join(destination, "keep.txt"), "utf8"),
      "Existing destination",
    );
    assert.deepEqual(await fs.readdir(destination), ["keep.txt"]);
    assert.deepEqual(await fs.readdir(library.root), [
      path.basename(destination),
    ]);
  },
);
