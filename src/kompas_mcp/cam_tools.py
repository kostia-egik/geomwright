from __future__ import annotations

from typing import Any


def register_cam_tools(mcp: Any, adapter: Any) -> None:
    @mcp.tool()
    def inspect_cam(document_id: str) -> dict:
        """Read a recognized cam's saved recipe and verification status, without writes.

        Requires an exact opened document ID. A version-2 recipe contains request,
        width, rotation_deg, tolerance and name for a new create_cam call. Legacy
        cams have no recoverable recipe. Recognition is not a fresh geometry audit.
        Partial results are explicitly unverified; never update them in place.
        """
        return adapter.inspect_cam(document_id)

    @mcp.tool()
    def create_cam(
        request: dict[str, Any], width: float = 12.0, rotation_deg: float = 0.0,
        tolerance: float = 0.01, name: str = "Geomwright cam",
        execute: bool = False, confirm_write: bool = False, visible: bool = True,
    ) -> dict:
        """Plan or create ONE solid cam in a new KOMPAS part, without shaft/hub/bore.

        request uses the cam calculation contract: base_radius, max_lift,
        open_angle/close_angle (CAM degrees), law, mechanism=direct|rocker,
        contact=flat|roller, lash and ramps. Direct example:
        {base_radius:30,max_lift:8,open_angle:60,close_angle:60,
         law:bounded_auto,mechanism:direct,contact:flat,tappet_diameter:40}.
        Rocker additionally uses roller_radius, roller_arm, roller_angle_deg,
        valve_arm, valve_angle_deg, valve_axis_deg. Optional timing block accepts
        crank angles via the existing timing conversion. The profile lies in
        global YZ; positive rotation_deg rotates Y toward Z about global +X.
        Width occupies X=[-width,0]. tolerance is sampled geometric accuracy in mm,
         not a manufacturing tolerance or slack for engineering limits. Refused
         candidates never enter KOMPAS. Curvature uses cubic stationary points;
         contact/pressure checks still use sampled follower positions.
        execute=false is read-only preflight; writing also needs confirm_write=true.
        Returns document, sketch/feature references, actual body bounds/volume and
        curve/contact verification. Numeric create-only profile: change inputs by
        creating a new cam, then compose other elements through standard operations.
        """
        return adapter.create_cam(request,width=width,rotation_deg=rotation_deg,
                                  tolerance=tolerance,name=name,execute=execute,
                                  confirm_write=confirm_write,visible=visible)
