# Procedural Rainy Coffee Shop — Blender 5.2 Environment Generator

`coffee_shop_generator.py` is a single, self-contained Blender 5.2.0 Python
script that procedurally builds a hyperrealistic, cozy independent coffee
shop on a stormy city evening — and exports it as a Unity-ready game
environment. No external assets are required.

## What it builds

| System | Contents |
| --- | --- |
| Architecture | Walls, floor-to-ceiling glazing, entrance door, roof, exposed beams, columns, trim, baseboards, wood slat paneling, oak plank flooring |
| Coffee bar | Counter, espresso machine, two grinders, batch brewer, sink, stocked pastry display case, POS register, chalkboard menus, shelving with mugs/cups, napkin holders, coffee bean bags |
| Seating | Round cafe tables + chairs, booths, window bar + stools, couch, armchairs, reading corner |
| Decor | Bookshelves with randomized books, potted + hanging plants, artwork, rugs, cloth-simulated curtains, pendant/floor lamps, neon OPEN sign, candles, string lights |
| Exterior street | Wet road + sidewalks, background buildings with lit windows, storefronts + awnings, street lights, traffic signal, benches, parked cars, trash cans, utility poles with sagging wires |
| Weather | Collision-enabled particle rain (adjustable intensity), wind + turbulence, reflective puddles, droplets/streaks/condensation on the glass, randomized lightning flashes, `THUNDER_##` timeline markers for SFX sync |
| Physics | Cloth curtains, rigid-body chairs/props, soft-body cushions, dust motes, animated volumetric coffee/espresso steam |
| Lighting | Warm 2700–3200K interior practicals vs. cold blue-gray storm exterior, flickering candles, street sodium lamps, atmosphere scatter volume |
| Cameras | 6 cinematic cameras cut into a 30-second marker-bound sequence with eased dolly moves, physical DOF and a rack-focus shot |
| Rendering | Cycles: adaptive sampling + denoising, deep GI bounces, volumetrics, caustics, AgX color management, motion blur |
| Export | `export_for_unity()` — LOD0–LOD3 generation (`_LODn` naming), texture budget (2K/4K/8K), FBX + GLB + texture export with clean transforms and baked animation |

## Usage

1. Open **Blender 5.2.0** → *Scripting* workspace → *New* text block.
2. Paste the entire contents of `coffee_shop_generator.py`.
3. Press **Run Script**. `main()` builds everything automatically.

Headless:

```bash
blender --background --python coffee_shop_generator.py
```

Re-export at any time from the Python console:

```python
export_for_unity()
```

## Configuration

Every tunable lives in the `CONFIG` dict at the top of the script:
random seed, shop dimensions, rain intensity, lightning frequency, color
temperatures, texture budget (2048/4096/8192), LOD ratios, export toggles
and Cycles quality settings.

## AI texture system

On first run the script creates a `Textures/` tree next to the .blend
(falling back to the system temp dir for unsaved files):

```
Textures/
├── wood/  ├── leather/  ├── fabric/  ├── concrete/  ├── metal/
├── food/  ├── decals/   ├── weather/ ├── ceramic/   ├── glass/ └── paper/
```

Each category contains `stable_diffusion/`, `flux/`, `midjourney/` and
`local/` subfolders plus a `texture_manifest.json` describing the expected
filenames. Drop AI-generated maps (albedo / roughness / metallic / normal /
displacement, matched by keyword) into any of these folders and they are
discovered and wired into the PBR materials automatically on the next run.
All materials remain fully procedural when no textures are present.

## Unity import

- 1 Blender unit = 1 m; FBX is exported with Unity axis conversion and a
  scale factor of 1.
- Meshes carry `_LOD0`…`_LOD3` suffixes for automatic LOD Group creation.
- `UnityExport/UNITY_IMPORT_NOTES.json` lists the thunder-marker frames for
  audio synchronization.

## Requirements

- Blender 5.2.0 (also runs on 4.x — shader socket names and the
  layered-Action API are handled version-tolerantly).
- No Python package dependencies; only the bundled `bpy` API is used.
