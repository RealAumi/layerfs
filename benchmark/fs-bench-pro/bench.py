#!/usr/bin/env python3
"""Single entry point for the fs-bench-pro workload rollout."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import uuid

HERE = Path(__file__).resolve().parent


def catalogue(tier=None):
    rows = []
    for path in sorted((HERE / "families").glob("*/family.json")):
        family = json.loads(path.read_text())
        if family["family"] != path.parent.name:
            raise ValueError("family path/name mismatch: " + str(path))
        for case in family["cases"]:
            rows.append({"family": family["family"], **case})
    if len({(row["family"], row["id"]) for row in rows}) != len(rows):
        raise ValueError("duplicate family/case identity")
    if tier is not None:
        tiers = json.loads((HERE / "tiers.json").read_text())
        if tier not in tiers:
            raise ValueError("unknown declared tier: " + tier)
        by_key = {(row["family"], row["id"]): row for row in rows}
        selected = [(family, case) for family, cases in tiers[tier].items() for case in cases]
        if len(set(selected)) != len(selected) or any(key not in by_key for key in selected):
            raise ValueError("tier has duplicate or unregistered case")
        rows = [by_key[key] for key in selected]
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="every frozen family and case")
    listing.add_argument("--json", action="store_true")
    listing.add_argument("--tier", choices=("everyday", "heavy"))
    building = commands.add_parser("build", help="locked release runtime and pinned-image daemon")
    building.add_argument("--out", type=Path)
    building.add_argument("--reuse-unchanged", type=Path,
                          help="qualified full build; rebuild host runtime only and retain exact unchanged binary scopes")
    preparing = commands.add_parser("prepare", help="build a sealed fixture master from a committed recipe")
    preparing.add_argument("fixture")
    preparing.add_argument("--build", type=Path, required=True)
    preparing.add_argument("--out", type=Path)
    preparing.add_argument("--reuse-producer", type=Path, help="sealed historical setup preparation with the same complete original producer")
    running = commands.add_parser("run", help="one sample per selected case at this clean identity")
    running.add_argument("family")
    running.add_argument("--case")
    running.add_argument("--build", type=Path, required=True)
    running.add_argument("--prepared", type=Path, required=True)
    running.add_argument("--out", type=Path, required=True)
    verifying = commands.add_parser("verify", help="verify retained observations without replaying a sample")
    verifying.add_argument("run", type=Path)
    verifying.add_argument("--membership-audit", type=Path,
                           help="fresh offline census of copies of retained closed Stores; no sample replay")
    verifying.add_argument("--build", type=Path)
    reporting = commands.add_parser("report", help="generate the two CSVs and report-template table")
    reporting.add_argument("run", type=Path)
    parity = commands.add_parser("parity", help="original fixture/operation/oracle parity for a ported family")
    parity.add_argument("family")
    parity.add_argument("--prepared", type=Path, required=True)
    parity.add_argument("--out", type=Path, required=True)
    parity.add_argument("--build", type=Path,
                        help="sealed runtime/native build required by contextual and historical parity")
    args = parser.parse_args(argv)
    if args.command == "build":
        from engine import identity
        results = identity.ROOT / "benchmark-results/fs-bench-pro"
        output = args.out or results / ("build-" + uuid.uuid4().hex)
        output = output.resolve()
        if not output.is_relative_to(results.resolve()):
            parser.error("build output must be a fresh directory under benchmark-results/fs-bench-pro")
        result = (identity.build_runtime(output, args.reuse_unchanged)
                  if args.reuse_unchanged is not None else identity.build(output))
        print(json.dumps({"build": str(output), "status": result["status"],
                          "binaries": result["binaries"]}, indent=2))
        return
    if args.command == "run":
        from engine import fixtures, identity, io_observer, project, receipts, workspace
        current = identity.source_identity()
        if args.family not in ("cluster-two/cells", "init_namespace", *fixtures.IMPORT_FAMILIES, *fixtures.WORKSPACE_FAMILIES):
            parser.error("family workload runner is not implemented yet; all workload cases remain visible in list")
        registered = ([{"id": cell, "cache_class": "B", "v016_case": ""} for cell in fixtures.CELL_RECIPES]
            if args.family == "cluster-two/cells" else json.loads((HERE / "families" / args.family / "family.json").read_text())["cases"])
        if args.case and args.case not in {case["id"] for case in registered}:
            parser.error("case is not in this frozen selection")
        if any(case.get("status") == "pending" for case in registered):
            parser.error("pending cases cannot be sampled")
        output = args.out.resolve()
        results = identity.ROOT / "benchmark-results/fs-bench-pro"
        if not output.is_relative_to(results.resolve()):
            parser.error("run output must be under benchmark-results/fs-bench-pro")
        output.mkdir(parents=True, exist_ok=True)
        selection_file = output / "run.json"
        if selection_file.exists():
            selection = json.loads(selection_file.read_text())
            if (selection["family"], selection["source_commit"], selection["product_tree"], selection["cases"]) != (
                    args.family, current["source_commit"], current["product_tree"], registered):
                parser.error("run registration differs; append-only run cannot change identity")
        else:
            receipts.write_new(selection_file, {"family": args.family, "cases": registered,
                "source_commit": current["source_commit"], "source_tree": current["source_tree"],
                "product_tree": current["product_tree"], "image": identity.IMAGE,
                "date": datetime.now().strftime("%Y-%m-%d"), "identity": current,
                "build": str(args.build.resolve()), "prepared": str(args.prepared.resolve())})
        selected = [args.case] if args.case else [case["id"] for case in registered]
        failed = False
        for cell in selected:
            case = next(item for item in registered if item["id"] == cell)
            recipe = fixtures.CELL_RECIPES[cell] if args.family == "cluster-two/cells" else case["fixture"]["recipe"]
            prepared = args.prepared if (args.prepared / "prepared.json").exists() else args.prepared / recipe
            # Diagnostic kernel observer beside the case, outside every timer; see engine/io_observer.py.
            io_observer.start(output / (cell + ".io-observer"), args.build)
            try:
                if args.family == "cluster-two/cells":
                    result = workspace.one_cell(cell, prepared, args.build, output / cell)
                elif args.family in ("init_namespace", *fixtures.IMPORT_FAMILIES):
                    result = project.one_init(case, prepared, args.build, output / cell, family=args.family)
                elif args.family=="repository_history":
                    result = project.one_repository_history(case,prepared,args.build,output/cell)
                else:
                    result = workspace.one_family_case(args.family, case, prepared, args.build, output / cell)
            finally:
                io_observer.stop(output / cell)
            proof_only = case.get("proof_only") is True
            if proof_only and (result.get("proof_only") is not True or result.get("performance_mode") != "verification-only"
                               or type(result.get("sample_count")) is not int or result["sample_count"] != 0
                               or type(result.get("verification_attempt_count")) is not int or result["verification_attempt_count"] != 1):
                raise ValueError("verification-only driver requires one proof attempt and no performance sample")
            if result.get("publication_guard"):
                receipts.acknowledge_guarded(output / cell, result)
            if args.family in (*fixtures.IMPORT_FAMILIES, *fixtures.WORKSPACE_FAMILIES):
                workspace.dispose_family_resources(output / cell, result)
            print(json.dumps({**{key: result.get(key) for key in ("case", "status", "counts", "cleanup", "container", "original_failure", "evidence")},
                              "io_label": result.get("io_observer", {}).get("label")}))
            failed |= ((result.get("proof_status") != "PASS" or result.get("functional_status") != "PASS" or result["status"] == "FAIL")
                       if proof_only else result["status"] != "PASS")
        return 1 if failed else 0
    if args.command == "verify":
        from engine import fixtures, oracle, project, receipts
        if args.membership_audit is not None:
            if args.build is None:
                parser.error("a membership audit requires --build")
            result = project.audit_membership(args.run, args.build, args.membership_audit)
            print(json.dumps(result, indent=2))
            return 1 if result["status"] != "PASS" else 0
        if args.build is not None:
            parser.error("--build is selected only with --membership-audit")
        selection, recorded = receipts.load_run(args.run)
        results = []
        for case in selection["cases"]:
            folder = args.run / case["id"]
            if selection["family"] in ("init_namespace", *fixtures.IMPORT_FAMILIES, *fixtures.WORKSPACE_FAMILIES) and case["id"] in recorded:
                row = recorded[case["id"]]
                result = {"case": case["id"], "status": row["proof_status"],
                          "scope": "sealed retained independent public-read proof and original evidence hashes", "proof": row.get("verification")}
            elif (folder / "actual/observation.json").exists() and (folder / "expected/observation.json").exists():
                result = oracle.compare_recorded(folder / "expected", folder / "actual", case["id"])
            else:
                result = {"case": case["id"], "status": "NOT_RUN", "reason": "complete retained oracle evidence unavailable"}
            results.append(result)
        print(json.dumps(results, indent=2))
        return 1 if any(row["status"] not in ("PASS", "NOT_APPLICABLE") for row in results) else 0
    if args.command == "report":
        from engine import receipts
        result = receipts.report(args.run)
        print(result["table"])
        print("CSV destination: " + result["destination"])
        return
    if args.command == "parity":
        from engine import fixtures, project
        if args.family not in ("init_namespace", *fixtures.IMPORT_FAMILIES, *fixtures.WORKSPACE_FAMILIES):
            parser.error("this family's parity transcription is not implemented yet")
        family = json.loads((HERE / "families" / args.family / "family.json").read_text())
        try:
            result = (project.parity_namespace(family, args.prepared, args.out) if args.family == "init_namespace"
                      else project.parity_import(family, args.prepared, args.out, args.build) if args.family in fixtures.IMPORT_FAMILIES
                      else project.parity_repository_history(family,args.prepared,args.out,args.build) if args.family=="repository_history"
                      else project.parity_footprint(family,args.prepared,args.out,args.build) if args.family=="store_footprint"
                      else project.parity_workspace(family, args.prepared, args.out, build_folder=args.build)
                      if args.build is not None else project.parity_workspace(family, args.prepared, args.out))
        except project.ParityFailure as failure:
            result = failure.result
            print(json.dumps({"family": result["family"], "status": "FAIL", "cases": len(result["cases"]),
                              "samples": 0, "evidence": str(failure.output)}, indent=2))
            return 1
        print(json.dumps({"family": result["family"], "status": result["status"],
                          "cases": len(result["cases"]), "samples": 0}, indent=2))
        return 0
    if args.command == "prepare":
        from engine import fixtures, identity
        results = identity.ROOT / "benchmark-results/fs-bench-pro"
        output = args.out or results / ("prepared-" + args.fixture + "-" + uuid.uuid4().hex)
        output = output.resolve()
        if not output.is_relative_to(results.resolve()):
            parser.error("fixture output must be a fresh directory under benchmark-results/fs-bench-pro")
        if args.reuse_producer is None:
            result = fixtures.prepare(args.fixture, output, args.build)
        else:
            family, case = fixtures.family_case(args.fixture)
            if family["family"] != "historical_access":
                parser.error("--reuse-producer is limited to original historical access setup")
            result = fixtures.prepare_historical_workspace(family, case, output, args.build,
                                                          closed_producer_folder=args.reuse_producer)
        print(json.dumps({"prepared": str(output), "status": result["status"],
                          "master_volume": result["master_volume"], "fixture": result["fixture"]}, indent=2))
        return
    rows = catalogue(args.tier)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("family\tcase\tstatus\tv016_case\treference")
        for row in rows:
            reference = row.get("reference") or {}
            print("\t".join((row["family"], row["id"], row["status"], row["v016_case"],
                             reference.get("release", "UNAVAILABLE"))))
        print(f"families={len({row['family'] for row in rows})} cases={len(rows)}")


if __name__ == "__main__":
    raise SystemExit(main())
