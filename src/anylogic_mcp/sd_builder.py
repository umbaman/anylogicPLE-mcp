"""System Dynamics .alp XML builder for AnyLogic 8.9.x.

Emits AnyLogic Workspace XML for pure SD models. Key fragments:

**TableFunction** (lookup)::

    <TableFunction AccessType="public" StaticFunction="false">
      <Id>...</Id>
      <Name><![CDATA[LynxMortality]]></Name>
      <InterpolationMethod>LINEAR</InterpolationMethod>
      <OutOfRangeBehaviour>EXTRAPOLATE</OutOfRangeBehaviour>  <!-- ERROR|EXTRAPOLATE|CUSTOM|CLAMP -->
      <Argument><![CDATA[0]]></Argument>
      <Value><![CDATA[0.5]]></Value>
      ...
    </TableFunction>

**Links** (causal dependencies under ``<Dependences>``)::

    <Link SourceId="111" TargetId="222" Polarity="null">
      <Id>...</Id>
      <Name><![CDATA[111-222]]></Name>
      ...
    </Link>

**Control** (presentation slider when ``ui_control="slider"``)::

    <Control Type="Slider">
      <Id>...</Id>
      <Name><![CDATA[slider_Area]]></Name>
      <X>50</X><Y>400</Y>
      <Width>150</Width><Height>40</Height>
      <Minimum><![CDATA[20]]></Minimum>
      <Maximum><![CDATA[500]]></Maximum>
      <DefaultValue><![CDATA[100]]></DefaultValue>
      <Link><![CDATA[Area]]></Link>
      <Orientation>HORIZONTAL</Orientation>
    </Control>

Sliders are auto-positioned: ``x`` advances by 170px; a new row every 5 sliders.
"""

from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Tuple

from .model_builder import _CONVERTER_UUIDS, _agent_links
from .sd_schema import (
    AuxDef,
    ChartDef,
    ChartSeriesDef,
    FlowDef,
    ParameterDef,
    SDModelDefinition,
    StockDef,
    TableFunctionDef,
    TimeUnit,
)
from .sd_templates import build_template

_CHART_COLORS = [-10496, -6632142, -13434879, -16711936, -16776961]


class _IDs:
    def __init__(self) -> None:
        self._n = int(time.time() * 1000)

    def next(self) -> int:
        self._n += 1
        return self._n


def _java_pkg(name: str) -> str:
    pkg = re.sub(r"[^a-zA-Z0-9]", "_", name).lower().strip("_")
    if pkg and pkg[0].isdigit():
        pkg = "model_" + pkg
    return pkg or "model"


def _time_unit_code(unit: TimeUnit) -> str:
    mapping = {
        "Year": "YEAR",
        "Month": "MONTH",
        "Day": "DAY",
        "Hour": "HOUR",
        "Minute": "MINUTE",
        "Second": "SECOND",
    }
    return mapping[unit]


def _stock_xml(
    stock: StockDef,
    var_id: int,
    expression: str,
    x: int,
    y: int,
) -> str:
    return f"""\
				<Variable Class="StockVariable">
					<Id>{var_id}</Id>
					<Name><![CDATA[{stock.name}]]></Name>
					<X>{x}</X><Y>{y}</Y>
					<Label><X>-30</X><Y>15</Y></Label>
					<PublicFlag>false</PublicFlag>
					<PresentationFlag>true</PresentationFlag>
					<ShowLabel>true</ShowLabel>
					<Properties Array="false">
					<EquationStyle>classic</EquationStyle>
					<Width>20</Width>
					<Height>20</Height>
						<Expression><![CDATA[{expression}]]></Expression>
						<InitialValue><![CDATA[{stock.initial_value}]]></InitialValue>
						<Color/>
					</Properties>
				</Variable>
"""


