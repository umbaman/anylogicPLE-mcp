"""Main MCP Server for AnyLogic Cloud API with PLE compliance."""

import asyncio
import os
import json
import uuid
from pathlib import Path
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from pydantic import ValidationError

from .ple_validator import PLEValidator, ModelSimplifier, PLELimits
from .model_builder import AnyLogicModelBuilder, ModelDefinition
from .sd_builder import SDModelBuilder
from .sd_schema import SDModelDefinition, SDSchemaError, format_issue
from .sd_validator import SDValidator
from .sd_templates import build_template
from .cloud_client import AnyLogicCloudClient


# Initialize components
validator = PLEValidator()
simplifier = ModelSimplifier(validator)
builder = AnyLogicModelBuilder()
sd_builder = SDModelBuilder()
sd_validator = SDValidator()

# In-memory model store (keyed by UUID, valid for the lifetime of the server process)
models_store = {}

# Create MCP server
app = Server("anylogic-mcp-server")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="anylogic_create_model_ple",
            description=(
                "Create an AnyLogic simulation model that complies with PLE (Personal Learning Edition) limits. "
                "The model will be validated against PLE restrictions: max 10 agent types, "
                "max 200 blocks per agent, max 50,000 dynamic agents. "
                "Use this to create models that can be downloaded and run in free AnyLogic PLE."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the simulation model"
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what the model simulates"
                    },
                    "model_type": {
                        "type": "string",
                        "enum": ["simple_queue", "factory", "warehouse", "hospital", "custom"],
                        "description": "Type of model to create (uses pre-built templates)",
                        "default": "custom"
                    },
                    "template_params": {
                        "type": "object",
                        "description": "Parameters for template models (e.g., num_docks, arrival_rate)",
                        "properties": {
                            "arrival_rate": {"type": "string"},
                            "service_time": {"type": "string"},
                            "num_servers": {"type": "integer"},
                            "num_docks": {"type": "integer"},
                            "queue_capacity": {"type": "string"},
                            "duration": {"type": "number"}
                        }
                    },
                    "agent_types": {
                        "type": "array",
                        "description": "Custom agent types (for 'custom' model_type)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "blocks": {
                                    "type": "array",
                                    "description": (
                                        "Supported block types: Source, Delay, Sink, Queue. "
                                        "Source params: interarrivalTime (e.g. 'exponential(1.0/10.0)'). "
                                        "Delay params: capacity (e.g. '2'), delayTime (e.g. 'triangular(5,10,15)'). "
                                        "Queue and Sink need no params. "
                                        "A Queue is auto-inserted before each Delay."
                                    ),
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "type": {"type": "string"},
                                            "name": {"type": "string"},
                                            "params": {"type": "object"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "auto_simplify": {
                        "type": "boolean",
                        "description": "Automatically simplify model if it exceeds PLE limits",
                        "default": True
                    }
                },
                "required": ["name", "description"]
            }
        ),
        Tool(
            name="anylogic_validate_ple",
            description=(
                "Check if a model definition complies with AnyLogic PLE (Personal Learning Edition) limits. "
                "Returns detailed information about limit usage and any violations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model_id": {
                        "type": "string",
                        "description": "ID of the model to validate"
                    }
                },
                "required": ["model_id"]
            }
        ),
        Tool(
            name="anylogic_upload_to_cloud",
            description=(
                "Upload a PLE-compliant model to AnyLogic Cloud. "
                "Requires ANYLOGIC_API_KEY to be set. "
                "The model will be available for running simulations in the cloud, "
                "and source files can be downloaded for use in local AnyLogic PLE."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model_id": {
                        "type": "string",
                        "description": "ID of the model to upload"
                    },
                    "enable_source_download": {
                        "type": "boolean",
                        "description": "Allow downloading model source files (.alp)",
                        "default": True
                    },
                    "make_public": {
                        "type": "boolean",
                        "description": "Make model publicly accessible",
                        "default": False
                    }
                },
                "required": ["model_id"]
            }
        ),
        Tool(
            name="anylogic_download_for_ple",
            description=(
                "Get download information for running model in AnyLogic PLE locally. "
                "Returns the model file and instructions for opening in free AnyLogic PLE software."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model_id": {
                        "type": "string",
                        "description": "Local model ID (before upload) or cloud model ID (after upload)"
                    }
                },
                "required": ["model_id"]
            }
        ),
        Tool(
            name="anylogic_get_ple_limits",
            description=(
                "Get information about AnyLogic PLE (Personal Learning Edition) limitations. "
                "Useful for understanding what restrictions apply when creating models."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="anylogic_get_sd_schema",
            description=(
                "Return the JSON Schema and usage notes for System Dynamics model definitions. "
                "Use before anylogic_create_sd_model_ple to understand the explicit schema "
                "(stocks, flows, auxiliaries, parameters with optional ui_control='slider', "
                "table_functions, links, charts).\n\n"
                "Example follow-up payload for anylogic_create_sd_model_ple:\n"
                "{\n"
                '  "name": "Inventory",\n'
                '  "description": "Simple stock-flow",\n'
                '  "sd_model": {\n'
                '    "time_unit": "Month",\n'
                '    "duration": 60,\n'
                '    "parameters": [\n'
                '      {"name": "restockRate", "default": "50", '
                '"slider_min": 0, "slider_max": 100, "ui_control": "slider"}\n'
                "    ],\n"
                '    "stocks": [{"name": "Inventory", "initial_value": "200"}],\n'
                '    "flows": [\n'
                '      {"name": "restocking", "formula": "restockRate", "target": "Inventory"}\n'
                "    ],\n"
                '    "links": [{"source": "restockRate", "target": "restocking"}, '
                '{"source": "restocking", "target": "Inventory"}]\n'
                "  }\n"
                "}"
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="anylogic_create_sd_model_ple",
            description=(
                "Create a PLE-compliant AnyLogic System Dynamics model from an explicit schema. "
                "Supports stocks, flows, auxiliaries, parameters (ui_control slider), "
                "table functions (sorted X, EXTRAPOLATE/CLAMP/ERROR/CUSTOM), causal links, "
                "and TimePlot charts. Max 200 SD variables "
                "(stocks+flows+auxiliaries+parameters+table_functions). "
                "Validation failures return JSON objects with error/field/suggestion. "
                "Pure SD models do not use the Process Modeling Library; PLE applies a ~5-hour "
                "wall-clock simulation guidance at 1:1 animation speed. "
                "Use template for built-in models: predator_prey, simple_stock_flow.\n\n"
                "Minimal custom example:\n"
                "{\n"
                '  "name": "Demo",\n'
                '  "description": "One stock",\n'
                '  "sd_model": {\n'
                '    "duration": 10,\n'
                '    "stocks": [{"name": "S", "initial_value": "1", "expression": "inflow"}],\n'
                '    "flows": [{"name": "inflow", "formula": "1", "target": "S"}],\n'
                '    "links": [{"source": "inflow", "target": "S"}]\n'
                "  }\n"
                "}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the simulation model"
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what the model simulates"
                    },
                    "template": {
                        "type": "string",
                        "enum": [
                            "predator_prey",
                            "simple_stock_flow"
                        ],
                        "description": "Optional built-in SD template (overrides sd_model if set)"
                    },
                    "template_params": {
                        "type": "object",
                        "description": "Optional overrides for template (e.g. duration, name)"
                    },
                    "sd_model": {
                        "type": "object",
                        "description": (
                            "Explicit System Dynamics definition. Required when template is omitted. "
                            "Fields: time_unit, duration, stocks[], flows[], auxiliaries[], "
                            "parameters[] (optional ui_control='slider', slider_min, slider_max), "
                            "table_functions[], links[], charts[]. "
                            "Call anylogic_get_sd_schema for the full JSON Schema."
                        )
                    }
                },
                "required": ["name", "description"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""

    try:
        if name == "anylogic_create_model_ple":
            return await create_model_ple(arguments)
        elif name == "anylogic_validate_ple":
            return await validate_ple(arguments)
        elif name == "anylogic_upload_to_cloud":
            return await upload_to_cloud(arguments)
        elif name == "anylogic_download_for_ple":
            return await download_for_ple(arguments)
        elif name == "anylogic_get_ple_limits":
            return await get_ple_limits(arguments)
        elif name == "anylogic_get_sd_schema":
            return await get_sd_schema(arguments)
        elif name == "anylogic_create_sd_model_ple":
            return await create_sd_model_ple(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error executing {name}: {str(e)}"
        )]


# ---------------------------------------------------------------------------
# SD helpers
# ---------------------------------------------------------------------------

def _issues_from_exception(exc: BaseException) -> list[dict[str, str]]:
    """Normalize schema/semantic failures into MCP-friendly issue dicts."""
    if isinstance(exc, SDSchemaError):
        return exc.to_dict_list()

    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if isinstance(cause, SDSchemaError):
        return cause.to_dict_list()

    if isinstance(exc, ValidationError):
        issues: list[dict[str, str]] = []
        for err in exc.errors():
            raw = (err.get("ctx") or {}).get("error")
            if isinstance(raw, SDSchemaError):
                issues.extend(raw.to_dict_list())
                continue
            if isinstance(raw, BaseException):
                nested = _issues_from_exception(raw)
                if nested and nested[0]["error"] != str(raw):
                    issues.extend(nested)
                    continue
            loc = ".".join(str(x) for x in err.get("loc", ())) or "model"
            msg = err.get("msg", str(exc))
            # Strip pydantic's "Value error, " prefix when present
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, "):]
            issues.append(
                format_issue(
                    msg,
                    loc,
                    "Fix this field and call anylogic_get_sd_schema if unsure.",
                )
            )
        return issues or [
            format_issue(str(exc), "model", "Call anylogic_get_sd_schema for schema details.")
        ]

    return [
        format_issue(
            str(exc),
            "model",
            "Call anylogic_get_sd_schema for schema details.",
        )
    ]


def _format_issues_block(title: str, issues: list[dict[str, str]]) -> str:
    lines = [title]
    for issue in issues:
        lines.append(json.dumps(issue, ensure_ascii=False))
    return "\n".join(lines)


def _build_model_bytes(model_data: dict) -> bytes:
    """Build .alp bytes for a stored model (DES or SD)."""
    model_def = model_data['definition']
    if model_data.get('binary') is not None:
        return model_data['binary']

    paradigm = model_def.get('paradigm', 'discrete_event')
    if paradigm == 'system_dynamics':
        sd_data = model_def.get('system_dynamics', {})
        sd_def = SDModelDefinition(
            name=model_def['name'],
            description=model_def['description'],
            time_unit=model_def.get('time_unit', 'Year'),
            duration=model_def.get('duration', 50),
            stocks=sd_data.get('stocks', []),
            flows=sd_data.get('flows', []),
            auxiliaries=sd_data.get('auxiliaries', []),
            parameters=sd_data.get('parameters', []),
            table_functions=sd_data.get('table_functions', []),
            links=sd_data.get('links', []),
            charts=sd_data.get('charts'),
        )
        return sd_builder.build_model(sd_def)

    if model_data['type'] == 'custom':
        definition = ModelDefinition(
            name=model_def['name'],
            description=model_def['description'],
            agent_types=model_def.get('agent_types', []),
            duration=model_def.get('duration', 480),
        )
        return builder.build_model(definition)

    if model_data['type'] in (
        'predator_prey', 'simple_stock_flow'
    ):
        return sd_builder.build_from_template(model_data['type'], model_def)

    return builder.build_from_template(model_data['type'], model_def)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def create_model_ple(args: dict) -> list[TextContent]:
    """Create a PLE-compliant model."""

    model_type = args.get('model_type', 'custom')
    model_name = args['name']
    model_desc = args['description']

    model_id = str(uuid.uuid4())

    if model_type == 'custom':
        model_def = {
            'id': model_id,
            'name': model_name,
            'description': model_desc,
            'agent_types': args.get('agent_types', []),
            'uses_process_library': True,
            'duration': args.get('template_params', {}).get('duration', 480),
            'duration_hours': args.get('template_params', {}).get('duration', 480) / 60
        }
    else:
        template_params = args.get('template_params', {})
        template_params['name'] = model_name
        template_params['description'] = model_desc

        model_bytes = builder.build_from_template(model_type, template_params)

        # Reflect the actual expanded block list for validation
        # (_build_flow auto-injects a Queue before each Delay)
        if model_type == 'simple_queue':
            agent_types = [{'name': 'Customer', 'blocks': [
                {'type': 'Source'}, {'type': 'Queue'}, {'type': 'Delay'}, {'type': 'Sink'}
            ]}]
        elif model_type == 'factory':
            agent_types = [{'name': 'Part', 'blocks': [
                {'type': 'Source'}, {'type': 'Queue'}, {'type': 'Delay'},
                {'type': 'Queue'}, {'type': 'Delay'}, {'type': 'Sink'}
            ]}]
        elif model_type == 'warehouse':
            agent_types = [{'name': 'Truck', 'blocks': [
                {'type': 'Source'}, {'type': 'Queue'}, {'type': 'Delay'}, {'type': 'Sink'}
            ]}]
        elif model_type == 'hospital':
            agent_types = [{'name': 'Patient', 'blocks': [
                {'type': 'Source'}, {'type': 'Queue'}, {'type': 'Delay'},
                {'type': 'Queue'}, {'type': 'Delay'}, {'type': 'Sink'}
            ]}]
        else:
            agent_types = []

        model_def = {
            'id': model_id,
            'name': model_name,
            'description': model_desc,
            'agent_types': agent_types,
            'uses_process_library': True,
            'duration': template_params.get('duration', 480),
            'duration_hours': template_params.get('duration', 480) / 60
        }

        models_store[model_id] = {
            'definition': model_def,
            'binary': model_bytes,
            'type': model_type
        }

    # Validate against PLE limits
    validation = validator.validate_model(model_def)

    simplified = False
    simplifications = []

    if not validation.is_valid and args.get('auto_simplify', True):
        model_def, simplifications = simplifier.simplify_to_ple_compliance(model_def)
        validation = validator.validate_model(model_def)
        simplified = True

    if model_id not in models_store:
        models_store[model_id] = {
            'definition': model_def,
            'binary': None,
            'type': model_type
        }

    response_text = f"""Model Created: {model_name}
{'=' * 60}

Model ID: {model_id}
Type: {model_type}

PLE Compliance: {'✓ PASSED' if validation.is_valid else '✗ FAILED'}

Limits Usage:
"""

    for key, value in validation.usage.items():
        response_text += f"  • {key.replace('_', ' ').title()}: {value}\n"

    if validation.errors:
        response_text += "\n❌ Errors:\n"
        for error in validation.errors:
            response_text += f"  • {error}\n"

    if validation.warnings:
        response_text += "\n⚠️  Warnings:\n"
        for warning in validation.warnings:
            response_text += f"  • {warning}\n"

    if simplified:
        response_text += f"\n🔧 Auto-Simplified: Yes\n"
        response_text += "Simplifications made:\n"
        for change in simplifications:
            response_text += f"  • {change}\n"

    if not validation.is_valid:
        suggestions = validator.suggest_simplifications(model_def)
        if suggestions:
            response_text += "\n💡 Suggestions:\n"
            for suggestion in suggestions:
                response_text += f"{suggestion}\n\n"

    if validation.is_valid:
        response_text += "\n✅ This model is ready to use with AnyLogic PLE!\n"
        response_text += f"\nNext steps:\n"
        response_text += f"  1. Upload to cloud: anylogic_upload_to_cloud(model_id='{model_id}')\n"
        response_text += f"  2. Download for PLE: anylogic_download_for_ple(model_id='{model_id}')\n"

    return [TextContent(type="text", text=response_text)]


async def validate_ple(args: dict) -> list[TextContent]:
    """Validate model against PLE limits."""
    model_id = args['model_id']

    if model_id not in models_store:
        return [TextContent(
            type="text",
            text=f"Model not found: {model_id}\n\nAvailable models: {list(models_store.keys())}"
        )]

    model_def = models_store[model_id]['definition']
    validation = validator.validate_model(model_def)

    response_text = f"""PLE Validation Results
{'=' * 60}

Model: {model_def['name']}
Compliance: {'✓ PASSED' if validation.is_valid else '✗ FAILED'}

Limits Usage:
"""

    for key, value in validation.usage.items():
        response_text += f"  • {key.replace('_', ' ').title()}: {value}\n"

    if validation.errors:
        response_text += "\n❌ Errors:\n"
        for error in validation.errors:
            response_text += f"  • {error}\n"

    if validation.warnings:
        response_text += "\n⚠️  Warnings:\n"
        for warning in validation.warnings:
            response_text += f"  • {warning}\n"

    return [TextContent(type="text", text=response_text)]


async def upload_to_cloud(args: dict) -> list[TextContent]:
    """Upload model to AnyLogic Cloud."""
    model_id = args['model_id']

    if model_id not in models_store:
        return [TextContent(
            type="text",
            text=f"Model not found: {model_id}"
        )]

    api_key = os.getenv('ANYLOGIC_API_KEY')
    if not api_key or api_key == 'your_api_key_here':
        return [TextContent(
            type="text",
            text="""❌ AnyLogic Cloud API Key Not Configured

To upload models to AnyLogic Cloud:

1. Get an API key from: https://cloud.anylogic.com/settings/api-keys

2. Add it to the "env" block in your .mcp.json:
   {
     "mcpServers": {
       "anylogic": {
         "command": "...",
         "args": [],
         "env": {
           "ALP_OUTPUT_DIR": "...",
           "ANYLOGIC_API_KEY": "your_actual_key"
         }
       }
     }
   }

3. Reload VS Code (Ctrl+Shift+P > Developer: Reload Window)

For now, use anylogic_download_for_ple to get the .alp file without uploading to cloud.
"""
        )]

    model_data = models_store[model_id]
    model_def = model_data['definition']

    if model_data['binary'] is None:
        model_bytes = _build_model_bytes(model_data)
        models_store[model_id]['binary'] = model_bytes
    else:
        model_bytes = model_data['binary']

    try:
        async with AnyLogicCloudClient() as client:
            result = await client.upload_model(
                model_name=model_def['name'],
                model_data=model_bytes,
                enable_source_download=args.get('enable_source_download', True),
                make_public=args.get('make_public', False)
            )

        cloud_model_id = result.get('id', 'unknown')
        cloud_url = result.get('url', 'https://cloud.anylogic.com')

        models_store[model_id]['cloud_id'] = cloud_model_id

        response_text = f"""✅ Model Uploaded Successfully!
{'=' * 60}

Model: {model_def['name']}
Cloud Model ID: {cloud_model_id}

🌐 Cloud URL: {cloud_url}
📥 Download available: {'Yes' if args.get('enable_source_download', True) else 'No'}

Next Steps:
  1. View in cloud: {cloud_url}
  2. Download for PLE: anylogic_download_for_ple(model_id='{model_id}')
  3. Run simulations in cloud or locally in AnyLogic PLE
"""

        return [TextContent(type="text", text=response_text)]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"❌ Upload failed: {str(e)}\n\nPlease check your API key and network connection."
        )]


