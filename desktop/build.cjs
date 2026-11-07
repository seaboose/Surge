const esbuild = require("esbuild");
const fs = require("node:fs");
const path = require("node:path");

function options(development = false, paths = {}) {
  const { sourceDir = "src", outputDir = "dist", nodePaths } = paths;
  return {
    entryPoints: [path.join(sourceDir, "main.jsx")],
    bundle: true,
    loader: { ".ttf": "file", ".svg": "dataurl" },
    assetNames: "fonts/[name]",
    outfile: path.join(outputDir, "app.js"),
    ...(nodePaths ? { nodePaths } : {}),
    minify: !development,
    sourcemap: development ? "linked" : false,
    sourcesContent: development,
    define: {
      "process.env.NODE_ENV": JSON.stringify(
        development ? "development" : "production",
      ),
    },
    legalComments: "eof",
  };
}

function build(development = false, paths = {}) {
  const { sourceDir = "src", outputDir = "dist" } = paths;
  fs.mkdirSync(outputDir, { recursive: true });
  esbuild.buildSync(options(development, paths));
  fs.copyFileSync(
    path.join(sourceDir, "index.html"),
    path.join(outputDir, "index.html"),
  );
  fs.mkdirSync(path.join(outputDir, "fonts"), { recursive: true });
  for (const name of ["Inter-OFL.txt", "JetBrainsMono-OFL.txt"])
    fs.copyFileSync(
      path.join(sourceDir, "fonts", name),
      path.join(outputDir, "fonts", name),
    );
  if (development) {
    esbuild.buildSync({
      entryPoints: [path.join(sourceDir, "style.css")],
      outfile: path.join(outputDir, "style.css"),
      sourcemap: "linked",
      sourcesContent: true,
    });
  } else {
    fs.copyFileSync(
      path.join(sourceDir, "style.css"),
      path.join(outputDir, "style.css"),
    );
    // These are known generated artifacts, never editable source files.
    for (const name of ["app.js.map", "app.css.map", "style.css.map"])
      fs.rmSync(path.join(outputDir, name), { force: true });
  }
}

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.some((arg) => arg !== "--development"))
    throw new Error("Usage: node build.cjs [--development]");
  build(args.includes("--development"));
}
module.exports = { options, build };