def _flow_xml(
    flow: FlowDef,
    var_id: int,
    stock_ids: Dict[str, int],
    x: int,
    y: int,
) -> str:
    attrs = []
    if flow.source:
        attrs.append(f'SourceId="{stock_ids[flow.source]}"')
    if flow.target:
        attrs.append(f'TargetId="{stock_ids[flow.target]}"')
    attr_str = " ".join(attrs)
    return f"""\
				<Variable Class="Flow">
					<Id>{var_id}</Id>
					<Name><![CDATA[{flow.name}]]></Name>
					<X>{x}</X><Y>{y}</Y>
					<Label><X>-15</X><Y>-30</Y></Label>
					<PublicFlag>false</PublicFlag>
					<PresentationFlag>true</PresentationFlag>
					<ShowLabel>true</ShowLabel>
					<Properties {attr_str} External="false" Constant="false" Array="false">
						<Formula><![CDATA[{flow.formula}]]></Formula>
						<Color/>
						<ValveIndex>1</ValveIndex>
						<Points>
							<Point><X>0</X><Y>0</Y></Point>
							<Point><X>80</X><Y>0</Y></Point>
							<Point><X>160</X><Y>0</Y></Point>
						</Points>
					</Properties>
				</Variable>
"""


def _aux_xml(aux: AuxDef, var_id: int, x: int, y: int) -> str:
    return f"""\
				<Variable Class="AuxVariable">
					<Id>{var_id}</Id>
					<Name><![CDATA[{aux.name}]]></Name>
					<X>{x}</X><Y>{y}</Y>
					<Label><X>-40</X><Y>-5</Y></Label>
					<PublicFlag>false</PublicFlag>
					<PresentationFlag>true</PresentationFlag>
					<ShowLabel>true</ShowLabel>
					<Properties External="false" Constant="false" Array="false">
						<Formula><![CDATA[{aux.formula}]]></Formula>
						<Color/>
					</Properties>
				</Variable>
"""


def _parameter_xml(param: ParameterDef, var_id: int, x: int, y: int) -> str:
    editor = ""
    if param.slider_min is not None and param.slider_max is not None:
        label = param.label or param.name
        editor = f"""\
						<ParameterEditor>
							<Id>0</Id>
							<Name><![CDATA[null]]></Name>
							<Label><![CDATA[{label}]]></Label>
							<EditorContolType>SLIDER</EditorContolType>
							<MinSliderValue><![CDATA[{param.slider_min}]]></MinSliderValue>
							<MaxSliderValue><![CDATA[{param.slider_max}]]></MaxSliderValue>
							<DelimeterType>NO_DELIMETER</DelimeterType>
						</ParameterEditor>
"""
    return f"""\
				<Variable Class="Parameter">
					<Id>{var_id}</Id>
					<Name><![CDATA[{param.name}]]></Name>
					<X>{x}</X><Y>{y}</Y>
					<Label><X>-40</X><Y>-20</Y></Label>
					<PublicFlag>false</PublicFlag>
					<PresentationFlag>true</PresentationFlag>
					<ShowLabel>true</ShowLabel>
					<Properties SaveInSnapshot="true" ModificatorType="STATIC">
						<Type><![CDATA[double]]></Type>
						<UnitType><![CDATA[NONE]]></UnitType>
						<SdArray>false</SdArray>
						<DefaultValue Class="CodeValue">
							<Code><![CDATA[{param.default}]]></Code>
						</DefaultValue>
{editor}					</Properties>
				</Variable>
"""


def _table_function_xml(tf: TableFunctionDef, var_id: int, x: int, y: int) -> str:
    """Build ``<TableFunction>`` with ordered ``<Argument>`` / ``<Value>`` pairs."""
    args = "\n".join(f"\t\t\t\t\t<Argument><![CDATA[{p.x}]]></Argument>" for p in tf.points)
    vals = "\n".join(f"\t\t\t\t\t<Value><![CDATA[{p.y}]]></Value>" for p in tf.points)
    return f"""\
				<TableFunction AccessType="public" StaticFunction="false">
					<Id>{var_id}</Id>
					<Name><![CDATA[{tf.name}]]></Name>
					<X>{x}</X><Y>{y}</Y>
					<Label><X>10</X><Y>0</Y></Label>
					<PublicFlag>false</PublicFlag>
					<PresentationFlag>true</PresentationFlag>
					<ShowLabel>true</ShowLabel>
					<InterpolationMethod>{tf.interpolation}</InterpolationMethod>
					<OutOfRangeBehaviour>{tf.out_of_range}</OutOfRangeBehaviour>
					<OutOfRangeCustomValue><![CDATA[0.0]]></OutOfRangeCustomValue>
					<ApproximationOrder><![CDATA[1]]></ApproximationOrder>
					<LoadFromDatabase><![CDATA[false]]></LoadFromDatabase>
					<ValuesQuery>
						<TableReference>
						</TableReference>
							<ArgumentColumnReference>
							</ArgumentColumnReference>
							<ValueColumnReference>
							</ValueColumnReference>
					</ValuesQuery>
{args}
{vals}
				</TableFunction>
"""


