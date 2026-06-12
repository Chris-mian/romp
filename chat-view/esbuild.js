// Two bundles: the extension host (Node/CJS) and the webview (browser/IIFE),
// plus the webview stylesheet. esbuild only strips types — run `npm run
// typecheck` for real type checking.
const esbuild = require("esbuild");
const fs = require("fs");
const path = require("path");

const production = process.argv.includes("--production");
const watch = process.argv.includes("--watch");
const tests = process.argv.includes("--tests");

/** @type {import('esbuild').BuildOptions} */
const extension = {
  entryPoints: ["src/extension.ts"],
  bundle: true,
  format: "cjs",
  platform: "node",
  target: "node18",
  outfile: "dist/extension.js",
  external: ["vscode", "bufferutil", "utf-8-validate"],   // ws optional native addons
  sourcemap: !production,
  minify: production,
  logLevel: "info",
};

// The standalone web kernel (bin/romp-serve runs dist/kernel.js): same host
// logic as the extension, no vscode. ws's optional native addons are external
// (pure-JS fallbacks are used when they're absent).
/** @type {import('esbuild').BuildOptions} */
const kernel = {
  entryPoints: ["src/kernel/server.ts"],
  bundle: true,
  format: "cjs",
  platform: "node",
  target: "node18",
  outfile: "dist/kernel.js",
  external: ["bufferutil", "utf-8-validate"],
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

// Unit tests for the pure modules (src/*.test.ts): bundled to out-tests/ and
// run with the built-in `node --test` runner — no extra test framework.
function testBuild() {
  const entries = ["src", "src/kernel"].flatMap((dir) =>
    fs
      .readdirSync(path.join(__dirname, dir))
      .filter((f) => f.endsWith(".test.ts"))
      .map((f) => dir + "/" + f),
  );
  /** @type {import('esbuild').BuildOptions} */
  return {
    entryPoints: entries,
    bundle: true,
    format: "cjs",
    platform: "node",
    target: "node18",
    outdir: "out-tests",
    sourcemap: "inline",
    logLevel: "info",
  };
}

async function main() {
  if (tests) {
    await esbuild.build(testBuild());
  } else if (watch) {
    const a = await esbuild.context(extension);
    const b = await esbuild.context(webview);
    const c = await esbuild.context(kernel);
    await Promise.all([a.watch(), b.watch(), c.watch()]);
    console.log("watching…");
  } else {
    await esbuild.build(extension);
    await esbuild.build(webview);
    await esbuild.build(kernel);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
