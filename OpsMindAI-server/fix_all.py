#!/usr/bin/env python3
"""
cd ~/Videos/OpsMindAI-final/OpsMindAI-server
python3 fix_all.py
"""
import os, re, pathlib, sys, shutil, json, subprocess

BASE = pathlib.Path(__file__).parent

def ok(msg):  print(f"✓ {msg}")
def info(msg): print(f"  {msg}")
def die(msg): print(f"✗ ERROR: {msg}", file=sys.stderr); sys.exit(1)

# ══════════════════════════════════════════════════════════════════
# FIX 1 — celery_app.py: suppress Event loop is closed noise
# ══════════════════════════════════════════════════════════════════
ca = BASE / "opsmindai/core/celery_app.py"
if not ca.exists(): die(f"Not found: {ca}")
txt = ca.read_text()
if "warnings.filterwarnings" not in txt:
    txt = txt.replace(
        "import os\n\nfrom celery import Celery",
        "import os\nimport warnings\n\nwarnings.filterwarnings(\n    'ignore',\n    message='.*Event loop is closed.*',\n    category=RuntimeWarning,\n)\n\nfrom celery import Celery",
        1
    )
    ca.write_text(txt)
    ok("celery_app.py: added Event loop suppression")
else:
    ok("celery_app.py: already patched")

# ══════════════════════════════════════════════════════════════════
# FIX 2 — Diagnose why data/tests/{job_id}/ is empty
# ══════════════════════════════════════════════════════════════════
tests_dir = BASE / "data/tests"
print(f"\n── Checking persistent test storage at {tests_dir} ──")
if not tests_dir.exists():
    print("  data/tests/ does not exist yet — will be created on next Phase 1 run")
else:
    jobs = sorted(tests_dir.iterdir()) if tests_dir.exists() else []
    print(f"  Found {len(jobs)} job dir(s)")
    for j in jobs[-3:]:  # show last 3
        files = list(j.glob("*"))
        print(f"  {j.name}/  ({len(files)} files)")
        for f in files[:5]:
            print(f"    {f.name}  ({f.stat().st_size} bytes)")

# ══════════════════════════════════════════════════════════════════
# FIX 3 — agent.py: add debug logging to copy block so we can see
#          exactly what's happening in Phase 2
# ══════════════════════════════════════════════════════════════════
ag = BASE / "opsmindai/agents/testing/agent.py"
txt = ag.read_text()

OLD = '''        if generated_files:
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
                logger.info("Copied %d generated test file(s) into %s", copied, tests_dest)'''

NEW = '''        logger.info("Phase2 copy: persistent_dir=%r has_files=%d",
                    persistent_dir,
                    len(list(__import__('pathlib').Path(persistent_dir).glob('*')) if persistent_dir and __import__('os').path.isdir(persistent_dir) else []))
        if generated_files:
            tests_dest = os.path.join(repo_root, "tests", "unit")
            os.makedirs(tests_dest, exist_ok=True)
            copied = 0
            for gf in generated_files:
                fname = os.path.basename(gf.get("output_file", ""))
                if not fname:
                    continue
                src_path = None
                p1 = os.path.join(persistent_dir, fname) if persistent_dir else ""
                p2 = gf.get("output_file", "")
                logger.info("Phase2 copy: trying fname=%r p1_exists=%s p2_exists=%s",
                            fname,
                            os.path.exists(p1) if p1 else False,
                            os.path.exists(p2) if p2 else False)
                if p1 and os.path.exists(p1):
                    src_path = p1
                elif p2 and os.path.exists(p2):
                    src_path = p2
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
                logger.info("Copied %d generated test file(s) into %s", copied, tests_dest)'''

if OLD in txt:
    txt = txt.replace(OLD, NEW, 1)
    ag.write_text(txt)
    ok("agent.py: added debug logging to Phase 2 copy block")
elif "Phase2 copy:" in txt:
    ok("agent.py: debug logging already present")
else:
    # Try to patch without the exact match - just add logging before the if generated_files
    import re as _re
    if '"No test files found in persistent_dir' in txt:
        ok("agent.py: copy logic present, adding minimal debug log")
        txt2 = txt.replace(
            'persistent_dir: str = state.get("persistent_dir", "")\n\n        if generated_files:',
            'persistent_dir: str = state.get("persistent_dir", "")\n        logger.info("Phase2 copy check: persistent_dir=%r exists=%s file_count=%d",\n                    persistent_dir,\n                    os.path.isdir(persistent_dir) if persistent_dir else False,\n                    len(os.listdir(persistent_dir)) if persistent_dir and os.path.isdir(persistent_dir) else 0)\n\n        if generated_files:',
            1
        )
        if txt2 != txt:
            ag.write_text(txt2)
            ok("agent.py: added minimal debug log")
        else:
            print("  (could not add debug log, but copy logic is present)")
    else:
        die("copy logic not found in agent.py — run patch_phase2.py first")

# ══════════════════════════════════════════════════════════════════
# Clear pyc
# ══════════════════════════════════════════════════════════════════
cleared = sum(1 for p in BASE.rglob("*.pyc") if p.unlink() or True)
ok(f"Cleared {cleared} .pyc files")

print("""
══════════════════════════════════════
DONE — restart worker then run Phase 1 + Phase 2 again.
After the run, check the Celery log for lines starting with:
  'Phase2 copy check:'  ← tells you if persistent_dir has files
  'Phase2 copy: trying' ← shows each file lookup

Also check:
  ls ~/Videos/OpsMindAI-final/OpsMindAI-server/data/tests/
Should show a folder named testgen_XXXX with .ts/.py files in it.

Restart command:
  pkill -f 'celery.*worker' && sleep 1
  celery -A opsmindai.core.celery_app worker --loglevel=info
══════════════════════════════════════""")
