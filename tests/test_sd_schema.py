"""Tests for System Dynamics schema validation."""

import pytest
from pydantic import ValidationError

from anylogic_mcp.sd_schema import (
    AuxDef,
    ChartDef,
    ChartSeriesDef,
    FlowDef,
    LinkDef,
    ParameterDef,
    SDModelDefinition,
    SDSchemaError,
    StockDef,
    TableFunctionDef,
    TablePointDef,
)
from anylogic_mcp.sd_validator import SDValidator


def _minimal_sd(**overrides):
    base = {
        "name": "Test",
        "description": "Test model",
        "time_unit": "Year",
        "duration": 10,
        "stocks": [
            StockDef(name="Inventory", initial_value="100", expression="inflow - outflow"),
        ],
        "flows": [
            FlowDef(name="inflow", formula="1", target="Inventory"),
            FlowDef(name="outflow", formula="0.5", source="Inventory"),
        ],
        "links": [
            LinkDef(source="inflow", target="Inventory"),
            LinkDef(source="Inventory", target="outflow"),
        ],
    }
    base.update(overrides)
    return SDModelDefinition(**base)


def _raise_text(exc_info) -> str:
    err = exc_info.value
    if isinstance(err, SDSchemaError):
        return " ".join(i["error"] for i in err.issues)
    return str(err)


