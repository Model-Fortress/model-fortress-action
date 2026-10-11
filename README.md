# Model Fortress — GitHub Action

Scan and red-team your AI models on every PR and **fail the build on a policy-gate
breach**, with findings published to the **Security** tab as SARIF.

Cloud-agnostic: point `api-base` at your instance (SaaS or an Azure / AWS / GCP
marketplace install) and authenticate with a Personal Access Token.

## Usage

```yaml
permissions:
  contents: read
  security-events: write   # required for the SARIF upload

jobs:
  model-security:
    runs-on: ubuntu-latest
    steps:
      - uses: your-org/model-fortress-action@v1
        with:
          api-base: ${{ secrets.MF_API_BASE }}
          token:    ${{ secrets.MF_TOKEN }}
          tenant:   ${{ secrets.MF_TENANT }}
          model-id: ${{ vars.MODEL_ID }}
          # optional:
          scan-tool: modelscan
          redteam:   "true"
          probes:    "dan,encoding"
          generations: "5"
```

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `api-base` | — (required) | Instance API base, e.g. `https://app.au2mait.com/api` |
| `token` | — (required) | Personal Access Token (store as a secret) |
| `tenant` | — (required) | Tenant id |
| `model-id` | — (required) | Model to test |
| `scan` | `true` | Run a static scan |
| `scan-tool` | `modelscan` | `modelscan` / `modelaudit` / `picklescan` / `gguf-scan` |
| `redteam` | `false` | Also run a red-team assessment |
| `probes` | `""` | Red-team probe spec, e.g. `dan,encoding` |
| `generations` | `""` | Red-team generations per probe |
| `fail-on-gate` | `true` | Fail the build on a policy-gate breach |
| `upload-sarif` | `true` | Export + upload SARIF to the Security tab |
| `timeout` | `1800` | Max seconds to wait per job |
| `python-version` | `3.11` | Python used to run the CLI |
| `cli-version` | `""` | Install this `model-fortress-cli` from PyPI instead of the bundled copy |
| `cli-source` | `""` | Install the CLI from this pip source instead of the bundled copy |

## Outputs

| Output | Description |
|--------|-------------|
| `scan-id` | id of the scan that ran |
| `run-id` | id of the red-team run that ran |

The action bundles the `mf` CLI, so it works without any PyPI dependency. Pin a
published version with `cli-version` once `model-fortress-cli` is on PyPI.

## Publishing to the GitHub Marketplace

1. Put this folder in its own public repo, e.g. `your-org/model-fortress-action`
   (`action.yml` must be at the repo root).
2. Tag a release: `git tag v1.0.0 && git push --tags`, then on the GitHub release
   page tick **"Publish this Action to the GitHub Marketplace"**.
3. Maintain a moving **`v1`** tag so consumers can pin `@v1` — the included
   `.github/workflows/retag.yml` does this automatically on each `v1.*` release.
