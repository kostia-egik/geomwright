from __future__ import annotations

from dataclasses import dataclass

from .constraints import ConstraintPlan, ConstraintSpec, ConstraintStageSpec
from .dimensions import DimensionBinding, VariableSpec
from .directions import DirectionAlias
from .entities import Point, Segment, SketchModel
from .frames import Frame2D, Vector2
from .measurements import MeasurementExpectation
from .orientation import LoopOrientationExpectation
from .relations import PointRelationExpectation
from .verify import SketchPreflightPlan


@dataclass(frozen=True)
class FlatV60ThreadProfileSpec:
    pitch: float
    crest_y: float
    root_y: float
    outer_half_width: float
    root_half_width: float
    frame_id: str = "profile_lcs"


def build_flat_v60_thread_profile_preflight(spec: FlatV60ThreadProfileSpec) -> SketchPreflightPlan:
    """Build a small runtime contract for the common flat V60 profile sketch.

    The factory is intentionally COM-free. It models the tiny interaction layer:
    semantic entities, local frame contract, contour topology, staged constraints,
    dimensions, and sanity checks that should pass before KOMPAS receives calls.
    """

    model = SketchModel(
        name="flat_v60_thread_profile",
        expected_loops=("profile",),
        points=(
            Point("left_outer", -spec.outer_half_width, spec.crest_y, role="left crest point"),
            Point("left_root", -spec.root_half_width, spec.root_y, role="left root point"),
            Point("right_root", spec.root_half_width, spec.root_y, role="right root point"),
            Point("right_outer", spec.outer_half_width, spec.crest_y, role="right crest point"),
            Point("crest_center", 0.0, spec.crest_y, role="crest reference"),
            Point("root_center", 0.0, spec.root_y, role="root reference"),
        ),
        primitives=(
            Segment("left_flank", "left_outer", "left_root", role="left flank", loop_id="profile"),
            Segment("root_flat", "left_root", "right_root", role="flat root", loop_id="profile"),
            Segment("right_flank", "right_root", "right_outer", role="right flank", loop_id="profile"),
            Segment("crest_flat", "right_outer", "left_outer", role="flat crest", loop_id="profile"),
        ),
        metadata={"profile": "flat_v60"},
    )

    variables = (
        VariableSpec("P", spec.pitch, role="thread pitch"),
        VariableSpec("H_OUTER", spec.outer_half_width * 2.0, role="outer profile width"),
        VariableSpec("H_ROOT", spec.root_half_width * 2.0, role="root flat width"),
        VariableSpec("DEPTH", abs(spec.crest_y - spec.root_y), role="radial thread depth"),
    )

    return SketchPreflightPlan(
        model=model,
        frame=Frame2D(
            id=spec.frame_id,
            x_axis=Vector2(1.0, 0.0),
            y_axis=Vector2(0.0, 1.0),
            x_role="pitch direction",
            y_role="radial outward",
        ),
        direction_aliases=(
            DirectionAlias("pitch_forward", Vector2(1.0, 0.0), "+x", role="profile pitch direction"),
            DirectionAlias("radial_outward", Vector2(0.0, 1.0), "+y", role="profile radial direction"),
        ),
        constraints=ConstraintPlan(
            stages=(
                ConstraintStageSpec("anchor", required_ids=("fix_crest_center",)),
                ConstraintStageSpec("orientation", required_ids=("root_horizontal", "crest_horizontal")),
                ConstraintStageSpec("shape", required_ids=("left_flank_profile", "right_flank_profile")),
                ConstraintStageSpec("driving_dimensions"),
                ConstraintStageSpec("deferred"),
            ),
            constraints=(
                ConstraintSpec("fix_crest_center", "fixed", ("crest_center",), stage="anchor", role="anchor origin"),
                ConstraintSpec("root_horizontal", "horizontal", ("root_flat",), stage="orientation", role="root flat"),
                ConstraintSpec("crest_horizontal", "horizontal", ("crest_flat",), stage="orientation", role="crest flat"),
                ConstraintSpec("centerline_vertical", "vertical", ("crest_center", "root_center"), stage="orientation", role="radial axis"),
                ConstraintSpec("left_flank_profile", "coincident", ("left_outer", "left_root"), stage="shape", role="left flank endpoints"),
                ConstraintSpec("right_flank_profile", "coincident", ("right_outer", "right_root"), stage="shape", role="right flank endpoints"),
            ),
        ),
        relations=(
            PointRelationExpectation("outer_left_right", "left_of", "left_outer", "right_outer", role="crest width"),
            PointRelationExpectation("root_left_right", "left_of", "left_root", "right_root", role="root width"),
            PointRelationExpectation("left_root_below_crest", "below", "left_root", "left_outer", role="radial depth"),
            PointRelationExpectation("right_root_below_crest", "below", "right_root", "right_outer", role="radial depth"),
            PointRelationExpectation("crest_center_same_y", "same_y", "crest_center", "left_outer", role="crest reference"),
            PointRelationExpectation("root_center_same_y", "same_y", "root_center", "left_root", role="root reference"),
        ),
        measurements=(
            MeasurementExpectation("outer_width", "horizontal_distance", ("left_outer", "right_outer"), spec.outer_half_width * 2.0, role="crest width"),
            MeasurementExpectation("root_width", "horizontal_distance", ("left_root", "right_root"), spec.root_half_width * 2.0, role="root width"),
            MeasurementExpectation("thread_depth", "vertical_distance", ("crest_center", "root_center"), abs(spec.crest_y - spec.root_y), role="radial depth"),
        ),
        orientations=(LoopOrientationExpectation(loop_id="profile", orientation="ccw"),),
        variables=variables,
        dimensions=(
            DimensionBinding("dim_outer_width", "horizontal_distance", ("left_outer", "right_outer"), "H_OUTER", role="outer width"),
            DimensionBinding("dim_root_width", "horizontal_distance", ("left_root", "right_root"), "H_ROOT", role="root width"),
            DimensionBinding("dim_depth", "vertical_distance", ("crest_center", "root_center"), "DEPTH", role="radial depth"),
            DimensionBinding("dim_pitch_ref", "horizontal_distance", ("left_outer", "right_outer"), "P", expression="P", required=False, role="pitch reference"),
        ),
    )
