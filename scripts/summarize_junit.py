from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a bounded JSON summary from pytest JUnit XML")
    parser.add_argument("xml", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = ET.parse(args.xml).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    summary = {
        "tests": sum(int(suite.attrib.get("tests", 0)) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", 0)) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", 0)) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", 0)) for suite in suites),
        "time_seconds": sum(float(suite.attrib.get("time", 0.0)) for suite in suites),
        "failed_tests": [],
    }
    for case in root.iter("testcase"):
        failure = case.find("failure")
        error = case.find("error")
        if failure is None and error is None:
            continue
        issue = failure if failure is not None else error
        summary["failed_tests"].append({
            "node": "::".join(filter(None, (case.attrib.get("classname"), case.attrib.get("name")))),
            "kind": "failure" if failure is not None else "error",
            "message": (issue.attrib.get("message") or "").splitlines()[0][:300],
        })
    summary["ok"] = summary["failures"] == 0 and summary["errors"] == 0
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(json.dumps({
            "ok": summary["ok"], "tests": summary["tests"], "failures": summary["failures"],
            "errors": summary["errors"], "summary": str(args.output),
        }, ensure_ascii=False))
    else:
        print(text)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
