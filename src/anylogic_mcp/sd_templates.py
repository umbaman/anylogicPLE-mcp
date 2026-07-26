"""Built-in System Dynamics model templates."""

from __future__ import annotations

from typing import Any, Optional

from .sd_schema import (
    AuxDef,
    ChartDef,
    ChartSeriesDef,
    FlowDef,
    LinkDef,
    ParameterDef,
    SDModelDefinition,
    StockDef,
    TableFunctionDef,
    TablePointDef,
)


def build_template(template_name: str, params: Optional[dict[str, Any]] = None) -> SDModelDefinition:
    params = params or {}
    builders = {
        "predator_prey": _predator_prey,
        "simple_stock_flow": _simple_stock_flow,
    }
    fn = builders.get(template_name)
    if fn is None:
        raise ValueError(
            f"Unknown SD template: {template_name}. "
            f"Available: {', '.join(sorted(builders))}"
        )
    return fn(params)


def _predator_prey(params: dict[str, Any]) -> SDModelDefinition:
    name = params.get("name", "Predator Prey")
    description = params.get(
        "description",
        "Classical predator-prey dynamics (lynx and hares)",
    )
    return SDModelDefinition(
        name=name,
        description=description,
        time_unit="Year",
        duration=float(params.get("duration", 100)),
        parameters=[
            ParameterDef(
                name="Area",
                default="100",
                label="Area",
                slider_min=20,
                slider_max=500,
                ui_control="slider",
            ),
            ParameterDef(
                name="HareNatality",
                default="1.25",
                label="Hare natality",
                slider_min=0.25,
                slider_max=3.0,
                ui_control="slider",
            ),
            ParameterDef(
                name="LynxNatality",
                default="0.25",
                label="Lynx natality",
                slider_min=0.1,
                slider_max=0.5,
                ui_control="slider",
            ),
        ],
        stocks=[
            StockDef(name="Hares", initial_value="6000", expression="HareBirths - HareDeaths"),
            StockDef(name="Lynx", initial_value="125", expression="LynxBirths - LynxDeaths"),
        ],
        flows=[
            FlowDef(
                name="HareBirths",
                formula="Math.max(Hares, 0) * HareNatality",
                target="Hares",
            ),
            FlowDef(
                name="HareDeaths",
                formula="HareDensity * Lynx",
                source="Hares",
            ),
            FlowDef(
                name="LynxBirths",
                formula="Lynx * LynxNatality",
                target="Lynx",
            ),
            FlowDef(
                name="LynxDeaths",
                formula="Lynx * LynxMortality(HareDensity)",
                source="Lynx",
            ),
        ],
        auxiliaries=[
            AuxDef(name="HareDensity", formula="Hares / Area"),
        ],
        table_functions=[
            TableFunctionDef(
                name="LynxMortality",
                points=[
                    TablePointDef(x=0, y=0.5),
                    TablePointDef(x=20, y=0.4),
                    TablePointDef(x=40, y=0.3),
                    TablePointDef(x=60, y=0.2),
                    TablePointDef(x=80, y=0.1),
                ],
            ),
        ],
        links=[
            LinkDef(source="Hares", target="HareBirths"),
            LinkDef(source="HareNatality", target="HareBirths"),
            LinkDef(source="Hares", target="HareDeaths"),
            LinkDef(source="HareDensity", target="HareDeaths"),
            LinkDef(source="Lynx", target="HareDeaths"),
            LinkDef(source="Lynx", target="LynxBirths"),
            LinkDef(source="LynxNatality", target="LynxBirths"),
            LinkDef(source="Lynx", target="LynxDeaths"),
            LinkDef(source="HareDensity", target="LynxDeaths"),
            LinkDef(source="Hares", target="HareDensity"),
            LinkDef(source="Area", target="HareDensity"),
        ],
        charts=[
            ChartDef(
                title="Populations",
                series=[
                    ChartSeriesDef(title="Hares", expression="Hares"),
                    ChartSeriesDef(title="Lynx", expression="Lynx"),
                ],
            ),
        ],
    )


def _simple_stock_flow(params: dict[str, Any]) -> SDModelDefinition:
    name = params.get("name", "Simple Stock Flow")
    description = params.get("description", "Single-stock inventory with inflow and outflow")
    return SDModelDefinition(
        name=name,
        description=description,
        time_unit="Month",
        duration=float(params.get("duration", 60)),
        parameters=[
            ParameterDef(name="restockRate", default="50"),
            ParameterDef(name="demandRate", default="40"),
        ],
        stocks=[
            StockDef(
                name="Inventory",
                initial_value="200",
                expression="restocking - sales",
            ),
        ],
        flows=[
            FlowDef(name="restocking", formula="restockRate", target="Inventory"),
            FlowDef(name="sales", formula="demandRate", source="Inventory"),
        ],
        links=[
            LinkDef(source="restockRate", target="restocking"),
            LinkDef(source="restocking", target="Inventory"),
            LinkDef(source="demandRate", target="sales"),
            LinkDef(source="Inventory", target="sales"),
        ],
        charts=[
            ChartDef(
                title="Inventory",
                series=[ChartSeriesDef(title="Inventory", expression="Inventory")],
            ),
        ],
    )
