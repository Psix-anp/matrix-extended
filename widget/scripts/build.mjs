import { cp, mkdir, rm } from "node:fs/promises";
import { build } from "esbuild";

await rm("dist", { recursive: true, force: true });
await mkdir("dist", { recursive: true });

await build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  outfile: "dist/widget.js",
  format: "iife",
  platform: "browser",
  target: ["es2022"],
  minify: true,
  sourcemap: false,
  legalComments: "none",
  loader: { ".css": "css" },
});

await cp("index.html", "dist/index.html");
console.log("Widget built in widget/dist");
