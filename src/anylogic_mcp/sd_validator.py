"""Semantic validation for System Dynamics model definitions.

Performs checks beyond Pydantic field validation:

* Stock expression consistency with connected flows
* Algebraic dependency cycles among auxiliaries/flows (stocks break cycles)
* Unused auxiliary (dead code) warnings
* Missing causal-link coverage warnings
* Duration / PLE wall-clock guidance

Errors and warnings are returned as MCP-friendly dicts with
``error`` / ``field`` / ``suggestion`` keys (warnings use the same shape;
``error`` holds the warning text).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .sd_schema import (
    JAVA_KEYWORDS,
    SDModelDefinition,
    extract_formula_identifiers,
    format_issue,
)


@dataclass
class SDValidationResult:
    is_valid: bool
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def error_messages(self) -> list[str]:
        return [e["error"] for e in self.errors]

    def warning_messages(self) -> list[str]:
        return [w["error"] for w in self.warnings]


class SDValidator:
    """Additional semantic checks beyond Pydantic schema validation."""

    def validate(self, model: SDModelDefinition) -> SDValidationResult:
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []

        stock_exprs = model.stock_expressions()
        self._check_stock_flow_consistency(model, stock_exprs, errors)
        self._check_algebraic_cycles(model, errors)
        self._check_unused_auxiliaries(model, warnings)
        self._check_link_coverage(model, warnings)
        self._check_duration_warning(model, warnings)

        return SDValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _check_stock_flow_consistency(
        self,
        model: SDModelDefinition,
        stock_exprs: dict[str, str],
        errors: list[dict[str, str]],
    ) -> None:
        for stock in model.stocks:
            if not stock.expression:
                continue
            inflows = {f.name for f in model.flows if f.target == stock.name}
            outflows = {f.name for f in model.flows if f.source == stock.name}
            expr_idents = extract_formula_identifiers(stock.expression)
            flow_refs = inflows | outflows
            missing = flow_refs - expr_idents
            if missing:
                errors.append(
                    format_issue(
                        f"Stock '{stock.name}' expression does not reference connected flows: "
                        f"{sorted(missing)}",
                        f"stocks.{stock.name}.expression",
                        f"Include {sorted(missing)} in the stock net-rate expression, "
                        "or disconnect those flows.",
                    )
                )

    def _check_algebraic_cycles(
        self,
        model: SDModelDefinition,
        errors: list[dict[str, str]],
    ) -> None:
        """Detect algebraic loops among non-stock variables that can deadlock evaluation.

        Stocks are excluded as intermediate nodes because integration breaks feedback
        into ordinary differential equations rather than simultaneous equations.
        """
        stock_names = {s.name for s in model.stocks}
        nodes: set[str] = set()
        graph: dict[str, set[str]] = {}

        def add_edge(src: str, dst: str) -> None:
            if src in stock_names or dst in stock_names:
                return
            nodes.add(src)
            nodes.add(dst)
            graph.setdefault(dst, set()).add(src)

        for flow in model.flows:
            nodes.add(flow.name)
            for ref in extract_formula_identifiers(flow.formula):
                if ref in JAVA_KEYWORDS or ref == flow.name:
                    continue
                if ref in model.all_variable_names():
                    add_edge(ref, flow.name)

        for aux in model.auxiliaries:
            nodes.add(aux.name)
            for ref in extract_formula_identifiers(aux.formula):
                if ref in JAVA_KEYWORDS or ref == aux.name:
                    continue
                if ref in model.all_variable_names():
                    add_edge(ref, aux.name)

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in nodes}
        path: list[str] = []

        def dfs(node: str) -> list[str] | None:
            color[node] = GRAY
            path.append(node)
            for pred in graph.get(node, ()):
                if pred not in color:
                    continue
                if color[pred] == GRAY:
                    cycle_start = path.index(pred)
                    return path[cycle_start:] + [pred]
                if color[pred] == WHITE:
                    found = dfs(pred)
                    if found:
                        return found
            path.pop()
            color[node] = BLACK
            return None

        for n in sorted(nodes):
            if color[n] == WHITE:
                cycle = dfs(n)
                if cycle:
                    cycle_str = " -> ".join(cycle)
                    errors.append(
                        format_issue(
                            f"Algebraic dependency cycle detected: {cycle_str}",
                            "auxiliaries/flows",
                            "Break the loop by introducing a stock, delaying one equation, "
                            "or removing a circular formula reference.",
                        )
                    )
                    return

    def _check_unused_auxiliaries(
        self,
        model: SDModelDefinition,
        warnings: list[dict[str, str]],
    ) -> None:
        if not model.auxiliaries:
            return

        used: set[str] = set()
        for flow in model.flows:
            used |= extract_formula_identifiers(flow.formula)
        for aux in model.auxiliaries:
            used |= extract_formula_identifiers(aux.formula)
        for stock in model.stocks:
            if stock.expression:
                used |= extract_formula_identifiers(stock.expression)
        if model.charts:
            for chart in model.charts:
                for series in chart.series:
                    used |= extract_formula_identifiers(series.expression)

        for aux in model.auxiliaries:
            # An auxiliary is "used" if something else references it.
            referenced_elsewhere = aux.name in used and any(
                aux.name in extract_formula_identifiers(src)
                for src in [
                    *[f.formula for f in model.flows],
                    *[a.formula for a in model.auxiliaries if a.name != aux.name],
                    *[s.expression for s in model.stocks if s.expression],
                    *(
                        series.expression
                        for chart in (model.charts or [])
                        for series in chart.series
                    ),
                ]
            )
            if not referenced_elsewhere:
                warnings.append(
                    format_issue(
                        f"Auxiliary '{aux.name}' is never referenced (dead code)",
                        f"auxiliaries.{aux.name}",
                        "Reference it in a flow/auxiliary/chart, or remove it.",
                    )
                )

    def _check_link_coverage(
        self,
        model: SDModelDefinition,
        warnings: list[dict[str, str]],
    ) -> None:
        linked = {(lnk.source, lnk.target) for lnk in model.links}
        known = model.all_variable_names()

        for flow in model.flows:
            refs = extract_formula_identifiers(flow.formula) & known
            for ref in refs:
                if ref == flow.name:
                    continue
                if (ref, flow.name) not in linked and (flow.name, ref) not in linked:
                    warnings.append(
                        format_issue(
                            f"Flow '{flow.name}' uses '{ref}' but no causal link is declared "
                            f"between them",
                            f"links ({ref} -> {flow.name})",
                            f"Add LinkDef(source='{ref}', target='{flow.name}').",
                        )
                    )

        for aux in model.auxiliaries:
            refs = extract_formula_identifiers(aux.formula) & known
            for ref in refs:
                if ref == aux.name:
                    continue
                if (ref, aux.name) not in linked and (aux.name, ref) not in linked:
                    warnings.append(
                        format_issue(
                            f"Auxiliary '{aux.name}' uses '{ref}' but no causal link is declared "
                            f"between them",
                            f"links ({ref} -> {aux.name})",
                            f"Add LinkDef(source='{ref}', target='{aux.name}').",
                        )
                    )

    def _check_duration_warning(
        self,
        model: SDModelDefinition,
        warnings: list[dict[str, str]],
    ) -> None:
        hours = model._duration_hours()
        if hours > 5:
            warnings.append(
                format_issue(
                    f"Simulation duration (~{hours:.0f} wall-clock hours at 1:1 speed) may exceed "
                    "PLE's 5-hour limit for non-Process-Library models",
                    "duration",
                    "Use faster animation or shorter duration for long horizons.",
                )
            )
