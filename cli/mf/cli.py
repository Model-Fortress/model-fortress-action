"""`mf` — the Model Fortress CI/CD command line.

Scan or red-team a model from a pipeline and fail the build on a policy-gate breach.

    mf scan    --model-id <id> --tool modelscan      # static scan + gate
    mf redteam --model-id <id> --probes dan,encoding  # red-team + gate
    mf gate    --scan-id <id> | --run-id <id>         # verdict for an existing job
    mf export  --job-id <id> --format sarif -o out.sarif.json
    mf models  list

Config comes from flags or the environment:
    MF_API_BASE   e.g. https://app.au2mait.com/api   (your instance's API base)
    MF_TOKEN      a Personal Access Token
    MF_TENANT     your tenant id

Exit codes:  0 = passed   1 = gate breached / job failed / timed out   2 = usage or transport error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from .client import ApiError, Client, GateTimeout
from . import __version__

# Terminal statuses per job kind.
SCAN_TERMINAL = {"DONE", "FAILED", "COMPLETED", "SUCCESS", "CLEAN", "ERROR", "CANCELLED"}
RT_TERMINAL = {"DONE", "PARTIAL", "FAILED", "CANCELLED"}

EXT = {"sarif": "sarif.json", "json": "json", "csv": "csv", "pdf": "pdf"}


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _info(msg: str) -> None:
    print(msg, file=sys.stderr)


def _client(args: argparse.Namespace) -> Client:
    return Client(
        api_base=args.api_base,
        token=args.token,
        tenant=args.tenant,
        timeout=args.http_timeout,
    )


def _poll(client: Client, path: str, status_key: str, terminal: set[str], timeout: int, interval: int) -> dict:
    deadline = time.time() + timeout
    last: Any = {}
    while time.time() < deadline:
        last = client.data(client.get(path))
        status = str((last or {}).get(status_key, "")).upper()
        if status in terminal:
            return last
        time.sleep(interval)
    raise GateTimeout(f"timed out after {timeout}s waiting for {status_key} to finish")


def _emit_gate(args: argparse.Namespace, verdict: dict, job_id: str, kind: str) -> int:
    print(json.dumps(verdict, indent=2))
    if not getattr(args, "gate", True):
        return 0
    gate = (verdict or {}).get("gate", {}) if isinstance(verdict, dict) else {}
    if gate.get("passed"):
        _info(f"PASS — {kind} {job_id}")
        return 0
    if not gate.get("evaluated"):
        # No governing policy / nothing to gate on. Don't fail the build on its own,
        # unless the job itself failed (passed will be False then too, handled below).
        if gate.get("passed") is not False:
            _info(f"PASS — {kind} {job_id} (no policy gate evaluated)")
            return 0
    reason = "gate breached" if gate.get("breached") else f"{kind} did not pass"
    _err(f"FAIL — {reason} (fail_on={gate.get('fail_on')})")
    return 1


# ------------------------------- commands -------------------------------
def cmd_scan(args: argparse.Namespace) -> int:
    c = _client(args)
    scan_id = args.scan_id
    if not scan_id:
        if not args.model_id:
            _err("provide --scan-id (existing) or --model-id (to trigger a new scan)")
            return 2
        body: dict[str, Any] = {"scan_tool": args.tool}
        if args.metadata:
            body["scan_metadata"] = json.loads(args.metadata)
        created = c.data(c.post(f"/model-governance/model/{args.model_id}/model-scan", body))
        scan_id = created.get("scan_id")
        _info(f"started scan {scan_id}")
    if not args.wait:
        print(scan_id)
        return 0
    verdict = _poll(
        c,
        f"/model-governance/model-scan/{scan_id}/gate",
        status_key="scan_status",
        terminal=SCAN_TERMINAL,
        timeout=args.timeout,
        interval=args.poll,
    )
    return _emit_gate(args, verdict, str(scan_id), "scan")


def cmd_redteam(args: argparse.Namespace) -> int:
    c = _client(args)
    run_id = args.run_id
    if not run_id:
        if not args.model_id:
            _err("provide --run-id (existing) or --model-id (to trigger a new run)")
            return 2
        rto: dict[str, Any] = {}
        if args.probes:
            rto["probes"] = args.probes
        if args.generations:
            rto["generations"] = args.generations
        metadata: dict[str, Any] = {"red_team_options": rto}
        if args.metadata:
            metadata.update(json.loads(args.metadata))
        body = {"llm_red_teaming_tool": args.tool, "llm_red_teaming_metadata": metadata}
        created = c.data(c.post(f"/model-governance/model/{args.model_id}/llm-red-teaming", body))
        run_id = created.get("llm_red_teaming_id")
        _info(f"started red-team run {run_id}")
    if not args.wait:
        print(run_id)
        return 0
    _poll(
        c,
        f"/model-governance/llm-red-teaming/{run_id}",
        status_key="llm_red_teaming_status",
        terminal=RT_TERMINAL,
        timeout=args.timeout,
        interval=args.poll,
    )
    verdict = c.data(c.get(f"/model-governance/llm-red-teaming/{run_id}/gate"))
    return _emit_gate(args, verdict, str(run_id), "redteam")


def cmd_gate(args: argparse.Namespace) -> int:
    c = _client(args)
    if args.scan_id:
        v = c.data(c.get(f"/model-governance/model-scan/{args.scan_id}/gate"))
        return _emit_gate(args, v, args.scan_id, "scan")
    if args.run_id:
        v = c.data(c.get(f"/model-governance/llm-red-teaming/{args.run_id}/gate"))
        return _emit_gate(args, v, args.run_id, "redteam")
    _err("provide --scan-id or --run-id")
    return 2


def cmd_export(args: argparse.Namespace) -> int:
    c = _client(args)
    raw = c.request("GET", f"/jobs/{args.job_id}/export", query=f"format={args.format}", raw=True)
    out = args.output or f"{args.job_id}.{EXT.get(args.format, args.format)}"
    with open(out, "wb") as f:
        f.write(raw)
    _info(f"wrote {out} ({len(raw)} bytes)")
    print(json.dumps({"job_id": args.job_id, "format": args.format, "output": out, "bytes": len(raw)}))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    c = _client(args)
    resp = c.data(c.get("/model-governance/models", query="page=1&page_size=100"))
    items = resp.get("items", []) if isinstance(resp, dict) else (resp or [])
    if args.json:
        print(json.dumps(items, indent=2))
        return 0
    for m in items:
        print(
            "\t".join(
                [
                    str(m.get("model_id", "")),
                    str(m.get("model_name", "")),
                    str(m.get("model_source", "")),
                    str(m.get("model_upload_status", m.get("upload_status", ""))),
                ]
            )
        )
    return 0


# ------------------------------- parser -------------------------------
def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--api-base", default=os.environ.get("MF_API_BASE"), help="e.g. https://app.au2mait.com/api  [env MF_API_BASE]")
    p.add_argument("--token", default=os.environ.get("MF_TOKEN"), help="Personal Access Token  [env MF_TOKEN]")
    p.add_argument("--tenant", default=os.environ.get("MF_TENANT"), help="tenant id  [env MF_TENANT]")
    p.add_argument("--http-timeout", type=int, default=int(os.environ.get("MF_HTTP_TIMEOUT", "30")), help="per-request timeout seconds")


def _add_wait(p: argparse.ArgumentParser) -> None:
    p.add_argument("--wait", dest="wait", action="store_true", default=True, help="wait for the job to finish (default)")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="submit and print the id, don't wait")
    p.add_argument("--gate", dest="gate", action="store_true", default=True, help="fail the build on a gate breach (default)")
    p.add_argument("--no-gate", dest="gate", action="store_false", help="print the verdict but always exit 0")
    p.add_argument("--timeout", type=int, default=1800, help="max seconds to wait for completion")
    p.add_argument("--poll", type=int, default=5, help="seconds between status polls")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mf", description="Model Fortress CI/CD client")
    ap.add_argument("--version", action="version", version=f"mf {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="run a static scan and gate on its policy verdict")
    _add_common(p); _add_wait(p)
    p.add_argument("--model-id", help="model to scan (triggers a new scan)")
    p.add_argument("--scan-id", help="gate on an existing scan instead")
    p.add_argument("--tool", default="modelscan", help="scanner: modelscan | modelaudit | picklescan | gguf-scan")
    p.add_argument("--metadata", help="extra scan_metadata as a JSON string")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("redteam", help="run a red-team assessment and gate on its policy verdict")
    _add_common(p); _add_wait(p)
    p.add_argument("--model-id", help="model to red-team (triggers a new run)")
    p.add_argument("--run-id", help="gate on an existing run instead")
    p.add_argument("--tool", default="model_red_teaming", help="engine: model_red_teaming | openrt | pyrit | art")
    p.add_argument("--probes", help="comma-separated probe spec, e.g. dan,encoding")
    p.add_argument("--generations", type=int, help="generations per probe")
    p.add_argument("--metadata", help="extra llm_red_teaming_metadata as a JSON string")
    p.set_defaults(func=cmd_redteam)

    p = sub.add_parser("gate", help="fetch the policy-gate verdict for an existing job")
    _add_common(p)
    p.add_argument("--scan-id")
    p.add_argument("--run-id")
    p.set_defaults(func=cmd_gate, gate=True)

    p = sub.add_parser("export", help="download a job's findings (SARIF/JSON/CSV/PDF)")
    _add_common(p)
    p.add_argument("--job-id", required=True, help="a scan id or red-team run id")
    p.add_argument("--format", default="sarif", choices=["sarif", "json", "csv", "pdf"])
    p.add_argument("-o", "--output", help="output file (default <job-id>.<ext>)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("models", help="model inventory")
    psub = p.add_subparsers(dest="models_command", required=True)
    pl = psub.add_parser("list", help="list models")
    _add_common(pl)
    pl.add_argument("--json", action="store_true", help="output JSON")
    pl.set_defaults(func=cmd_models)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except GateTimeout as e:
        _err(str(e))
        return 1
    except ApiError as e:
        _err(str(e))
        return 2
    except ValueError as e:
        _err(f"bad --metadata JSON: {e}")
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
