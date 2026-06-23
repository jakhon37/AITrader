---
name: check-violations
description: Use this skill when auditing code for architecture violations, checking for banned patterns like datetime.now(), detecting cross-division imports that violate dependency rules, finding hardcoded secrets or values, or verifying coding standards before a division is marked complete.
---

# check-violations

Scans the codebase for patterns that violate the AITrader architecture rules. Run before marking any division complete.

## Run all checks at once

```bash
PYTHONPATH=src python scripts/project_overview.py
```

Or run each check individually:

---

## Check 1 — Banned time calls (breaks replay)

Any direct call to `datetime.now()` or `datetime.utcnow()` inside `src/` (except in `src/core/clock.py` itself) means the code is not replay-safe.

```bash
# Find violations
grep -rn "datetime\.now\(\)\|datetime\.utcnow()\|time\.time()" src/ \
  --include="*.py" \
  | grep -v "src/core/clock.py"
```

Expected output: **nothing**. Any hit is a violation. Fix by injecting and using `self.clock.now()`.

---

## Check 2 — Cross-division import violations

Divisions must only import from their allowed dependencies (see MASTER.md dependency graph). The most common illegal imports:

```bash
# Division 2 (D02-DATA) must not import from features/ (Division 1 (D01-CORE) (D04-TECHNICAL))
grep -rn "from features\." src/fundamental/ --include="*.py"
grep -rn "import features" src/fundamental/ --include="*.py"

# Division 1 (D01-CORE) (D04-TECHNICAL) must not import from fundamental/
grep -rn "from fundamental\." src/features/ --include="*.py"

# Division 5 (decision) must not import from data/ directly
grep -rn "from data\." src/decision/ --include="*.py"

# Division 6 (execution) must not import from decision/
grep -rn "from decision\." src/execution/ --include="*.py"

# Nobody except Division 1 (D01-CORE) defines signal models
grep -rn "class.*Signal.*BaseModel" src/ --include="*.py" \
  | grep -v "src/core/contracts.py"

# Division 7 (D07-NOTIFIER) (notifications) must not import from execution/ or decision/
grep -rn "from execution\.\|from decision\." src/notifier/ --include="*.py"
```

All of these must return **nothing**.

---

## Check 3 — Hardcoded secrets and values

```bash
# No API keys in code
grep -rn "sk-\|Bearer \|api_key\s*=\s*['\"]" src/ --include="*.py" \
  | grep -v "\.env\|config\.\|os\.getenv\|os\.environ"

# No hardcoded IP addresses
grep -rn "[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}" src/ --include="*.py" \
  | grep -v "127\.0\.0\.1\|0\.0\.0\.0\|localhost"

# No hardcoded magic numbers in trading logic (use config)
# This is a manual review — look for unexplained float/int literals in decision/ and execution/
grep -rn "= 0\.[0-9]\{2,\}\|= [0-9]\{2,\}\." src/decision/ src/execution/ --include="*.py" \
  | grep -v "test_\|#\|0\.0\|1\.0\|0\.5"
```

---

## Check 4 — Signal construction not using new_signal_id

Every signal must have a properly formatted signal_id:

```bash
# Find manual signal_id construction (should use new_signal_id())
grep -rn "signal_id\s*=" src/ --include="*.py" \
  | grep -v "new_signal_id\|test_\|contracts\.py"
```

Any result that's not using `new_signal_id()` should be flagged.

---

## Check 5 — Blocking calls on async loop

```bash
# time.sleep() in async code blocks the event loop
grep -rn "time\.sleep(" src/ --include="*.py"

# requests library (sync) — should use aiohttp
grep -rn "import requests\b\|requests\.get\|requests\.post" src/ --include="*.py"
```

Expected: **nothing**. Use `asyncio.sleep()` and `aiohttp` instead.

---

## Check 6 — print() instead of structured logger

```bash
# Find raw print() calls in src/ (not in tests/ or scripts/)
grep -rn "^\s*print(" src/ --include="*.py" \
  | grep -v "# debug\|scripts/"
```

All logging should use `from src.core.logging import get_logger; log = get_logger("division_name")`.

---

## Check 7 — Missing type annotations

```bash
# mypy strict check — missing annotations
mypy src --disallow-untyped-defs --ignore-missing-imports 2>&1 \
  | grep "error: Function is missing"
```

Every function in `src/` must have type annotations on arguments and return type.

---

## Check 8 — Signal schema defined outside contracts.py

```bash
grep -rn "class.*Signal.*BaseModel\|class.*Event.*BaseModel" src/ --include="*.py" \
  | grep -v "src/core/contracts.py\|test_"
```

Expected: **nothing**. All signal schemas live exclusively in `src/core/contracts.py`.

---

## Check 9 — Ruff and format

```bash
ruff check src tests scripts
ruff format --check src tests scripts
```

Both must exit with code 0.

---

## Check 10 — Future data leakage in training (Division 8)

```bash
# Find any direct use of future rows in feature builder
grep -rn "shift(-\|\.future\|look_ahead" src/models/ --include="*.py" \
  | grep -v "label_builder\|# intentional forward"
```

`shift(-N)` is only valid in `label_builder.py` (for constructing target labels). Any use in `feature_builder.py` is a data leakage violation.

---

## Full pre-completion checklist

Run before setting a division's status to COMPLETE:

```bash
echo "=== 1. Ruff lint ===" && ruff check src tests scripts
echo "=== 2. Ruff format ===" && ruff format --check src tests scripts
echo "=== 3. mypy ===" && mypy src --ignore-missing-imports
echo "=== 4. datetime violations ===" && grep -rn "datetime\.now\(\)\|datetime\.utcnow()" src/ --include="*.py" | grep -v "clock.py"
echo "=== 5. Cross-division imports ===" && grep -rn "from features\." src/fundamental/ --include="*.py"
echo "=== 6. Blocking calls ===" && grep -rn "time\.sleep(" src/ --include="*.py"
echo "=== 7. print() calls ===" && grep -rn "^\s*print(" src/ --include="*.py"
echo "=== 8. Signal schema outside contracts ===" && grep -rn "class.*Signal.*BaseModel" src/ --include="*.py" | grep -v "contracts.py"
echo "=== All checks done ==="
```

All checks must produce **no output** (no violations found) before a division can be marked complete.
