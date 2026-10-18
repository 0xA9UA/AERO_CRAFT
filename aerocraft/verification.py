"""Evidence-bound port progress and release checks; packaging is not completion."""

from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid
import xml.etree.ElementTree as ET
import zipfile

from .common import CraftError, RUNTIME, read_json, sha256, write_json
from . import bedrock, inventory, porting, projects, toolchains


def fingerprint(project):
    """Hash inputs, including generators and tests, but never generated receipts."""
    project = Path(project).resolve()
    inputs = {}
    for name in ("aero-project.json", "aero-port.json", "package.json", "package-lock.json", "tsconfig.json"):
        p = project / name
        if p.is_symlink():
            raise CraftError(f"Verification inputs must not be symlinks: {p}")
        if p.is_file():
            inputs[name] = sha256(p)
    for name in ("packs", "src", "tests"):
        if (project / name).is_symlink():
            raise CraftError(f"Verification inputs must not be symlinks: {project / name}")
        for p in sorted((project / name).rglob("*")):
            if p.is_symlink():
                raise CraftError(f"Verification inputs must not be symlinks: {p}")
            if p.is_file():
                inputs[p.relative_to(project).as_posix()] = sha256(p)
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return {"sha256": digest, "files": inputs}


def start_port(source, project, mod_id, profile="bedrock-stable", client_platform="android", latest=False):
    """Create/adopt a project and durable required-feature contract without replacing files."""
    source, project = Path(source).resolve(), Path(project).resolve()
    if not source.is_file():
        raise CraftError("Start-port requires an existing source JAR/MCADDON; inspect source directories separately.")
    identity = inventory.inspect_artifact(source)
    if not project.exists():
        projects.create(project, profile, mod_id)
    config = read_json(project / "aero-project.json")
    if config.get("loader") != "bedrock":
        raise CraftError("The verified port workflow currently targets Bedrock projects.")
    contract_path = project / "aero-port.json"
    if contract_path.exists():
        existing = read_json(contract_path)
        if existing.get("source", {}).get("sha256") != identity["sha256"]:
            raise CraftError("This project already tracks a different source. Use a new project.")
        return {"project": str(project), "contract": str(contract_path), "created": False, "next": status(project)}
    target = {k: config[k] for k in ("profile", "minecraft", "server_api", "engine_version")}
    target["requested_latest"] = bool(latest)
    target["resolution"] = None
    contract = {
        "schema_version": 1,
        "source": {"path": str(source), "sha256": identity["sha256"]},
        "target": target,
        "client_platform": client_platform,
        "features": [{"feature": key, "required": True, "status": "unassessed",
                      "source_evidence": [], "target_implementation": [], "tests": [],
                      "native_assertions": [], "adaptation": "", "guidance": value}
                     for key, value in porting.FEATURES.items()],
        "acceptance": {"native_scenario_required": True, "connected_client_required": True},
    }
    write_json(contract_path, contract)
    write_json(project / ".aero/source-inventory.json", identity)
    return {"project": str(project), "contract": str(contract_path), "created": True,
            "next": "Implement and verify one generator → cable → machine slice before expanding content. Run verify_project; use port_status after every repair. Required features cannot be dropped to obtain completion."}


def _local_file(project, value):
    if not isinstance(value, str) or not value:
        return None
    p = (project / value).resolve()
    return p if p.is_relative_to(project) and p.is_file() else None


