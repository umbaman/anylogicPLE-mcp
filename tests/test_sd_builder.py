"""Tests for System Dynamics .alp XML builder."""

import xml.etree.ElementTree as ET

import pytest

from anylogic_mcp.sd_builder import SDModelBuilder
from anylogic_mcp.sd_templates import build_template


@pytest.fixture
def sd_builder():
    return SDModelBuilder()


def xml(data: bytes) -> str:
    return data.decode("utf-8")


class TestSDBuiler:
    def test_predator_prey_generates_valid_xml(self, sd_builder):
        definition = build_template("predator_prey", {})
        out = xml(sd_builder.build_model(definition))
        assert '<?xml version="1.0"' in out
        assert "<AnyLogicWorkspace" in out
        ET.fromstring(out)

    def test_contains_sd_elements(self, sd_builder):
        definition = build_template("predator_prey", {})
        out = xml(sd_builder.build_model(definition))
        assert 'Class="StockVariable"' in out
        assert 'Class="Flow"' in out
        assert 'Class="AuxVariable"' in out
        assert 'Class="Parameter"' in out
        assert "<Dependences>" in out
        assert "<TableFunctions>" in out
        assert "<TimePlot>" in out

    def test_flow_source_target_ids(self, sd_builder):
        definition = build_template("simple_stock_flow", {})
        out = xml(sd_builder.build_model(definition))
        assert 'TargetId="' in out
        assert 'SourceId="' in out
        assert "<![CDATA[Inventory]]>" in out

    def test_year_time_unit(self, sd_builder):
        definition = build_template("predator_prey", {})
        out = xml(sd_builder.build_model(definition))
        assert "<ModelTimeUnit><![CDATA[Year]]></ModelTimeUnit>" in out
        assert "<FinalTime><![CDATA[100.0]]></FinalTime>" in out

    def test_unique_ids(self, sd_builder):
        definition = build_template("predator_prey", {})
        out = xml(sd_builder.build_model(definition))
        import re
        ids = re.findall(r"<Id>(\d+)</Id>", out)
        # ParameterEditor uses fixed Id 0 (AnyLogic convention); ignore those duplicates
        nonzero = [i for i in ids if i != "0"]
        assert len(nonzero) == len(set(nonzero))
        assert len(nonzero) > 10

    def test_build_from_template(self, sd_builder):
        out = xml(sd_builder.build_from_template("predator_prey", {}))
        assert "<![CDATA[Hares]]>" in out

    def test_has_agent_links_matching_connections_id(self, sd_builder):
        """AnyLogic crashes on open if ConnectionsId has no matching AgentLinks."""
        import re

        definition = build_template("predator_prey", {})
        out = xml(sd_builder.build_model(definition))
        assert "<AgentLinks>" in out
        assert "<AgentLink>" in out
        assert "<![CDATA[connections]]>" in out

        conn_match = re.search(r"<ConnectionsId>(\d+)</ConnectionsId>", out)
        assert conn_match is not None
        conn_id = conn_match.group(1)
        # AgentLink Id must equal ConnectionsId
        assert f"<AgentLink>\n\t\t\t\t\t<Id>{conn_id}</Id>" in out or (
            f"<Id>{conn_id}</Id>" in out
            and out.find("<AgentLinks>") < out.find(f"<Id>{conn_id}</Id>")
        )

    def test_has_converters_applied_outside_model(self, sd_builder):
        definition = build_template("simple_stock_flow", {})
        out = xml(sd_builder.build_model(definition))
        assert "<ConvertersApplied>" in out
        assert "</Model>" in out
        assert out.find("</Model>") < out.find("<ConvertersApplied>")
        assert "<BypassInitialScreen>true</BypassInitialScreen>" in out

    def test_agent_links_before_presentation(self, sd_builder):
        definition = build_template("predator_prey", {})
        out = xml(sd_builder.build_model(definition))
        assert out.find("<TableFunctions>") < out.find("<AgentLinks>")
        assert out.find("<AgentLinks>") < out.find("<Presentation>")

    def test_simulation_experiment_has_parameters(self, sd_builder):
        """AnyLogic NPE on open if SimulationExperiment lacks <Parameters>."""
        definition = build_template("predator_prey", {})
        out = xml(sd_builder.build_model(definition))
        # Parameters must appear inside SimulationExperiment, before PresentationProperties
        exp_idx = out.find("<SimulationExperiment")
        assert exp_idx != -1
        exp_end = out.find("</SimulationExperiment>", exp_idx)
        exp_block = out[exp_idx:exp_end]
        assert "<Parameters>" in exp_block
        assert "</Parameters>" in exp_block
        assert "<ParameterName><![CDATA[Area]]></ParameterName>" in exp_block
        assert exp_block.find("<Parameters>") < exp_block.find("<PresentationProperties>")

    def test_has_required_library_and_physical_dims(self, sd_builder):
        definition = build_template("simple_stock_flow", {})
        out = xml(sd_builder.build_model(definition))
        assert "com.anylogic.libraries.modules.markup_descriptors" in out
        assert "<RequiredLibraryReference>" in out
        assert "<PhysicalLength" in out
        assert "<LayoutTypeApplyOnStartup>true</LayoutTypeApplyOnStartup>" in out
        assert "<NetworkTypeApplyOnStartup>true</NetworkTypeApplyOnStartup>" in out

    def test_openable_structure_invariants(self, sd_builder):
        """Structural checklist aligned with DES builder / AnyLogic ground truth."""
        for template in ("predator_prey", "simple_stock_flow"):
            out = xml(sd_builder.build_from_template(template, {}))
            for tag in (
                "<AgentLinks>",
                "<Parameters>",
                "<BypassInitialScreen>true</BypassInitialScreen>",
                "<ConvertersApplied>",
                "<RequiredLibraryReference>",
                "<PhysicalLength",
            ):
                assert tag in out, f"{template} missing {tag}"
            ET.fromstring(out)


