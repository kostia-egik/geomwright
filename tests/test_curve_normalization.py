from __future__ import annotations

import pytest

from kompas_mcp.connect_curve import normalize_connect_curve_params
from kompas_mcp.trimmed_curve import normalize_trimmed_curve_params


class TestConnectCurveNormalization:
    def test_normalizes_supported_parameters(self) -> None:
        result = normalize_connect_curve_params(
            {
                "curve1_connect_vertex": False,
                "curve2_connect_vertex": True,
                "curve1_connect_type": "tangent",
                "curve2_connect_type": "normal",
                "tension": 25.0,
                "name": "Connector",
            }
        )

        assert result["curve1_connect_vertex"] is False
        assert result["curve2_connect_vertex"] is True
        assert result["curve1_connect_type"] == 1
        assert result["curve2_connect_type"] == 2
        assert result["tension"] == pytest.approx(25.0)
        assert result["name"] == "Connector"

    def test_accepts_integer_type(self) -> None:
        assert normalize_connect_curve_params({"curve1_connect_type": 1})["curve1_connect_type"] == 1

    def test_rejects_out_of_range_tension(self) -> None:
        with pytest.raises(ValueError, match="tension"):
            normalize_connect_curve_params({"tension": -1.0})

    def test_rejects_unknown_type(self) -> None:
        with pytest.raises(ValueError, match="connect curve type"):
            normalize_connect_curve_params({"curve1_connect_type": "unknown"})


class TestTrimmedCurveNormalization:
    def test_normalizes_reference_and_direction(self) -> None:
        result = normalize_trimmed_curve_params(
            {
                "point_name": "Trim point",
                "offset": 5.0,
                "direction": False,
                "sense": False,
                "offset_type": 2,
                "name": "Trimmed",
            }
        )

        assert result == {
            "name": "Trimmed",
            "point_name": "Trim point",
            "offset": 5.0,
            "direction": False,
            "sense": False,
            "offset_type": 2,
        }

    def test_uses_boolean_direction_and_sense(self) -> None:
        result = normalize_trimmed_curve_params({"offset": 1.0, "direction": 0, "sense": 1})
        assert result["direction"] is False
        assert result["sense"] is True

    def test_rejects_non_positive_offset(self) -> None:
        with pytest.raises(ValueError, match="positive finite"):
            normalize_trimmed_curve_params({"offset": 0.0})