def _gate(project):
    """Read-only, fail-closed release verdict. Never trust prose or file counts."""
    project = Path(project).resolve()
    blockers = []
    static = bedrock.validate(project)
    blockers.extend(static["errors"])
    report_path = project / ".aero/verification/latest.json"
    report = read_json(report_path) if report_path.is_file() else {}
    if report.get("passed") is not True or report.get("failure"):
        blockers.append("The latest verification run did not pass as a whole.")
    current = fingerprint(project)
    if report.get("inputs", {}).get("sha256") != current["sha256"]:
        blockers.append("Verification is missing or stale. Run verify_project for these exact source, pack and test files.")
    for layer in ("static", "api", "unit", "build", "native"):
        if report.get("layers", {}).get(layer, {}).get("passed") is not True:
            blockers.append(f"Required {layer} verification has not passed.")
    if report.get("layers", {}).get("build", {}).get("deterministic") is not True:
        blockers.append("Deterministic artifact packaging has not been verified.")
    artifact = report.get("artifact") or {}
    artifact_path = _local_file(project, artifact.get("path"))
    if not artifact_path or sha256(artifact_path) != artifact.get("sha256"):
        blockers.append("No unchanged, hash-bound addon artifact has been verified.")
    candidate_ready = not blockers
    contract_path = project / "aero-port.json"
    contract = read_json(contract_path) if contract_path.is_file() else None
    if contract is None:
        blockers.append("No aero-port.json acceptance contract. Start/adopt the port with start_port before claiming completion.")
    else:
        source = Path(contract.get("source", {}).get("path", ""))
        if not source.is_file() or sha256(source) != contract.get("source", {}).get("sha256"):
            blockers.append("The recorded source artifact is missing or its hash changed.")
            candidate_ready = False
        source_members = set()
        if source.is_file() and zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as z:
                source_members = set(z.namelist())
        passed_tests = set(report.get("layers", {}).get("unit", {}).get("passed_tests", []))
        native = report.get("layers", {}).get("native", {})
        passed_native = {a.get("name") for a in (native.get("scenario") or {}).get("assertions", []) if a.get("passed") is True}
        features = contract.get("features", [])
        represented = {f.get("feature") for f in features if isinstance(f, dict)}
        for missing in set(porting.FEATURES) - represented:
            blockers.append(f"Required feature category {missing} was removed from the port contract.")
        for feature in features:
            name = feature.get("feature", "unnamed")
            if feature.get("required") is not True:
                blockers.append(f"{name}: removing required scope is not evidence of a completed port.")
            if feature.get("status") not in {"implemented", "adapted", "verified"}:
                blockers.append(f"{name}: status is {feature.get('status', 'unassessed')}.")
            if feature.get("status") == "adapted" and not feature.get("adaptation", "").strip():
                blockers.append(f"{name}: describe the target adaptation and its behavior limits.")
            evidence = feature.get("source_evidence", [])
            if not evidence or any(not isinstance(e, str) or e.split("#", 1)[0] not in source_members for e in evidence):
                blockers.append(f"{name}: source_evidence must identify actual source archive members (optionally #method).")
            implementation = feature.get("target_implementation", [])
            if not implementation or any(not _local_file(project, p) for p in implementation):
                blockers.append(f"{name}: target_implementation must identify existing project files.")
            tests = feature.get("tests", [])
            assertions = feature.get("native_assertions", [])
            if not tests and not assertions:
                blockers.append(f"{name}: no executable acceptance test is mapped to this feature.")
            if any(t not in passed_tests for t in tests):
                blockers.append(f"{name}: one or more named unit tests did not pass in the current verification run.")
            if any(t not in passed_native for t in assertions):
                blockers.append(f"{name}: one or more native scenario assertions did not pass.")
        if features and passed_tests == {"energy caps without mutating the saved state"}:
            blockers.append("The unchanged starter test does not verify a mod port's mechanics.")
        acceptance = contract.get("acceptance", {})
        if acceptance.get("native_scenario_required") is not True or acceptance.get("connected_client_required") is not True:
            blockers.append("Required native scenario and connected-client acceptance cannot be disabled.")
        if not passed_native:
            blockers.append("Add tests/native-smoke.js with project-specific gameplay and restart assertions; generic boot checks are insufficient.")
        if contract.get("target", {}).get("requested_latest"):
            resolution = contract.get("target", {}).get("resolution") or {}
            if (resolution.get("resolved") is not True or not resolution.get("checked_at")
                    or resolution.get("profile_matches_latest") is not True):
                blockers.append("The requested latest target has not been resolved against official release metadata.")
            expected_server = resolution.get("bedrock_server_version")
            if expected_server and native.get("server_version") != expected_server:
                blockers.append("Native verification did not run on the resolved latest Bedrock server version.")
        client_path = project / ".aero/client-evidence.json"
        client = read_json(client_path) if client_path.is_file() else {}
        if (client.get("artifact_sha256") != artifact.get("sha256") or not artifact.get("sha256")
                or client.get("platform") != contract.get("client_platform")
                or client.get("observed") is not True or not client.get("observer")
                or not client.get("minecraft_version")):
            blockers.append("Connected-client evidence is missing for this exact artifact and target platform. Do not infer Android visuals/touch behavior from BDS.")
        raw_version = client.get("minecraft_version", "")
        observed = [int(x) for x in raw_version.split(".")] if isinstance(raw_version, str) and re.fullmatch(r"\d+(?:\.\d+){1,3}", raw_version) else []
        if len(observed) == 2 and observed[0] >= 20:
            observed.insert(0, 1)  # Store labels such as 26.52 use the 1.26.52 engine line.
        minimum = contract.get("target", {}).get("engine_version", [1, 26, 50])
        if len(observed) < 3 or observed[:3] < minimum:
            blockers.append("Observed client Minecraft version is missing, invalid, or older than the target engine requirement.")
        required_checks = {"import", "activation", "visible_content", "textures", "interaction", "restart"}
        if not required_checks.issubset(set(client.get("passed_checks", []))):
            blockers.append("Client checks must cover import, activation, visible_content, textures, interaction and restart.")
        evidence_files = client.get("evidence", [])
        if not evidence_files or any(not _local_file(project, p) for p in evidence_files):
            blockers.append("Client evidence must reference captured screenshots/logs stored in the project; a claimed pass alone is insufficient.")
    blockers = list(dict.fromkeys(blockers))
    return {"passed": not blockers, "ready": not blockers, "candidate_ready": candidate_ready,
            "project": str(project),
            "artifact": {"path": str(artifact_path), "sha256": artifact.get("sha256")} if artifact_path else None,
            "blockers": blockers, "verification": str(report_path),
            "scope": "Recorded acceptance and executed checks for exact inputs; this gate is not a proof of arbitrary mod equivalence."}


