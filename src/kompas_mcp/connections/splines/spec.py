"""Public request contract for straight-sided spline joints (ГОСТ 1139-80)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StraightSplineRequest(BaseModel):
    """Один прямобочный шлицевой венец или его втулка.

    Размер задаётся обозначением из таблиц 1-3 ГОСТ 1139-80 (например,
    ``8x36x40``) либо явными ``tooth_count``/``inner_diameter_mm``/
    ``outer_diameter_mm``/``tooth_width_mm``. Явные размеры, совпадающие со
    строкой стандарта, используют её табличные ``d1``, ``a``, ``c`` и ``r``;
    несовпадающие считаются нестандартными и требуют явной галтели.
    """

    model_config = ConfigDict(extra="forbid")

    standard: Literal["gost_1139_80"] = Field(
        default="gost_1139_80",
        title="Стандарт",
        description="Система стандарта. Пока реализован ГОСТ 1139-80.",
    )
    series: Literal["light", "medium", "heavy"] = Field(
        default="medium",
        title="Серия",
        description="Лёгкая, средняя или тяжёлая серия ГОСТ 1139-80.",
    )
    designation: str | None = Field(
        default=None,
        title="Обозначение",
        description="Обозначение вида z x d x D, например 8x36x40.",
    )
    tooth_count: int | None = Field(default=None, ge=4, le=40, title="Число зубьев z")
    inner_diameter_mm: float | None = Field(default=None, gt=1.0, le=500.0, title="Внутренний диаметр d, мм")
    outer_diameter_mm: float | None = Field(default=None, gt=1.0, le=600.0, title="Наружный диаметр D, мм")
    tooth_width_mm: float | None = Field(default=None, gt=0.0, le=100.0, title="Ширина зуба b, мм")
    body: Literal["shaft", "hub"] = Field(
        default="shaft",
        title="Носитель",
        description="Вал (наружные шлицы) или втулка (внутренние шлицы).",
    )
    centering: Literal["inner_diameter", "outer_diameter", "side_faces"] = Field(
        default="inner_diameter",
        title="Способ центрирования",
        description="Центрирование по d, по D или по боковым сторонам b.",
    )
    execution: Literal["auto", "plain", "recessed"] = Field(
        default="auto",
        title="Исполнение вала",
        description=(
            "auto: центрирование по d - корень d с галтелью (исполнение 3), "
            "по D или b - корень d1 (исполнение 2). Исполнение 1 (обкатка) "
            "сохраняется в отчёте как табличные d1/a, но не строится."
        ),
    )
    root_fillet_mm: float | None = Field(
        default=None, ge=0.05, le=10.0,
        title="Галтель r, мм",
        description="Явная галтель для нестандартного размера; для табличного - ограничение r не более.",
    )
    tip_chamfer_mm: float | None = Field(
        default=None, ge=0.0, le=10.0,
        title="Фаска c, мм",
        description="Фаска c x 45 торцов зубьев вала; пусто - табличное c.",
    )
    length_mm: float = Field(
        default=30.0, gt=0.2, le=2000.0,
        title="Длина шлицевого участка, мм",
        description="Длина собственного носителя: вала или втулки.",
    )
    hub_outside_diameter_mm: float | None = Field(
        default=None, gt=1.0, le=1000.0,
        title="Наружный диаметр втулки, мм",
        description="Явный наружный диаметр кольцевой заготовки втулки; пусто - рекомендуемая стенка.",
    )
    fit_centering: str | None = Field(
        default=None,
        title="Посадка центрирующего элемента",
        description='Запись вида "H7/f7"; пусто - посадка по умолчанию для способа центрирования.',
    )
    fit_side: str | None = Field(
        default=None,
        title="Посадка по боковым сторонам b",
        description='Запись вида "H9/f9"; пусто - посадка по умолчанию.',
    )
    include_tip_chamfer: bool = Field(
        default=True,
        title="Фаска зубьев вала",
        description="Строить фаску c x 45 на торцах зубьев вала; для втулки не применяется в этом срезе.",
    )

    @model_validator(mode="after")
    def _validate_explicit_size(self) -> "StraightSplineRequest":
        explicit = (self.tooth_count, self.inner_diameter_mm, self.outer_diameter_mm, self.tooth_width_mm)
        if self.designation:
            if any(value is not None for value in explicit):
                raise ValueError("задайте либо designation, либо явные размеры, но не оба варианта")
        elif any(value is None for value in explicit):
            raise ValueError("нужны designation либо все четыре явных размера z, d, D, b")
        return self


class StraightSplineCreateRequest(StraightSplineRequest):
    """Create-only MCP request: plan with execute=false, write with both flags."""

    name: str = Field(default="Geomwright spline", min_length=1, max_length=120)
    execute: bool = False
    confirm_write: bool = False
    visible: bool = True

    @model_validator(mode="after")
    def _validate_write_confirmation(self) -> "StraightSplineCreateRequest":
        if self.execute and self.confirm_write is not True:
            raise ValueError("confirm_write=true is required when execute=true")
        return self


def spline_selection() -> dict:
    """Studio selection metadata: series, sizes, centering and execution options."""
    from .straight import straight_spline_selection

    return straight_spline_selection()
