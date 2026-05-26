#!/usr/bin/env python3
"""
Run this script from inside OpsMindAI-server:
  cd ~/Videos/OpsMindAI-final/OpsMindAI-server
  python3 patch_phase2.py
"""
import os, re, shutil, pathlib, sys

BASE = pathlib.Path(__file__).parent
AGENT   = BASE / "opsmindai/agents/testing/agent.py"
TESTGEN = BASE / "opsmindai/agents/testing/test_generator.py"
PYCACHE = BASE / "opsmindai/agents/testing/__pycache__"

def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

if not AGENT.exists():   die(f"Not found: {AGENT}")
if not TESTGEN.exists(): die(f"Not found: {TESTGEN}")

# ── Backup ────────────────────────────────────────────────────────────────────
for p in [AGENT, TESTGEN]:
    bak = p.with_suffix(".py.bak")
    if not bak.exists():
        shutil.copy2(p, bak)
        print(f"Backed up {p.name} → {bak.name}")

# ── Patch test_generator.py ───────────────────────────────────────────────────
tg = TESTGEN.read_text()

# 1. Add persistent_dir param to _output_path
OLD_OP = '''def _output_path(source_file: str, framework: str, repo_root: str = ".") -> str:'''
NEW_OP = '''def _output_path(source_file: str, framework: str, repo_root: str = ".", persistent_dir=None) -> str:'''
if OLD_OP in tg:
    tg = tg.replace(OLD_OP, NEW_OP, 1)
    print("✓ test_generator: patched _output_path signature")
elif "persistent_dir" in tg:
    print("✓ test_generator: _output_path already patched")
else:
    die("Could not find _output_path in test_generator.py")

# 2. Add persistent_dir logic inside _output_path (after the docstring, before stem=)
OLD_STEM = '''    stem = Path(source_file).stem
    if framework == "pytest":
        out = os.path.join(repo_root, "tests", "unit", f"test_{stem}.py")
    else:
        out = os.path.join(repo_root, "tests", "unit", f"{stem}.test.ts")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    return out'''
NEW_STEM = '''    stem = Path(source_file).stem
    if persistent_dir:
        os.makedirs(persistent_dir, exist_ok=True)
        if framework == "pytest":
            return os.path.join(persistent_dir, f"test_{stem}.py")
        else:
            return os.path.join(persistent_dir, f"{stem}.test.ts")
    if framework == "pytest":
        out = os.path.join(repo_root, "tests", "unit", f"test_{stem}.py")
    else:
        out = os.path.join(repo_root, "tests", "unit", f"{stem}.test.ts")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    return out'''
if OLD_STEM in tg:
    tg = tg.replace(OLD_STEM, NEW_STEM, 1)
    print("✓ test_generator: patched _output_path body")
elif "if persistent_dir:" in tg:
    print("✓ test_generator: _output_path body already patched")
else:
    die("Could not find _output_path body in test_generator.py")

# 3. Add persistent_dir param to generate_tests signature
OLD_SIG = '''    model: Optional[str] = None,
) -> GeneratedTests:'''
NEW_SIG = '''    model: Optional[str] = None,
    persistent_dir: Optional[str] = None,
) -> GeneratedTests:'''
if OLD_SIG in tg and "persistent_dir: Optional[str] = None," not in tg:
    tg = tg.replace(OLD_SIG, NEW_SIG, 1)
    print("✓ test_generator: patched generate_tests signature")
else:
    print("✓ test_generator: generate_tests signature already patched")

# 4. Pass persistent_dir to _output_path call
OLD_OUT = "    out_path = _output_path(file_path, framework, repo_root)"
NEW_OUT = "    out_path = _output_path(file_path, framework, repo_root, persistent_dir=persistent_dir)"
if OLD_OUT in tg:
    tg = tg.replace(OLD_OUT, NEW_OUT, 1)
    print("✓ test_generator: patched _output_path call")
elif "persistent_dir=persistent_dir" in tg:
    print("✓ test_generator: _output_path call already patched")
else:
    die("Could not find _output_path call in test_generator.py")

TESTGEN.write_text(tg)
print("✓ test_generator.py saved\n")

# ── Patch agent.py ────────────────────────────────────────────────────────────
ag = AGENT.read_text()

# 1. Create persistent_dir after _clone_repo in run_generation
OLD_CLONE = "        # Clone repo\n        repo_root = _clone_repo(repo_url, branch, token)"
NEW_CLONE = """        # Clone repo
        repo_root = _clone_repo(repo_url, branch, token)

        # Persistent dir — test files survive temp clone cleanup
        persistent_dir = os.path.join(
            os.environ.get("OPSMIND_OUTPUT_DIR",
                "/home/nabakumr/Videos/OpsMindAI-final/OpsMindAI-server/data/tests"),
            job_id,
        )
        os.makedirs(persistent_dir, exist_ok=True)
        logger.info("Persistent test output dir: %s", persistent_dir)"""
if OLD_CLONE in ag and "persistent_dir" not in ag:
    ag = ag.replace(OLD_CLONE, NEW_CLONE, 1)
    print("✓ agent: created persistent_dir in run_generation")