def gate(project):
    """Return actionable not-ready JSON even when saved evidence is malformed."""
    try:
        return _gate(project)
    except (CraftError, OSError, ValueError, TypeError, KeyError, AttributeError, zipfile.BadZipFile) as exc:
        return {"passed": False, "ready": False, "candidate_ready": False,
                "project": str(Path(project).resolve()), "artifact": None,
                "blockers": [f"Invalid or unreadable project/verification evidence: {exc}. Repair it and rerun verify_project."],
                "verification": str(Path(project).resolve() / ".aero/verification/latest.json")}


def status(project):
    verdict = gate(project)
    verdict["next_actions"] = list(dict.fromkeys([
        "Fix the content/API failures; never suppress them to get a green build.",
        "Implement one working end-to-end machine chain and tests before generating the remaining catalog.",
        "Run verify_project, repair reported failures, then run port_status again.",
        "Keep every required feature and unobserved client behavior explicit until verified.",
    ])) if not verdict["ready"] else []
    return verdict


def _run(command, project, log, timeout=900):
    """Capture direct subprocess status, never a shell pipeline's final exit code."""
    try:
        result = subprocess.run([str(x) for x in command], cwd=project,
                                env=toolchains.environment(), capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout)
        text = result.stdout + result.stderr
        log.write_text(text, encoding="utf-8")
        return {"passed": result.returncode == 0, "exit_code": result.returncode,
                "log": str(log), "tail": text[-8000:]}, result.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.write_text(str(exc), encoding="utf-8")
        return {"passed": False, "log": str(log), "error": str(exc)}, ""


