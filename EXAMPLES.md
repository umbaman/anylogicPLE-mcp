# Example Prompts — AnyLogic MCP Server

Use these prompts in Claude Code after installing the MCP server and creating `.mcp.json`.

---

## System Dynamics

### Predator-prey
```
Create a predator-prey SD model using template predator_prey.
100-year horizon. Download the .alp file.
```

### Simple stock-flow
```
Create a simple stock-flow inventory model using template simple_stock_flow.
60-month horizon. Download the .alp file.
```

### Custom SD model
```
Call anylogic_get_sd_schema first, then create an SD model "InventoryDynamics":
- Stock Inventory (initial 500), inflow restocking rate 40/month, outflow sales 35/month
- Time unit Month, duration 60
- Include causal links and a TimePlot of Inventory
Download the .alp file.
```

### Get SD schema
```
Show me the System Dynamics model schema for anylogic_create_sd_model_ple.
```

---

## Templates (Discrete Event)

### Simple queue
```
Create a simple queue model called "BankQueue": 1 server, customers arriving
every 5 minutes, service time triangular(2,3,4) minutes.
Make it PLE-compliant and give me the .alp file.
```

### Warehouse
```
Create a warehouse simulation with 4 loading docks. Trucks arrive every 20 minutes
(exponential), loading time triangular(30,45,60) minutes.
Ensure it fits PLE limits and download the .alp file.
```

### Factory production line
```
Build a factory model: parts arrive every 10 minutes.
Machine A takes triangular(5,8,12) min (1 machine).
Machine B takes triangular(3,5,8) min (1 machine).
Give me the .alp file.
```

### Hospital ER
```
Hospital ER: patients arrive every 12 minutes.
Triage: 1 nurse, triangular(5,8,12) min.
Treatment: 3 doctors, triangular(20,30,45) min.
Download the .alp file.
```

---

## Custom models

### Single-stage with multiple servers
```
Create a custom model "CallCenter" with entity "Call":
- Source "arrivals": interarrivalTime exponential(1.0/8.0)
- Delay "handling": capacity 5, delayTime triangular(4,7,12)
- Sink "done"
Download the .alp file.
```

### Two-stage pipeline
```
Create a custom model "PrintShop" with entity "Order":
- Source "orders": interarrivalTime exponential(1.0/6.0)
- Delay "printing": capacity 3, delayTime triangular(4,6,10)
- Delay "finishing": capacity 1, delayTime triangular(2,3,5)
- Sink "shipped"
Make it PLE-compliant and give me the .alp file.
```

### Long simulation
```
Create a simple queue model "WeekSim" running for 10080 minutes (1 week):
- arrivals: exponential(1.0/15.0)
- service: capacity 2, delayTime triangular(10,20,30)
Download the .alp file.
```

---

## Manufacturing

### CNC job shop — three sequential operations
Parts arrive every 15 min. Two roughing machines, one semi-finish, one finish cell.
Bottleneck is semi-finish (ρ ≈ 0.80); roughing and finish run at ρ ≈ 0.42 and 0.56.
```
Create a custom model "CNCJobShop" with entity "Job":
- Source "arrivals": interarrivalTime exponential(1.0/15.0)
- Delay "roughing": capacity 2, delayTime triangular(8,12,18)
- Delay "semifinish": capacity 1, delayTime triangular(8,12,16)
- Delay "finishing": capacity 1, delayTime triangular(5,8,12)
- Sink "shipped"
Give me the .alp file.
```

### PCB assembly line — SMD + solder + inspection
Boards enter every 8 min. Soldering oven is the bottleneck (ρ ≈ 0.92); two
inspectors keep the final stage light (ρ ≈ 0.21).
```
Create a custom model "PCBAssembly" with entity "Board":
- Source "arrivals": interarrivalTime exponential(1.0/8.0)
- Delay "smdPlacement": capacity 1, delayTime triangular(3,5,8)
- Delay "soldering": capacity 1, delayTime triangular(5,7,10)
- Delay "inspection": capacity 2, delayTime triangular(2,3,5)
- Sink "complete"
Give me the .alp file.
```