async def download_for_ple(args: dict) -> list[TextContent]:
    """Get download information for PLE."""
    model_id = args['model_id']

    if model_id not in models_store:
        return [TextContent(
            type="text",
            text=f"Model not found: {model_id}"
        )]

    model_data = models_store[model_id]
    model_def = model_data['definition']

    if model_data['binary'] is None:
        model_bytes = _build_model_bytes(model_data)
        models_store[model_id]['binary'] = model_bytes
    else:
        model_bytes = model_data['binary']

    # Save to file — ALP_OUTPUT_DIR env var controls destination, falls back to home directory
    output_dir = Path(os.getenv('ALP_OUTPUT_DIR', Path.home()))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{model_def['name'].replace(' ', '_')}.alp"
    with open(output_path, 'wb') as f:
        f.write(model_bytes)

    file_size_kb = len(model_bytes) / 1024

    response_text = f"""📦 Model Ready for AnyLogic PLE
{'=' * 60}

Model: {model_def['name']}
File: {str(output_path)}
Size: {file_size_kb:.1f} KB

✅ This model is PLE-compliant and ready to use!

📥 How to Use:

1. Download AnyLogic PLE (free):
   https://www.anylogic.com/downloads/personal-learning-edition-download/

2. Install AnyLogic PLE (takes ~15 minutes)

3. Open the .alp file in AnyLogic PLE:
   File → Open → Select {str(output_path)}

4. Click the green "Run" button to see your simulation!

💡 Features Available in PLE:
  • Full visualization
  • Interactive controls (play, pause, speed up)
  • Statistics and charts
  • Modify and re-run the model
  • Export results

🎯 Your Model Stats:
"""

    validation = validator.validate_model(model_def)
    for key, value in validation.usage.items():
        response_text += f"  • {key.replace('_', ' ').title()}: {value}\n"

    return [TextContent(type="text", text=response_text)]