def _slider_control_xml(
    param: ParameterDef,
    control_id: int,
    x: int,
    y: int,
) -> str:
    """Build presentation ``<Control Type="Slider">`` linked to a parameter.

    XML shape::

        <Control Type="Slider">
          ...
          <Minimum>...</Minimum>
          <Maximum>...</Maximum>
          <DefaultValue>...</DefaultValue>
          <Link><![CDATA[parameterName]]></Link>
        </Control>
    """
    label = param.label or param.name
    return f"""\
					<Control Type="Slider">
						<Id>{control_id}</Id>
						<Name><![CDATA[slider_{param.name}]]></Name>
						<X>{x}</X><Y>{y}</Y>
						<Label><X>0</X><Y>-20</Y></Label>
						<PublicFlag>true</PublicFlag>
						<PresentationFlag>true</PresentationFlag>
						<ShowLabel>true</ShowLabel>
						<DrawMode>SHAPE_DRAW_2D3D</DrawMode>
						<EmbeddedIcon>false</EmbeddedIcon>
						<Width>150</Width>
						<Height>40</Height>
						<Minimum><![CDATA[{param.slider_min}]]></Minimum>
						<Maximum><![CDATA[{param.slider_max}]]></Maximum>
						<DefaultValue><![CDATA[{param.default}]]></DefaultValue>
						<Link><![CDATA[{param.name}]]></Link>
						<Orientation>HORIZONTAL</Orientation>
						<Action><![CDATA[]]></Action>
						<Caption><![CDATA[{label}]]></Caption>
					</Control>
"""


def _slider_positions(count: int) -> List[Tuple[int, int]]:
    """Auto-layout for presentation sliders: 5 per row, 170px horizontal step."""
    positions: List[Tuple[int, int]] = []
    for i in range(count):
        col = i % 5
        row = i // 5
        positions.append((50 + col * 170, 400 + row * 70))
    return positions


def _link_xml(link_id: int, source_id: int, target_id: int, x: int, y: int) -> str:
    return f"""\
				<Link SourceId="{source_id}" TargetId="{target_id}" Polarity="null">
					<Height>20.0</Height>
					<PolarityPosition>0.95</PolarityPosition>
					<Direction><X>100</X><Y>0</Y></Direction>
					<Id>{link_id}</Id>
					<Name><![CDATA[{source_id}-{target_id}]]></Name>
					<X>{x}</X><Y>{y}</Y>
					<Label><X>10</X><Y>0</Y></Label>
					<PublicFlag>false</PublicFlag>
					<PresentationFlag>true</PresentationFlag>
					<ShowLabel>false</ShowLabel>
					<Color/>
					<LineWidth>1</LineWidth>
					<Delay>false</Delay>
				</Link>
"""


def _dataset_expression(idx: int, title: str, expression: str, color: int, ds_id: int) -> str:
    ds_name = f"dataset{idx}" if idx > 0 else "dataset"
    return f"""\
					<DatasetExpression>
						<Title><![CDATA[{title}]]></Title>
						<Id>{ds_id}</Id>
						<Expression><![CDATA[{ds_name}]]></Expression>
						<Color>{color}</Color>
						<Expression2><![CDATA[{expression}]]></Expression2>
						<Expression2Flag>true</Expression2Flag>
						<PointStyle>NONE</PointStyle>
						<LineWidth>1.0</LineWidth>
					</DatasetExpression>
"""


