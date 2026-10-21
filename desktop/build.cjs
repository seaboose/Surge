const esbuild = require("esbuild");
const fs = require("node:fs");
fs.mkdirSync("dist", { recursive: true });
esbuild.buildSync({
  entryPoints: ["src/main.jsx"],
  bundle: true,
  outfile: "dist/app.js",
  minify: true,
  sourcemap: false,
  define: { "process.env.NODE_ENV": '"production"' },
  legalComments: "eof",
});
fs.copyFileSync("src/index.html", "dist/index.html");
fs.copyFileSync("src/style.css", "dist/style.css");