class TestSDSchema:
    def test_valid_minimal_model(self):
        model = _minimal_sd()
        assert model.variable_count() == 3

    def test_auto_stock_expression(self):
        model = SDModelDefinition(
            name="Auto",
            description="Auto expression",
            duration=10,
            stocks=[StockDef(name="X", initial_value="0")],
            flows=[
                FlowDef(name="in", formula="1", target="X"),
                FlowDef(name="out", formula="0.5", source="X"),
            ],
            links=[
                LinkDef(source="in", target="X"),
                LinkDef(source="X", target="out"),
            ],
        )
        assert model.stock_expressions()["X"] == "in + -out"

    def test_rejects_duplicate_names(self):
        with pytest.raises((ValidationError, SDSchemaError), match="Duplicate name"):
            _minimal_sd(
                auxiliaries=[AuxDef(name="Inventory", formula="1")],
            )

    def test_rejects_unknown_flow_source(self):
        with pytest.raises((ValidationError, SDSchemaError), match="not a defined stock"):
            _minimal_sd(
                flows=[FlowDef(name="bad", formula="1", source="Missing")],
            )

    def test_rejects_unknown_formula_ref(self):
        with pytest.raises(
            (ValidationError, SDSchemaError),
            match="not found|unknown identifier|not a defined",
        ):
            SDModelDefinition(
                name="Test",
                description="Test",
                duration=10,
                stocks=[StockDef(name="Inventory", initial_value="100", expression="inflow")],
                flows=[FlowDef(name="inflow", formula="unknownVar", target="Inventory")],
                links=[LinkDef(source="inflow", target="Inventory")],
            )

    def test_rejects_unsafe_formula(self):
        with pytest.raises((ValidationError, SDSchemaError), match="disallowed"):
            _minimal_sd(
                flows=[FlowDef(name="inflow", formula="new Object()", target="Inventory")],
            )

    def test_rejects_invalid_java_name(self):
        with pytest.raises((ValidationError, SDSchemaError), match="valid Java identifier"):
            _minimal_sd(
                stocks=[StockDef(name="123bad", initial_value="0", expression="0")],
            )

    def test_rejects_non_numeric_stock_initial(self):
        with pytest.raises((ValidationError, SDSchemaError), match="numeric literal"):
            StockDef(name="S", initial_value="foo")

    def test_rejects_slider_min_not_less_than_max(self):
        with pytest.raises((ValidationError, SDSchemaError), match="slider_min < slider_max"):
            ParameterDef(name="p", default="1", slider_min=10, slider_max=5)

    def test_rejects_default_outside_slider_range(self):
        with pytest.raises((ValidationError, SDSchemaError), match="outside"):
            ParameterDef(name="p", default="100", slider_min=0, slider_max=10)

    def test_rejects_ui_control_slider_without_range(self):
        with pytest.raises((ValidationError, SDSchemaError), match="ui_control"):
            ParameterDef(name="p", default="1", ui_control="slider")

    def test_table_function_one_point_ok(self):
        tf = TableFunctionDef(name="tf", points=[TablePointDef(x=0, y=1)])
        assert len(tf.points) == 1

    def test_table_function_rejects_unsorted_x(self):
        with pytest.raises((ValidationError, SDSchemaError), match="sorted ascending"):
            TableFunctionDef(
                name="tf",
                points=[TablePointDef(x=2, y=1), TablePointDef(x=1, y=0)],
            )

    def test_table_function_rejects_duplicate_x(self):
        with pytest.raises((ValidationError, SDSchemaError), match="duplicate X"):
            TableFunctionDef(
                name="tf",
                points=[TablePointDef(x=1, y=1), TablePointDef(x=1, y=2)],
            )

    def test_table_function_clamp_ok(self):
        tf = TableFunctionDef(
            name="tf",
            points=[TablePointDef(x=0, y=0), TablePointDef(x=1, y=1)],
            out_of_range="CLAMP",
        )
        assert tf.out_of_range == "CLAMP"

    def test_chart_rejects_unknown_expression(self):
        with pytest.raises((ValidationError, SDSchemaError), match="not found"):
            _minimal_sd(
                charts=[
                    ChartDef(
                        title="Bad",
                        series=[ChartSeriesDef(title="x", expression="riceArea")],
                    )
                ]
            )

    def test_chart_rejects_empty_series(self):
        with pytest.raises(ValidationError):
            ChartDef(title="Empty", series=[])

    def test_structured_error_has_field_and_suggestion(self):
        with pytest.raises((ValidationError, SDSchemaError)) as exc_info:
            ParameterDef(name="p", default="99", slider_min=0, slider_max=10)
        # Prefer unwrapped SDSchemaError when available
        err = exc_info.value
        issues = []
        if isinstance(err, SDSchemaError):
            issues = err.to_dict_list()
        else:
            for e in err.errors():
                raw = (e.get("ctx") or {}).get("error")
                if isinstance(raw, SDSchemaError):
                    issues.extend(raw.to_dict_list())
        assert issues, "expected structured SDSchemaError issues"
        assert "error" in issues[0] and "field" in issues[0] and "suggestion" in issues[0]
        assert "outside" in issues[0]["error"]

    def test_to_store_dict(self):
        model = _minimal_sd()
        store = model.to_store_dict("test-id")
        assert store["paradigm"] == "system_dynamics"
        assert store["uses_process_library"] is False
        assert store["system_dynamics"]["variable_count"] == 3


class TestSDValidatorSemantics:
    def test_detects_algebraic_cycle(self):
        model = SDModelDefinition(
            name="Cycle",
            description="Algebraic loop",
            duration=10,
            stocks=[StockDef(name="S", initial_value="1", expression="f")],
            flows=[FlowDef(name="f", formula="a", target="S")],
            auxiliaries=[
                AuxDef(name="a", formula="b"),
                AuxDef(name="b", formula="a"),
            ],
            links=[
                LinkDef(source="f", target="S"),
                LinkDef(source="a", target="f"),
                LinkDef(source="b", target="a"),
                LinkDef(source="a", target="b"),
            ],
        )
        result = SDValidator().validate(model)
        assert not result.is_valid
        assert any("cycle" in e["error"].lower() for e in result.errors)
        assert "suggestion" in result.errors[0]

    def test_warns_unused_auxiliary(self):
        model = _minimal_sd(
            auxiliaries=[AuxDef(name="orphan", formula="1")],
        )
        result = SDValidator().validate(model)
        assert result.is_valid
        assert any("orphan" in w["error"] and "never referenced" in w["error"] for w in result.warnings)
