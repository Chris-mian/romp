// Publish the shared recency colour (./age-color) to pages that load no webview bundle — the
// kernel's landing SHELL, whose inline scripts (the bell panel, _LANDING_ERRS_JS) want the same
// "(Xm ago)" tints as the panes but cannot import a module. Built as its own tiny dist entry
// (esbuild.js) and included by _landing() before the errs script; consumers must feature-test
// (`window.__rompAgeColor`) and fall back to their dim default, so a stale dist can't break them.
import { ageColorReadable } from "./age-color";

(window as unknown as { __rompAgeColor: (ageSecs: number) => string }).__rompAgeColor = ageColorReadable;
