"""
opsmindai/agents/testing/coverage_analyzer.py

Runs pytest/Jest test suites, parses coverage output, computes delta
against the previous run stored in Redis, enforces the coverage gate,
and posts a GitHub PR comment when the gate fails.

Pipeline:
    1. Run pytest --cov (or jest --coverage)
    2. Parse coverage.xml / lcov.info
    3. Load previous coverage from Redis
    4. Compute delta; evaluate gate (threshold from models.yaml / env)
    5. Persist new baseline to Redis; embed in RAG KB
    6. Post GitHub PR comment on gate failure (when PR context available)
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Redis key templates
_COV_KEY   = "coverage:{repo_url}:{branch}"
_JOB_KEY   = "testing:job:{job_id}"


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class FileCoverage:
    """Per-file coverage statistics."""
    filename: str
    line_rate: float        # 0.0 – 1.0
    lines_covered: int
    lines_valid: int
    branch_rate: float = 0.0


@dataclass
class CoverageResult:
    """Aggregated coverage outcome for a test run."""
    coverage_pct: float            # 0.0 – 100.0
    delta_pct: float               # positive = improved
    lines_covered: int
    lines_total: int
    file_breakdown: dict[str, float]   # {filename: coverage_pct}
    gate_passed: bool
    threshold: float
    previous_pct: float
    raw_xml_path: Optional[str] = None
    raw_output: Optional[str] = None


# ── Lazy imports ──────────────────────────────────────────────────────────────

def _get_rag_pipeline():
    from opsmindai.memory.rag_pipeline import RAGPipeline
    return RAGPipeline()


# ── Threshold loading ─────────────────────────────────────────────────────────

def _load_threshold(override: Optional[float] = None) -> float:
    """
    Load coverage threshold from (in priority order):
      1. Explicit override argument
      2. COVERAGE_THRESHOLD env var
      3. config/models.yaml [coverage_threshold]
      4. Default 0.80

    Args:
        override: Caller-supplied threshold (0.0–1.0), takes precedence.

    Returns:
        Threshold as a float between 0.0 and 1.0.
    """
    if override is not None:
        return float(override)

    env_val = os.environ.get("COVERAGE_THRESHOLD")
    if env_val:
        return float(env_val)

    # Try models.yaml
    yaml_path = Path("config/models.yaml")
    if yaml_path.exists():
        try:
            import yaml  # type: ignore
            with open(yaml_path) as f:
                cfg = yaml.safe_load(f)
            val = cfg.get("coverage_threshold")
            if val is not None:
                return float(val)
        except Exception as exc:
            logger.debug("Could not load models.yaml threshold: %s", exc)

    return 0.80   # SRS default


# ── Test execution ────────────────────────────────────────────────────────────

def _install_deps(repo_path: str, framework: str) -> None:
    """
    Install test runner + coverage tool + repo dependencies before running tests.
    Runs pip/npm install inside the cloned repo so tests don't fail on missing imports.
    """
    import sys

    if framework == "pytest":
        # Always ensure pytest + pytest-cov are present
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pytest", "pytest-cov", "--quiet"],
            capture_output=True, timeout=120,
        )
        # Install repo deps if requirements file exists
        for req_file in ("requirements.txt", "requirements-dev.txt", "requirements-test.txt"):
            req_path = os.path.join(repo_path, req_file)
            if os.path.exists(req_path):
                logger.info("Installing deps from %s", req_file)
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", req_path, "--quiet"],
                    capture_output=True, timeout=180, cwd=repo_path,
                )
                break
        # Also handle pyproject.toml / setup.py installs
        if os.path.exists(os.path.join(repo_path, "pyproject.toml")):
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", ".", "--quiet"],
                capture_output=True, timeout=180, cwd=repo_path,
            )
        elif os.path.exists(os.path.join(repo_path, "setup.py")):
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", ".", "--quiet"],
                capture_output=True, timeout=180, cwd=repo_path,
            )
    else:  # jest or vitest
        # Ensure node_modules are installed
        pkg_json = os.path.join(repo_path, "package.json")
        if os.path.exists(pkg_json) and not os.path.isdir(os.path.join(repo_path, "node_modules")):
            logger.info("Running npm install in %s", repo_path)
            subprocess.run(
                ["npm", "install", "--prefer-offline", "--no-audit"],
                capture_output=True, timeout=180, cwd=repo_path,
            )
        # For vitest: always ensure @vitest/coverage-v8 is installed
        # (it may not be in the repo's package.json even if vitest is)
        if framework == "vitest":
            coverage_v8_path = os.path.join(repo_path, "node_modules", "@vitest", "coverage-v8")
            if not os.path.isdir(coverage_v8_path):
                logger.info("Installing @vitest/coverage-v8 for coverage reporting")
                # Read vitest version from package.json to install matching coverage-v8
                _pkg_path = os.path.join(repo_path, "package.json")
                _vitest_ver = ""
                try:
                    import json as _j
                    _pkg = _j.load(open(_pkg_path))
                    _all = {**_pkg.get("dependencies", {}), **_pkg.get("devDependencies", {})}
                    _raw = _all.get("vitest", "")
                    import re as _re
                    _m = _re.search(r"(\d+\.\d+\.\d+)", _raw)
                    if _m:
                        _vitest_ver = _m.group(1)
                except Exception:
                    pass
                _pkg_spec = (
                    f"@vitest/coverage-v8@{_vitest_ver}"
                    if _vitest_ver else "@vitest/coverage-v8"
                )
                logger.info("Installing %s for coverage reporting", _pkg_spec)
                subprocess.run(
                    ["npm", "install", "--save-dev", _pkg_spec,
                     "--no-audit", "--legacy-peer-deps"],
                    capture_output=True, timeout=120, cwd=repo_path,
                )


def _run_pytest(repo_path: str, extra_args: list[str] | None = None) -> tuple[str, int]:
    """
    Execute pytest with coverage in the given repo directory.

    Args:
        repo_path:   Absolute path to repository root.
        extra_args:  Additional pytest CLI arguments.

    Returns:
        Tuple of (stdout+stderr combined, return_code).
    """
    # Create a minimal conftest.py if none exists — prevents import path issues
    conftest = os.path.join(repo_path, "conftest.py")
    if not os.path.exists(conftest):
        with open(conftest, "w") as _f:
            _f.write("# Auto-generated by OpsMind testing agent\n")

    cmd = [
        "python", "-m", "pytest",
        "tests/",                           # only run the generated tests dir
        "--cov=.",
        "--cov-report=xml:coverage.xml",
        "--cov-report=term-missing",
        "--continue-on-collection-errors",  # don't abort on import errors
        "--ignore=node_modules",
        "-v",
        "--tb=short",
    ] + (extra_args or [])

    logger.info("Running pytest in %s: %s", repo_path, " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=600,
    )
    combined = result.stdout + "\n" + result.stderr
    return combined, result.returncode


def _run_jest(repo_path: str, extra_args: list[str] | None = None) -> tuple[str, int]:
    """
    Execute Jest with --coverage in the given repo directory.

    Args:
        repo_path:  Absolute path to repository root.
        extra_args: Additional Jest CLI arguments.

    Returns:
        Tuple of (stdout+stderr combined, return_code).
    """
    cmd = [
        "npx", "jest",
        "--coverage",
        "--coverageReporters=lcov",
        "--coverageReporters=text",
        "--forceExit",
    ] + (extra_args or [])

    logger.info("Running jest in %s: %s", repo_path, " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=600,
    )
    combined = result.stdout + "\n" + result.stderr
    return combined, result.returncode


def _run_vitest(repo_path: str, extra_args: list[str] | None = None) -> tuple[str, int]:
    """
    Execute Vitest with coverage in the given repo directory.

    Writes a temporary vitest config to ensure:
      - Generated tests in tests/unit/ are discovered
      - Coverage is scoped to src/ (not node_modules / test files)
      - lcov + text reporters are active

    Args:
        repo_path:  Absolute path to repository root.
        extra_args: Additional Vitest CLI arguments.

    Returns:
        Tuple of (stdout+stderr combined, return_code).
    """
    import json as _json

    # Write a temporary vitest config that overrides test include paths
    # so our generated tests/unit/*.test.ts files are always discovered
    tmp_config_path = os.path.join(repo_path, "vitest.opsmind.config.mjs")
    # Check if repo has a vite.config that already sets up React plugin + test env
    import os as _os
    _vite_cfg = _os.path.join(repo_path, "vite.config.js")
    _vite_cfg_ts = _os.path.join(repo_path, "vite.config.ts")
    _has_vite_cfg = _os.path.exists(_vite_cfg) or _os.path.exists(_vite_cfg_ts)
    _base_import = (
        "import { mergeConfig } from 'vite';\nimport baseConfig from './vite.config.js';"
        if _os.path.exists(_vite_cfg)
        else "import { mergeConfig } from 'vite';\nimport baseConfig from './vite.config.ts';"
        if _os.path.exists(_vite_cfg_ts)
        else None
    )

    # Check for setup file
    import os as _os2
    _setup_candidates = [
        _os2.path.join(repo_path, "src", "test", "setup.js"),
        _os2.path.join(repo_path, "src", "test", "setup.ts"),
        _os2.path.join(repo_path, "src", "setupTests.js"),
        _os2.path.join(repo_path, "src", "setupTests.ts"),
    ]
    _setup_file = next((s for s in _setup_candidates if _os2.path.exists(s)), None)
    _setup_line = (
        f"    setupFiles: ['{_os2.path.relpath(_setup_file, repo_path)}'],"
        if _setup_file else ""
    )

    # Strategy: use the repo's existing vite.config.js as the base
    # (it already has jsdom, setupFiles, React plugin) and write a thin
    # wrapper that extends it — but write it as a .js file inside the repo
    # so ESM resolution works correctly from node_modules.
    #
    # vitest 3.x caches .mjs configs to a temp timestamp file, breaking
    # relative node_modules resolution. Writing a plain .js in the repo root
    # avoids this entirely since Node resolves from the repo's node_modules.

    _has_react = _os2.path.exists(_os2.path.join(repo_path, "node_modules", "@vitejs", "plugin-react"))
    _react_import = "import react from '@vitejs/plugin-react';" if _has_react else ""
    _react_plugin = "plugins: [react()]," if _has_react else ""

    config_content = f"""import {{ defineConfig }} from 'vitest/config';
{_react_import}
export default defineConfig({{
  {_react_plugin}
  test: {{
    include: [
      'tests/unit/**/*.{{test,spec}}.{{js,ts,jsx,tsx}}',
      'src/**/*.{{test,spec}}.{{js,ts,jsx,tsx}}',
    ],
    environment: 'jsdom',
{_setup_line}
    coverage: {{
      enabled: true,
      provider: 'v8',
      reporter: ['lcov', 'text'],
      include: ['src/**'],
      exclude: [
        'src/**/*.{{test,spec}}.*',
        'src/**/__mocks__/**',
        'node_modules/**',
      ],
      reportsDirectory: './coverage',
    }},
  }},
}});
"""
    try:
        with open(tmp_config_path, "w") as f:
            f.write(config_content)
        logger.info("Wrote temporary vitest config to %s", tmp_config_path)
    except Exception as exc:
        logger.warning("Could not write vitest config: %s", exc)
        tmp_config_path = None

    cmd = [
        "npx", "vitest", "run",
        "--coverage",
        "--coverage.reportOnFailure=true",  # write lcov even when tests fail
    ]
    if tmp_config_path:
        cmd += ["--config", os.path.basename(tmp_config_path)]
    cmd += (extra_args or [])

    logger.info("Running vitest in %s: %s", repo_path, " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=repo_path,          # run FROM repo root so node_modules is found
        capture_output=True,
        text=True,
        timeout=600,
    )
    combined = result.stdout + "\n" + result.stderr
    if result.returncode != 0:
        logger.warning("Vitest output:\n%s", combined[-3000:])

    # Clean up temp config
    if tmp_config_path and os.path.exists(tmp_config_path):
        try:
            os.remove(tmp_config_path)
        except Exception:
            pass

    return combined, result.returncode


def _detect_js_framework(repo_path: str) -> str:
    """Return 'vitest' if vitest is in package.json deps/scripts, else 'jest'."""
    pkg_path = os.path.join(repo_path, "package.json")
    if not os.path.exists(pkg_path):
        return "jest"
    try:
        import json as _json
        with open(pkg_path, encoding="utf-8") as f:
            pkg = _json.load(f)
        all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "vitest" in all_deps:
            return "vitest"
        scripts = pkg.get("scripts", {})
        if any("vitest" in str(v) for v in scripts.values()):
            return "vitest"
    except Exception:
        pass
    return "jest"


# ── Coverage parsing ──────────────────────────────────────────────────────────

def _parse_coverage_xml(xml_path: str) -> tuple[float, int, int, dict[str, float]]:
    """
    Parse a coverage.xml file produced by pytest-cov (Cobertura format).

    Args:
        xml_path: Absolute path to coverage.xml.

    Returns:
        Tuple of:
          - overall line-rate as percentage (0.0–100.0)
          - total lines covered (int)
          - total lines valid (int)
          - file_breakdown dict {filename: pct}

    Raises:
        FileNotFoundError: If coverage.xml does not exist.
        ET.ParseError: If XML is malformed.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    overall_rate = float(root.attrib.get("line-rate", 0.0)) * 100.0
    lines_covered = int(root.attrib.get("lines-covered", 0))
    lines_valid   = int(root.attrib.get("lines-valid", 1))

    file_breakdown: dict[str, float] = {}
    for cls in root.iter("class"):
        fname     = cls.attrib.get("filename", "unknown")
        line_rate = float(cls.attrib.get("line-rate", 0.0)) * 100.0
        file_breakdown[fname] = round(line_rate, 2)

    return round(overall_rate, 2), lines_covered, lines_valid, file_breakdown