def build_checks(project, output):
    """Enforce API coverage and run real test files, independent of npm script aliases."""
    project, output = Path(project).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = read_json(project / "aero-project.json")
    toolchains.npm(["ci", "--no-audit", "--no-fund"], project)
    for name, expected in (("@minecraft/server", config["server_api"]),
                           ("@minecraft/server-ui", config["server_ui_api"]),
                           ("typescript", config["typescript"])):
        if read_json(project / "node_modules" / name / "package.json")["version"] != expected:
            raise CraftError(f"Installed {name} does not match aero-project.json.")
    type_config = output / "tsconfig.json"
    # TypeScript globs need forward slashes even on Windows.
    write_json(type_config, {"compilerOptions": {"target": "ES2022", "module": "ESNext",
               "moduleResolution": "Bundler", "strict": True, "allowJs": True, "checkJs": True,
               "noEmit": True, "skipLibCheck": True},
               "include": [(project / "packs/**/*.js").as_posix()]})
    api, _ = _run([toolchains.node(), project / "node_modules/typescript/bin/tsc",
                   "--project", type_config], project, output / "typecheck.log")
    test_files = sorted(p for p in (project / "tests").rglob("*")
                        if p.name.endswith((".test.mjs", ".test.js", ".test.cjs")))
    if not test_files:
        unit = {"passed": False, "error": "No executable *.test.mjs/js/cjs files under tests/.", "passed_tests": []}
    else:
        unit, stdout = _run([toolchains.node(), "--test", "--test-reporter=junit", *test_files], project, output / "unit.xml")
        try:
            xml = ET.fromstring(stdout)
            cases = list(xml.iter("testcase"))
            invoked_files = {p.resolve() for p in test_files}
            unit["passed_tests"] = [c.attrib["name"] for c in cases
                                    if c.find("failure") is None and c.find("error") is None and c.find("skipped") is None
                                    and (project / c.attrib["name"].replace("\\", "/")).resolve() not in invoked_files]
            unit["passed"] = unit["passed"] and bool(unit["passed_tests"])
        except (ET.ParseError, KeyError):
            unit.update(passed=False, passed_tests=[], error="Could not verify Node's JUnit test results.")
    return {"api": api, "unit": unit}


def verify(project, server=None, timeout=120):
    project = Path(project).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = project / ".aero/verification" / stamp
    output.mkdir(parents=True)
    result = {"schema_version": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
              "inputs": fingerprint(project), "layers": {}, "artifact": None, "passed": False,
              "scope": "Content checks, mandatory API typecheck, named unit tests, deterministic build, native registry/gameplay/restart. Client checks remain separate."}
    layers = result["layers"]
    layers["static"] = bedrock.validate(project)
    try:
        if layers["static"]["passed"]:
            layers.update(build_checks(project, output))
            if layers["api"]["passed"] and layers["unit"]["passed"]:
                package = bedrock.package(project)
                artifact = Path(package["artifact"])
                result["artifact"] = {"path": artifact.relative_to(project).as_posix(), "sha256": sha256(artifact)}
                again = bedrock.package(project)
                layers["build"] = {"passed": sha256(again["artifact"]) == result["artifact"]["sha256"], "deterministic": True}
                from .smoke import bedrock_smoke
                native_output = RUNTIME / "verification-native" / stamp
                layers["native"] = bedrock_smoke(project, server, native_output, timeout)
    except (CraftError, OSError, ValueError, subprocess.SubprocessError) as exc:
        result["failure"] = str(exc)
    for layer in ("api", "unit", "build", "native"):
        layers.setdefault(layer, {"passed": False, "status": "not_run"})
    if result["inputs"] != fingerprint(project):
        result["failure"] = "Project inputs changed during verification. Rerun against stable inputs."
    result["passed"] = all(layers[k]["passed"] for k in ("static", "api", "unit", "build", "native")) and "failure" not in result
    write_json(output / "report.json", result)
    write_json(project / ".aero/verification/latest.json", result)
    # Verification success means the executed layers passed; release readiness is separate.
    result["release"] = gate(project)
    result["report"] = str(output / "report.json")
    return result