def _time_plot(
    plot_id: int,
    rec_id: int,
    datasets_xml: str,
    time_unit: TimeUnit,
    duration: float,
) -> str:
    unit_code = _time_unit_code(time_unit)
    return f"""\
				<TimePlot>
					<Id>{plot_id}</Id>
					<Name><![CDATA[plot]]></Name>
					<X>470</X><Y>170</Y>
					<Label><X>0</X><Y>-10</Y></Label>
					<PublicFlag>true</PublicFlag>
					<PresentationFlag>true</PresentationFlag>
					<ShowLabel>false</ShowLabel>
					<DrawMode>SHAPE_DRAW_2D3D</DrawMode>
					<AutoUpdate>true</AutoUpdate>
					<RecurrenceProperties>
						<Id>{rec_id}</Id>
						<OccurrenceAtTime>true</OccurrenceAtTime>
						<OccurrenceDate>1592092800000</OccurrenceDate>
						<OccurrenceTime Class="CodeUnitValue">
							<Code><![CDATA[0]]></Code>
							<Unit Class="TimeUnits"><![CDATA[{unit_code}]]></Unit>
						</OccurrenceTime>
						<RecurrenceCode Class="CodeUnitValue">
							<Code><![CDATA[1]]></Code>
							<Unit Class="TimeUnits"><![CDATA[{unit_code}]]></Unit>
						</RecurrenceCode>
					</RecurrenceProperties>
					<EmbeddedIcon>false</EmbeddedIcon>
					<Width>320</Width>
					<Height>220</Height>
					<BackgroundColor/>
					<BorderColor/>
					<ChartArea>
						<XOffset>50</XOffset><YOffset>30</YOffset>
						<Width>240</Width><Height>140</Height>
						<BackgroundColor>-1</BackgroundColor>
						<BorderColor>-16777216</BorderColor>
						<GridColor>-12566464</GridColor>
					</ChartArea>
					<Legend>
						<Place>SOUTH</Place>
						<TextColor>-16777216</TextColor>
						<Size>30</Size>
					</Legend>
					<Labels>
						<HorLabelsPosition>DEFAULT</HorLabelsPosition>
						<VerLabelsPosition>DEFAULT</VerLabelsPosition>
						<TextColor>-12566464</TextColor>
					</Labels>
					<ShowLegend>true</ShowLegend>
					<TimeWindowsMovementType>MOVEMENT_WITH_TIME</TimeWindowsMovementType>
					<TimeWindowUnits>MODEL_TIME_UNIT</TimeWindowUnits>
					<VerScaleFromExpression><![CDATA[0]]></VerScaleFromExpression>
					<VerScaleToExpression><![CDATA[1]]></VerScaleToExpression>
					<VerScaleType>AUTO</VerScaleType>
					<DrawLine>true</DrawLine>
					<Interpolation>LINEAR</Interpolation>
{datasets_xml}				<SamplesToKeep>100</SamplesToKeep>
					<TimeWindowExpression><![CDATA[{duration}]]></TimeWindowExpression>
					<FillAreaUnderLine>false</FillAreaUnderLine>
					<LabelFormat>MODEL_TIME_UNITS</LabelFormat>
				</TimePlot>
"""


def _layout_positions(model: SDModelDefinition) -> Dict[str, Tuple[int, int]]:
    positions: Dict[str, Tuple[int, int]] = {}
    for i, stock in enumerate(model.stocks):
        col = i % 3
        row = i // 3
        positions[stock.name] = (200 + col * 220, 120 + row * 140)
    for i, flow in enumerate(model.flows):
        if flow.target and flow.target in positions:
            sx, sy = positions[flow.target]
            positions[flow.name] = (sx - 120, sy)
        elif flow.source and flow.source in positions:
            sx, sy = positions[flow.source]
            positions[flow.name] = (sx + 120, sy)
        else:
            positions[flow.name] = (80, 80 + i * 50)
    for i, aux in enumerate(model.auxiliaries):
        positions[aux.name] = (520, 60 + i * 45)
    for i, param in enumerate(model.parameters):
        positions[param.name] = (720, 60 + i * 45)
    for i, tf in enumerate(model.table_functions):
        positions[tf.name] = (-180, 20 + i * 40)
    return positions


