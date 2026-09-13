#!/usr/bin/env node
/**
 * Contract drift check.  Regenerates openapi.json from the FastAPI service and api.d.ts from
 * openapi.json into a temp dir and diffs them against the committed files.  Exit 1 on drift.
 *
 * Usage: node scripts/check-drift.mjs   (run from packages/contracts; needs `uv` on PATH)
 */
import { execFileSync } from "node:child_process";
import { readFileSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const here = resolve(new URL(".", import.meta.url).pathname, "..");
const repo = resolve(here, "../..");
const tmp = mkdtempSync(join(tmpdir(), "contracts-"));

const env = {
  ...process.env,
  DEPLOYMENT_PROFILE: "local",
  LOCAL_USER_ALLOWLIST: process.env.LOCAL_USER_ALLOWLIST || "drift-check@example.com:analyst",
  DATABASE_URL: process.env.DATABASE_URL || "postgresql+psycopg://postgres:postgres@localhost:5432/unused",
};

const freshSpecPath = join(tmp, "openapi.json");
execFileSync("uv", ["run", "tariff-api", "openapi", "-o", freshSpecPath], { cwd: repo, env, stdio: "inherit" });
const committedSpec = readFileSync(join(here, "openapi.json"), "utf8");
const freshSpec = readFileSync(freshSpecPath, "utf8");

let drift = false;
if (committedSpec !== freshSpec) {
  console.error("DRIFT: packages/contracts/openapi.json differs from the running service. Run `make contracts`.");
  drift = true;
}

const freshTypes = join(tmp, "api.d.ts");
execFileSync("npx", ["openapi-typescript", join(here, "openapi.json"), "-o", freshTypes, "--alphabetize"], {
  cwd: here,
  stdio: "inherit",
});
const committedTypes = readFileSync(join(here, "src/api.d.ts"), "utf8");
if (committedTypes !== readFileSync(freshTypes, "utf8")) {
  console.error("DRIFT: packages/contracts/src/api.d.ts is stale. Run `make contracts`.");
  drift = true;
}
writeFileSync(join(tmp, "result.txt"), drift ? "drift" : "ok");
if (drift) process.exit(1);
console.log("contracts: no drift");