async def get_ple_limits(args: dict) -> list[TextContent]:
    """Get PLE limits information."""
    from .ple_validator import PLELimits

    limits_info = f"""AnyLogic Personal Learning Edition (PLE) - Limitations
{'=' * 60}

📊 Model Size Restrictions:
  • Maximum agent types: {PLELimits.MAX_AGENT_TYPES}
  • Maximum blocks per agent: {PLELimits.MAX_BLOCKS_PER_AGENT}
  • Maximum system dynamics variables: {PLELimits.MAX_SYSTEM_DYNAMICS_VARS}
  • Maximum dynamically created agents: {PLELimits.MAX_DYNAMIC_AGENTS:,}
  • Maximum simulation time: {PLELimits.MAX_SIMULATION_TIME_HOURS} hours
    (No limit when using Process Modeling Library)

🔧 Optimization Restrictions (OptQuest):
  • Maximum iterations: {PLELimits.MAX_OPTQUEST_ITERATIONS}
  • Maximum decision variables: {PLELimits.MAX_OPTQUEST_VARIABLES}

📜 Usage Restrictions:
  • For educational and personal learning only
  • Cannot be used for commercial modeling work
  • Cannot be used for paid research projects
  • Models created in PLE can be opened in commercial versions

💡 Tips for Working Within PLE Limits:

1. Reduce Agent Types:
   ✓ Use collections instead of separate agent types
   ✓ Combine similar agents (e.g., Worker1 + Worker2 → Worker)
   ✓ Use resource pools for identical entities

2. Reduce Blocks Per Agent:
   ✓ Aggregate sequential processes
   ✓ Move complex logic to embedded agents
   ✓ Use custom Java code instead of many blocks

3. Reduce Dynamic Agents:
   ✓ Use representative sampling (simulate 1/10th of real entities)
   ✓ Adjust arrival rates and simulation duration
   ✓ Use continuous flows instead of discrete entities

4. Remove Time Limit:
   ✓ Always use Process Modeling Library
   ✓ This removes the 5-hour simulation limit

🎓 Getting AnyLogic PLE:
   Download: https://www.anylogic.com/downloads/personal-learning-edition-download/
   Requirements: Windows/Mac/Linux, 4GB RAM, any GPU
   Installation: ~15 minutes
   License: Free forever

🚀 Upgrading from PLE:
   If you need commercial use or exceed PLE limits:
   • AnyLogic Professional: ~$5,000/year
   • AnyLogic University: Discounted for academics
   • Models created in PLE can be opened in commercial versions
"""

    return [TextContent(type="text", text=limits_info)]