class TestSliderControls:
    def test_slider_control_xml_generated(self, sd_builder):
        from anylogic_mcp.sd_schema import (
            FlowDef,
            LinkDef,
            ParameterDef,
            SDModelDefinition,
            StockDef,
        )

        definition = SDModelDefinition(
            name="SliderDemo",
            description="Slider control demo",
            duration=10,
            parameters=[
                ParameterDef(
                    name="rate",
                    default="5",
                    slider_min=0,
                    slider_max=10,
                    ui_control="slider",
                ),
            ],
            stocks=[StockDef(name="S", initial_value="1", expression="inflow")],
            flows=[FlowDef(name="inflow", formula="rate", target="S")],
            links=[
                LinkDef(source="rate", target="inflow"),
                LinkDef(source="inflow", target="S"),
            ],
        )
        out = xml(sd_builder.build_model(definition))
        assert 'Type="Slider"' in out
        assert '<Control Type="Slider">' in out
        assert "<Link><![CDATA[rate]]></Link>" in out
        assert "<Minimum><![CDATA[0" in out
        assert "<Maximum><![CDATA[10" in out

    def test_slider_auto_layout_wraps_every_five(self, sd_builder):
        from anylogic_mcp.sd_builder import _slider_positions

        positions = _slider_positions(6)
        assert positions[0] == (50, 400)
        assert positions[4] == (50 + 4 * 170, 400)
        assert positions[5] == (50, 470)

    def test_predator_prey_emits_slider_controls(self, sd_builder):
        out = xml(sd_builder.build_from_template("predator_prey", {}))
        assert out.count('Type="Slider"') == 3
        assert "<Link><![CDATA[Area]]></Link>" in out


class TestRoundTrip:
    def test_schema_to_xml_round_trip_identity(self, sd_builder):
        """schema → XML → parse key elements and verify they match the schema."""
        from anylogic_mcp.sd_schema import (
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

        definition = SDModelDefinition(
            name="RoundTrip",
            description="Round trip check",
            time_unit="Month",
            duration=24,
            parameters=[
                ParameterDef(
                    name="k",
                    default="2",
                    slider_min=0,
                    slider_max=5,
                    ui_control="slider",
                ),
            ],
            stocks=[StockDef(name="Level", initial_value="10", expression="flowIn")],
            flows=[FlowDef(name="flowIn", formula="k * helper", target="Level")],
            auxiliaries=[AuxDef(name="helper", formula="1")],
            table_functions=[
                TableFunctionDef(
                    name="lookup",
                    points=[TablePointDef(x=0, y=0), TablePointDef(x=1, y=1)],
                    out_of_range="CLAMP",
                ),
            ],
            links=[
                LinkDef(source="k", target="flowIn"),
                LinkDef(source="helper", target="flowIn"),
                LinkDef(source="flowIn", target="Level"),
            ],
            charts=[
                ChartDef(
                    title="Level",
                    series=[
                        ChartSeriesDef(title="Level", expression="Level", color=-16776961),
                    ],
                )
            ],
        )
        out = xml(sd_builder.build_model(definition))
        root = ET.fromstring(out)

        names = {
            el.findtext("Name")
            for el in root.iter("Variable")
        }
        assert "Level" in names
        assert "flowIn" in names
        assert "helper" in names
        assert "k" in names

        tf = root.find(".//TableFunction")
        assert tf is not None
        assert tf.findtext("Name") == "lookup"
        assert tf.findtext("OutOfRangeBehaviour") == "CLAMP"
        xs = [float(a.text) for a in tf.findall("Argument")]
        ys = [float(v.text) for v in tf.findall("Value")]
        assert xs == [0.0, 1.0]
        assert ys == [0.0, 1.0]

        control = root.find(".//Control[@Type='Slider']")
        assert control is not None
        assert control.findtext("Link") == "k"

        expr2 = root.find(".//Expression2")
        assert expr2 is not None
        assert expr2.text == "Level"

        assert root.findtext(".//ModelTimeUnit") == "Month"
        assert root.findtext(".//FinalTime") == "24.0"

        # Rebuild from dumped store dict and confirm identical structural fingerprint
        store = definition.to_store_dict("rid")
        rebuilt = SDModelDefinition(
            name=store["name"],
            description=store["description"],
            time_unit=store["time_unit"],
            duration=store["duration"],
            stocks=store["system_dynamics"]["stocks"],
            flows=store["system_dynamics"]["flows"],
            auxiliaries=store["system_dynamics"]["auxiliaries"],
            parameters=store["system_dynamics"]["parameters"],
            table_functions=store["system_dynamics"]["table_functions"],
            links=store["system_dynamics"]["links"],
            charts=store["system_dynamics"]["charts"],
        )
        out2 = xml(sd_builder.build_model(rebuilt))
        root2 = ET.fromstring(out2)

        def fingerprint(r: ET.Element) -> tuple:
            return (
                sorted(
                    (el.get("Class"), el.findtext("Name"))
                    for el in r.iter("Variable")
                ),
                [
                    (tf.findtext("Name"), tf.findtext("OutOfRangeBehaviour"))
                    for tf in r.iter("TableFunction")
                ],
                [
                    (c.findtext("Link"), c.findtext("Minimum"), c.findtext("Maximum"))
                    for c in r.iter("Control")
                ],
                [e.text for e in r.iter("Expression2")],
            )

        assert fingerprint(root) == fingerprint(root2)

