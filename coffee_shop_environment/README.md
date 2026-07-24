# SPDX-License-Identifier: MIT
"""
Cozy Coffee Shop — Blender 5.2 Procedural Environment for Unity
================================================================

A production-structured, fully procedural rainy-evening coffee shop scene
generated with the Blender Python API. Designed for cinematic close-ups and
Unity game-level import.

## Quick Start

1. Install **Blender 5.2.0**
2. Open Blender → Scripting workspace
3. Open `CREATE_COZY_COFFEE_SHOP.py`
4. Click **Run Script**

CLI:

```bash
blender --background --python CREATE_COZY_COFFEE_SHOP.py
```

## What Gets Built

| System | Class | Features |
|--------|-------|----------|
| Architecture | `ArchitectureBuilder` | Walls, floor, ceiling, roof, columns, trim, wood paneling, FT windows with rain glass |
| Furniture | `FurnitureBuilder` | Tables, booths, armchairs, couches, reading corner |
| Coffee Bar | `CoffeeBarBuilder` | Counter, espresso machine, grinders, display, pastries, register, menus, props |
| Decor | `DecorBuilder` | Books, plants, art, rugs, curtains, lamps, signs, candles |
| Exterior | `ExteriorBuilder` | Sidewalk, road, buildings, lights, cars, benches (LOD-ready) |
| Weather | `WeatherSystem` | Rain particles, wind, puddles, lightning, thunder markers, steam |
| Lighting | `LightingSystem` | Warm 2700–3200K interior vs cold storm exterior |
| Physics | `PhysicsSystem` | Cloth curtains, rigid bodies, soft cushions |
| Animation | `AnimationSystem` | Wind sway, candle flicker |
| Cameras | `CameraSystem` | Interior/exterior cams + 30s cinematic dolly |
| Materials | `MaterialManager` | Full PBR Principled BSDF library |
| Textures | `TextureManager` | SD / Flux / Midjourney / local auto-wire |
| Optimize | `OptimizationSystem` | High/Med/Low + LOD0–3, 2K/4K/8K metadata |
| Export | `ExportManager` | `export_for_unity()` → FBX, GLB, textures, JSON |

## Folder Layout

```
CREATE_COZY_COFFEE_SHOP.py          # Blender entry (Run Script)
coffee_shop_environment/
  main.py                          # main()
  builders.py                      # EnvironmentBuilder, CoffeeShopBuilder
  architecture.py / furniture.py / coffee_bar.py / decor.py / exterior.py
  material_manager.py / texture_manager.py
  weather_system.py / lighting_system.py / physics_system.py
  animation_system.py / camera_system.py
  optimization.py / export_manager.py
  config.py / helpers.py
  textures/                        # AI + local PBR maps
  export/                          # FBX / GLB / textures / JSON output
```

## AI Textures

Drop maps into:

```
coffee_shop_environment/textures/<category>/<source>/
```

Categories: `wood`, `leather`, `fabric`, `concrete`, `metal`, `food`, `decals`, `weather`, `glass`, `ceramic`, `paper`  
Sources: `stable_diffusion`, `flux`, `midjourney`, `local`  

Naming: `{name}_basecolor.png`, `_roughness.png`, `_metallic.png`, `_normal.png`, `_displacement.png`

## Unity Import

After running the script, import from `coffee_shop_environment/export/`:

- `CozyCoffeeShop.fbx` or `CozyCoffeeShop.glb`
- `textures/`
- `CozyCoffeeShop_unity.json` — LOD groups, thunder sync frames, camera list

Scale: **1 unit = 1 meter**. FBX axis: forward `-Z`, up `Y`.

## Re-export

In Blender's Python console after a build:

```python
from coffee_shop_environment.export_manager import export_for_unity
export_for_unity()
```

Or call `export_for_unity()` from the entry script module.
