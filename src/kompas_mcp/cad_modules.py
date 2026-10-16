"""Host-side discovery and bounded dispatch for existing CAD families.

This registry describes capabilities; it does not implement CAD algorithms or
turn create-only families into an editable model graph.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
import json
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .gears import (
    BevelGearCreateRequest, BevelGearRequest,
    InternalGearCreateRequest, InternalGearRequest,
    SpurGearCreateRequest, SpurGearRequest,
    build_bevel_gear_preview, build_internal_gear_preview, build_spur_gear_preview,
)
from .gears.cad import build_bevel_gear_plan, build_gear_spur_plan, build_internal_gear_plan
from .runtime_errors import classify_runtime_error
from .cad_module_bindings import (
    chain_plan, chain_plan_data, chain_preview, create_chain, create_plan,
    gear_plan_data, inspect_chain, inspect_plan,
    cam_plan, cam_plan_data, cam_preview, create_cam_module, inspect_cam_module,
    ModuleInputRequired, silent_plan, silent_plan_data, silent_preview,
    create_silent_module, inspect_silent_module,
)
from .cams.module_contract import CamModuleParameters
from .transmissions.silent_geometry import SilentChainSelectionRequest
from .cad_pulley_bindings import (PULLEY_MODELS, PULLEY_EXAMPLES, pulley_preview, pulley_plan,
    pulley_plan_data, create_pulley_module, inspect_pulley_module)
from .cad_spring_bindings import (CompressionSpringParameters, spring_preview, spring_plan,
    spring_plan_data, create_spring_module, inspect_spring_module)
from .cad_extension_bindings import (ExtensionSpringParameters, extension_preview, extension_plan,
    extension_plan_data, create_extension_module, inspect_extension_module)
from .cad_torsion_bindings import (TorsionSpringParameters, torsion_preview, torsion_plan,
    torsion_plan_data, create_torsion_module, inspect_torsion_module)
from .cad_disc_bindings import (DiscSpringParameters, disc_preview, disc_plan,
    disc_plan_data, create_disc_module, inspect_disc_module)
from .cad_shaft_bindings import (SteppedShaftParameters, shaft_preview, shaft_plan,
    shaft_plan_data, create_shaft_module, inspect_shaft_module)
from .cad_cone_bindings import (ExternalConeParameters,cone_preview,cone_plan,cone_plan_data,create_cone_module,inspect_cone_module)
from .cad_polygon_bindings import (ExternalPolygonParameters, polygon_preview, polygon_plan,
    polygon_plan_data, create_polygon_module, inspect_polygon_module)
from .cad_flat_bindings import (ExternalFlatParameters, flat_preview, flat_plan,
    flat_plan_data, create_flat_module, inspect_flat_module)
from .cad_diaphragm_bindings import (DiaphragmSpringParameters, diaphragm_preview, diaphragm_plan,
    diaphragm_plan_data, create_diaphragm_module, inspect_diaphragm_module)
from .transmission_tools import ChainSprocketCreateRequest, ChainSprocketPreviewRequest


ModuleAction = Literal["preview", "plan", "create", "inspect"]


class CadModuleRequest(BaseModel):
    """One module action. Obtain family parameter schemas with get_cad_module_contract."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[1] = 1
    module_id: str = Field(min_length=1, max_length=80)
    action: ModuleAction
    parameters: dict[str, Any] = Field(default_factory=dict)
    name: str | None = Field(
        default=None, min_length=1, max_length=120,
        description="Omit to use the module's default_name.",
    )
    document_id: str | None = None
    confirm_write: bool = False
    visible: bool = True

    @model_validator(mode="after")
    def _target(self) -> "CadModuleRequest":
        if self.action == "inspect":
            if not self.document_id or not self.document_id.strip():
                raise ValueError("inspect requires the exact opened document_id")
            if self.parameters:
                raise ValueError("inspect reads saved parameters; do not supply parameters")
        elif self.document_id is not None:
            raise ValueError("document_id is only supported for inspect; create makes a new part")
        if self.confirm_write and self.action != "create":
            raise ValueError("confirm_write is only supported for create")
        return self