### Automotive paint shop — prep → prime → top coat → inspection
Bodies arrive every 20 min. Top coat booth is the bottleneck (ρ ≈ 0.75).
```
Create a custom model "PaintShop" with entity "Body":
- Source "arrivals": interarrivalTime exponential(1.0/20.0)
- Delay "prep": capacity 3, delayTime triangular(10,15,20)
- Delay "priming": capacity 2, delayTime triangular(20,25,35)
- Delay "topCoat": capacity 2, delayTime triangular(25,30,40)
- Delay "inspection": capacity 1, delayTime triangular(5,8,12)
- Sink "done"
Give me the .alp file.
```

### Food packaging line — primary pack → label → case pack
Products exit the filler every 3 min. Three primary packers and two labellers
keep pace; a single case packer is the bottleneck (ρ ≈ 0.78).
```
Create a custom model "FoodPackaging" with entity "Product":
- Source "arrivals": interarrivalTime exponential(1.0/3.0)
- Delay "primaryPack": capacity 3, delayTime triangular(3,5,8)
- Delay "labelApply": capacity 2, delayTime triangular(1,2,3)
- Delay "casePack": capacity 1, delayTime triangular(4,6,10)
- Sink "dispatched"
Give me the .alp file.
```

### Stamping / press shop — high-throughput blanking
Blanks fed every 2 min by coil feed. Four presses and two deburring cells;
all utilisation below 50% — good for showing a well-balanced, high-speed line.
```
Create a custom model "StampingLine" with entity "Blank":
- Source "coilFeed": interarrivalTime exponential(1.0/2.0)
- Delay "stamping": capacity 4, delayTime triangular(1,2,3)
- Delay "deburring": capacity 2, delayTime triangular(2,3,5)
- Sink "finished"
Give me the .alp file.
```

### One 8-hour production shift — machining → assembly → test
Work orders released every 10 min. Testing cell is the bottleneck (ρ ≈ 0.83);
watch its queue grow over the 480-minute shift window.
```
Create a custom model "ShiftProduction" with entity "WorkOrder":
- Duration: 480 minutes
- Source "release": interarrivalTime exponential(1.0/10.0)
- Delay "machining": capacity 3, delayTime triangular(12,18,25)
- Delay "assembly": capacity 2, delayTime triangular(8,12,18)
- Delay "testing": capacity 1, delayTime triangular(5,8,12)
- Sink "complete"
Give me the .alp file.
```

### Injection moulding cell — moulding → cooling → trimming
Parts cycle every 6 min. Two cooling stations and two trimmers; utilisation
well below 50% — model is stable, useful for demonstrating high OEE.
```
Create a custom model "InjectionMoulding" with entity "Part":
- Source "mouldCycle": interarrivalTime exponential(1.0/6.0)
- Delay "cooling": capacity 2, delayTime triangular(3,4,6)
- Delay "trimming": capacity 2, delayTime triangular(2,3,5)
- Sink "finished"
Give me the .alp file.
```

### Identify the bottleneck in a manufacturing line
Ask Claude to build and interpret the model in one step:
```
Create a 3-stage manufacturing model "BottleneckDemo" with entity "Part":
- Arrivals every 12 minutes (exponential)
- Stage 1 "cutting": 2 machines, triangular(8,10,14) min
- Stage 2 "welding": 1 station, triangular(9,11,14) min
- Stage 3 "painting": 1 booth, triangular(5,7,10) min
Give me the .alp file, and tell me which stage is the bottleneck and why.
```

---

## Queries

### Check PLE limits
```
What are the AnyLogic PLE limitations?
```

### Validate a model
```
Validate model <model_id> against PLE limits.
```

---

## Tips

**Interarrival time is a rate, not a mean.**
AnyLogic treats `interarrivalTime` as events per minute:
- ✅ `exponential(1.0/20.0)` → mean 20 min between arrivals
- ❌ `exponential(20)` → 20 arrivals per minute (400× too fast)

**State arrival and service times separately.**
The server calculates traffic intensity (ρ) automatically. For a stable queue, ρ < 1:
- ρ = arrival_rate / (num_servers × service_rate)

**All time values are in minutes.**

**Queue blocks are auto-inserted.**
A `Queue` is automatically placed before each `Delay` block.
You don't need to specify it unless you want it in a custom position.
