# Model Fortress — CI/CD & API

Scan and red-team your models from a pipeline and **fail the build on a policy-gate
breach**. Ships as a small, dependency-free Python CLI (`mf`) over the public API.

Cloud-agnostic by design: the CLI talks to **your instance's API base URL** with a
Personal Access Token, so the same pipeline works whether you bought Model Fortress on
the **Azure, AWS or GCP marketplace** — only `MF_API_BASE` changes.

## Install

```bash
pip install ./backend/ci        # from this repo
# or, once published:  pip install model-fortress-cli
```

The CLI is stdlib-only (no third-party deps), so it runs in any CI image.

## Configure

| Env | Flag | Meaning |
|-----|------|---------|
| `MF_API_BASE` | `--api-base` | your instance's API base, e.g. `https://app.au2mait.com/api` |
| `MF_TOKEN`    | `--token`    | a Personal Access Token (create one in the app → settings) |
| `MF_TENANT`   | `--tenant`   | your tenant id |

## Commands

```bash
# Static scan: submit, wait, fail on the policy gate
mf scan --model-id <id> --tool modelscan      # modelscan | modelaudit | picklescan | gguf-scan

# Red-team: submit, wait, fail on the policy gate
mf redteam --model-id <id> --probes dan,encoding --generations 5

# Verdict for an existing job (no wait)
mf gate --scan-id <id>
mf gate --run-id  <id>

# Download findings (SARIF for code-scanning dashboards, or JSON/CSV/PDF)
mf export --job-id <id> --format sarif -o mf.sarif.json

# Inventory
mf models list
```

Useful flags on `scan` / `redteam`: `--no-wait` (submit and print the id),
`--no-gate` (print the verdict but never fail), `--timeout` (max wait, default 1800s),
`--poll` (seconds between polls, default 5), `--metadata '<json>'`.

## Exit codes

| Code | Meaning |
|------|---------|
| `0`  | gate passed (or `--no-gate`) |
| `1`  | **gate breached, job failed, or timed out** — fail the build |
| `2`  | usage or transport error (bad flags, unreachable API, auth) |

The gate is **fail-closed**: a failed scan/run never passes, a breach fails the build,
and a job with no governing policy doesn't fail on its own.

## The gate endpoints

```
GET /tenant/<t>/model-governance/model-scan/<scan_id>/gate
GET /tenant/<t>/model-governance/llm-red-teaming/<run_id>/gate
```
both return `{ ..._status, policy_id, policy_name, gate: { evaluated, fail_on, breached, passed } }`.
Auth: `Authorization: Bearer <PAT>`. The "fail on <severity>" threshold comes from the
Scan Policy governing that model.

## Pipeline examples

- `examples/github-actions.yml` — PR gate + SARIF upload to the Security tab
- `examples/gitlab-ci.yml` — MR gate + SAST report
- `examples/azure-pipelines.yml`
- `examples/generic.sh` — Jenkins / CircleCI / cron

## Notes

- Create a **Personal Access Token** per pipeline and store it as a CI secret; scope it
  to the tenant you're gating.
- `mf_scan_gate.py` (the earlier single-file script) still works and is kept for
  back-compat, but the `mf` CLI supersedes it and adds red-teaming, export and inventory.
