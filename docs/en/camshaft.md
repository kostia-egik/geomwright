# Camshaft lobes: calculation and CAD

[Documentation](../README.md) · English · [Русский](../ru/camshaft.md)

Studio turns valve events and a lift law into a sampled cam contact envelope.
It is an engineering preview, not a reconstruction of a production camshaft or
a manufacturing approval. Accepted profiles can be built in KOMPAS as one solid
cam, without a shaft, hub or bore.

## Open the editor

Install and start Studio using the [project instructions](../../README.md#install),
then choose **New model → Valve train → Camshafts → Camshaft lobe**.
KOMPAS is not required for the host-side cam calculation. The workspace can show
a disconnected state while the preview remains usable.

The three tabs have different responsibilities:

1. **Phases** accepts signed crank angles relative to TDC/BDC. Negative means
   before the reference. The summary uses an absolute 720° crank cycle, starting
   at firing TDC: exhaust BDC 180°, overlap TDC 360°, intake BDC 540°.
   The circular diagram overlays the two revolutions; it is not a 360° cycle.
2. **Kinematics** shows the base circle, rocker or tappet, and two valve positions.
   The cam outline and rocker body are illustrative. Its pressure indicator is a
   radial layout estimate, not the maximum operating pressure angle.
3. **Cam** calculates the envelope from the lift law, contact, and mechanism.
   Rise/fall angles and clearance ramps are in **camshaft degrees**, half the
   crankshaft angle. The input lift and lash are valve-side millimetres.

## Build in KOMPAS

Start visible KOMPAS and open **Cam**. Set the width, additional rotation about X
and CAD curve accuracy. The event must leave a nonzero base-circle interval;
CAD profiles without a base arc are not supported. **Create in KOMPAS** becomes available after accepted
preflight. Rejected candidates, errors and stale calculations cannot authorize a
write. Inputs are recalculated before creation; the illustrative Kinematics
outline is never used for CAD.

The profile lies in global YZ: preview horizontal is Y, vertical is Z. Positive
additional rotation turns +Y toward +Z about +X; the valve phase is already
included. The solid occupies X=`[-width,0]`. A new unsaved part contains two
operations, **Sketch Cam Profile** and **Extrusion Cam**. After verification it
appears in the workspace; use the normal document command to save it.

The working profile is one cubic NURBS, closed by a true circular base arc.
Arc-length interpolation retains tangent continuity and refines knots if position
or curvature checks fail. The source is sampled at 10 points per degree, with
held-out points that are not interpolation nodes. Verification covers closure,
base tangency, stationary curvature points of every cubic span, the base-arc
radius, and sampled self-intersection. At selected follower positions, flat
support and roller distance use extrema of the curve itself, rather than its
sampled vertices. Roller pressure angle uses every source-grid position and the
actual curve tangent; flat
profiles are also checked for concave/undercut regions. Verification has a finite
sampling budget, so an excessive base radius at tight accuracy can be rejected
before writing. These are sampled checks, not continuous global proofs.

Actual curve parameters are read after rebuild. Results include the verification,
body bounds, volume and single-solid status. Volume is compared with the integral
of the actual profile rather than the input form dimensions. Default accuracy is
`0.01 mm`; it bounds profile/contact recovery accuracy, not slack for curvature,
tappet diameter or pressure-angle limits. Independent numerical comparison floors
are `1e-8 mm` and `1e-6 degrees`. This is not a manufacturing tolerance. A profile
previously accepted slightly below its curvature requirement may now be rejected;
increasing CAD tolerance cannot bypass the engineering limit.

The profile is **numeric and create-only**, without full sketch parameterization.
`CAM_*` variables are metadata, not driving parameters. Changed inputs require a
new cam; persisted geometry remains read-only in Studio. Version-2 blocks retain
the full calculation recipe and, for Studio builds, the original form. **Create a
new cam from these settings** restores that form without changing the source
part. For MCP variants not representable in the current Studio form, use the
saved MCP recipe. Legacy version-1 blocks remain recognizable but have no full
recoverable recipe or confirmed persisted verification status. A shaft, another cam, hub,
bore or other structure belongs to separate standard operations. The result exports
sketch and extrusion references for subsequent composition.

Bounded `CAM_RECIPE_*` text chunks carry a version and SHA-256 checksum, checked
on readback. Read-only `inspect_cam(document_id)` returns the recognized block,
recipe and persisted verification status. Pass recipe fields `request`, `width`,
`rotation_deg`, `tolerance` and `name` to a new `create_cam` call. Recognition is
not a fresh geometry audit.

Native readback leaves the block unverified until host checks pass. Finalization
matches the exact document, references, actual curve and bounds before setting
`CAM_VERIFIED=1`. Errors include `partial_result` with the stage and owned-document
identifier when available. Cancellation/timeouts stop the child bridge, not
KOMPAS; created objects remain open. Inspect a partial document before retrying:
retry creates a separate new part, never resumes or automatically closes the
partial one. An interruption before the first document checkpoint may leave its
identifier unknown. Cancellation is not transactional rollback.

MCP exposes `create_cam`. Without `execute=true` it returns a plan without COM;
writing also requires `confirm_write=true`:

```json
{
  "request": {
    "mechanism": "direct", "contact": "flat", "law": "bounded_auto",
    "base_radius": 30, "max_lift": 8, "open_angle": 60, "close_angle": 60,
    "tappet_diameter": 40
  },
  "width": 12, "rotation_deg": 0, "tolerance": 0.01,
  "execute": true, "confirm_write": true
}
```

`open_angle` and `close_angle` are cam degrees; the optional `timing` block uses
the existing crank-event conversion. Rockers use the arm/contact parameters in
`kompas_mcp/cams/spec.py`; Studio translates its layout into that contract.

## Calculation contract

- Direct drive uses a flat translating follower. The envelope includes the
  angular derivative of lift; it is not simply the polar lift graph.
- Rocker drive uses a roller and fixed arm lengths with a flat valve-end contact.
  Valve-axis projection determines rotation; the physical arm does not change
  length. The normal comes from the tangent of the roller-centre trajectory.
- Pressure angles compare the contact normal and follower direction in the same
  coordinate frame. Rotating the profile does not change their extrema.
- Derivatives are with respect to **cam radians**: mm/rad, mm/rad², mm/rad³.
  They are not physical velocity/acceleration without a specified shaft speed.
- Positive lash adds opening/closing ramps outside the valve event. The default
  cubic `smooth` ramp is C1, not acceleration-continuous. The displayed continuity
  order describes this prescribed motion, not valve-train dynamics.
   The contact-aware spline and automatic selection use quintic `smooth_c2` ramps by default, retaining
  C2 continuity of the complete follower motion. Jerk can still jump at junctions.
- Sampling is bounded at 10 points per degree; Studio's Cam tab and CAD preflight
  use that same density to select the same profile. Self-intersection
  and curvature diagnostics are sampled estimates, not exact global proofs.
- Flat-contact undercut checks `base radius + lift + acceleration > 0`.
  Roller undercut compares the roller radius with **convex pitch-curve** radius,
  not the finished cam's minimum absolute curvature radius.

## Motion charts

On **Cam**, switch from **Profile** to **S/V/A/J charts**. The four panels show
lift, velocity, acceleration and jerk. Direct drive uses translating follower
motion; a rocker uses the commanded valve-side lift, not roller-centre motion
or rocker angle. The command includes lash take-up; actual net valve lift is
also shown as a dashed S curve.

X uses cam degrees from complete-motion start, including the opening ramp.
Derivatives come from the kernel in mm/rad, mm/rad² and mm/rad³, without finite
differences or conversion to time derivatives. Ramps are shaded; each panel
has its own vertical scale. Hover or use the keyboard-capable slider for a shared
cursor, stage name and sampled values. Acceleration/jerk caps appear as ± dashed
lines and text; a cap far outside the scale remains labelled in the header.

Finite peak values come from the calculation summary rather than the drawn
polyline: standard-law, spline and C2-ramp extrema are analytic. Known derivative
jumps are not joined by lines. For C1 motion the finite plotted jerk does not
represent the impulse at an acceleration jump; the interface labels these
junctions. Charts are not continuous geometric proofs or replacements for warnings.

During recalculation or after an error, previous charts are dimmed and labelled.
Their values and caps belong to the previous result, not the new form inputs.
Phases, Kinematics and other modules hide the charts. Kernel and Studio return
`motion_chart` arrays, windows, caps and break metadata; no KOMPAS access is needed.

## Selecting feasible parameters

Studio defaults to **Select an available law automatically** (`bounded_auto`).
It compares 3-4-5, 4-5-6-7, 5-6-7-8-9 and cycloidal laws. Without nose dwell it
also tries C2 motion splines; direct flat contact adds the contact-aware C2 spline.
Dimensions, timing and caps
stay unchanged. Passing candidates are ranked by peak angular jerk, then list order.

This works for **rocker followers** too: each candidate goes through fixed-arm
inverse kinematics and roller-envelope construction, with pressure angle, convex
pitch curvature, finished-profile curvature and self-intersection checks. It does
not apply the flat-face support equation to a rocker or assume a constant ratio.
Acceleration and jerk caps also apply to manually selected laws. On a rocker,
they constrain the commanded **valve-side lift coordinate including lash ramps**,
not rocker angular acceleration or roller-centre acceleration. Standard-law and
C2-ramp extrema are analytic and sampling-independent; geometry checks are sampled.

If none passes, the candidate with fewer issues is displayed with an explicit
**not accepted** warning. Failure in these bounded families does not prove every profile
impossible. The kernel's `selection` records status and candidate issues.

Change one input at a time and recheck: extend the event/ramps or reduce lift for
derivative violations; increase the flat tappet's working diameter for edge
contact; increase the base or extend motion for flat undercut; try a smaller
roller or larger base for roller undercut; revise axis/arm layout for pressure
angle. These are search directions, not guaranteed improvements to all metrics.
Stretching the angle by `k` reduces acceleration by `1/k²` and jerk by `1/k³`.
Only relax supplied caps after revisiting their engineering justification.
Normal clearance take-up and module-scope notes are not shown as geometry alarms.

## Motion splines for rocker and direct drive

Choose **C2 motion spline with contact checks** (`motion_spline`) on Cam, or leave
automatic selection enabled. Piecewise-linear valve acceleration on nine fixed
knots integrates into cubic lift, quadratic velocity and constant jerk spans.
Two pulse amplitudes solve the required nose lift and zero velocity. Both flanks
share nose acceleration, retaining C2 even for unequal durations; jerk can jump.

The budget is 48 pulse/nose-acceleration combinations. Monotonicity and derivative
extrema are analytic. Kinematically valid candidates are ranked by main-event jerk,
then acceleration and a stable ID; contact checking stops at the first passing
candidate. This is not free-knot optimization or global lift-area maximization.

Each candidate runs the actual mechanism/envelope calculation, including lash
ramps, checking complete-profile curvature, pressure angle, undercut, face reach
where applicable, and self-intersection. Search uses at least two points per degree;
promising candidates receive a doubled-density check, capped at ten points per
degree. Geometry validation is still sampled, not a continuous proof. Inputs are
not relaxed. Peak arm-projection reach is rejected as inverse-kinematic singularity.

No kinematic candidate produces `cam_motion_no_kinematic_solution`. Contact
failure produces `synthesis.status = no_passing_candidate`, a clearly unaccepted
contour and diagnostics. `synthesis` reports the candidate ID, acceleration controls,
tested counts and actual density. Nose dwell is unsupported. An input nose radius
belongs only to flat-contact synthesis; motion-spline nose geometry follows from
the motion and actual mechanism.

Synthetic rocker example, **not an engine limit recommendation**: keep Studio's
initial geometry (60 mm base diameter, 10 mm roller radius, 30 mm roller arm,
cam axis `(0, 50)`, valve end `(60, 4)`), 8 mm lift, 0.3 mm lash and intake timing
`-10 / +50` (240 crank degrees). Set both ramps to 25 cam degrees, acceleration
cap to 100 mm/rad² and jerk cap to 250 mm/rad³. All four standard laws exceed
the jerk cap; automatic selection chooses `motion_spline`, with complete-motion
peaks about 52.52 mm/rad² and 216.68 mm/rad³, and pressure angle about 13.47°.

## Small base, high direct lift

Choose **Direct** on Kinematics, then **Contact-aware C2 spline**
on Cam. This option is separate from the normalized polynomial motion laws;
it can be selected manually independently of automatic selection.

The spline solves the flat-face support equation `h'' + h = ρ`, where
`h = base radius + lash + valve lift`. Piecewise-linear positive curvature `ρ`
gives continuous lift, velocity, and acceleration with a nonzero nose
deceleration. Segment integration is analytic. A fixed 12-knot family and a
bounded nose-radius search select a monotone solution by peak contact offset,
subject to any specified acceleration and jerk limits;
this is not a global optimum or a reproduction of Tilden's proprietary software.
Opening and closing can have different durations but share the same nose radius.
Roller/rocker drive and nose dwell are not supported by this profile.

Minimum curvature is an explicit input. Leave nose radius blank for bounded
selection, or enter a required radius. A failure to find a family solution is
reported separately from a necessary geometric support bound.
The minimum-radius constraint applies to the main valve event; clearance ramps
are checked separately and warn if the complete profile falls below that radius.

Positive curvature alone is not enough. Minimizing contact width without
derivative limits can produce an excessive initial acceleration spike. Set
**Max. |acceleration|** and **Max. |jerk|** for the actual valve train; blank fields
mean unbounded and produce an explicit warning. Main-event derivative extrema
are evaluated analytically on every segment, including both sides of jerk jumps.
Complete-motion diagnostics also check clearance ramps. These are **cam-angle**
derivatives, not time acceleration or force limits. At constant shaft speed,
time acceleration scales with `ω²` and jerk with `ω³`; mass, springs and RPM
are outside this module's contract: a separate tool validates them and supplies
input limits. Their absence is not a geometry error.

Reproducible geometric example, **not an OEM cam card**:

| Setting | Value |
| --- | --- |
| Intake opening / closing | -70° from TDC / +70° from BDC (320° crank event) |
| Mechanism / law | Direct / contact-aware C2 spline |
| Base diameter / valve lift | 30 mm / 18 mm |
| Lash / opening and closing ramps | 0.3 mm / 25° camshaft each |
| Minimum curvature / nose radius | 3 mm / automatic |
| Max. angular acceleration / jerk | 100 mm/rad² / 1500 mm/rad³ |
| Tappet working diameter / edge allowance | 48 mm / 0.5 mm |

These derivative limits are example inputs, not universal engine limits.
This produces an 18.3 mm radial height above the base, minimum active curvature
of 3 mm, and a required tappet working diameter of about 46.63 mm. Remaining
edge allowance is about 0.68 mm after the requested 0.5 mm allowance.
Peak angular acceleration is about 90.81 mm/rad², jerk 1477.13 mm/rad³.
The profile has no sampled self-intersection; inverse flat-face contact
reproduces the prescribed lift.

Tappet width matters for **all** direct flat laws. Contact-point offset is the
angular lift derivative, not lift itself. Studio checks the working face diameter,
edge allowance, and lateral offset; unspecified width remains unverified.
For the new spline, span velocity extrema are analytic rather than sample-only.
Standard-law peak contact offsets are also evaluated independently of sampling.

Shortening the same valve event to 240° crank is not fixed by choosing another
spline: for the stated sizes and 3 mm minimum radius each flank must exceed about
66.05° camshaft (a symmetric event over 264.20° crank is a necessary, not
sufficient, bound). Shorter feasible events also tend to need wider tappets.
The generator does not enlarge the base, lower the lift, or widen the event silently.

## Published references

| Reference | Intake BTDC / ABDC | Exhaust BBDC / ATDC | Duration | Overlap |
| --- | --- | --- | --- | --- |
| Kent TR4-6 | 42° / 68° | 78° / 32° | 290° | 74° |
| Stock TR2, Elgin data reported by Tilden | 10° / 50° | 50° / 10° | 240° | 20° |
| TilTech 270, Tilden | 28° / 62° | 66° / 24° | 270° | 52° |

For Kent TR4-6 enter `-42, 68, -78, 32` in the four phase fields. The intake
centre is 103° ATDC; the calculated cam event spans 145°. These values verify
timing conversion only. Seat duration, duration at 0.050-inch lift, gross cam
lift, net cam lift, and valve lift are different quantities and must not be mixed.

Sources checked on 2026-10-01:

- [Kent TR4-6 manufacturer card](https://www.kentcams.com/part/TR4-6).
- [Tilden Triumph cam comparison](https://www.tildentechnologies.com/Cams/TriumphCams.html).
- [Tilden cam design](https://www.tildentechnologies.com/Cams/CamDesign.html):
  flat-follower contact distance and curvature equations.

## Comparison with other approaches

Sources checked 2026-10-02:

- [Tilden / Opticam](https://www.tildentechnologies.com/Cams/CamDesign.html)
  assumes velocity, acceleration and jerk limits are known for lobe design, and
  describes constrained piecewise motion with cubic/quartic splines. Our fixed
  12-knot family search is substantially narrower.
- [CamTrax64 official features](https://camnetics.com/camtrax64/) separate cam,
  follower and motion types, including swinging arms, standard laws and user
  points, with S/V/A/J, curvature and pressure-angle charts/tables. Its force/stress
  features are not requirements for our geometry scope.
- The public DYNACAM page is password-protected; its private documentation was
  not used to make implementation or feature claims.

A geometry tool with externally established derivative limits is a valid scope,
but this module is not yet a full replacement: free segment programs, measured
lift import, continuous-family rocker optimization and
manufacturing export remain missing. Rockers currently get bounded selection of
existing laws and bounded C2 motion synthesis with contact checks, not free-control
optimization under continuous geometric constraints. Adding masses/RPM would
not close these geometry gaps.

## Readiness and remaining limits

The supported preview is suitable for timing and geometric exploration, not
production sign-off. A selected polynomial or cycloidal law does not reproduce
a measured OEM lift curve. Exact reproduction needs a lift table or measured
contour plus follower and installation geometry.

The valve-pad radius affects the illustrative layout only; finite-radius pad
contact synthesis is not implemented. Direct-drive lateral offset does not alter
the infinite-flat-face envelope, but does alter its finite-face edge check.
The working diameter must describe the usable flat surface, not the outside
diameter of a chamfered bucket. The schematic lash placement is not a full assembled contact
simulation. No spring forces, RPM-dependent dynamics, contact stress, wear,
collision simulation or manufacturing tolerance approval is supplied. CAD creation,
rebuild and save/reopen acceptance cover the direct C2 and roller-rocker control
examples, not every parameter combination. Do not interpret a warning-free profile
as a safe engine design.

Developers: `kompas_mcp/cams/` owns the calculation; `geomwright/studio/camshaft.py`
adapts it to Canvas. Focused verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cams.py tests/test_camshaft_studio.py tests/test_geomwright_studio.py -q
```
