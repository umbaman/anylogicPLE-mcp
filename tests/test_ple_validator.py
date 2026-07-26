"""Basic tests for AnyLogic MCP Server."""

import pytest
from anylogic_mcp.ple_validator import PLEValidator, PLELimits


def test_ple_limits_constants():
    """Test that PLE limits are defined correctly."""
    assert PLELimits.MAX_AGENT_TYPES == 10
    assert PLELimits.MAX_BLOCKS_PER_AGENT == 200
    assert PLELimits.MAX_SYSTEM_DYNAMICS_VARS == 200
    assert PLELimits.MAX_DYNAMIC_AGENTS == 50_000
    assert PLELimits.MAX_SIMULATION_TIME_HOURS == 5


def test_validator_accepts_compliant_model():
    """Test that a PLE-compliant model passes validation."""
    validator = PLEValidator()

    model = {
        'agent_types': [
            {
                'name': 'Customer',
                'blocks': [
                    {'type': 'Source'},
                    {'type': 'Queue'},
                    {'type': 'Delay'},
                    {'type': 'Sink'}
                ]
            }
        ],
        'duration': 480,
        'duration_hours': 8,
        'uses_process_library': True
    }

    result = validator.validate_model(model)

    assert result.is_valid
    assert len(result.errors) == 0


def test_validator_rejects_too_many_agent_types():
    """Test that validator rejects models with too many agent types."""
    validator = PLEValidator()

    # Create 11 agent types (exceeds limit of 10)
    agent_types = [
        {'name': f'Agent{i}', 'blocks': []}
        for i in range(11)
    ]

    model = {
        'agent_types': agent_types,
        'duration': 480,
        'duration_hours': 8,
        'uses_process_library': True
    }

    result = validator.validate_model(model)

    assert not result.is_valid
    assert len(result.errors) > 0
    assert any('agent types' in error.lower() for error in result.errors)


def test_validator_rejects_too_many_blocks():
    """Test that validator rejects agents with too many blocks."""
    validator = PLEValidator()

    # Create an agent with 201 blocks (exceeds limit of 200)
    blocks = [{'type': 'Queue'} for _ in range(201)]

    model = {
        'agent_types': [
            {'name': 'OverloadedAgent', 'blocks': blocks}
        ],
        'duration': 480,
        'duration_hours': 8,
        'uses_process_library': True
    }

    result = validator.validate_model(model)

    assert not result.is_valid
    assert len(result.errors) > 0
    assert any('blocks' in error.lower() for error in result.errors)


def test_validator_usage_stats():
    """Test that validator provides usage statistics."""
    validator = PLEValidator()

    model = {
        'agent_types': [
            {'name': 'Customer', 'blocks': [{'type': 'Source'}]},
            {'name': 'Server', 'blocks': [{'type': 'Service'}]}
        ],
        'duration': 480,
        'duration_hours': 8,
        'uses_process_library': True
    }

    result = validator.validate_model(model)

    assert 'agent_types' in result.usage
    assert 'blocks_per_agent' in result.usage
    assert '2/10' in result.usage['agent_types']


def test_validator_sd_model():
    """Test PLE validation for system dynamics models."""
    validator = PLEValidator()

    model = {
        'paradigm': 'system_dynamics',
        'uses_process_library': False,
        'duration': 50,
        'duration_hours': 50 * 24 * 365,
        'system_dynamics': {
            'variable_count': 25,
            'stocks': [],
            'flows': [],
        },
    }

    result = validator.validate_model(model)
    assert result.is_valid
    assert '25/200' in result.usage['system_dynamics_vars']


def test_validator_rejects_too_many_sd_vars():
    """Test that validator rejects SD models exceeding variable limit."""
    validator = PLEValidator()

    model = {
        'paradigm': 'system_dynamics',
        'uses_process_library': False,
        'system_dynamics': {'variable_count': 201},
    }

    result = validator.validate_model(model)
    assert not result.is_valid
    assert any('system dynamics variables' in e.lower() for e in result.errors)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