def _default_charts(model: SDModelDefinition) -> list[ChartDef]:
    if model.charts:
        return model.charts
    series = [
        ChartSeriesDef(title=s.name, expression=s.name)
        for s in model.stocks[:5]
    ]
    if model.auxiliaries:
        series.append(
            ChartSeriesDef(
                title=model.auxiliaries[0].name,
                expression=model.auxiliaries[0].name,
            )
        )
    if not series:
        return []
    return [ChartDef(title="System Dynamics", series=series)]


class SDModelBuilder:
    """Builds AnyLogic .alp files for pure System Dynamics models."""

    def build_model(self, definition: SDModelDefinition) -> bytes:
        ids = _IDs()
        pkg = _java_pkg(definition.name)
        positions = _layout_positions(definition)
        stock_exprs = definition.stock_expressions()

        model_id = ids.next()
        db_id = ids.next()
        frame_id = ids.next()
        main_id = ids.next()
        main_gp = ids.next()
        main_ds = ids.next()
        scale_id = ids.next()
        link_conn_id = ids.next()
        main_lvl = ids.next()
        exp_id = ids.next()
        run_id = ids.next()
        stop_time = f"{definition.duration:.1f}".rstrip("0").rstrip(".")
        if "." not in stop_time:
            stop_time = f"{stop_time}.0"

        var_ids: Dict[str, int] = {}
        variables_xml = ""

        for stock in definition.stocks:
            vid = ids.next()
            var_ids[stock.name] = vid
            x, y = positions[stock.name]
            variables_xml += _stock_xml(stock, vid, stock_exprs[stock.name], x, y)

        for flow in definition.flows:
            vid = ids.next()
            var_ids[flow.name] = vid
            x, y = positions[flow.name]
            variables_xml += _flow_xml(flow, vid, var_ids, x, y)

        for aux in definition.auxiliaries:
            vid = ids.next()
            var_ids[aux.name] = vid
            x, y = positions[aux.name]
            variables_xml += _aux_xml(aux, vid, x, y)

        for param in definition.parameters:
            vid = ids.next()
            var_ids[param.name] = vid
            x, y = positions[param.name]
            variables_xml += _parameter_xml(param, vid, x, y)

        table_functions_xml = ""
        for tf in definition.table_functions:
            vid = ids.next()
            var_ids[tf.name] = vid
            x, y = positions[tf.name]
            table_functions_xml += _table_function_xml(tf, vid, x, y)

        dependences_xml = ""
        for link in definition.links:
            link_id = ids.next()
            sx, sy = positions.get(link.source, (100, 100))
            dependences_xml += _link_xml(
                link_id, var_ids[link.source], var_ids[link.target], sx, sy
            )

        plot_id = ids.next()
        rec_id = ids.next()
        datasets_xml = ""
        charts = _default_charts(definition)
        for chart in charts:
            for i, series in enumerate(chart.series):
                ds_id = ids.next()
                color = (
                    series.color
                    if series.color is not None
                    else _CHART_COLORS[i % len(_CHART_COLORS)]
                )
                datasets_xml += _dataset_expression(
                    i, series.title, series.expression, color, ds_id
                )
        time_plot_xml = _time_plot(
            plot_id, rec_id, datasets_xml, definition.time_unit, definition.duration
        )

        slider_params = [p for p in definition.parameters if p.ui_control == "slider"]
        slider_xy = _slider_positions(len(slider_params))
        controls_xml = ""
        for param, (sx, sy) in zip(slider_params, slider_xy):
            controls_xml += _slider_control_xml(param, ids.next(), sx, sy)

        unit_code = _time_unit_code(definition.time_unit)
        converters_xml = "\n".join(f"\t<Uuid>{u}</Uuid>" for u in _CONVERTER_UUIDS)

        experiment_params = ""
        for param in definition.parameters:
            experiment_params += f"""\
				<Parameter>
					<ParameterName><![CDATA[{param.name}]]></ParameterName>
				</Parameter>
"""

        main_xml = f"""\
		<ActiveObjectClass>
			<Id>{main_id}</Id>
			<Name><![CDATA[Main]]></Name>
			<Generic>false</Generic>
			<GenericParameter>
				<Id>{main_gp}</Id>
				<Name><![CDATA[{main_gp}]]></Name>
				<GenericParameterValue Class="CodeValue">
					<Code><![CDATA[T extends Agent]]></Code>
				</GenericParameterValue>
				<GenericParameterLabel><![CDATA[Generic parameter:]]></GenericParameterLabel>
			</GenericParameter>
			<FlowChartsUsage>ENTITY</FlowChartsUsage>
			<SamplesToKeep>100</SamplesToKeep>
			<LimitNumberOfArrayElements>false</LimitNumberOfArrayElements>
			<ElementsLimitValue>100</ElementsLimitValue>
			<MakeDefaultViewArea>true</MakeDefaultViewArea>
			<SceneGridColor/>
			<SceneBackgroundColor>-4144960</SceneBackgroundColor>
			<SceneSkybox>null</SceneSkybox>
			<AgentProperties>
				<EnvironmentDefinesInitialLocation>true</EnvironmentDefinesInitialLocation>
				<RotateAnimationTowardsMovement>true</RotateAnimationTowardsMovement>
				<RotateAnimationVertically>false</RotateAnimationVertically>
				<VelocityCode Class="CodeUnitValue">
					<Code><![CDATA[10]]></Code>
					<Unit Class="SpeedUnits"><![CDATA[MPS]]></Unit>
				</VelocityCode>
				<PhysicalLength Class="CodeUnitValue">
					<Code><![CDATA[1]]></Code>
					<Unit Class="LengthUnits"><![CDATA[METER]]></Unit>
				</PhysicalLength>
				<PhysicalWidth Class="CodeUnitValue">
					<Code><![CDATA[1]]></Code>
					<Unit Class="LengthUnits"><![CDATA[METER]]></Unit>
				</PhysicalWidth>
				<PhysicalHeight Class="CodeUnitValue">
					<Code><![CDATA[1]]></Code>
					<Unit Class="LengthUnits"><![CDATA[METER]]></Unit>
				</PhysicalHeight>
			</AgentProperties>
			<EnvironmentProperties>
					<EnableSteps>false</EnableSteps>
					<StepDurationCode Class="CodeUnitValue">
						<Code><![CDATA[1.0]]></Code>
						<Unit Class="TimeUnits"><![CDATA[SECOND]]></Unit>
					</StepDurationCode>
					<SpaceType>CONTINUOUS</SpaceType>
					<WidthCode><![CDATA[500]]></WidthCode>
					<HeightCode><![CDATA[500]]></HeightCode>
					<ZHeightCode><![CDATA[0]]></ZHeightCode>
					<ColumnsCountCode><![CDATA[100]]></ColumnsCountCode>
					<RowsCountCode><![CDATA[100]]></RowsCountCode>
					<NeigborhoodType>MOORE</NeigborhoodType>
					<LayoutType>USER_DEF</LayoutType>
					<LayoutTypeApplyOnStartup>true</LayoutTypeApplyOnStartup>
					<NetworkType>USER_DEF</NetworkType>
					<NetworkTypeApplyOnStartup>true</NetworkTypeApplyOnStartup>
					<ConnectionsPerAgentCode><![CDATA[2]]></ConnectionsPerAgentCode>
					<ConnectionsRangeCode><![CDATA[50]]></ConnectionsRangeCode>
					<NeighborLinkFractionCode><![CDATA[0.95]]></NeighborLinkFractionCode>
					<MCode><![CDATA[10]]></MCode>
			</EnvironmentProperties>
			<DatasetsCreationProperties>
				<AutoCreate>true</AutoCreate>
					<Id>{main_ds}</Id>
					<OccurrenceAtTime>true</OccurrenceAtTime>
					<OccurrenceDate>1592092800000</OccurrenceDate>
					<OccurrenceTime Class="CodeUnitValue">
						<Code><![CDATA[0]]></Code>
						<Unit Class="TimeUnits"><![CDATA[{unit_code}]]></Unit>
					</OccurrenceTime>
					<RecurrenceCode Class="CodeUnitValue">
						<Code><![CDATA[1]]></Code>
						<Unit Class="TimeUnits"><![CDATA[{unit_code}]]></Unit>
					</RecurrenceCode>
			</DatasetsCreationProperties>
			<ScaleRuler>
				<Id>{scale_id}</Id>
				<Name><![CDATA[scale]]></Name>
				<X>0</X><Y>-150</Y>
				<PublicFlag>false</PublicFlag>
				<PresentationFlag>false</PresentationFlag>
				<ShowLabel>false</ShowLabel>
				<DrawMode>SHAPE_DRAW_2D3D</DrawMode>
				<Length>100</Length>
				<Rotation>0</Rotation>
				<ScaleType>BASED_ON_LENGTH</ScaleType>
				<ModelLength>10</ModelLength>
				<LengthUnits>METER</LengthUnits>
				<Scale>10</Scale>
				<InheritedFromParentAgentType>true</InheritedFromParentAgentType>
			</ScaleRuler>
			<CurrentLevel>{main_lvl}</CurrentLevel>
			<ConnectionsId>{link_conn_id}</ConnectionsId>
			<Variables>
{variables_xml}			</Variables>
			<Dependences>
{dependences_xml}			</Dependences>
			<TableFunctions>
{table_functions_xml}			</TableFunctions>
{_agent_links(link_conn_id)}
			<Presentation>
				<Level>
					<Id>{main_lvl}</Id>
					<Name><![CDATA[level]]></Name>
					<X>0</X><Y>0</Y>
					<Label><X>10</X><Y>0</Y></Label>
					<PublicFlag>true</PublicFlag>
					<PresentationFlag>true</PresentationFlag>
					<ShowLabel>false</ShowLabel>
					<DrawMode>SHAPE_DRAW_2D3D</DrawMode>
					<Z>0</Z>
					<LevelVisibility>DIM_NON_CURRENT</LevelVisibility>
				<Presentation>
{time_plot_xml}{controls_xml}				</Presentation>
				</Level>
			</Presentation>
		</ActiveObjectClass>
"""

        xml = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!--
