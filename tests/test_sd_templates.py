"""Tests for built-in SD templates."""

import pytest

from anylogic_mcp.sd_builder import SDModelBuilder
from anylogic_mcp.sd_templates import build_template
from anylogic_mcp.sd_validator import SDValidator
from anylogic_mcp.ple_validator import PLEValidator


@pytest.fixture
def sd_builder():
    return SDModelBuilder()


class TestSDTemplates:
    @pytest.mark.parametrize("template", [
        "predator_prey",
        "simple_stock_flow",
    ])
    def test_template_validates(self, template):
        definition = build_template(template, {})
        sd_result = SDValidator().validate(definition)
        assert sd_result.is_valid, sd_result.errors

    @pytest.mark.parametrize("template", [
        "predator_prey",
        "simple_stock_flow",
    ])
    def test_template_generates_xml(self, sd_builder, template):
        definition = build_template(template, {})
        data = sd_builder.build_model(definition)
        assert len(data) > 1000

    def test_unknown_template_raises(self):
        with pytest.raises(ValueError, match="Unknown SD template"):
            build_template("nonexistent", {})

    def test_predator_prey_ple_compliant(self):
        definition = build_template("predator_prey", {})
        store = definition.to_store_dict("id")
        result = PLEValidator().validate_model(store)
        assert result.is_valid
        assert definition.variable_count() <= 200