class CadModuleResult(BaseModel):
    """Compact result; verified means fresh creation readback, never recipe recognition."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[1] = 1
    module_id: str
    action: ModuleAction
    ok: bool = False
    stage: Literal["previewed", "planned", "verified", "recognized", "refused", "failed"]
    executed: bool | None = Field(
        default=False, description="Null on a runtime failure when write completion is unknown."
    )
    verified: bool = False
    parameters: dict[str, Any] | None = Field(
        default_factory=dict, description="Null when inspection cannot recover a complete recipe."
    )
    data: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    partial_result: dict[str, Any] | None = None


@dataclass(frozen=True)
class CadModule:
    module_id: str
    title: str
    request_model: type[BaseModel]
    default_name: str
    preview: Callable[[dict], dict]
    plan: Callable[..., dict]
    create: Callable[[Any, dict, bool], dict]
    inspect: Callable[[Any, str], dict]
    limitations: tuple[str, ...]
    example_parameters: dict[str, Any]
    selection_tools: tuple[str, ...]
    frame: dict[str, str]
    units: dict[str, str]
    plan_data: Callable[[dict], dict] = gear_plan_data
    creation_policy: str = "new_unsaved_part"

    def descriptor(self) -> dict:
        return {
            "module_id": self.module_id,
            "title": self.title,
            "contract_version": 1,
            "default_name": self.default_name,
            "creation_policy": self.creation_policy,
            "actions": ["preview", "plan", "create", "inspect"],
            "capabilities": {
                "create_new_document": True, "inspect": True,
                "recreate_from_recipe": True, "update_in_place": False,
                "apply_to_existing_body": False,
            },
        }


CAD_MODULES = {
    "gear_spur": CadModule(
        module_id="gear_spur",
        title="External cylindrical gear (spur or helical)",
        request_model=SpurGearRequest,
        default_name=SpurGearCreateRequest.model_fields["name"].default,
        preview=build_spur_gear_preview,
        plan=build_gear_spur_plan,
        create=partial(create_plan, method="create_gear_spur"),
        inspect=partial(inspect_plan, method="inspect_gear_spur"),
        limitations=(
            "Creates one new unsaved part; no hub, mounting bore or shaft.",
            "Numeric create-only profile; changed inputs require a new part.",
            "Nominal sharp-rack root envelope and fitted flanks; not a manufacturing conformity claim.",
            "Inspect recognizes ownership and a saved recipe, not a fresh geometry audit.",
            "Recipe recreation depends on the inspected block's recreatable flag.",
            "Failed or cancelled creation may leave a partial document; there is no automatic rollback or retry.",
        ),
        example_parameters={"module_mm": 2, "tooth_count": 20, "face_width_mm": 20},
        selection_tools=("list_gear_standards",),
        frame={"axis": "global_x", "axial_interval_mm": "[-face_width_mm, 0]",
               "profile_plane": "global_yz"},
        units={"length": "mm", "angle": "degrees", "body_volume": "cm3",
                "body_surface_area": "cm2", "body_mass": "g"},
    ),
    "gear_internal": CadModule(
        module_id="gear_internal",
        title="Internal cylindrical gear (spur or helical ring)",
        request_model=InternalGearRequest,
        default_name=InternalGearCreateRequest.model_fields["name"].default,
        preview=build_internal_gear_preview,
        plan=build_internal_gear_plan,
        create=partial(create_plan, method="create_gear_internal"),
        inspect=partial(inspect_plan, method="inspect_gear_internal"),
        limitations=(
            "Creates one new unsaved ring with an explicit outside diameter; no housing or hub.",
            "Numeric create-only profile; changed inputs require a new part.",
            "Nominal involute with cubic-Bezier root transitions, not an exact pinion-cutter envelope.",
            "Over-pin measurement is not performed for helical internal gears.",
            "Inspect recognizes ownership and a saved recipe, not a fresh geometry audit.",
            "Recipe recreation depends on the inspected block's recreatable flag.",
            "Failed or cancelled creation may leave a partial document; there is no automatic rollback or retry.",
        ),
        example_parameters={"module_mm": 2, "tooth_count": 40, "face_width_mm": 20,
                            "ring_outside_diameter_mm": 100},
        selection_tools=("list_gear_standards",),
        frame={"axis": "global_x", "axial_interval_mm": "[-face_width_mm, 0]",
               "profile_plane": "global_yz"},
        units={"length": "mm", "angle": "degrees", "body_volume": "cm3",
               "body_surface_area": "cm2", "body_mass": "g"},
    ),
    "gear_bevel": CadModule(
        module_id="gear_bevel",
        title="Straight bevel gear (nominal Tredgold projection)",
        request_model=BevelGearRequest,
        default_name=BevelGearCreateRequest.model_fields["name"].default,
        preview=build_bevel_gear_preview,
        plan=build_bevel_gear_plan,
        create=partial(create_plan, method="create_gear_bevel"),
        inspect=partial(inspect_plan, method="inspect_gear_bevel"),
        limitations=(
            "Creates one new unsaved straight bevel wheel with a dish blank; no mounting bore or hub.",
            "Only straight teeth are implemented; tooth_type='circular' is rejected.",
            "Nominal Tredgold projection, not exact spherical involute or a cutter-generated octoid.",
            "No mating contact or strength calculation; CAD verification is not manufacturing conformity.",
            "Face width is along the pitch cone, not the global-X axial thickness.",
            "Automatic rim extensions are body-shape heuristics, not normative rack dimensions.",
            "Numeric create-only profile; changed inputs require a new part.",
            "Inspect recognizes ownership and a saved recipe, not a fresh geometry audit.",
            "Recipe recreation depends on the inspected block's recreatable flag.",
            "Failed or cancelled creation may leave a partial document; there is no automatic rollback or retry.",
        ),
        example_parameters={"module_mm": 3, "tooth_count": 20, "pitch_cone_angle_deg": 45},
        selection_tools=("list_gear_standards",),
        frame={"axis": "global_x", "face_width_direction": "pitch_cone_generator",
               "profile_planes": "two cone-normal tooth-space sections",
               "axial_extent": "plan: verification.criteria.expected_bounds_mm; create: data.body.bounds_mm"},
        units={"length": "mm", "angle": "degrees", "body_volume": "cm3",
               "body_surface_area": "cm2", "body_mass": "g"},
    ),
    "chain_sprocket": CadModule(
        module_id="chain_sprocket", title="Roller/bush chain sprocket (single or multiple rows)",
        request_model=ChainSprocketPreviewRequest,
        default_name=ChainSprocketCreateRequest.model_fields["name"].default,
        preview=chain_preview, plan=chain_plan, create=create_chain, inspect=inspect_chain,
        plan_data=chain_plan_data,
        limitations=(
            "Creates one new unsaved sprocket; no bore, hub, keyway or shaft interface.",
            "Dimensions and tooth width come from the selected chain catalog; multi-row designations require matching row_count.",
            "Multi-row creation requires catalog transverse pitch and plate-height data; simplex-only entries cannot be extended.",
            "Uses the existing nominal KOMPAS-compatible tooth construction; profile_strategy identifies source limits and compatibility rules.",
            "Driving variables and constrained sketches do not imply an implemented in-place editing API; changed inputs require a new build.",
            "Inspect recognizes ownership and a saved recipe, not fresh geometry; no stored geometry-verification stamp is available.",
            "Recipe recreation depends on the inspected block's recreatable flag.",
            "Failed or cancelled creation may leave a partial document; there is no automatic rollback or retry.",
        ),
        example_parameters={"designation": "ISO_08B", "chain_type": "roller", "tooth_count": 19, "row_count": 1},
        selection_tools=("list_chain_profiles",),
        frame={"axis": "global_x", "profile_plane": "global_yz", "row_direction": "negative_global_x",
               "axial_extent": "[-data.geometry.total_face_width, 0]; actual bounds in data.body.bounds_mm",
               "width_source": "selected_chain_catalog"},
        units={"length": "mm", "angle": "degrees", "body_volume": "cm3",
               "body_surface_area": "cm2", "body_mass": "g"},
    ),
    "cam": CadModule(
        module_id="cam", title="Cam lobe (direct flat/roller or fixed-arm roller rocker)",
        request_model=CamModuleParameters, default_name="Geomwright cam",
        preview=cam_preview, plan=cam_plan, create=create_cam_module, inspect=inspect_cam_module,
        plan_data=cam_plan_data,
        limitations=(
            "Creates one new unsaved solid cam; no shaft, hub or bore.",
            "Engineering contact-envelope model, not a standards-based or OEM contour reconstruction.",
            "Numeric create-only profile; CAM_* variables are metadata, not driving dimensions.",
            "Requires a nonzero base-circle interval; CAD preflight uses 10 samples per cam degree.",
            "Tolerance bounds sampled profile/contact error; it cannot relax curvature, face reach or pressure-angle limits.",
            "No RPM-dependent dynamics, strength, contact stress or manufacturing approval.",
            "Inspect reads the recipe and persisted verification marker, not a fresh geometry audit.",
            "Legacy version-1 cams have no complete recoverable recipe; recreation requires data.recreatable=true.",
            "Failed or cancelled creation may leave a partial document; there is no automatic rollback or retry.",
        ),
        example_parameters={"request": {"base_radius": 30, "max_lift": 6, "open_angle": 70,
            "close_angle": 70, "dwell_angle": 10, "law": "polydyne_345", "tappet_diameter": 40},
            "width": 12, "rotation_deg": 0, "tolerance": 0.01},
        selection_tools=(),
        frame={"axis": "global_x", "profile_plane": "global_yz", "axial_interval_mm": "[-width, 0]",
               "rotation": "positive rotation_deg turns +Y toward +Z about +X"},
        units={"length": "mm", "angle": "cam degrees (timing: crank degrees)",
               "angular_acceleration": "mm/rad2", "angular_jerk": "mm/rad3",
               "body_volume": "cm3", "body_surface_area": "cm2", "body_mass": "g"},
    ),
    "silent_chain_sprocket": CadModule(
        module_id="silent_chain_sprocket", title="Silent-chain sprocket (GOST, DIN/ASME open reconstructions)",
        request_model=SilentChainSelectionRequest, default_name="Geomwright silent sprocket",
        preview=silent_preview, plan=silent_plan, create=create_silent_module, inspect=inspect_silent_module,
        plan_data=silent_plan_data,
        limitations=(
            "Requires explicit chain designation and physical tooth count; there is no default catalog selection.",
            "Creates one new unsaved functional rim, solid to the axis; no bore, hub or shaft interface.",
            "DIN and ASME are labelled open reconstructions, not certified standard profiles; ASME selections identify pitch/guide, not chain designations.",
            "Missing engineering dimensions and source conflicts require explicit inputs; preview suggestions are never silently accepted.",
            "body_depth_mm controls detail-view framing only, not a bore or CAD readiness.",
            "Numeric create-only profile; changed inputs require a new part, not replacement of an existing body.",
            "Verification compares material removed by the pattern with source-cut volume times the physical tooth count.",
            "Inspect recognizes ownership and saved parameters, not a fresh geometry audit; no stored verification stamp is available.",
            "Failed or cancelled creation may leave a partial document; there is no automatic rollback or retry.",
        ),
        example_parameters={"standard": "din_8190_8191_open", "family": "outer", "designation": "08-020A",
                            "physical_tooth_count": 23},
        selection_tools=("list_silent_chain_profiles",),
        frame={"axis": "global_x", "profile_plane": "global_yz", "axial_interval_mm": "[0, functional_width_mm]",
               "width_source": "completed axial source profile; not necessarily face_width_mm"},
        units={"length": "mm", "angle": "degrees", "body_volume": "cm3", "body_surface_area": "cm2", "body_mass": "g"},
    ),
}


CAD_MODULES["compression_spring"] = CadModule(
    module_id="compression_spring", title="Compression springs (cylindrical, two-zone, conical legacy generator)",
    request_model=CompressionSpringParameters, default_name="Geomwright compression spring",
    preview=spring_preview, plan=spring_plan, create=create_spring_module, inspect=inspect_spring_module,
    plan_data=spring_plan_data, creation_policy="saved_unique_export_then_open",
    limitations=(
        "Uses the existing legacy saved construction and post-save binding path; creates a unique file in KOMPAS_EXPORT_DIR and returns it opened.",
        "Engineering geometry only; no load, stiffness, strength or fatigue certification.",
        "Supports global-origin compression variants; arbitrary legacy workflow/placement expressions are not accepted by this typed interface.",
        "height and legacy free_length are wire-centreline spans; standard_length is the physical end-to-end length in the legacy grinding/extreme-plane model. Supply only one length input.",
        "Inspect recognizes checksummed creation inputs and owned profile/sweep roots, not current geometry or formula-driving audit.",
        "Old springs without this recipe cannot reconstruct missing inputs; no in-place editing through the common interface.",
        "Failures can leave a document or saved file; no automatic rollback or retry.",
        "No new Studio spring block is implemented in this legacy-interface stage.",
        "End pitch = wire diameter + end_pitch_gap (shared default0.01 mm). This axial increment is not a certified minimum surface clearance. Explicit zero is preserved and may produce CAD_SELF_INTERSECTION; legacy calls and old recipes without this field retain zero.",
    ),
    example_parameters={"variant": "cylindrical", "mean_diameter": 30, "wire_diameter": 4,
                        "height": 48, "turns": 6},
    selection_tools=("list_spring_size_catalogs", "find_spring_sizes", "resolve_spring_size"),
    frame={"axis": "global_x", "origin": "legacy_global_origin", "profile": "normal to final path endpoint",
           "extents": "actual data.body.bounds_mm; ground end cuts change the axial envelope"},
    units={"length": "mm", "angle": "degrees", "turns": "revolutions", "body_volume": "cm3",
           "body_surface_area": "cm2", "body_mass": "g"},
)


CAD_MODULES["extension_spring"] = CadModule(
    module_id="extension_spring", title="Extension spring (legacy engineering hooks)",
    request_model=ExtensionSpringParameters, default_name="Geomwright extension spring",
    preview=extension_preview, plan=extension_plan, plan_data=extension_plan_data,
    create=create_extension_module, inspect=inspect_extension_module,
    creation_policy="saved_unique_export_then_open",
    limitations=(
        "Creates a unique saved export and returns it opened; existing legacy scenario tools are unchanged.",
        "Engineering geometry, not a calculation of load, initial tension, strength or fatigue.",
        "Independent left/right selection of eight legacy hook families, including self-wrapping and final bent-ring geometry under the historical bent_coil_left_spike identifier.",
        "Hook-family dimensions are shared when both ends use the same family; arbitrary per-end dimension namespaces are not implemented.",
        "Mixed machine/V, both self-wrapping/bent-ring orders, symmetric self-wrapping/bent-ring and custom self-wrapping controls pass save/reopen. An earlier sketch Update/session-readback failure remains recorded; no automatic retry is implemented.",
        "Global X coil axis at global origin; no arbitrary placement or raw workflow expressions.",
        "gap must be at least minimum_gap; unlike legacy, the shared interface refuses silent clamping.",
        "Creation verifies native coil dimensions/hand, valid sweep, positive solid and recipe/volume after reopen; hook contact/loading is not certified.",
        "Inspect recognizes a checksummed recipe, not current geometry or driving edits. Old files without a complete recipe cannot be recreated by guessing.",
        "No in-place editing or new Studio block. Failed creation may leave a file/document; no automatic retry or rollback.",
    ),
    example_parameters={"outer_diameter": 22, "wire_diameter": 2, "turns": 6, "hook_type": "machine_hooks"},
    selection_tools=("list_spring_size_catalogs", "find_spring_sizes", "resolve_spring_size"),
    frame={"axis": "global_x", "origin": "global_origin", "height_reference": "coil_only_not_hook_to_hook",
           "extents": "actual data.body.bounds_mm including both hooks"},
    units={"length": "mm", "turns": "revolutions", "body_volume": "cm3", "body_surface_area": "cm2", "body_mass": "g"},
)


CAD_MODULES["torsion_spring"] = CadModule(
    module_id="torsion_spring", title="Torsion spring (legacy engineering coil and legs)",
    request_model=TorsionSpringParameters, default_name="Geomwright torsion spring",
    preview=torsion_preview, plan=torsion_plan, plan_data=torsion_plan_data,
    create=create_torsion_module, inspect=inspect_torsion_module,
    creation_policy="saved_unique_export_then_open",
    limitations=(
        "Uses the existing legacy generator; creates a unique saved export and returns it opened.",
        "Engineering geometry, not torque, stiffness, strength or fatigue certification.",
        "Global X coil axis at global origin; actual body bounds include legs.",
        "Tangent legs require zero start phase; radial/axial-transition legs support nonzero phase.",
        "gap must be at least minimum_gap>0; no silent clamping in this shared interface.",
        "Inspect recognizes creation inputs, not a fresh geometry/formula audit. No in-place editing or new Studio block.",
        "Failures may leave partial files/documents; no automatic retry or rollback.",
    ),
    example_parameters={"wire_diameter": 2, "mean_diameter": 20, "turns": 5, "leg_length": 25},
    selection_tools=("list_spring_size_catalogs", "find_spring_sizes", "resolve_spring_size"),
    frame={"axis": "global_x", "origin": "global_origin", "height_reference": "coil_only_not_leg_extents"},
    units={"length": "mm", "angle": "degrees", "turns": "revolutions", "body_volume": "cm3", "body_surface_area": "cm2", "body_mass": "g"},
)


CAD_MODULES["disc_spring"] = CadModule(
    module_id="disc_spring", title="Disc/Belleville spring (legacy normal-thickness ring)",
    request_model=DiscSpringParameters, default_name="Geomwright disc spring",
    preview=disc_preview, plan=disc_plan, plan_data=disc_plan_data,
    create=create_disc_module, inspect=inspect_disc_module,
    creation_policy="saved_unique_export_then_open",
    limitations=(
        "Engineering conical ring with normal thickness; no load/strength/fatigue or standard conformity certification.",
        "Use cone_height or legacy free_height, not both. Legacy free_height subtracts thickness to obtain cone_height, not exact finished axial span.",
        "Uses existing parameterized legacy profile and full rotation about global X; no stack or general assembly composition.",
        "Legacy CAD radius/height driving associations are not fully verified: cone-height variable edits alone do not rebuild geometry and coupled size edits can violate nominal radii. Recreate rather than edit the variable table through this module.",
        "Creates a unique saved export, opens it and checks native body, circular-edge diameters, bounds and analytical volume through save/reopen.",
        "Inspect recognizes a checksummed creation recipe, not a current geometry/formula audit or in-place edit. No new Studio block.",
        "Failures may retain a partial document/file; no automatic retry or rollback.",
    ),
    example_parameters={"outer_diameter":50,"inner_diameter":25,"thickness":2,"cone_height":3},
    selection_tools=("list_spring_size_catalogs", "find_spring_sizes", "resolve_spring_size"),
    frame={"axis":"global_x","origin":"legacy_first_profile_vertex","extents":"plan.data.geometry.axial_interval_mm and actual body bounds"},
    units={"length":"mm","angle":"degrees","body_volume":"cm3","body_surface_area":"cm2","body_mass":"g"},
)


CAD_MODULES["diaphragm_spring"] = CadModule(
    module_id="diaphragm_spring", title="Diaphragm spring (legacy slotted engineering workflow)",
    request_model=DiaphragmSpringParameters, default_name="Geomwright diaphragm spring",
    preview=diaphragm_preview, plan=diaphragm_plan, plan_data=diaphragm_plan_data,
    create=create_diaphragm_module, inspect=inspect_diaphragm_module,
    creation_policy="saved_unique_export_then_open",
    limitations=(
        "Existing no-bend/single-bend/S-bend geometry, radial slots and circle/oval terminal reliefs; no load/strength/standard certification.",
        "Single-bend final inner diameter is calculated; specify exactly one of free_height and tip_length. S-bend needs explicit intermediate dimensions.",
        "Slots and reliefs are through-all cuts grouped in one full circular pattern; count includes the original group.",
        "Per-sketch constraint states are returned after reopen; full definition of every saved sketch and in-place driving edits are not certified. This integration does not redesign the legacy constraint system; recreate from inputs.",
        "Creation verifies one solid, native pattern/source structure, repeated material removal, outer diameter, axial bounds and volume/recipe persistence.",
        "Inspect recognizes saved metadata and owned roots, not a new geometry audit. No new Studio block, stack or general composition.",
        "Failures may retain a partial document/file; no automatic retry or rollback.",
    ),
    example_parameters={"tip_variant":"s_bend","outer_diameter":240,"body_inner_diameter":120,"inner_diameter":78,
        "thickness":3,"cone_height":6,"free_height":28,"tip_bend_inner_radius":8,
        "second_tip_bend_inner_radius":7,"first_tip_inner_diameter":82,"first_tip_height":24,
        "slot_end_radius":100,"slot_start_width":4,"slot_end_width":4,"slot_fillet_radius":1,
        "entry_clearance":.5,"relief_variant":"circle","relief_radius":6,"slot_count":12},
    selection_tools=(),
    frame={"axis":"global_x","profile":"global_xoy","extents":"plan.data.geometry.axial_interval_mm and actual body bounds"},
    units={"length":"mm","angle":"degrees","body_volume":"cm3","body_surface_area":"cm2","body_mass":"g"},
)


CAD_MODULES["stepped_shaft"] = CadModule(
    module_id="stepped_shaft",title="Stepped shaft (legacy full rotational body)",
    request_model=SteppedShaftParameters,default_name="Geomwright stepped shaft",
    preview=shaft_preview,plan=shaft_plan,plan_data=shaft_plan_data,create=create_shaft_module,inspect=inspect_shaft_module,
    creation_policy="saved_unique_export_then_open",selection_tools=(),
    example_parameters={"steps":[{"length":20,"diameter":30},{"length":35,"diameter":40},{"length":15,"diameter":25}]},
    limitations=("Creates a new full rotational solid at global origin, about global X; no partial-angle or arbitrary placement mode in this typed adapter.",
        "Adjacent equal diameters are rejected by legacy validation; represent a continuous cylinder as one step.",
        "No holes, fillets, chamfers, threads, external-body application or new Studio block.",
        "Creation checks each trimmed cylindrical step, bounds, analytical volume, fully defined profile and save/reopen.",
        "Inspect reads checksummed creation metadata and owned roots, not current geometry or manual edits; recreate from inputs.",
        "Diameter/length geometry driving readback passes in an isolated probe; historical solver labels used a reversed enum decoder and require fresh review. In-place editing is not certified.",
        "At most 100 steps: bounded recipe and geometry readback. Failed creation may retain a partial file/document; no retry or rollback."),
    frame={"axis":"global_x","profile_plane":"global_xoy","origin":"global_origin","axial_interval_mm":"[0, sum(step.length)]"},
    units={"length":"mm","body_volume":"cm3","body_surface_area":"cm2","body_mass":"g"},
)


CAD_MODULES["external_conical_step"] = CadModule(
    module_id="external_conical_step",title="External cone (legacy standalone rotational body)",
    request_model=ExternalConeParameters,default_name="Geomwright external cone",
    preview=cone_preview,plan=cone_plan,plan_data=cone_plan_data,create=create_cone_module,inspect=inspect_cone_module,
    creation_policy="saved_unique_export_then_open",selection_tools=(),
    example_parameters={"definition_mode":"diameters_length","start_diameter":40,"end_diameter":20,"length":30},
    limitations=("Creates a new solid frustum at global origin, full rotation about global X; no internal cone, threads or external-body application.",
        "Five legacy definition modes; cone angle is the half-angle to the axis, conicity is absolute diameter difference / length.",
        "Only independent fields of the selected mode are accepted. One-diameter modes require explicit inward/outward slope; cylinders/equal diameters and zero tip diameters are refused.",
        "Creation checks native cone trimmed end radii, bounds, analytical volume, fully defined profile and save/reopen.",
        "Inspect recognizes ECON_RECIPE creation inputs and owned roots, not a new geometry/driving audit. Changed inputs create a new part; no new Studio block or in-place editing.",
        "Failures can leave a partial file/document; no automatic retry or rollback."),
    frame={"axis":"global_x","profile_plane":"global_xoy","origin":"global_origin","axial_interval_mm":"[0, resolved length]","ends":"start at X=0; end at X=length"},
    units={"length":"mm","angle":"degrees","conicity":"dimensionless","body_volume":"cm3","body_surface_area":"cm2","body_mass":"g"},
)


CAD_MODULES["external_polygonal_step"] = CadModule(
    module_id="external_polygonal_step", title="External polygon (legacy standalone solid prism)",
    request_model=ExternalPolygonParameters, default_name="Geomwright external polygon",
    preview=polygon_preview, plan=polygon_plan, plan_data=polygon_plan_data,
    create=create_polygon_module, inspect=inspect_polygon_module,
    creation_policy="saved_unique_export_then_open", selection_tools=(),
    example_parameters={"diameter":30,"length":25,"side_count":6,"diameter_mode":"inscribed_circle",
        "rotation_angle_degrees":0,"axial_direction":"forward"},
    limitations=("Creates a new regular-polygon solid prism only; no internal cut, foreign-body application, finishing or new Studio block.",
        "Side count 3..64 bounds profile/readback cost, not a standard or an exhaustive live certification.",
        "POLY_D1, POLY_L1 and POLY_A1 drive diameter, length and orientation within the angular branch selected at creation; crossing that branch requires recreation.",
        "Side count, diameter interpretation and axial direction require recreation. No public in-place editing.",
        "Creation checks one solid, native vertices/bounds, analytical volume and fully defined profile. Interactive mode retains the saved visible document; fresh reopen is deferred.",
        "Inspect recognizes creation recipe and owned roots, not current geometry or manual driving edits.",
        "Failures may retain a partial file/document; no automatic retry or rollback."),
    frame={"axis":"global_x","profile_plane":"global_yoz","origin":"global_origin",
        "local_u":"global_z","local_v":"global_y","normal":"negative_global_x",
        "axial_interval_mm":"forward: [-length, 0]; backward: [0, length]"},
    units={"length":"mm","angle":"degrees","side_count":"dimensionless","body_volume":"cm3"},
)


CAD_MODULES["external_flat_step"] = CadModule(
    module_id="external_flat_step", title="External flat step (standalone cylinder with flats)",
    request_model=ExternalFlatParameters, default_name="Geomwright external flat",
    preview=flat_preview, plan=flat_plan, plan_data=flat_plan_data, create=create_flat_module, inspect=inspect_flat_module,
    creation_policy="saved_unique_export_then_open", selection_tools=(),
    example_parameters={"diameter":30,"length":25,"flat_depth":4,"flats_count":1,"axial_direction":"forward"},
    limitations=("Creates a new cylinder with one flat or two opposite flats; no internal cut, foreign-body application, finishing or new Studio block.",
        "Depth must satisfy 0 < flat_depth < diameter/2; non-finite or numerically unrepresentable profiles are rejected before CAD.",
        "FLAT_D1/FLAT_L1/FLAT_F1 drive diameter, length and flat depth. Flats count and direction require recreation; no public in-place editing.",
        "Creation checks native cylinder/flat/end faces, chord endpoints, bounds, analytical volume and fully defined profile (API7 native code1).",
        "Interactive mode retains the saved visible document and defers fresh reopen. Inspect recognizes creation inputs/owned roots, not a fresh geometry audit.",
        "Interactive MCP create/inspect/explicit reopen with the full recipe is live-verified for one-flat forward and two-flat backward D30/L25/F4; hidden isolation and every numeric boundary are not certified.",
        "Failures may retain partial documents/files; no automatic retry, closure or rollback."),
    frame={"axis":"global_x","profile_plane":"global_yoz","origin":"global_origin",
        "flat_planes":"Y=-(diameter/2-flat_depth); additionally Y=+(diameter/2-flat_depth) for two flats",
        "axial_interval_mm":"forward: [-length,0]; backward: [0,length]"},
    units={"length":"mm","flats_count":"dimensionless","profile_area":"mm2","body_volume":"cm3"},
)


_PULLEY_TITLES = {
    "v_belt": "V-belt pulley (classical/narrow-wedge or custom groove)",
    "poly_v": "Poly-V pulley (ISO PH/PJ/PK/PL/PM grooves)",
    "flat_belt": "Flat-belt pulley (cylindrical or circular crown)",
    "timing_trapezoidal": "Trapezoidal timing pulley (T/AT or custom geometry)",
    "timing_curvilinear": "Curvilinear timing pulley (HTD or custom geometry)",
}
for _family, _title in _PULLEY_TITLES.items():
    CAD_MODULES[_family] = CadModule(
        module_id=_family, title=_title, request_model=PULLEY_MODELS[_family],
        default_name="Geomwright pulley", preview=partial(pulley_preview, family=_family),
        plan=partial(pulley_plan, family=_family), create=partial(create_pulley_module, family=_family),
        inspect=partial(inspect_pulley_module, family=_family), plan_data=pulley_plan_data,
        limitations=(
            "Creates one new unsaved functional rim, solid to the axis; no bore, hub, shaft or retaining flange.",
            "Uses existing family-specific parametric sketches and operations; no manufacturing conformity is claimed.",
            "The shared interface is create-only; dedicated legacy apply/Studio editing interfaces are separate capabilities.",
            "Inspect returns the checksummed stored creation recipe, not a fresh geometry audit or an in-place edit.",
            "Older blocks without a full recipe remain recognizable but cannot substitute defaults for recreation.",
            "Detected driving-input changes invalidate recreation from the old creation recipe.",
            "Failed creation may leave a partial document; there is no automatic rollback or retry.",
        ) + {
            "v_belt": ("Custom/override dimensions are explicitly nonstandard; finishing options are saved in the recipe.",),
            "poly_v": ("Poly-V supports its catalog profiles only; arbitrary custom groove geometry is not implemented.",),
            "flat_belt": ("Flat crown is explicitly specified circular-arc geometry, not a standard-derived default.",),
            "timing_trapezoidal": ("Custom dimensions require designation=CUSTOM; the shared plan uses trapezoidal groove mechanics.",),
            "timing_curvilinear": ("Custom dimensions require designation=CUSTOM; the shared plan uses three-arc curvilinear groove mechanics.",),
        }[_family],
        example_parameters=PULLEY_EXAMPLES[_family],
        selection_tools={"v_belt": ("list_v_belt_profiles",), "poly_v": ("list_poly_v_profiles",)}.get(_family, ()),
        frame={"axis": "global_x", "axial_interval_mm": "[-face_width, 0]" if _family.startswith("timing_") else "[0, functional face width]",
               "profile_definition": "global_yz tooth space" if _family.startswith("timing_") else "axial/radial section through global_x"},
        units={"length": "mm", "angle": "degrees", "body_volume": "cm3", "body_surface_area": "cm2", "body_mass": "g"},
    )


def get_cad_module_contract(module_id: str | None = None) -> dict:
    """List implemented modules, or describe one without importing Studio or touching CAD."""
    if module_id is None:
        return {"ok": True, "contract_version": 1,
                "modules": [module.descriptor() for module in CAD_MODULES.values()]}
    module = CAD_MODULES.get(module_id)
    if module is None:
        return {"ok": False, "contract_version": 1,
                "error": {"code": "UNKNOWN_MODULE", "message": f"Unknown module_id: {module_id[:80]}",
                          "available_modules": list(CAD_MODULES)}}
    example = {"module_id": module_id, "action": "plan",
               "parameters": dict(module.example_parameters)}
    return {
        "ok": True,
        **module.descriptor(),
        "parameter_schema": module.request_model.model_json_schema(),
        "request_schema": CadModuleRequest.model_json_schema(),
        "result_schema": CadModuleResult.model_json_schema(),
        "defaults": (module.request_model.model_construct() if any(
            field.is_required() for field in module.request_model.model_fields.values())
            else module.request_model()).model_dump(exclude_none=True),
        "selection_tools": list(module.selection_tools),
        "units": dict(module.units),
        "frame": dict(module.frame),
        "limitations": list(module.limitations),
        "examples": {
            "plan": example,
            "create": {**example, "action": "create", "confirm_write": True},
            "inspect": {"module_id": module_id, "action": "inspect",
                        "document_id": "<exact opened document id from create.data.document>"},
        },
    }


def _failure(request: CadModuleRequest, code: str, message: str, **extra: Any) -> dict:
    return CadModuleResult(
        module_id=request.module_id, action=request.action, stage="refused",
        error={"code": code, "message": message, **extra},
    ).model_dump()


def _partial_document(error: BaseException) -> dict | None:
    """Preserve the existing gear runtime's legacy partial_document evidence."""
    partial = getattr(error, "partial_result", None)
    if isinstance(partial, dict):
        return partial
    marker = " | partial_document="
    if marker in str(error):
        try:
            document, _ = json.JSONDecoder().raw_decode(str(error).split(marker, 1)[1])
            return {"document": document, "verified": False, "rollback_performed": False}
        except (ValueError, TypeError):
            pass
    return None


