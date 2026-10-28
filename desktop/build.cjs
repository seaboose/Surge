const esbuild = require("esbuild");
const fs = require("node:fs");

function options(development = false) {
  return {
    entryPoints: ["src/main.jsx"],
    bundle: true,
    outfile: "dist/app.js",
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

function build(development) {
  fs.mkdirSync("dist", { recursive: true });
  esbuild.buildSync(options(development));
  fs.copyFileSync("src/index.html", "dist/index.html");
  if (development) {
    esbuild.buildSync({
      entryPoints: ["src/style.css"],
      outfile: "dist/style.css",
      sourcemap: "linked",
      sourcesContent: true,
    });
  } else {
    fs.copyFileSync("src/style.css", "dist/style.css");
    // These are known generated artifacts, never editable source files.
    for (const name of ["app.js.map", "app.css.map", "style.css.map"])
      fs.rmSync("dist/" + name, { force: true });
  }
}

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.some((arg) => arg !== "--development"))
    throw new Error("Usage: node build.cjs [--development]");
  build(args.includes("--development"));
}
module.exports = { options, build };