def _parse_lcov(lcov_path: str) -> tuple[float, int, int, dict[str, float]]:
    """
    Parse an lcov.info file produced by Jest --coverage.

    Args:
        lcov_path: Absolute path to lcov.info.

    Returns:
        Tuple of (overall_pct, lines_covered, lines_total, file_breakdown).
    """
    file_breakdown: dict[str, float] = {}
    total_found = 0
    total_hit   = 0
    current_file = ""
    found = hit = 0

    try:
        with open(lcov_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("SF:"):
                    current_file = line[3:]
                    found = hit = 0
                elif line.startswith("LF:"):
                    found = int(line[3:])
                elif line.startswith("LH:"):
                    hit = int(line[3:])
                elif line == "end_of_record":
                    if found > 0:
                        pct = round(hit / found * 100, 2)
                        file_breakdown[current_file] = pct
                        total_found += found
                        total_hit   += hit
    except FileNotFoundError:
        logger.warning("lcov.info not found at %s", lcov_path)
        return 0.0, 0, 0, {}

    overall = round(total_hit / total_found * 100, 2) if total_found > 0 else 0.0
    return overall, total_hit, total_found, file_breakdown


# ── Redis persistence ─────────────────────────────────────────────────────────

async def _load_previous_coverage(redis, repo_url: str, branch: str) -> float:
    """
    Load the last recorded coverage percentage from Redis.

    Args:
        redis:    Async Redis client.
        repo_url: Repository URL (used as part of Redis key).
        branch:   Branch name.

    Returns:
        Previous coverage as float (0.0–100.0); 0.0 if first run.
    """
    key = _COV_KEY.format(repo_url=repo_url, branch=branch)
    try:
        raw = await redis.get(key)
        if raw:
            data = json.loads(raw)
            return float(data.get("coverage_pct", 0.0))
    except Exception as exc:
        logger.warning("Could not load previous coverage from Redis: %s", exc)
    return 0.0


async def _save_coverage(redis, repo_url: str, branch: str, result: CoverageResult) -> None:
    """
    Persist current coverage to Redis for future delta comparisons.

    Args:
        redis:    Async Redis client.
        repo_url: Repository URL.
        branch:   Branch name.
        result:   CoverageResult to persist.
    """
    key = _COV_KEY.format(repo_url=repo_url, branch=branch)
    payload = {
        "coverage_pct":     result.coverage_pct,
        "lines_covered":    result.lines_covered,
        "lines_total":      result.lines_total,
        "file_breakdown":   result.file_breakdown,
        "recorded_at":      datetime.now(timezone.utc).isoformat(),
    }
    try:
        await redis.setex(key, 86400 * 90, json.dumps(payload))
        logger.info("Saved coverage %.1f%% to Redis key %s", result.coverage_pct, key)
    except Exception as exc:
        logger.warning("Could not save coverage to Redis: %s", exc)


# ── GitHub PR comment ─────────────────────────────────────────────────────────

def _build_pr_comment(result: CoverageResult, job_id: str) -> str:
    """
    Build a Markdown coverage table for posting as a GitHub PR comment.

    Args:
        result: CoverageResult data.
        job_id: OpsMind job ID for traceability.

    Returns:
        Markdown string.
    """
    gate_icon  = "✅" if result.gate_passed else "❌"
    delta_sign = "+" if result.delta_pct >= 0 else ""

    header = textwrap.dedent(f"""\
        ## {gate_icon} OpsMind Coverage Gate — {'PASSED' if result.gate_passed else 'FAILED'}

        | Metric | Value |
        |--------|-------|
        | Overall coverage | **{result.coverage_pct:.1f}%** |
        | Delta vs previous | **{delta_sign}{result.delta_pct:.1f}%** |
        | Threshold | {result.threshold * 100:.0f}% |
        | Lines covered | {result.lines_covered} / {result.lines_total} |
        | Job ID | `{job_id}` |
    """)

    if not result.gate_passed:
        header += (
            "\n> ⚠️ **This PR reduces test coverage. Merge is blocked until coverage "
            f"is ≥ {result.threshold * 100:.0f}% and delta ≥ 0.**\n"
        )

    # File breakdown (top 10 worst)
    worst = sorted(result.file_breakdown.items(), key=lambda x: x[1])[:10]
    if worst:
        header += "\n### Files with Lowest Coverage\n\n"
        header += "| File | Coverage |\n|------|----------|\n"
        for fname, pct in worst:
            icon = "🔴" if pct < 50 else ("🟡" if pct < 80 else "🟢")
            header += f"| `{fname}` | {icon} {pct:.1f}% |\n"

    return header


async def _post_github_pr_comment(
    comment: str,
    repo_url: str,
    pr_number: Optional[int],
) -> None:
    """
    Post a comment to a GitHub PR via PyGitHub.

    Args:
        comment:    Markdown comment body.
        repo_url:   HTTPS GitHub repo URL.
        pr_number:  PR number to comment on (skip if None).
    """
    if pr_number is None:
        logger.debug("No PR number provided — skipping GitHub comment")
        return

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        logger.warning("GITHUB_TOKEN not set — cannot post PR comment")
        return

    try:
        from github import Github  # PyGitHub
        match = re.search(r"github\.com[/:](.+?)(?:\.git)?$", repo_url)
        if not match:
            raise ValueError(f"Cannot parse repo slug from {repo_url}")
        repo_slug = match.group(1)
        gh   = Github(token)
        repo = gh.get_repo(repo_slug)
        pr   = repo.get_pull(pr_number)
        pr.create_issue_comment(comment)
        logger.info("Posted coverage comment to PR #%d", pr_number)
    except Exception as exc:
        logger.warning("Could not post GitHub PR comment: %s", exc)


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_and_analyze(
    job_id:     str,
    repo_path:  str,
    repo_url:   str,
    branch:     str,
    framework:  str = "pytest",
    threshold:  Optional[float] = None,
    pr_number:  Optional[int]   = None,
    redis       = None,
    extra_args: list[str] | None = None,
) -> CoverageResult:
    """
    Execute tests, parse coverage, compute delta, and enforce the gate.

    Args:
        job_id:     OpsMind job ID (used in Redis keys and PR comment).
        repo_path:  Absolute filesystem path to repository root.
        repo_url:   HTTPS GitHub URL (used for Redis coverage key).
        branch:     Branch name (used for Redis coverage key).
        framework:  'pytest' or 'jest'.
        threshold:  Override coverage threshold (0.0–1.0).
        pr_number:  GitHub PR number; if set, posts comment on gate failure.
        redis:      Async Redis client (required for delta comparison).
        extra_args: Extra CLI args forwarded to pytest / jest.

    Returns:
        CoverageResult with gate decision and full breakdown.

    Raises:
        RuntimeError: If the test runner exits with a non-zero code AND
                      no coverage output was produced (i.e. hard crash).
    """
    gate_threshold = _load_threshold(threshold)

    # ── 0. Install dependencies ───────────────────────────────────────────
    # Auto-upgrade 'jest' to 'vitest' if the repo uses it
    if framework == "jest":
        detected = _detect_js_framework(repo_path)
        if detected == "vitest":
            logger.info("Detected Vitest in repo — switching runner from jest to vitest")
            framework = "vitest"

    _install_deps(repo_path, framework)

    # ── 1. Run tests ──────────────────────────────────────────────────────
    if framework == "pytest":
        output, rc = _run_pytest(repo_path, extra_args)
        cov_xml   = os.path.join(repo_path, "coverage.xml")
        lcov_file = None
    elif framework == "vitest":
        output, rc = _run_vitest(repo_path, extra_args)
        cov_xml   = None
        lcov_file = os.path.join(repo_path, "coverage", "lcov.info")
    else:  # jest
        output, rc = _run_jest(repo_path, extra_args)
        cov_xml   = None
        lcov_file = os.path.join(repo_path, "coverage", "lcov.info")

    logger.info("Test runner exited with code %d (job=%s)", rc, job_id)
    if rc != 0:
        logger.warning("Test runner output (job=%s):\n%s", job_id, output[-3000:])

    # ── 2. Parse coverage ─────────────────────────────────────────────────
    if framework == "pytest":
        if not os.path.exists(cov_xml):
            if rc == 2:
                logger.warning(
                    "pytest exit code 2 — no tests collected in %s. "
                    "Check that test files exist in tests/unit/ and have no syntax errors. "
                    "Treating as 0%% coverage.",
                    repo_path,
                )
                return CoverageResult(
                    coverage_pct=0.0,
                    delta_pct=0.0,
                    lines_covered=0,
                    lines_total=0,
                    file_breakdown={},
                    gate_passed=False,
                    threshold=gate_threshold,
                    previous_pct=0.0,
                    raw_output=output,
                )
            raise RuntimeError(
                f"coverage.xml not found at {cov_xml}. "
                "Ensure pytest-cov is installed and tests are not all erroring out. "
                f"pytest output:\n{output[-1000:]}"
            )
        overall_pct, lines_covered, lines_total, file_breakdown = _parse_coverage_xml(cov_xml)
    else:  # jest or vitest — both produce lcov.info
        if lcov_file and os.path.exists(lcov_file):
            overall_pct, lines_covered, lines_total, file_breakdown = _parse_lcov(lcov_file)
        else:
            logger.warning("lcov.info not found; attempting text output parse")
            m = re.search(r"All files\s+\|\s+([\d.]+)", output)
            overall_pct    = float(m.group(1)) if m else 0.0
            lines_covered  = 0
            lines_total    = 0
            file_breakdown = {}

    # ── 3. Delta vs previous run ──────────────────────────────────────────
    previous_pct = 0.0
    if redis:
        previous_pct = await _load_previous_coverage(redis, repo_url, branch)

    delta_pct = round(overall_pct - previous_pct, 2)

    # ── 4. Gate decision ──────────────────────────────────────────────────
    gate_passed = (
        overall_pct >= (gate_threshold * 100)
        and delta_pct >= 0
    )

    result = CoverageResult(
        coverage_pct=overall_pct,
        delta_pct=delta_pct,
        lines_covered=lines_covered,
        lines_total=lines_total,
        file_breakdown=file_breakdown,
        gate_passed=gate_passed,
        threshold=gate_threshold,
        previous_pct=previous_pct,
        raw_xml_path=cov_xml,
    )

    logger.info(
        "Coverage gate job=%s pct=%.1f%% delta=%.1f%% threshold=%.0f%% passed=%s",
        job_id, overall_pct, delta_pct, gate_threshold * 100, gate_passed,
    )

    # ── 5. Persist to Redis ───────────────────────────────────────────────
    if redis:
        await _save_coverage(redis, repo_url, branch, result)

    # ── 6. Embed in RAG KB ────────────────────────────────────────────────
    try:
        rag = _get_rag_pipeline()
        summary = (
            f"Coverage run job={job_id} repo={repo_url} branch={branch} "
            f"pct={overall_pct:.1f}% delta={delta_pct:+.1f}% "
            f"gate={'passed' if gate_passed else 'failed'} "
            f"framework={framework}"
        )
        await rag.embed(
            content=summary,
            doc_type="test_result",
            metadata={
                "job_id":       job_id,
                "repo_url":     repo_url,
                "branch":       branch,
                "coverage_pct": overall_pct,
                "delta_pct":    delta_pct,
                "gate_passed":  gate_passed,
            },
        )
    except Exception as exc:
        logger.warning("RAG embed failed (non-fatal): %s", exc)

    # ── 7. GitHub PR comment on gate failure ──────────────────────────────
    if not gate_passed and pr_number:
        comment = _build_pr_comment(result, job_id)
        await _post_github_pr_comment(comment, repo_url, pr_number)

    return result


# ── Synchronous entry point for Phase 2 (no asyncio) ─────────────────────────

def run_and_analyze_sync(
    job_id:       str,
    repo_path:    str,
    repo_url:     str,
    branch:       str,
    framework:    str,
    threshold:    float,
    pr_number,
    redis_client,          # plain sync redis.Redis — no event loop needed
) -> "CoverageResult":
    """
    Synchronous version of run_and_analyze for use in Celery Phase 2.

    Bypasses asyncio entirely — all Redis reads/writes use the sync client
    directly. This eliminates all httpx/anyio event-loop teardown errors.
    """
    import json as _json
    import time as _time

    _COV_KEY_TPL = "coverage:{repo_url}:{branch}"

    def _load_prev() -> float:
        try:
            key = _COV_KEY_TPL.format(repo_url=repo_url, branch=branch)
            raw = redis_client.get(key)
            return float(raw) if raw else 0.0
        except Exception:
            return 0.0

    def _save_cov(pct: float) -> None:
        try:
            key = _COV_KEY_TPL.format(repo_url=repo_url, branch=branch)
            redis_client.set(key, str(pct))
            logger.info("Saved coverage %.1f%% to Redis key %s", pct, key)
        except Exception as exc:
            logger.warning("Failed to save coverage to Redis: %s", exc)

    # 1. Install deps
    _install_deps(repo_path, framework)

    # 2. Run tests
    if framework == "pytest":
        output, rc = _run_pytest(repo_path)
        cov_xml  = os.path.join(repo_path, "coverage.xml")
        lcov_file = None
    elif framework == "vitest":
        output, rc = _run_vitest(repo_path)
        cov_xml  = None
        lcov_file = os.path.join(repo_path, "coverage", "lcov.info")
    else:
        output, rc = _run_jest(repo_path)
        cov_xml  = None
        lcov_file = os.path.join(repo_path, "coverage", "lcov.info")

    logger.info("Test runner exited with code %d (job=%s)", rc, job_id)
    if rc != 0:
        logger.warning("Test runner output (job=%s):\n%s", job_id, output[-3000:])

    # 3. Parse coverage
    if framework == "pytest":
        if not os.path.exists(cov_xml):
            logger.warning("coverage.xml not found — treating as 0%%")
            overall_pct, lines_covered, lines_total, file_breakdown = 0.0, 0, 0, {}
        else:
            overall_pct, lines_covered, lines_total, file_breakdown = _parse_coverage_xml(cov_xml)
    else:
        if lcov_file and os.path.exists(lcov_file):
            overall_pct, lines_covered, lines_total, file_breakdown = _parse_lcov(lcov_file)
        else:
            logger.warning("lcov.info not found; attempting text output parse")
            import re as _re
            m = _re.search(r"All files\s+\|\s+([\d.]+)", output)
            overall_pct    = float(m.group(1)) if m else 0.0
            lines_covered  = 0
            lines_total    = 0
            file_breakdown = {}

    # 4. Delta
    previous_pct = _load_prev()
    delta_pct    = round(overall_pct - previous_pct, 2)

    # 5. Gate
    gate_threshold = threshold if threshold > 1.0 else threshold * 100
    gate_passed    = overall_pct >= gate_threshold

    logger.info(
        "Coverage gate job=%s pct=%.1f%% delta=%.1f%% threshold=%.0f%% passed=%s",
        job_id, overall_pct, delta_pct, gate_threshold, gate_passed,
    )

    # 6. Save to Redis
    _save_cov(overall_pct)

    # 7. Store in RAG KB (best-effort)
    try:
        from opsmindai.memory.rag_pipeline import RAGPipeline
        from opsmindai.memory.vector_store import upsert
        from opsmindai.memory.embedder import embed
        import uuid as _uuid
        summary = (
            f"Coverage run job={job_id} repo={repo_url} branch={branch} "
            f"pct={overall_pct:.1f}% delta={delta_pct:+.1f}% "
            f"gate={'passed' if gate_passed else 'failed'} framework={framework}"
        )
        entry_id = f"test_result_{_uuid.uuid4().hex[:16]}"
        vector   = embed(summary)
        upsert(
            entry_id=entry_id,
            vector=vector,
            content=summary,
            metadata={
                "type": "test_result",
                "job_id": job_id,
                "repo_url": repo_url,
                "branch": branch,
                "coverage_pct": overall_pct,
                "delta_pct": delta_pct,
                "gate_passed": gate_passed,
            },
        )
        logger.info("rag_pipeline store_result: type=test_result entry_id=%s", entry_id)
    except Exception as exc:
        logger.warning("RAG embed failed (non-fatal): %s", exc)

    return CoverageResult(
        coverage_pct  = overall_pct,
        delta_pct     = delta_pct,
        lines_covered = lines_covered,
        lines_total   = lines_total,
        file_breakdown= file_breakdown,
        gate_passed   = gate_passed,
        threshold     = gate_threshold,
        previous_pct  = previous_pct,
        raw_output    = output,
    )