from __future__ import annotations

from dataclasses import dataclass
import math

CRANK_DEGREES_PER_CAM_DEGREE = 2.0
FOUR_STROKE_CRANK_DEGREES = 720.0
TDC_DEGREES = (0.0, 360.0)
BDC_DEGREES = (180.0, 540.0)


def crank_angle(value: float, flag: str, reference_deg: float) -> float:
    normalized = str(flag or "").strip().upper()
    amount = float(value)
    reference = float(reference_deg)
    if not math.isfinite(amount) or not math.isfinite(reference):
        raise ValueError("crank angles must be finite")
    if normalized in ("BTDC", "BBDC"):
        return reference - amount
    if normalized in ("ATDC", "ABDC"):
        return reference + amount
    raise ValueError("flag must be one of BTDC, ATDC, BBDC, ABDC")


@dataclass(frozen=True)
class ValveCycle:
    intake_open: float
    intake_close: float
    exhaust_open: float
    exhaust_close: float
    overlap: tuple[tuple[float, float], ...]
    tdc: tuple[float, ...]
    bdc: tuple[float, ...]
    scale_deg: float = FOUR_STROKE_CRANK_DEGREES


def valve_cycle(
    *,
    intake_open: float,
    intake_close: float,
    exhaust_open: float,
    exhaust_close: float,
) -> ValveCycle:
    for label, opening, closing in (
        ("intake", intake_open, intake_close),
        ("exhaust", exhaust_open, exhaust_close),
    ):
        if not 0.0 <= float(opening) < float(closing) <= FOUR_STROKE_CRANK_DEGREES:
            raise ValueError(f"{label} event must satisfy 0 <= open < close <= 720")
    low = max(float(intake_open), float(exhaust_open))
    high = min(float(intake_close), float(exhaust_close))
    overlap = ((low, high),) if high > low else ()
    return ValveCycle(
        intake_open=float(intake_open),
        intake_close=float(intake_close),
        exhaust_open=float(exhaust_open),
        exhaust_close=float(exhaust_close),
        overlap=overlap,
        tdc=TDC_DEGREES,
        bdc=BDC_DEGREES,
    )


@dataclass(frozen=True)
class ValveEvent:
    open_angle: float
    dwell_angle: float
    close_angle: float
    phase_deg: float
    duration_cam_deg: float
    duration_crank_deg: float


def event_from_crank(
    *,
    open_deg: float,
    close_deg: float,
    dwell_deg: float = 0.0,
    nose_center_deg: float | None = None,
    cam_reference_deg: float = 0.0,
) -> ValveEvent:
    values = (open_deg, close_deg, dwell_deg, cam_reference_deg)
    if nose_center_deg is not None:
        values += (nose_center_deg,)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("valve event angles must be finite")
    duration_crank = float(close_deg) - float(open_deg)
    if duration_crank <= 0.0:
        raise ValueError("close_deg must be greater than open_deg")
    if duration_crank > FOUR_STROKE_CRANK_DEGREES:
        raise ValueError("valve event must not exceed 720 crank degrees")

    dwell_cam = float(dwell_deg) / CRANK_DEGREES_PER_CAM_DEGREE
    if dwell_cam < 0.0:
        raise ValueError("dwell_deg must be non-negative")

    if nose_center_deg is None:
        duration_cam = duration_crank / CRANK_DEGREES_PER_CAM_DEGREE
        if dwell_cam >= duration_cam:
            raise ValueError("dwell_deg must be shorter than the valve event")
        flank = (duration_cam - dwell_cam) / 2.0
        open_angle = flank
        close_angle = flank
    else:
        nose = float(nose_center_deg)
        half_dwell = float(dwell_deg) / 2.0
        open_flank_crank = nose - half_dwell - float(open_deg)
        close_flank_crank = float(close_deg) - (nose + half_dwell)
        if open_flank_crank <= 0.0 or close_flank_crank <= 0.0:
            raise ValueError("nose_center_deg must lie strictly inside the valve event")
        open_angle = open_flank_crank / CRANK_DEGREES_PER_CAM_DEGREE
        close_angle = close_flank_crank / CRANK_DEGREES_PER_CAM_DEGREE
        duration_cam = open_angle + dwell_cam + close_angle

    phase = float(open_deg) / CRANK_DEGREES_PER_CAM_DEGREE + float(cam_reference_deg)
    return ValveEvent(
        open_angle=open_angle,
        dwell_angle=dwell_cam,
        close_angle=close_angle,
        phase_deg=phase,
        duration_cam_deg=duration_cam,
        duration_crank_deg=duration_crank,
    )
