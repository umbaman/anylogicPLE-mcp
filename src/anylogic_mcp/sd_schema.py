"""Pydantic schema for System Dynamics model definitions.

Defines the explicit JSON/Python contract used by ``anylogic_create_sd_model_ple``:
stocks, flows, auxiliaries, parameters (optional ``ui_control`` sliders),
table functions, causal links, and TimePlot charts.

Validation covers Java-safe names, duplicate detection, formula references,
parameter slider ranges, table-function point ordering, and PLE's 200-variable
cap (stocks + flows + auxiliaries + parameters + table functions).
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .ple_validator import PLELimits

TimeUnit = Literal["Year", "Month", "Day", "Hour", "Minute", "Second"]
OutOfRangeBehaviour = Literal["ERROR", "EXTRAPOLATE", "CUSTOM", "CLAMP"]
UiControl = Literal["slider"]

JAVA_KEYWORDS = frozenset({
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "false", "final", "finally", "float", "for", "goto", "if",
    "implements", "import", "instanceof", "int", "interface", "long", "native",
    "new", "null", "package", "private", "protected", "public", "return",
    "short", "static", "strictfp", "super", "switch", "synchronized", "this",
    "throw", "throws", "transient", "true", "try", "void", "volatile", "while",
    "Math", "max", "min", "abs", "pow", "sqrt", "exp", "log", "sin", "cos",
    "tan", "floor", "ceil", "round",
})

JAVA_SAFE_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
IDENTIFIER_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
UNSAFE_FORMULA_PATTERNS = re.compile(
    r"(;|\bnew\b|\bimport\b|\bclass\b|\bRuntime\b|\bSystem\b|\bProcess\b|\bThread\b)",
    re.IGNORECASE,
)
NUMERIC_LITERAL_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
ARGB_MIN = -(2**31)
ARGB_MAX = 2**31 - 1


def format_issue(error: str, field: str, suggestion: str) -> dict[str, str]:
    """MCP-friendly validation issue payload."""
    return {"error": error, "field": field, "suggestion": suggestion}


def issue_message(issue: dict[str, str]) -> str:
    return f"{issue['error']} [field={issue['field']}] Suggestion: {issue['suggestion']}"


class SDSchemaError(ValueError):
    """Raised when SD schema validation fails with structured issue dicts."""

    def __init__(self, issues: list[dict[str, str]]):
        if not issues:
            issues = [format_issue("Unknown schema error", "model", "Check the SD schema.")]
        self.issues = issues
        super().__init__(
            issue_message(issues[0])
            if len(issues) == 1
            else f"{len(issues)} validation errors"
        )

    def to_dict_list(self) -> list[dict[str, str]]:
        return list(self.issues)


def _raise_issue(error: str, field: str, suggestion: str) -> None:
    raise SDSchemaError([format_issue(error, field, suggestion)])


def _validate_java_name(name: str, field_label: str) -> str:
    if not JAVA_SAFE_NAME.match(name):
        _raise_issue(
            f"{field_label} '{name}' is not a valid Java identifier",
            field_label.lower().replace(" ", "_"),
            "Use pattern [a-zA-Z_][a-zA-Z0-9_]* (letters, digits, underscore; no leading digit).",
        )
    if name in JAVA_KEYWORDS:
        _raise_issue(
            f"{field_label} '{name}' conflicts with a reserved Java keyword",
            field_label.lower().replace(" ", "_"),
            f"Rename '{name}' to a non-keyword identifier (e.g. '{name}_var').",
        )
    return name


def extract_formula_identifiers(formula: str) -> set[str]:
    """Return identifier tokens referenced in a formula expression."""
    return {m.group(1) for m in IDENTIFIER_RE.finditer(formula)}


def validate_formula_safe(formula: str, context: str) -> None:
    if UNSAFE_FORMULA_PATTERNS.search(formula):
        _raise_issue(
            f"Formula for {context} contains disallowed Java constructs",
            context,
            "Use math expressions with variable names, Math.*, max(), min(), and ternaries only.",
        )


def parse_numeric_literal(value: str, field: str) -> float:
    text = value.strip()
    if not NUMERIC_LITERAL_RE.match(text):
        _raise_issue(
            f"Value '{value}' is not a numeric literal",
            field,
            "Use a plain number such as '0', '100', or '1.5' (no variable references).",
        )
    return float(text)


def is_valid_argb(color: int) -> bool:
    return ARGB_MIN <= color <= ARGB_MAX


class TablePointDef(BaseModel):
    """One (x, y) sample for a table function; both values must be numeric."""

    x: float
    y: float


class StockDef(BaseModel):
    name: str
    initial_value: str = Field(description="Numeric literal for initial stock level")
    expression: Optional[str] = Field(
        default=None,
        description="Net rate expression (inflows minus outflows). Auto-derived from flows if omitted.",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_java_name(v, "Stock")

    @field_validator("initial_value")
    @classmethod
    def validate_initial_value(cls, v: str) -> str:
        parse_numeric_literal(v, "stocks.initial_value")
        return v.strip()


class FlowDef(BaseModel):
    name: str
    formula: str
    source: Optional[str] = Field(
        default=None,
        description="Source stock name (omit for cloud inflow)",
    )
    target: Optional[str] = Field(
        default=None,
        description="Target stock name (omit for cloud outflow)",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_java_name(v, "Flow")

    @field_validator("formula")
    @classmethod
    def validate_formula(cls, v: str) -> str:
        validate_formula_safe(v, "flow")
        return v


class AuxDef(BaseModel):
    name: str
    formula: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_java_name(v, "Auxiliary")

    @field_validator("formula")
    @classmethod
    def validate_formula(cls, v: str) -> str:
        validate_formula_safe(v, "auxiliary")
        return v


class ParameterDef(BaseModel):
    """Model parameter with optional experiment slider and presentation Control.

    Set ``ui_control="slider"`` to emit a ``<Control Type="Slider">`` on the
    presentation canvas, linked via ``<Link>parameterName</Link>``. Requires
    ``slider_min`` / ``slider_max``. When only min/max are set (without
    ``ui_control``), a ``ParameterEditor`` SLIDER is still emitted on the
    parameter itself.
    """

    name: str
    default: str
    label: Optional[str] = None
    slider_min: Optional[float] = None
    slider_max: Optional[float] = None
    ui_control: Optional[UiControl] = Field(
        default=None,
        description='Optional UI control; use "slider" to generate Control Type="Slider" XML',
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_java_name(v, "Parameter")

    @field_validator("default")
    @classmethod
    def validate_default(cls, v: str) -> str:
        validate_formula_safe(v, "parameter default")
        return v

    @model_validator(mode="after")
    def validate_slider_range(self) -> ParameterDef:
        has_min = self.slider_min is not None
        has_max = self.slider_max is not None
        if has_min != has_max:
            _raise_issue(
                f"Parameter '{self.name}' must set both slider_min and slider_max together",
                f"parameters.{self.name}.slider_min",
                "Provide both slider_min and slider_max, or omit both.",
            )
        if has_min and has_max:
            assert self.slider_min is not None and self.slider_max is not None
            if not (self.slider_min < self.slider_max):
                _raise_issue(
                    f"Parameter '{self.name}' requires slider_min < slider_max "
                    f"(got {self.slider_min} and {self.slider_max})",
                    f"parameters.{self.name}.slider_min",
                    "Increase slider_max or decrease slider_min so the range is non-empty.",
                )
            default_val = parse_numeric_literal(
                self.default, f"parameters.{self.name}.default"
            )
            if not (self.slider_min <= default_val <= self.slider_max):
                _raise_issue(
                    f"Parameter '{self.name}' default {default_val} is outside "
                    f"[{self.slider_min}, {self.slider_max}]",
                    f"parameters.{self.name}.default",
                    f"Set default between {self.slider_min} and {self.slider_max}.",
                )
        if self.ui_control == "slider":
            if not has_min or not has_max:
                _raise_issue(
                    f"Parameter '{self.name}' has ui_control='slider' but missing slider range",
                    f"parameters.{self.name}.ui_control",
                    "Set slider_min and slider_max when ui_control is 'slider'.",
                )
        return self


class TableFunctionDef(BaseModel):
    """Lookup table emitted as AnyLogic ``<TableFunction>``.

    Points must be sorted ascending by ``x`` with no duplicate X values.
    ``out_of_range`` maps to ``<OutOfRangeBehaviour>`` (ERROR, EXTRAPOLATE,
    CUSTOM, CLAMP).
    """

    name: str
    points: list[TablePointDef] = Field(min_length=1)
    interpolation: Literal["LINEAR", "STEP"] = "LINEAR"
    out_of_range: OutOfRangeBehaviour = "EXTRAPOLATE"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_java_name(v, "TableFunction")

    @model_validator(mode="after")
    def validate_points(self) -> TableFunctionDef:
        xs = [p.x for p in self.points]
        for i in range(1, len(xs)):
            if xs[i] == xs[i - 1]:
                _raise_issue(
                    f"TableFunction '{self.name}' has duplicate X value {xs[i]}",
                    f"table_functions.{self.name}.points",
                    "Remove duplicate X points; each X must be unique.",
                )
            if xs[i] < xs[i - 1]:
                _raise_issue(
                    f"TableFunction '{self.name}' points are not sorted ascending by X",
                    f"table_functions.{self.name}.points",
                    f"Sort points so X increases (found {xs[i - 1]} then {xs[i]}).",
                )
        return self


class LinkDef(BaseModel):
    """Causal link emitted as ``<Link SourceId="..." TargetId="...">``."""

    source: str
    target: str

    @field_validator("source", "target")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        return _validate_java_name(v, "Link endpoint")


class ChartSeriesDef(BaseModel):
    """One TimePlot series; ``expression`` becomes ``<Expression2>``."""

    title: str
    expression: str
    color: Optional[int] = Field(
        default=None,
        description="Optional ARGB signed 32-bit color for the series line",
    )

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if not is_valid_argb(v):
            _raise_issue(
                f"Chart series color {v} is not a valid ARGB signed 32-bit int",
                "charts.series.color",
                f"Use an int in [{ARGB_MIN}, {ARGB_MAX}] (AnyLogic style, e.g. -16776961).",
            )
        return v


class ChartDef(BaseModel):
    """TimePlot chart; requires at least one series."""

    title: str = "Time Plot"
    series: list[ChartSeriesDef] = Field(min_length=1)


class SDModelDefinition(BaseModel):
    """Explicit System Dynamics model contract for AnyLogic .alp generation."""

    name: str
    description: str
    time_unit: TimeUnit = "Year"
    duration: float = Field(gt=0, description="Simulation stop time in model time units")
    stocks: list[StockDef] = Field(default_factory=list)
    flows: list[FlowDef] = Field(default_factory=list)
    auxiliaries: list[AuxDef] = Field(default_factory=list)
    parameters: list[ParameterDef] = Field(default_factory=list)
    table_functions: list[TableFunctionDef] = Field(default_factory=list)
    links: list[LinkDef] = Field(default_factory=list)
    charts: Optional[list[ChartDef]] = None

    @model_validator(mode="after")
    def validate_model(self) -> SDModelDefinition:
        self._check_unique_names()
        self._check_stock_flow_refs()
        self._check_link_endpoints()
        self._check_formula_refs()
        self._check_chart_series()
        self._check_ple_variable_limit()
        return self

    def all_variable_names(self) -> set[str]:
        names: set[str] = set()
        for coll in (self.stocks, self.flows, self.auxiliaries, self.parameters):
            for item in coll:
                names.add(item.name)
        for tf in self.table_functions:
            names.add(tf.name)
        return names

    def variable_count(self) -> int:
        """PLE SD variable count: stocks + flows + auxiliaries + parameters + table functions."""
        return (
            len(self.stocks)
            + len(self.flows)
            + len(self.auxiliaries)
            + len(self.parameters)
            + len(self.table_functions)
        )

    def stock_expressions(self) -> dict[str, str]:
        """Resolved net-rate expression per stock."""
        result: dict[str, str] = {}
        for stock in self.stocks:
            if stock.expression:
                result[stock.name] = stock.expression
                continue
            inflows = [f.name for f in self.flows if f.target == stock.name]
            outflows = [f.name for f in self.flows if f.source == stock.name]
            if not inflows and not outflows:
                _raise_issue(
                    f"Stock '{stock.name}' has no expression and no connected flows",
                    f"stocks.{stock.name}",
                    "Add inflow/outflow connections or set an explicit expression.",
                )
            terms: list[str] = []
            terms.extend(inflows)
            for out in outflows:
                terms.append(f"-{out}" if not out.startswith("-") else out)
            result[stock.name] = " + ".join(terms) if terms else "0"
        return result

    def to_store_dict(self, model_id: str) -> dict[str, Any]:
        return {
            "id": model_id,
            "name": self.name,
            "description": self.description,
            "paradigm": "system_dynamics",
            "uses_process_library": False,
            "time_unit": self.time_unit,
            "duration": self.duration,
            "duration_hours": self._duration_hours(),
            "system_dynamics": {
                "stocks": [s.model_dump() for s in self.stocks],
                "flows": [f.model_dump() for f in self.flows],
                "auxiliaries": [a.model_dump() for a in self.auxiliaries],
                "parameters": [p.model_dump() for p in self.parameters],
                "table_functions": [t.model_dump() for t in self.table_functions],
                "links": [lnk.model_dump() for lnk in self.links],
                "charts": [c.model_dump() for c in self.charts] if self.charts else None,
                "variable_count": self.variable_count(),
            },
        }

    def _duration_hours(self) -> float:
        unit_hours = {
            "Second": 1 / 3600,
            "Minute": 1 / 60,
            "Hour": 1,
            "Day": 24,
            "Month": 24 * 30,
            "Year": 24 * 365,
        }
        return self.duration * unit_hours[self.time_unit]

    def _check_unique_names(self) -> None:
        seen: dict[str, str] = {}
        for kind, items in (
            ("stock", self.stocks),
            ("flow", self.flows),
            ("auxiliary", self.auxiliaries),
            ("parameter", self.parameters),
            ("table_function", self.table_functions),
        ):
            for item in items:
                if item.name in seen:
                    _raise_issue(
                        f"Duplicate name '{item.name}' used as both {seen[item.name]} and {kind}",
                        f"{kind}s.{item.name}",
                        f"Rename one of the '{item.name}' declarations so every name is unique.",
                    )
                seen[item.name] = kind

    def _check_stock_flow_refs(self) -> None:
        stock_names = {s.name for s in self.stocks}
        for flow in self.flows:
            if flow.source and flow.source not in stock_names:
                available = sorted(stock_names) or ["(none)"]
                _raise_issue(
                    f"Flow '{flow.name}' source '{flow.source}' is not a defined stock",
                    f"flows.{flow.name}.source",
                    f"Available stocks: {available}",
                )
            if flow.target and flow.target not in stock_names:
                available = sorted(stock_names) or ["(none)"]
                _raise_issue(
                    f"Flow '{flow.name}' target '{flow.target}' is not a defined stock",
                    f"flows.{flow.name}.target",
                    f"Available stocks: {available}",
                )
            if not flow.source and not flow.target:
                _raise_issue(
                    f"Flow '{flow.name}' must have at least one of source or target",
                    f"flows.{flow.name}",
                    "Set source and/or target to a defined stock name.",
                )

    def _check_link_endpoints(self) -> None:
        known = self.all_variable_names()
        available = sorted(known) or ["(none)"]
        for link in self.links:
            if link.source not in known:
                _raise_issue(
                    f"Link source '{link.source}' is not a defined variable",
                    "links.source",
                    f"Available: {available}",
                )
            if link.target not in known:
                _raise_issue(
                    f"Link target '{link.target}' is not a defined variable",
                    "links.target",
                    f"Available: {available}",
                )

    def _check_formula_refs(self) -> None:
        known = self.all_variable_names()
        for flow in self.flows:
            self._check_formula_identifiers(flow.formula, flow.name, known)
        for aux in self.auxiliaries:
            self._check_formula_identifiers(aux.formula, aux.name, known, allow_self=False)
        for stock in self.stocks:
            expr = stock.expression or ""
            if expr:
                self._check_formula_identifiers(expr, stock.name, known, allow_self=False)
        for param in self.parameters:
            self._check_formula_identifiers(param.default, param.name, known, allow_self=False)

    def _check_chart_series(self) -> None:
        if not self.charts:
            return
        known = self.all_variable_names()
        available = sorted(known) or ["(none)"]
        for ci, chart in enumerate(self.charts):
            if not chart.series:
                _raise_issue(
                    f"Chart '{chart.title}' must have at least 1 series",
                    f"charts[{ci}].series",
                    "Add at least one series with title and expression.",
                )
            for si, series in enumerate(chart.series):
                refs = extract_formula_identifiers(series.expression)
                for ident in refs:
                    if ident in JAVA_KEYWORDS:
                        continue
                    if ident not in known:
                        _raise_issue(
                            f"Chart series Expression2 references unknown variable '{ident}'",
                            f"charts[{ci}].series[{si}].expression",
                            f"Variable '{ident}' not found. Available: {available}",
                        )

    def _check_formula_identifiers(
        self,
        formula: str,
        owner: str,
        known: set[str],
        allow_self: bool = True,
    ) -> None:
        available = sorted(known) or ["(none)"]
        for ident in extract_formula_identifiers(formula):
            if ident in JAVA_KEYWORDS:
                continue
            if not allow_self and ident == owner:
                continue
            if ident not in known:
                _raise_issue(
                    f"Variable '{ident}' not found in formula for '{owner}'",
                    owner,
                    f"Variable '{ident}' not found. Available: {available}",
                )

    def _check_ple_variable_limit(self) -> None:
        count = self.variable_count()
        if count > PLELimits.MAX_SYSTEM_DYNAMICS_VARS:
            _raise_issue(
                f"Too many system dynamics variables: {count} "
                f"(PLE limit: {PLELimits.MAX_SYSTEM_DYNAMICS_VARS})",
                "variable_count",
                "Reduce stocks, flows, auxiliaries, parameters, or table functions.",
            )