elif "persistent_dir" in ag:
    print("✓ agent: persistent_dir already in run_generation")
else:
    die("Could not find _clone_repo call in agent.py run_generation")

# 2. Pass persistent_dir to generate_tests
OLD_CALL = """                result: GeneratedTests = await generate_tests(
                    repo_url=repo_url,
                    file_path=fp,
                    source_code=source,
                    framework=framework,
                    threshold=threshold,
                    repo_root=repo_root,
                    model=model,
                )"""
NEW_CALL = """                result: GeneratedTests = await generate_tests(
                    repo_url=repo_url,
                    file_path=fp,
                    source_code=source,
                    framework=framework,
                    threshold=threshold,
                    repo_root=repo_root,
                    model=model,
                    persistent_dir=persistent_dir,
                )"""
if OLD_CALL in ag:
    ag = ag.replace(OLD_CALL, NEW_CALL, 1)
    print("✓ agent: passed persistent_dir to generate_tests")
elif "persistent_dir=persistent_dir" in ag:
    print("✓ agent: generate_tests call already patched")
else:
    die("Could not find generate_tests call in agent.py")

# 3. Store persistent_dir in Redis
OLD_REDIS = '            "repo_root":       repo_root,   # kept for run_suite step'
NEW_REDIS = '            "repo_root":       repo_root,\n            "persistent_dir":  persistent_dir,'
if OLD_REDIS in ag:
    ag = ag.replace(OLD_REDIS, NEW_REDIS, 1)
    print("✓ agent: stored persistent_dir in Redis state")
elif '"persistent_dir":' in ag:
    print("✓ agent: persistent_dir already in Redis state")
else:
    die("Could not find Redis update in agent.py run_generation")

# 4. Replace copy logic in run_suite
OLD_COPY = """        # ── Copy generated test files into the (possibly fresh) clone ────
        # Phase 1 wrote tests to the OLD temp dir; Phase 2 needs them here.
        generated_files: list[dict] = state.get("generated_files", [])
        if generated_files:
            tests_dest = os.path.join(repo_root, "tests", "unit")
            os.makedirs(tests_dest, exist_ok=True)
            copied = 0
            for gf in generated_files:
                src_path = gf.get("output_file", "")
                if src_path and os.path.exists(src_path):
                    dest = os.path.join(tests_dest, os.path.basename(src_path))
                    if os.path.abspath(src_path) != os.path.abspath(dest):
                        shutil.copy2(src_path, dest)
                    copied += 1
                    logger.info("Copied generated test %s → %s", src_path, dest)
            if copied == 0:
                # output_file paths point to old /tmp — try reconstructing from source_file
                logger.warning(
                    "Generated test files not found at original paths — "
                    "pytest will run on whatever tests exist in the cloned repo."
                )
            else:
                logger.info("Copied %d generated test file(s) into %s", copied, tests_dest)"""
NEW_COPY = """        # ── Copy generated test files into the (possibly fresh) clone ────
        generated_files: list[dict] = state.get("generated_files", [])
        persistent_dir: str = state.get("persistent_dir", "")

        if generated_files:
            tests_dest = os.path.join(repo_root, "tests", "unit")
            os.makedirs(tests_dest, exist_ok=True)
            copied = 0
            for gf in generated_files:
                fname = os.path.basename(gf.get("output_file", ""))
                if not fname:
                    continue
                # Priority 1: persistent_dir (survives temp cleanup)
                # Priority 2: original output_file path
                src_path = None
                if persistent_dir and os.path.exists(os.path.join(persistent_dir, fname)):
                    src_path = os.path.join(persistent_dir, fname)
                elif gf.get("output_file") and os.path.exists(gf["output_file"]):
                    src_path = gf["output_file"]
                if src_path:
                    dest = os.path.join(tests_dest, fname)
                    if os.path.abspath(src_path) != os.path.abspath(dest):
                        shutil.copy2(src_path, dest)
                    copied += 1
                    logger.info("Copied generated test %s → %s", src_path, dest)
            if copied == 0:
                logger.warning(
                    "No test files found in persistent_dir=%r or original paths",
                    persistent_dir,
                )
            else:
                logger.info("Copied %d generated test file(s) into %s", copied, tests_dest)"""
if OLD_COPY in ag:
    ag = ag.replace(OLD_COPY, NEW_COPY, 1)
    print("✓ agent: patched run_suite copy logic")
elif "persistent_dir: str = state.get" in ag:
    print("✓ agent: run_suite copy logic already patched")
else:
    die("Could not find copy logic in agent.py run_suite")

AGENT.write_text(ag)
print("✓ agent.py saved\n")

# ── Clear pyc cache ───────────────────────────────────────────────────────────
cleared = 0
for pyc in BASE.rglob("*.pyc"):
    pyc.unlink()
    cleared += 1
print(f"✓ Cleared {cleared} .pyc files\n")

print("=" * 50)
print("PATCH COMPLETE — now restart your Celery worker:")
print("  pkill -f 'celery.*worker'")
print("  celery -A opsmindai.core.celery_app worker --loglevel=info")