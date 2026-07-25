# API Overview — Cozy Coffee Shop Blender Generator

## Required entry points

- `main()` — full build + optional Unity export
- `export_for_unity()` — FBX / GLB / textures / sidecar JSON

## Classes

| Class | Module | Responsibility |
|-------|--------|----------------|
| `EnvironmentBuilder` | `builders.py` | Scene clear, collections, units, Cycles, materials bootstrap |
| `CoffeeShopBuilder` | `builders.py` | Architecture + furniture + bar + decor + exterior |
| `MaterialManager` | `material_manager.py` | Principled BSDF PBR library |
| `TextureManager` | `texture_manager.py` | AI/local texture discovery & auto-connect |
| `WeatherSystem` | `weather_system.py` | Rain, wind, puddles, lightning, thunder, steam |
| `LightingSystem` | `lighting_system.py` | Warm interior / cold exterior cinematic lighting |
| `AnimationSystem` | `animation_system.py` | Wind sway, flicker, timeline |
| `CameraSystem` | `camera_system.py` | Shot cameras + 30s cinematic dolly |
| `ExportManager` | `export_manager.py` | Unity export wrapper |
| `PhysicsSystem` | `physics_system.py` | Cloth / rigid / soft / particles |
| `OptimizationSystem` | `optimization.py` | High/Med/Low + LOD0–3 |

## Dimensions (meters)

- Shop: 14 × 18 × 3.6 m (playable interior)
- Window bank: ~12 m floor-to-ceiling
- Exterior street strip for window views with LOD tags
