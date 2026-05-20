from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def _escape_vbs_string(value: str) -> str:
    return value.replace('"', '""')


def _backup_existing_targets(changes: list[dict[str, Any]], backup_root: str) -> dict[str, str]:
    backup_dir = Path(backup_root)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backups: dict[str, str] = {}

    for change in changes:
        target = change.get("new_path")
        if not target or not Path(target).exists():
            continue
        if target in backups:
            continue

        source = Path(target)
        candidate = backup_dir / source.name
        counter = 2
        while candidate.exists():
            candidate = backup_dir / f"{source.stem}-{counter}{source.suffix}"
            counter += 1

        candidate.write_bytes(source.read_bytes())
        backups[target] = str(candidate)

    return backups


def run_vbs_file_relink(
    assembly_path: str,
    changes: list[dict[str, Any]],
    *,
    output_path: str | None = None,
    backup_root: str | None = None,
) -> dict[str, Any]:
    assembly = Path(assembly_path)
    if not assembly.exists():
        raise RuntimeError(f"Assembly does not exist: {assembly_path}")

    output = Path(output_path or assembly_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    backup_root = backup_root or os.path.join(os.environ.get("KOMPAS_EXPORT_DIR", r"C:\Temp\kompas-mcp"), "relink-backups")
    backups = _backup_existing_targets(changes, backup_root)

    with tempfile.TemporaryDirectory(prefix="kompas-vbs-relink-", dir=os.environ.get("KOMPAS_MCP_TEMP_DIR", r"C:\Windows\Temp")) as temp_dir:
        temp_root = Path(temp_dir)
        changes_path = temp_root / "changes.tsv"
        result_path = temp_root / "result.tsv"
        script_path = temp_root / "run-relink.vbs"

        changes_lines = []
        for change in changes:
            old_path = change.get("old_path") or ""
            new_path = change.get("new_path") or ""
            if old_path and new_path:
                changes_lines.append(f"{old_path}\t{new_path}")
        changes_path.write_text("\n".join(changes_lines), encoding="utf-16")

        script = f"""Option Explicit
Dim assemblyPath, outputPath, changesPath, resultPath
assemblyPath = "{_escape_vbs_string(str(assembly))}"
outputPath = "{_escape_vbs_string(str(output))}"
changesPath = "{_escape_vbs_string(str(changes_path))}"
resultPath = "{_escape_vbs_string(str(result_path))}"

Function NormPath(value)
  NormPath = LCase(Replace(value, "/", "\\"))
End Function

Sub Walk(parent, prefix, changes, outFile)
  On Error Resume Next
  Dim parts, child, i, itemId, currentPath, updatedPath, newPath, key, ok, errMsg
  Set parts = parent.Parts
  If Err.Number <> 0 Then
    Err.Clear
    Exit Sub
  End If

  For i = 0 To parts.Count - 1
    Set child = parts.Item(i)
    itemId = prefix & "/" & CStr(i)
    currentPath = child.FileName
    key = NormPath(currentPath)
    If changes.Exists(key) Then
      newPath = changes(key)
      Err.Clear
      ok = child.SaveAs(newPath)
      errMsg = ""
      If Err.Number <> 0 Then
        ok = False
        errMsg = Err.Description
        Err.Clear
      End If
      updatedPath = child.FileName
      outFile.WriteLine itemId & vbTab & CStr(ok) & vbTab & currentPath & vbTab & updatedPath & vbTab & errMsg
    End If
    Call Walk(child, itemId, changes, outFile)
  Next
End Sub

Dim fso, ts, outFile, line, parts, changes, k5, app7, doc
Set fso = CreateObject("Scripting.FileSystemObject")
If LCase(assemblyPath) <> LCase(outputPath) Then
  fso.CopyFile assemblyPath, outputPath, True
End If

Set changes = CreateObject("Scripting.Dictionary")
Set ts = fso.OpenTextFile(changesPath, 1, False, -1)
Do Until ts.AtEndOfStream
  line = ts.ReadLine
  If Len(line) > 0 Then
    parts = Split(line, vbTab)
    If UBound(parts) >= 1 Then
      changes(NormPath(parts(0))) = parts(1)
    End If
  End If
Loop
ts.Close

Set outFile = fso.OpenTextFile(resultPath, 2, True, -1)
Set k5 = CreateObject("KOMPAS.Application.5")
k5.Visible = True
k5.ActivateControllerAPI
Set app7 = k5.ksGetApplication7()
app7.HideMessage = 1
Set doc = app7.Documents.Open(outputPath, True, False)
Call Walk(doc.TopPart, "root", changes, outFile)
doc.Save
doc.Close 0
app7.Quit
outFile.Close
"""
        script_path.write_text(script, encoding="utf-16")

        completed = subprocess.run(
            ["cscript", "//nologo", str(script_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "VBS relink failed")
        if not result_path.exists():
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "VBS relink did not produce a result file")

        applied: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for line in result_path.read_text(encoding="utf-16").splitlines():
            if not line:
                continue
            parts = line.split("\t")
            item_id = parts[0] if len(parts) > 0 else ""
            ok = (parts[1].strip().lower() == "true") if len(parts) > 1 else False
            old_path = parts[2] if len(parts) > 2 else ""
            new_path = parts[3] if len(parts) > 3 else ""
            err_msg = parts[4] if len(parts) > 4 else ""
            payload = {
                "item_id": item_id,
                "old_path": old_path,
                "new_path": new_path,
                "backup_path": backups.get(new_path),
                "method": "save_as",
            }
            if ok:
                applied.append(payload)
            else:
                payload["error"] = err_msg or "SaveAs returned False"
                failed.append(payload)

    return {
        "output_path": str(output),
        "applied_count": len(applied),
        "failed_count": len(failed),
        "applied": applied,
        "failed": failed,
        "saved": True,
    }