def run_cad_module(request: CadModuleRequest, adapter: Any) -> dict:
    """Validate, plan and delegate to an existing family; never retry a failed write."""
    module = CAD_MODULES.get(request.module_id)
    if module is None:
        return _failure(request, "UNKNOWN_MODULE", "Use get_cad_module_contract to select a module.",
                        available_modules=list(CAD_MODULES))
    if request.action == "create" and not request.confirm_write:
        return _failure(request, "WRITE_CONFIRMATION_REQUIRED", "create requires confirm_write=true")

    result = CadModuleResult(module_id=request.module_id, action=request.action, stage="refused")
    cad_called = False
    try:
        if request.action == "inspect":
            cad_called = True
            block = module.inspect(adapter, request.document_id)
            if block.get("module") != module.module_id:
                return _failure(request, "WRONG_MODULE", "The exact document does not contain this module.")
            result.ok = True
            result.stage = "recognized"
            # Legacy ownership variables do not constitute a recoverable request.
            result.parameters = dict(block.get("profile") or {}) if block.get("recreatable") else None
            result.data = {key: block.get(key) for key in (
                "id", "name", "schema", "version", "status", "editable", "recreatable",
                "owned_references", "recipe_error",
            )}
            result.data["document_id"] = request.document_id
            if block.get("source_summary") is not None:
                result.data["source_summary"] = block["source_summary"]
            result.verification = {"scope": "ownership_and_recipe_recognition",
                                   "stored_verified": block.get("verified"), "fresh_geometry_audit": False}
        else:
            result.parameters = module.request_model.model_validate(request.parameters).model_dump(exclude_none=True)
            if request.action == "preview":
                preview = module.preview(result.parameters)
                result.ok = bool(preview.get("success"))
                result.stage = "previewed" if result.ok else "refused"
                result.data = {key: preview.get(key) for key in ("summary", "report", "warnings", "errors") if key in preview}
                if "report" in result.data:
                    report = dict(result.data["report"])
                    # The legacy flag describes the selected basic rack, not the manufactured gear.
                    report["basic_rack_conformity_claim"] = report.pop("conformity_claim", False)
                    result.data["report"] = report
                if not result.ok:
                    result.error = {"code": "INVALID_GEOMETRY", "message": "Correct the errors in data.errors."}
            else:
                plan = module.plan(result.parameters, name=request.name if request.name is not None else module.default_name)
                result.data = module.plan_data(plan)
                if request.action == "plan":
                    result.ok = True
                    result.stage = "planned"
                    result.verification = {"scope": "planned_expectations", "criteria": plan["verification"]}
                else:
                    cad_called = True
                    created = module.create(adapter, plan, request.visible)
                    result.executed = created.get("executed")
                    result.verification = {"scope": "creation_readback", **created.get("verification", {})}
                    result.verified = bool(created.get("ok") is True and created.get("executed") is True
                                           and result.verification.get("ok") is True)
                    result.ok = result.verified
                    result.stage = "verified" if result.ok else "failed"
                    result.data.update({key: created[key] for key in (
                        "document", "body", "saved", "closed", "diagnostics",
                    ) if key in created})
                    result.data["owned_references"] = list((created.get("block") or {}).get("owned_references") or [])
                    result.data["body_units"] = {"bounds_mm": "mm", "volume": "cm3", "surface_area": "cm2", "mass": "g"}
                    mode_reader = getattr(getattr(adapter, "runner", None), "get_cad_work_mode", None)
                    if callable(mode_reader):
                        selection = mode_reader()
                        result.data["cad_session"] = {
                            "mode": selection.get("host_mode") or selection["mode"],
                            "binding": selection.get("binding"),
                            "host_selection_stale": selection.get("host_selection_stale", False),
                            "per_action_ui_animation_guaranteed": False,
                        }
                    if not result.ok:
                        result.error = {"code": "UNVERIFIED_RESULT", "message": "Creation did not return successful CAD verification; inspect the document before another write."}
                        result.partial_result = created.get("partial_result")
        result.data["conformity_claim"] = False
        return result.model_dump()
    except ModuleInputRequired as exc:
        result.error = {"code": "INPUT_REQUIRED", "message": str(exc)}
        result.data = {"completion": exc.completion, "conformity_claim": False}
        if exc.source_summary is not None:
            result.data["source_summary"] = exc.source_summary
        return result.model_dump()
    except ValidationError as exc:
        if cad_called:
            result.stage = "failed"
            result.executed = None if request.action == "create" else False
            result.error = {"code": "INVALID_RUNTIME_RESULT", "message": str(exc)[:2000]}
            return result.model_dump()
        issues = exc.errors(include_url=False, include_context=False, include_input=False)
        compact_issues = [
            {"type": item["type"], "loc": tuple(str(part)[:120] for part in item["loc"]),
             "msg": item["msg"][:500]}
            for item in issues[:12]
        ]
        return _failure(request, "INVALID_PARAMETERS", "Fix parameters using the module's parameter_schema.",
                        issues=compact_issues, issue_count=len(issues), omitted_issues=max(0, len(issues) - 12))
    except (ValueError, RuntimeError, OSError) as exc:
        if not cad_called and isinstance(exc, ValueError):
            return _failure(request, "INVALID_PARAMETERS", str(exc)[:2000])
        result.stage = "failed"
        result.executed = None if request.action == "create" and cad_called else False
        result.error = classify_runtime_error(exc, stage=request.action)
        result.error["message"] = result.error["message"][:2000]
        result.partial_result = _partial_document(exc)
        if request.action == "create" and cad_called:
            result.error["retryable"] = False
            if result.error["code"] != "CAD_RUNTIME_INVALID":
                result.error["hint"] = "Read get_cad_session_guard first. For settled_failure call recover_cad_session with confirm_idle=false for automatic session audit, without asking the user. Unknown outcomes require explicit user idle/partial-document confirmation. After recovery inspect the partial document before writing; never retry blindly."
        return result.model_dump()
