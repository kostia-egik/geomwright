# Native transmission audit

Date: 2026-07-26

Environment: installed KOMPAS-3D v23

Scope: bounded discovery and command-dispatch audit; no transmission model was
created or saved.

## Result

The installed mechanical-transmission application is discoverable as:

```text
module: Shaft
title: Валы и механические передачи 3D+2D
app_id: APP_Shaft2D
manifest commands: 17
```

The module is registered through a procedure library and can be selected and
executed through the existing native command launcher.

## Manifest command map

Important commands found in the installed manifest:

| Command | Meaning | Context observed |
| --- | --- | --- |
| 201 | new mechanical model | 2D and 3D panels |
| 202 | mechanical-transmission calculations | 2D and 3D panels |
| 204 | additional constructions | 2D and 3D panels |
| 206 | mechanical-model construction | 2D and 3D panels |
| 207 | display by dimensions | 2D context |
| 210 | service symbols | 2D and 3D contexts |
| 211 | model info | 2D and 3D contexts |
| 213 | open calculation document | toolbar |
| 220 | update application documents | toolbar |

The duplicate IDs are context registrations, not separate calculation APIs.

## Static inspection

Bounded module inspection reported:

- 93 files in the installed module tree;
- one discovered database container;
- bounded interface scan of 40 files and 60 string hits;
- 15 registration artifacts;
- 98 C exports across 7 DLLs;
- four dispatch-like export candidates.

No proven public COM automation channel for calculation parameters was found.
The current assessment remains `launch_only_or_research` rather than headless
automation.

## Command 202 audit

Preview resolved command 202 to `Shaft` successfully without launching it.

Interactive launch was then explicitly authorized with:

```text
allow_interactive=true
post=true
```

The procedure-library call succeeded through the `automation_execute` signature
and posted the native command. The launch returned without adding, removing, or
changing documents. It opens the native interactive calculation interface.

The command does not expose its form fields, calculation object, selected gear
family, profile-shift method, or generating-tool parameters through the current
MCP/native bridge.

Three pre-existing changed user documents were open during the audit. They were
not activated, saved, closed, or modified by the audit.

## Capture boundary

The current host API has separate calls for launch and result capture:

- launch can preview or post a native command;
- capture can list documents/tree/items;
- capture does not inspect an open modal/native form;
- capture does not accept a result-kind selector or create an evidence artifact;
- there is no GUI-form automation layer.

Therefore the first external cylindrical pair cannot be completed unattended
with the current interfaces.

## Next manual/native experiment

Prerequisites:

1. start from a clean KOMPAS context or a dedicated disposable instance;
2. create a new 2D drawing/mechanical model;
3. capture the before-state;
4. post command 202;
5. manually create one external involute cylindrical pair;
6. save the calculation document and 2D model to an ignored evidence directory;
7. run command 206 to create exact 3D members;
8. save wheel and pinion artifacts;
9. capture after-state, trees, variables, attributes, and files;
10. repeat with a different `x1/x2` and generating-tool choice.

The manual step is a current automation blocker, not evidence that the native
module lacks the required calculation.

## Architectural consequence

Future transmission modules must not depend on command 202 or 206 at runtime.
Native outputs may be used as black-box reference evidence for profile points,
root transitions, calculation decisions, and 2D-to-3D operation ownership.