async def get_sd_schema(args: dict) -> list[TextContent]:
    """Return JSON Schema for System Dynamics model definitions."""
    schema = SDModelDefinition.model_json_schema()
    notes = """
System Dynamics schema usage
============================

Required top-level fields when not using a template:
  name, description, time_unit, duration, stocks, flows, links

Variable types:
  stocks[]       - {name, initial_value (numeric literal), expression?}
  flows[]        - {name, formula, source?, target?}  (omit source/target for cloud)
  auxiliaries[]  - {name, formula}
  parameters[]   - {name, default, label?, slider_min?, slider_max?, ui_control?}
                   ui_control: "slider" emits <Control Type="Slider"> linked via <Link>
                   default must lie in [slider_min, slider_max] when range is set
  table_functions[] - {name, points[{x,y}] (sorted unique X), interpolation?, out_of_range?}
                   out_of_range: ERROR | EXTRAPOLATE | CUSTOM | CLAMP
  links[]        - {source, target}  (endpoints must exist; algebraic cycles rejected)
  charts[]       - {title, series[{title, expression, color?}]}  (series Expression2 must exist)

Validations:
  - Java-safe names [a-zA-Z_][a-zA-Z0-9_]*
  - Duplicate names rejected
  - Formula identifiers must reference declared variables
  - Unused auxiliaries produce warnings
  - Variable count = stocks+flows+auxiliaries+parameters+table_functions (max 200)

Templates (pass as template=):
  predator_prey, simple_stock_flow

Example (custom with slider):
{
  "name": "Inventory",
  "description": "Stock with restock slider",
  "sd_model": {
    "time_unit": "Month",
    "duration": 60,
    "parameters": [
      {"name": "restockRate", "default": "50", "slider_min": 0, "slider_max": 100, "ui_control": "slider"}
    ],
    "stocks": [{"name": "Inventory", "initial_value": "200"}],
    "flows": [{"name": "restocking", "formula": "restockRate", "target": "Inventory"}],
    "links": [
      {"source": "restockRate", "target": "restocking"},
      {"source": "restocking", "target": "Inventory"}
    ]
  }
}

Workflow:
  1. anylogic_get_sd_schema  (this tool)
  2. anylogic_create_sd_model_ple
  3. anylogic_download_for_ple(model_id=...)
"""
    response = json.dumps(schema, indent=2) + notes
    return [TextContent(type="text", text=response)]