*************************************************
	         AnyLogic Project File
*************************************************
-->
<AnyLogicWorkspace WorkspaceVersion="1.9" AnyLogicVersion="8.9.8.202602271015" AlpVersion="8.9.7">
<Model>
	<Id>{model_id}</Id>
	<Name><![CDATA[{definition.name}]]></Name>
	<Description><![CDATA[{definition.description}]]></Description>
	<EngineVersion>6</EngineVersion>
	<JavaPackageName><![CDATA[{pkg}]]></JavaPackageName>
	<ModelTimeUnit><![CDATA[{definition.time_unit}]]></ModelTimeUnit>
	<Folders>
	</Folders>
	<ActiveObjectClasses>
		<!--   =========   Active Object Class   ========  -->
{main_xml}	</ActiveObjectClasses>
	<DifferentialEquationsMethod>EULER</DifferentialEquationsMethod>
	<MixedEquationsMethod>RK45_NEWTON</MixedEquationsMethod>
	<AlgebraicEquationsMethod>MODIFIED_NEWTON</AlgebraicEquationsMethod>
	<AbsoluteAccuracy>1.0E-5</AbsoluteAccuracy>
	<FixedTimeStep>0.001</FixedTimeStep>
	<RelativeAccuracy>1.0E-5</RelativeAccuracy>
	<TimeAccuracy>1.0E-5</TimeAccuracy>
	<InspectionWindowColorTheme>DEFAULT</InspectionWindowColorTheme>
	<Frame>
		<Id>{frame_id}</Id>
		<Width>1000</Width>
		<Height>600</Height>
	</Frame>
	<Database>
		<Id>{db_id}</Id>
		<Logging>false</Logging>
		<AutoExport>false</AutoExport>
		<ShutdownCompact>false</ShutdownCompact>
		<ImportSettings>
		</ImportSettings>
		<ExportSettings>
		</ExportSettings>
	</Database>

	<RunConfiguration ActiveObjectClassId="{main_id}">
		<Id>{run_id}</Id>
		<Name><![CDATA[RunConfiguration]]></Name>
		<MaximumMemory>512</MaximumMemory>
		<ModelTimeProperties>
			<StopOption><![CDATA[Stop at specified time]]></StopOption>
			<InitialDate><![CDATA[1592092800000]]></InitialDate>
			<InitialTime><![CDATA[0.0]]></InitialTime>
			<FinalDate><![CDATA[1594684800000]]></FinalDate>
			<FinalTime><![CDATA[{stop_time}]]></FinalTime>
		</ModelTimeProperties>
		<AnimationProperties>
			<StopNever>true</StopNever>
			<ExecutionMode>realTimeScaled</ExecutionMode>
			<RealTimeScale>1.0</RealTimeScale>
			<EnableZoomAndPanning>true</EnableZoomAndPanning>
			<EnableDeveloperPanel>false</EnableDeveloperPanel>
			<ShowDeveloperPanelOnStart>false</ShowDeveloperPanelOnStart>
		</AnimationProperties>
		<Inputs>
		</Inputs>
		<Outputs>
		</Outputs>
	</RunConfiguration>
	<Experiments>
		<!--   =========   Simulation Experiment   ========  -->
		<SimulationExperiment ActiveObjectClassId="{main_id}">
			<Id>{exp_id}</Id>
			<Name><![CDATA[Simulation]]></Name>
			<CommandLineArguments><![CDATA[]]></CommandLineArguments>
			<MaximumMemory>512</MaximumMemory>
			<RandomNumberGenerationType>fixedSeed</RandomNumberGenerationType>
			<CustomGeneratorCode>new Random()</CustomGeneratorCode>
			<SeedValue>1</SeedValue>
			<SelectionModeForSimultaneousEvents>LIFO</SelectionModeForSimultaneousEvents>
			<VmArgs><![CDATA[]]></VmArgs>
			<LoadRootFromSnapshot>false</LoadRootFromSnapshot>

			<Parameters>
{experiment_params}			</Parameters>
			<PresentationProperties>
				<EnableZoomAndPanning>true</EnableZoomAndPanning>
				<ExecutionMode><![CDATA[realTimeScaled]]></ExecutionMode>
				<Title><![CDATA[{definition.name} : Simulation]]></Title>
				<EnableDeveloperPanel>false</EnableDeveloperPanel>
				<ShowDeveloperPanelOnStart>false</ShowDeveloperPanelOnStart>
				<RealTimeScale>1.0</RealTimeScale>
			</PresentationProperties>
			<ModelTimeProperties>
				<StopOption><![CDATA[Stop at specified time]]></StopOption>
				<InitialDate><![CDATA[1592092800000]]></InitialDate>
				<InitialTime><![CDATA[0.0]]></InitialTime>
				<FinalDate><![CDATA[1594684800000]]></FinalDate>
				<FinalTime><![CDATA[{stop_time}]]></FinalTime>
			</ModelTimeProperties>
			<BypassInitialScreen>true</BypassInitialScreen>
		</SimulationExperiment>
	</Experiments>
    <RequiredLibraryReference>
		<LibraryName><![CDATA[com.anylogic.libraries.modules.markup_descriptors]]></LibraryName>
		<VersionMajor>1</VersionMajor>
		<VersionMinor>0</VersionMinor>
		<VersionBuild>0</VersionBuild>
    </RequiredLibraryReference>
</Model>
<ConvertersApplied>
{converters_xml}
</ConvertersApplied>
</AnyLogicWorkspace>
"""
        return xml.encode("utf-8")

    def build_from_template(self, template_name: str, params: Optional[dict] = None) -> bytes:
        """Build from a named SD template (``predator_prey``, etc.)."""
        definition = build_template(template_name, params or {})
        return self.build_model(definition)
