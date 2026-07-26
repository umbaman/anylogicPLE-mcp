# anylogicPLE-mcp

**MCP server that generates AnyLogic simulation models from natural-language prompts in Claude Code.**

Describe a queueing system, factory, or ER in plain language → get a `.alp` file that opens and runs in [AnyLogic PLE](https://www.anylogic.com/downloads/personal-learning-edition-download/) (the free edition). Models are validated automatically against PLE limits.

The goal of this project is to shorten the AnyLogic learning curve by giving you a working simulation model as a starting point. Run the simulation, observe the results, study how the model is built, and use it as a reference when building your next model from scratch.

Unlike most tools that focus on a single modeling approach, AnyLogic supports three paradigms in one environment — discrete event, agent-based, and system dynamics — covering virtually any industrial engineering problem you can think of, from factory floors to hospital ERs to supply chains. On top of that, the free PLE edition makes it accessible to anyone learning simulation, and the block-based Process Modeling Library maps naturally to code generation.

> **Disclaimer:** This project is not affiliated with or endorsed by AnyLogic. AnyLogic is a trademark of The AnyLogic Company. Generated models are subject to AnyLogic PLE's terms of use.

---

## Who is this for

If you are an industrial engineer, this tool lets you prototype a queuing or process model in natural language and have something running within minutes — skipping the initial friction of block wiring and XML quirks, and getting straight to the questions that matter: utilization rates, bottlenecks, throughput.

The current version handles **discrete event / queueing models** and **system dynamics models** (stocks, flows, auxiliaries, parameters with optional `ui_control` sliders, table functions with ordered points / out-of-range behaviour, causal links with cycle detection, TimePlot charts). Resource-constrained DES models (shift schedules, breakdowns, Seize/Release blocks) are not yet supported — that is where contributions are most welcome.

---

## What it looks like

You type this in Claude Code:

```
Create a 3-stage CNC job shop model "CNCJobShop":
- Jobs arrive every 15 minutes (exponential)
- Roughing: 2 machines, triangular(8,12,18) min
- Semi-finish: 1 machine, triangular(8,12,16) min
- Finishing: 1 machine, triangular(5,8,12) min
Give me the .alp file.
```

Claude calls the MCP tools, builds the `.alp` XML, saves the file to your output folder, and tells you which stage is the bottleneck. Open the file in AnyLogic PLE and click **Run**.

For **System Dynamics**, use the SD tools:

```
Create a predator-prey SD model using template predator_prey.
100-year horizon. Give me the .alp file.
```

Claude calls `anylogic_create_sd_model_ple`, validates the schema, and writes a stock-flow `.alp` with TimePlot charts.

---

## Requirements

- Python 3.10+
- [Claude Code](https://claude.ai/code) (VS Code extension or CLI)
- [AnyLogic PLE 8.9.8](https://www.anylogic.com/downloads/personal-learning-edition-download/) — free, to open and run generated models

---

## Install

### 1. Install the package

```cmd
pip install -e .
```

Find the entry point path — you need it in the next step:

```cmd
where anylogic-mcp       # Windows
which anylogic-mcp       # macOS / Linux
```

### 2. Create `.mcp.json` in your working directory

Create a file named `.mcp.json` in the folder you open in VS Code:

```json
{
  "mcpServers": {
    "anylogic": {
      "command": "/path/to/anylogic-mcp",
      "args": [],
      "env": {
        "ALP_OUTPUT_DIR": "/path/where/alp/files/are/saved"
      }
    }
  }
}
```

> **Windows:** use double backslashes in JSON paths:
> `"C:\\Users\\YourName\\AppData\\Local\\Programs\\Python\\Python312\\Scripts\\anylogic-mcp.exe"`
>
> See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for a full step-by-step walkthrough.

### 3. Reload VS Code

`Ctrl+Shift+P` → **Developer: Reload Window** → click **Allow** when prompted to approve the `anylogic` server.

Verify the connection:
```
What are the AnyLogic PLE limits?
```

---

## MCP tools

| Tool | What it does |
|---|---|
| `anylogic_create_model_ple` | Build and validate a DES model; returns a model ID |
| `anylogic_create_sd_model_ple` | Build and validate a System Dynamics model (explicit schema or template) |
| `anylogic_get_sd_schema` | Return JSON Schema and usage notes for SD models |
| `anylogic_download_for_ple` | Write the `.alp` file to `ALP_OUTPUT_DIR` |
| `anylogic_validate_ple` | Re-check a stored model against PLE limits |
| `anylogic_get_ple_limits` | Return all PLE restrictions |
| `anylogic_upload_to_cloud` | Upload to AnyLogic Cloud (requires API key) |

---

## Built-in templates

### Discrete event (DES)

| Template | Entity | Default config | Traffic intensity ρ |
|---|---|---|---|
| `warehouse` | Truck | 3 loading docks | 0.75 |
| `simple_queue` | Customer | 1 server | 0.60 |
| `factory` | Part | 2 machines in series (A→B) | 0.83 |
| `hospital` | Patient | triage + 3-doctor treatment | 0.88 |

### System dynamics (SD)

| Template | Description |
|---|---|
| `predator_prey` | Classic lynx–hare predator-prey model (with presentation sliders) |
| `simple_stock_flow` | Single-stock inventory with inflow/outflow |

#### Supported SD features

| Feature | Notes |
|---|---|
| Stocks / flows / auxiliaries | Java-safe names; duplicate names rejected |
| Parameters | `default`, optional `slider_min`/`slider_max`, optional `ui_control: "slider"` |
| Presentation sliders | When `ui_control: "slider"`, emits `<Control Type="Slider">` with `<Link>` and auto layout (5 per row) |
| Table functions | Points sorted by ascending unique X; `out_of_range`: ERROR, EXTRAPOLATE, CUSTOM, CLAMP |
| Causal links | Endpoints must exist; algebraic cycles among auxiliaries/flows are rejected |
| TimePlot charts | ≥1 series; `Expression2` must reference declared variables; optional ARGB `color` |
| PLE variable cap | stocks + flows + auxiliaries + parameters + table functions ≤ 200 |

#### Example: SD model with a slider

```json
{
  "name": "Inventory",
  "description": "Stock with restock slider",
  "sd_model": {
    "time_unit": "Month",
    "duration": 60,
    "parameters": [
      {
        "name": "restockRate",
        "default": "50",
        "slider_min": 0,
        "slider_max": 100,
        "ui_control": "slider"
      }
    ],
    "stocks": [{ "name": "Inventory", "initial_value": "200" }],
    "flows": [
      { "name": "restocking", "formula": "restockRate", "target": "Inventory" }
    ],
    "links": [
      { "source": "restockRate", "target": "restocking" },
      { "source": "restocking", "target": "Inventory" }
    ]
  }
}
```

Validation failures return MCP-friendly JSON objects with `error`, `field`, and `suggestion`
(for example when a formula references an unknown variable).

Custom DES models (any entity name, any block chain) and custom SD models (explicit `sd_model` schema) are fully supported.
See [EXAMPLES.md](EXAMPLES.md) for prompts covering manufacturing, service systems, healthcare, and system dynamics.

---

## Supported blocks

| Block | `params` keys | Notes |
|---|---|---|
| `Source` | `interarrivalTime` | **Always use `exponential(1.0/mean)` — AnyLogic treats this as a rate** |
| `Delay` | `capacity` (string), `delayTime` | Time unit: minutes; `capacity` = number of parallel servers |
| `Queue` | — | Auto-inserted before every `Delay`; only specify explicitly if needed elsewhere |
| `Sink` | — | |

> **Critical gotcha:** `exponential(10)` means 10 arrivals *per minute*, not one per 10 minutes.
> A warehouse with trucks arriving every 20 minutes needs `exponential(1.0/20.0)`.

---

## PLE limits (auto-enforced)

| Limit | Value |
|---|---|
| Agent types | 10 |
| Blocks per agent | 200 |
| Dynamic agents | 50,000 |
| Simulation time | 5 h *(unlimited when using Process Modeling Library — DES models use it; pure SD models do not)* |
| System dynamics variables | 200 |

---

## Opening generated models

1. Launch AnyLogic PLE 8.9.8
2. **File → Open** → select the `.alp` file from `ALP_OUTPUT_DIR`
3. Click the green **Run** button

---

## How the XML generation works

`model_builder.py` produces AnyLogic 8.9.8-compatible `.alp` XML for **discrete event** models.
`sd_builder.py` produces the same format for **system dynamics** models (stocks, flows, auxiliaries,
parameters, table functions, causal links, TimePlot charts, and optional `<Control Type="Slider">`
presentation controls).

The DES block ItemNames (e.g. Source = `1412336242928`) were extracted from a ground-truth AnyLogic file.
SD variable XML follows the same dialect as AnyLogic 8.9.x sample models (e.g. Predator Prey).

Key DES invariants:

- A `Queue` is auto-inserted before every `Delay` to buffer when server capacity is full
- Queue capacity is set to 100,000 (default in AnyLogic is 100, which causes OOM on long runs)
- `interarrivalTime` is always emitted in rate form: `exponential(1.0/mean)` not `exponential(mean)`
- Parameter name is `delayTime` (not `delay`); time unit is `MINUTE`
- `TimePlot` chart lives inside `Main/Presentation/Level/Presentation`, not in `SimulationExperiment`

---

## Project structure

```
├── src/anylogic_mcp/
│   ├── server.py          # MCP server and tool handlers
│   ├── model_builder.py   # DES .alp XML generator
│   ├── sd_schema.py       # Pydantic schema for SD models
│   ├── sd_validator.py    # SD semantic validation
│   ├── sd_builder.py      # SD .alp XML generator
│   ├── sd_templates.py    # Built-in SD templates
│   ├── ple_validator.py   # PLE limit checker
│   └── cloud_client.py    # AnyLogic Cloud upload (optional)
├── tests/
│   ├── test_model_builder.py
│   ├── test_ple_validator.py
│   ├── test_sd_schema.py
│   ├── test_sd_builder.py
│   └── test_sd_templates.py
└── pyproject.toml
```

Run the tests:

```cmd
# Windows
set PYTHONPATH=src && python -m pytest tests/ -v

# macOS / Linux
PYTHONPATH=src pytest tests/ -v
```

---

## Contributing

Pull requests are welcome. The most useful additions:

- **New block types** — `Service`, `Seize`/`Release`/`ResourcePool` for resource-constrained models.
  The ItemNames are already in `_ITEM_NAMES` in `model_builder.py`; what's needed is the
  parameter XML and connector wiring.
- **New templates** — supply chain, logistics, pedestrian flow.
- **Fluid Library support** — bulk/continuous flow (tanks, pipes) requires a different XML
  structure; the block ItemNames would need to be extracted from a ground-truth Fluid model.
- **Test coverage** — every new block type needs XML invariant tests matching the pattern
  in `test_model_builder.py`.

---

## Optional: AnyLogic Cloud upload

Set `ANYLOGIC_API_KEY` in the `env` block of `.mcp.json`:

```json
"env": {
  "ALP_OUTPUT_DIR": "...",
  "ANYLOGIC_API_KEY": "your_key_here"
}
```

Get a key at: https://cloud.anylogic.com/settings/api-keys

---

## License

MIT — see [LICENSE](LICENSE).

---

## Disclaimer

This project is not affiliated with or endorsed by AnyLogic. AnyLogic is a trademark of The AnyLogic Company. Generated models are subject to AnyLogic PLE's terms of use.
