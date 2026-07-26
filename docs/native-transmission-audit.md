# Native transmission audit

Date: 2026-07-26

Environment: installed KOMPAS-3D v23

Scope: bounded discovery and command-dispatch audit; no transmission model was
created or saved.

## Result and correction

The installed mechanical-transmission application is discoverable as:

```text
module: Shaft
title: Валы и механические передачи 3D+2D
app_id: APP_Shaft2D
manifest commands: 17
```

The module is registered through a procedure library and can be selected and
executed through the existing native command launcher.

The first audit invoked command 202 directly. That was a valid command-dispatch
probe but not a valid model-generation workflow: GEARS is a calculation backend
whose result must return to a Shaft host. A standalone invocation can calculate
or save a calculation result, but it has no owner that would build a drawing or
3D member.

## Manifest command map

Important commands found in the installed manifest:

| Command | Meaning | Context observed |
| --- | --- | --- |
| 201 | model design | `Shaft2D_toolBarSet`, 3D+2D workflow in a 2D document |
| 202 | mechanical-transmission calculations | shared GEARS backend; also directly registered |
| 204 | additional constructions | 2D and 3D panels |
| 206 | model design | `ShaftM3D_toolBarSet`, workflow from a 3D part |
| 207 | display by dimensions | 2D context |
| 210 | service symbols | 2D and 3D contexts |
| 211 | model info | 2D and 3D contexts |
| 213 | open calculation document | toolbar |
| 220 | update application documents | toolbar |

`ShaftA3D_toolBarSet` registers command 202 but not model-design command 201/206.
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

## Standalone command 202 audit

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
MCP/native bridge. More importantly, the standalone call has no Shaft owner to
receive the result, so absence of a drawing or 3D model is expected rather than a
failure of the calculation module.

Three pre-existing changed user documents were open during the audit. They were
not activated, saved, closed, or modified by the audit.

## Capture boundary

The current host API has separate calls for launch and result capture:

- launch can preview or post a native command;
- capture can list documents/tree/items;
- capture does not inspect an open modal/native form;
- capture does not accept a result-kind selector or create an evidence artifact;
- there is no GUI-form automation layer.

Therefore a complete native model requires the correct host entry point and
manual interaction with its UI. Direct command 202 is not used for the next
audit.

## Command 206 pulley attempt

A disposable 3D part was created and saved under ignored live evidence. It
contained only one neutral reference point. The part was explicitly activated
before command 206 was posted.

The disposable file was removed after the failed attempt because it contained no
successful pulley evidence.

Manifest context and launch evidence confirmed:

- command 206 belonged to `ShaftM3D_toolBarSet`;
- the procedure-library dispatch succeeded through `automation_execute`;
- Shaft created an additional unsaved `Untitled` document;
- the native Shaft model-design interface opened.

During manual creation of a simple V-belt pulley, the native interface reported
errors at multiple steps and became unusable. The operator restarted KOMPAS; all
open documents were consequently closed. No pulley model or reusable native
result was produced.

This attempt does not prove that Shaft cannot build the pulley. It proves that
the current command-plus-manual workflow is not safe or deterministic enough to
run inside a shared KOMPAS session.

### Revised safety boundary

Further Shaft/GEARS UI experiments require:

1. a dedicated disposable KOMPAS process, not merely another document/session in
   the shared process;
2. all user documents saved and closed before launch;
3. one experiment per process;
4. immediate stop after the first repeated native error;
5. screen-level/manual evidence of every UI choice;
6. no automatic retry of command 201, 202, or 206;
7. post-run document/file capture only after the operator confirms that the UI
   completed successfully.

Until those conditions are met, native pulley generation is not used as a
reference oracle.

## Deferred pulley-oriented experiment

Prerequisites:

When a dedicated disposable KOMPAS process is available:

1. record the clean session state;
2. manually launch the 3D Shaft application through the normal UI first;
3. reproduce the same path through command 206 only after the manual route is
   understood;
4. create one simple V-belt pulley without unrelated hub/bore details;
5. save/capture the result under ignored live evidence;
6. repeat the same pulley through the normal 3D+2D UI in a clean 2D document;
7. compare catalog fields, ownership, and generated geometry;
8. determine whether the pulley workflow invokes GEARS at all.

The manual step is a current automation blocker. Deep cylindrical-gear and GEARS
research is deferred until the gear phase; the immediate target is the pulley
catalog/profile/build workflow.

## Architectural consequence

Future transmission modules must not depend on command 201, 202, or 206 at
runtime. Native pulley outputs may be used as black-box reference evidence for
catalog fields, groove profiles, operation ownership, and 2D-to-3D generation.
