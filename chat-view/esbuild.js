// Two bundles: the extension host (Node/CJS) and the webview (browser/IIFE),
// plus the webview stylesheet. esbuild only strips types — run `npm run
// typecheck` for real type checking.
const esbuild = require("esbuild");

const production = process.argv.includes("--production");
const watch = process.argv.includes("--watch");

/** @type {import('esbuild').BuildOptions} */
const extension = {
  entryPoints: ["src/extension.ts"],
  bundle: true,
  format: "cjs",
  platform: "node",
  target: "node18",
  outfile: "dist/extension.js",
  external: ["vscode"],
  sourcemap: !production,
  minify: production,
  logLevel: "info",
};

/** @type {import('esbuild').BuildOptions} */
const webview = {
  entryPoints: [
    "src/webview/render.ts",
    "src/webview/styles.css",
    "src/webview/feed.ts",
    "src/webview/feed.css",
  ],
  bundle: true,
  format: "iife",
  platform: "browser",
  target: "es2020",
  outdir: "dist",
  sourcemap: !production,
  minify: production,
  logLevel: "info",
};

async function main() {
  if (watch) {
    const a = await esbuild.context(extension);
    const b = await esbuild.context(webview);
    await Promise.all([a.watch(), b.watch()]);
    console.log("watching…");
  } else {
    await esbuild.build(extension);
    await esbuild.build(webview);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
