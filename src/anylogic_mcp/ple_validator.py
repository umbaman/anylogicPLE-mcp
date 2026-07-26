"""PLE Compliance Validator - Ensures models fit within AnyLogic PLE limits."""

from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class PLELimits:
    """AnyLogic Personal Learning Edition limitations."""

    MAX_AGENT_TYPES = 10
    MAX_BLOCKS_PER_AGENT = 200
    MAX_SYSTEM_DYNAMICS_VARS = 200
    MAX_DYNAMIC_AGENTS = 50_000
    MAX_SIMULATION_TIME_HOURS = 5  # Except for Process Modeling Library

    # Optimization limits
    MAX_OPTQUEST_ITERATIONS = 500
    MAX_OPTQUEST_VARIABLES = 7


@dataclass
class ValidationResult:
    """Result of PLE validation check."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    usage: Dict[str, str]  # Human-readable usage stats

    def to_dict(self):
        return {
            "ple_compliant": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "limits_usage": self.usage
        }


class PLEValidator:
    """Validates AnyLogic models against PLE restrictions."""

    def __init__(self):
        self.limits = PLELimits()

    def validate_model(self, model_definition: dict) -> ValidationResult:
        errors = []
        warnings = []
        usage = {}

        paradigm = model_definition.get('paradigm', 'discrete_event')

        if paradigm == 'system_dynamics':
            return self._validate_sd_model(model_definition)

        # Check agent types
        agent_types = model_definition.get('agent_types', [])
        agent_count = len(agent_types)
        usage['agent_types'] = f"{agent_count}/{self.limits.MAX_AGENT_TYPES}"

        if agent_count > self.limits.MAX_AGENT_TYPES:
            errors.append(
                f"Too many agent types: {agent_count} "
                f"(PLE limit: {self.limits.MAX_AGENT_TYPES})"
            )
        elif agent_count > self.limits.MAX_AGENT_TYPES * 0.8:
            warnings.append(
                f"Approaching agent type limit: {agent_count}/"
                f"{self.limits.MAX_AGENT_TYPES}"
            )

        # Check blocks per agent
        max_blocks = 0
        problematic_agent = None

        for agent in agent_types:
            blocks = agent.get('blocks', [])
            block_count = len(blocks)

            if block_count > max_blocks:
                max_blocks = block_count
                problematic_agent = agent.get('name')

            if block_count > self.limits.MAX_BLOCKS_PER_AGENT:
                errors.append(
                    f"Agent '{agent.get('name')}' has too many blocks: "
                    f"{block_count} (PLE limit: {self.limits.MAX_BLOCKS_PER_AGENT})"
                )

        usage['blocks_per_agent'] = f"{max_blocks}/{self.limits.MAX_BLOCKS_PER_AGENT}"

        # Check system dynamics variables
        sd_vars = model_definition.get('system_dynamics', {}).get('variables', [])
        sd_var_count = len(sd_vars)
        usage['system_dynamics_vars'] = (
            f"{sd_var_count}/{self.limits.MAX_SYSTEM_DYNAMICS_VARS}"
        )

        if sd_var_count > self.limits.MAX_SYSTEM_DYNAMICS_VARS:
            errors.append(
                f"Too many system dynamics variables: {sd_var_count} "
                f"(PLE limit: {self.limits.MAX_SYSTEM_DYNAMICS_VARS})"
            )

        # Check dynamic agents (estimated)
        estimated_dynamic = self._estimate_dynamic_agents(model_definition)
        usage['dynamic_agents'] = f"{estimated_dynamic}/{self.limits.MAX_DYNAMIC_AGENTS}"

        if estimated_dynamic > self.limits.MAX_DYNAMIC_AGENTS:
            errors.append(
                f"Estimated dynamic agents ({estimated_dynamic}) exceeds "
                f"PLE limit ({self.limits.MAX_DYNAMIC_AGENTS})"
            )

        # Check simulation duration (if not using Process Library)
        uses_process_library = model_definition.get('uses_process_library', True)
        duration_hours = model_definition.get('duration_hours', 0)

        if not uses_process_library and duration_hours > self.limits.MAX_SIMULATION_TIME_HOURS:
            errors.append(
                f"Simulation duration ({duration_hours}h) exceeds PLE limit "
                f"({self.limits.MAX_SIMULATION_TIME_HOURS}h). "
                f"Use Process Modeling Library to remove this limit."
            )

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            usage=usage
        )

    def _estimate_dynamic_agents(self, model_definition: dict) -> int:
        sources = [
            block for agent in model_definition.get('agent_types', [])
            for block in agent.get('blocks', [])
            if block.get('type') == 'Source'
        ]

        total_entities = 0
        duration = model_definition.get('duration', 480)

        for source in sources:
            arrival_rate = source.get('arrival_rate', 1)
            total_entities += int(arrival_rate * duration)

        return total_entities

    def _validate_sd_model(self, model_definition: dict) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        usage: dict[str, str] = {}

        sd = model_definition.get('system_dynamics', {})
        sd_var_count = sd.get('variable_count')
        if sd_var_count is None:
            sd_var_count = sum(
                len(sd.get(key, []))
                for key in (
                    'stocks', 'flows', 'auxiliaries', 'parameters', 'table_functions'
                )
            )

        usage['system_dynamics_vars'] = (
            f"{sd_var_count}/{self.limits.MAX_SYSTEM_DYNAMICS_VARS}"
        )
        usage['agent_types'] = f"0/{self.limits.MAX_AGENT_TYPES}"
        usage['blocks_per_agent'] = f"0/{self.limits.MAX_BLOCKS_PER_AGENT}"
        usage['dynamic_agents'] = f"0/{self.limits.MAX_DYNAMIC_AGENTS}"

        if sd_var_count > self.limits.MAX_SYSTEM_DYNAMICS_VARS:
            errors.append(
                f"Too many system dynamics variables: {sd_var_count} "
                f"(PLE limit: {self.limits.MAX_SYSTEM_DYNAMICS_VARS})"
            )
        elif sd_var_count > self.limits.MAX_SYSTEM_DYNAMICS_VARS * 0.8:
            warnings.append(
                f"Approaching system dynamics variable limit: {sd_var_count}/"
                f"{self.limits.MAX_SYSTEM_DYNAMICS_VARS}"
            )

        duration_hours = model_definition.get('duration_hours', 0)
        if duration_hours > self.limits.MAX_SIMULATION_TIME_HOURS:
            warnings.append(
                f"Simulation duration (~{duration_hours:.0f} model-time hours) may exceed "
                f"PLE's {self.limits.MAX_SIMULATION_TIME_HOURS}-hour wall-clock guidance "
                "for non-Process-Library models at 1:1 animation speed."
            )

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            usage=usage,
        )

    def suggest_simplifications(self, model_definition: dict) -> List[str]:
        suggestions = []

        agent_count = len(model_definition.get('agent_types', []))
        if agent_count > self.limits.MAX_AGENT_TYPES:
            suggestions.append(
                f"Reduce agent types from {agent_count} to {self.limits.MAX_AGENT_TYPES}:\n"
                "  - Combine similar agent types (e.g., Worker1 + Worker2 → Worker)\n"
                "  - Use collections instead of separate agent types\n"
                "  - Use resource pools for identical entities"
            )

        for agent in model_definition.get('agent_types', []):
            block_count = len(agent.get('blocks', []))
            if block_count > self.limits.MAX_BLOCKS_PER_AGENT:
                suggestions.append(
                    f"Simplify agent '{agent.get('name')}' ({block_count} blocks):\n"
                    "  - Aggregate sequential processes into single blocks\n"
                    "  - Move logic to embedded agents\n"
                    "  - Use custom code instead of multiple blocks"
                )

        return suggestions


class ModelSimplifier:
    """Automatically simplifies models to fit PLE limits."""

    def __init__(self, validator: PLEValidator):
        self.validator = validator

    def simplify_to_ple_compliance(
        self,
        model_definition: dict
    ) -> tuple[dict, List[str]]:
        changes = []
        model = model_definition.copy()

        if len(model.get('agent_types', [])) > PLELimits.MAX_AGENT_TYPES:
            model, merge_changes = self._merge_agent_types(model)
            changes.extend(merge_changes)

        for i, agent in enumerate(model.get('agent_types', [])):
            if len(agent.get('blocks', [])) > PLELimits.MAX_BLOCKS_PER_AGENT:
                model['agent_types'][i], block_changes = self._aggregate_blocks(agent)
                changes.extend(block_changes)

        estimated = self.validator._estimate_dynamic_agents(model)
        if estimated > PLELimits.MAX_DYNAMIC_AGENTS:
            model, sample_changes = self._apply_sampling(model)
            changes.extend(sample_changes)

        return model, changes

    def _merge_agent_types(self, model: dict) -> tuple[dict, List[str]]:
        changes = ["Auto-merge of agent types is not yet implemented — reduce agent types manually."]
        return model, changes

    def _aggregate_blocks(self, agent: dict) -> tuple[dict, List[str]]:
        changes = [f"Auto-aggregation of blocks for '{agent.get('name')}' is not yet implemented — simplify the block chain manually."]
        return agent, changes

    def _apply_sampling(self, model: dict) -> tuple[dict, List[str]]:
        changes = ["Auto-sampling to reduce entity count is not yet implemented — lower the arrival rate or simulation duration manually."]
        return model, changes