async def create_sd_model_ple(args: dict) -> list[TextContent]:
    """Create a PLE-compliant System Dynamics model."""
    model_name = args['name']
    model_desc = args['description']
    model_id = str(uuid.uuid4())
    template = args.get('template')
    template_params = args.get('template_params', {})
    template_params['name'] = model_name
    template_params['description'] = model_desc

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    try:
        if template:
            sd_def = build_template(template, template_params)
            model_type = template
        else:
            sd_payload = args.get('sd_model')
            if not sd_payload:
                issue = format_issue(
                    "Provide either 'template' or 'sd_model'",
                    "sd_model",
                    "Call anylogic_get_sd_schema for the full schema, or set template="
                    "'predator_prey'|'simple_stock_flow'.",
                )
                return [TextContent(
                    type="text",
                    text=_format_issues_block("SD Model Creation Failed", [issue]),
                )]
            sd_payload = {**sd_payload, 'name': model_name, 'description': model_desc}
            sd_def = SDModelDefinition.model_validate(sd_payload)
            model_type = 'sd_custom'

        sd_semantic = sd_validator.validate(sd_def)
        if not sd_semantic.is_valid:
            errors.extend(sd_semantic.errors)
        warnings.extend(sd_semantic.warnings)

        model_def = sd_def.to_store_dict(model_id)

        validation = validator.validate_model(model_def)
        if not validation.is_valid:
            for err in validation.errors:
                errors.append(format_issue(err, "ple_limits", "Reduce model size to fit PLE limits."))
        for warn in validation.warnings:
            warnings.append(format_issue(warn, "ple_limits", "Consider shortening duration or simplifying."))

        if errors:
            response = f"""SD Model Creation Failed: {model_name}
{'=' * 60}

{_format_issues_block("Errors (JSON):", errors)}
"""
            if warnings:
                response += "\n" + _format_issues_block("Warnings (JSON):", warnings) + "\n"
            return [TextContent(type="text", text=response)]

        model_bytes = sd_builder.build_model(sd_def)
        models_store[model_id] = {
            'definition': model_def,
            'binary': model_bytes,
            'type': model_type,
            'paradigm': 'system_dynamics',
        }

        response_text = f"""SD Model Created: {model_name}
{'=' * 60}

Model ID: {model_id}
Paradigm: system_dynamics
Type: {model_type}
Variables: {sd_def.variable_count()}/{PLELimits.MAX_SYSTEM_DYNAMICS_VARS}
Time unit: {sd_def.time_unit}
Duration: {sd_def.duration}

PLE Compliance: PASSED

Limits Usage:
"""
        for key, value in validation.usage.items():
            response_text += f"  • {key.replace('_', ' ').title()}: {value}\n"

        if warnings:
            response_text += "\n" + _format_issues_block("Warnings (JSON):", warnings) + "\n"

        response_text += (
            f"\nThis model is ready for AnyLogic PLE.\n\nNext steps:\n"
            f"  1. Download: anylogic_download_for_ple(model_id='{model_id}')\n"
            f"  2. Open the .alp file in AnyLogic PLE 8.9.x and click Run\n"
        )
        return [TextContent(type="text", text=response_text)]

    except Exception as e:
        issues = _issues_from_exception(e)
        return [TextContent(
            type="text",
            text=(
                f"SD model validation failed: {model_name}\n"
                f"{'=' * 60}\n\n"
                f"{_format_issues_block('Errors (JSON):', issues)}\n"
            ),
        )]


async def _main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


def main():
    """Sync entry point for console_scripts."""
    asyncio.run(_main())


if __name__ == "__main__":
    main()
