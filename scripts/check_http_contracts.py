#!/usr/bin/env python3
"""Validate shared HTTP contracts artifacts used by FE/BE."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = ROOT / "shared" / "contracts" / "http_contracts_v1.json"
EXAMPLES_DIR = ROOT / "shared" / "contracts" / "examples"


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_keys_present(data, required_keys, context: str) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, f"{context}: example must be a JSON object"
    missing = [k for k in required_keys if k not in data]
    if missing:
        return False, f"{context}: missing required keys: {', '.join(missing)}"
    return True, ""


def _resolve_example_file(rel_path: str) -> Path:
    return (CONTRACT_FILE.parent / rel_path).resolve()


def _matches_type(value, type_name: str) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "null":
        return value is None
    if type_name == "number_or_null":
        return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))
    return False


def _validate_types(data, expected_types: dict, context: str) -> tuple[bool, str]:
    if not expected_types:
        return True, ""
    if not isinstance(data, dict):
        return False, f"{context}: expected JSON object for type validation"
    for key, type_name in expected_types.items():
        if key not in data:
            return False, f"{context}: key '{key}' not found for type validation"
        if not _matches_type(data[key], str(type_name)):
            actual = type(data[key]).__name__
            return False, (
                f"{context}: key '{key}' has invalid type '{actual}', expected '{type_name}'"
            )
    return True, ""


def main() -> int:
    if not CONTRACT_FILE.exists():
        print(f"HTTP contracts check failed: missing {CONTRACT_FILE.relative_to(ROOT)}")
        return 1
    if not EXAMPLES_DIR.exists():
        print(f"HTTP contracts check failed: missing {EXAMPLES_DIR.relative_to(ROOT)}")
        return 1

    payload = _load_json(CONTRACT_FILE)
    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        print("HTTP contracts check failed: endpoints list is empty or invalid")
        return 1

    parsed_examples = {}
    example_files = sorted(EXAMPLES_DIR.glob("*.json"))
    if not example_files:
        print("HTTP contracts check failed: no regression example payloads in shared/contracts/examples")
        return 1
    for file_path in example_files:
        try:
            parsed_examples[file_path.resolve()] = _load_json(file_path)
        except json.JSONDecodeError as exc:
            print(f"HTTP contracts check failed: invalid JSON in {file_path.relative_to(ROOT)}: {exc}")
            return 1

    seen = set()
    for idx, item in enumerate(endpoints):
        if not isinstance(item, dict):
            print(f"HTTP contracts check failed: endpoint #{idx} is not an object")
            return 1
        path = str(item.get("path") or "").strip()
        method = str(item.get("method") or "").strip().upper()
        if not path or not method:
            print(f"HTTP contracts check failed: endpoint #{idx} missing path/method")
            return 1
        key = (method, path)
        if key in seen:
            print(f"HTTP contracts check failed: duplicate endpoint {method} {path}")
            return 1
        seen.add(key)

        has_success_keys = "response_success_keys" in item or "response_success_headers" in item
        if not has_success_keys:
            print(f"HTTP contracts check failed: endpoint {method} {path} has no success contract keys")
            return 1
        success_example = str(item.get("success_example") or "").strip()
        error_example = str(item.get("error_example") or "").strip()
        success_headers_example = str(item.get("success_headers_example") or "").strip()

        if success_example:
            example_path = _resolve_example_file(success_example)
            example_data = parsed_examples.get(example_path)
            if example_data is None:
                print(
                    "HTTP contracts check failed: missing success_example "
                    f"{success_example} for {method} {path}"
                )
                return 1
            if "response_success_keys" in item:
                ok, msg = _ensure_keys_present(
                    example_data,
                    item.get("response_success_keys", []),
                    f"{method} {path} success_example",
                )
                if not ok:
                    print(f"HTTP contracts check failed: {msg}")
                    return 1
            ok, msg = _validate_types(
                example_data,
                item.get("response_success_types", {}),
                f"{method} {path} success_example",
            )
            if not ok:
                print(f"HTTP contracts check failed: {msg}")
                return 1

        if success_headers_example:
            example_path = _resolve_example_file(success_headers_example)
            example_data = parsed_examples.get(example_path)
            if example_data is None:
                print(
                    "HTTP contracts check failed: missing success_headers_example "
                    f"{success_headers_example} for {method} {path}"
                )
                return 1
            required_headers = item.get("response_success_headers", [])
            headers_from_example = example_data.get("required_headers", [])
            if not isinstance(headers_from_example, list):
                print(
                    "HTTP contracts check failed: "
                    f"{method} {path} success_headers_example must contain required_headers list"
                )
                return 1
            missing_headers = [h for h in required_headers if h not in headers_from_example]
            if missing_headers:
                print(
                    "HTTP contracts check failed: "
                    f"{method} {path} success_headers_example missing headers: {', '.join(missing_headers)}"
                )
                return 1

        if error_example:
            example_path = _resolve_example_file(error_example)
            example_data = parsed_examples.get(example_path)
            if example_data is None:
                print(
                    "HTTP contracts check failed: missing error_example "
                    f"{error_example} for {method} {path}"
                )
                return 1
            if "response_error_keys" in item:
                ok, msg = _ensure_keys_present(
                    example_data,
                    item.get("response_error_keys", []),
                    f"{method} {path} error_example",
                )
                if not ok:
                    print(f"HTTP contracts check failed: {msg}")
                    return 1
            ok, msg = _validate_types(
                example_data,
                item.get("response_error_types", {}),
                f"{method} {path} error_example",
            )
            if not ok:
                print(f"HTTP contracts check failed: {msg}")
                return 1

    print(
        "HTTP contracts checks passed. "
        f"Endpoints: {len(endpoints)}, examples: {len(example_files)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
