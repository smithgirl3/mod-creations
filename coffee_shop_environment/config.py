# SPDX-License-Identifier: MIT
"""
Global configuration for the cozy coffee shop procedural environment.
All dimensions are in meters (Blender / Unity meter scale).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PACKAGE_ROOT = Path(__file__).resolve().parent
TEXTURE_ROOT = PACKAGE_ROOT / "textures"
EXPORT_ROOT = PACKAGE_ROOT / "export"
BLEND_OUTPUT = EXPORT_ROOT / "CozyCoffeeShop.blend"

TEXTURE_CATEGORIES: List[str] = [
    "wood",
    "leather",
    "fabric",
    "concrete",
    "metal",
    "food",
    "decals",
    "weather",
    "glass",
    "ceramic",
    "paper",
]

# Supported AI / local texture sources (folder naming convention)
TEXTURE_SOURCES: List[str] = [
    "stable_diffusion",
    "flux",
    "midjourney",
    "local",
]

# ---------------------------------------------------------------------------
# Scene / shop dimensions (playable interior)
# ---------------------------------------------------------------------------
SHOP_WIDTH = 14.0          # X
SHOP_DEPTH = 18.0          # Y
SHOP_HEIGHT = 3.6          # Z interior ceiling
WALL_THICKNESS = 0.25
FLOOR_THICKNESS = 0.12
ROOF_THICKNESS = 0.35
BASEBOARD_HEIGHT = 0.12
TRIM_DEPTH = 0.04
COLUMN_SIZE = 0.35
WINDOW_SILL_HEIGHT = 0.08
WINDOW_HEADER_HEIGHT = 0.25

# Large floor-to-ceiling window bank on street side (-Y)
WINDOW_BANK_WIDTH = 12.0
WINDOW_PANE_WIDTH = 1.45
WINDOW_PANE_HEIGHT = 3.2
WINDOW_MULLION = 0.08
GLASS_THICKNESS = 0.012

# Exterior street depth visible through windows
STREET_WIDTH = 12.0
SIDEWALK_WIDTH = 3.0
BUILDING_ROW_DEPTH = 8.0
EXTERIOR_EXTENT = 40.0

# ---------------------------------------------------------------------------
# Lighting temperatures (Kelvin approximations via RGB)
# ---------------------------------------------------------------------------
INTERIOR_KELVIN_MIN = 2700
INTERIOR_KELVIN_MAX = 3200
EXTERIOR_STORM_COLOR = (0.35, 0.42, 0.55)  # blue-gray overcast
INTERIOR_WARM_COLOR = (1.0, 0.72, 0.45)
LIGHTNING_COLOR = (0.75, 0.82, 1.0)

# ---------------------------------------------------------------------------
# Weather defaults
# ---------------------------------------------------------------------------
RAIN_INTENSITY = 0.85          # 0..1
RAIN_PARTICLE_COUNT = 8000
WIND_STRENGTH = 0.35
PUDDLE_COUNT = 28
LIGHTNING_MIN_INTERVAL = 90    # frames @ 24fps
LIGHTNING_MAX_INTERVAL = 220
THUNDER_DELAY_FRAMES = 18      # sound sync markers after flash

# ---------------------------------------------------------------------------
# Animation / cameras
# ---------------------------------------------------------------------------
FPS = 24
CINEMATIC_DURATION_SECONDS = 30
CINEMATIC_FRAME_END = FPS * CINEMATIC_DURATION_SECONDS  # 720
DOF_FSTOP = 2.8

# ---------------------------------------------------------------------------
# Render (Cycles photorealism)
# ---------------------------------------------------------------------------
CYCLES_SAMPLES = 256
CYCLES_PREVIEW_SAMPLES = 64
CYCLES_MAX_BOUNCES = 12
CYCLES_DIFFUSE_BOUNCES = 6
CYCLES_GLOSSY_BOUNCES = 6
CYCLES_TRANSMISSION_BOUNCES = 12
CYCLES_VOLUME_BOUNCES = 4
CYCLES_CAUSTICS = True
USE_DENOISING = True
USE_VOLUME_SCATTER = True

# ---------------------------------------------------------------------------
# LOD / texture resolution
# ---------------------------------------------------------------------------
LOD_LEVELS = ("LOD0", "LOD1", "LOD2", "LOD3")
LOD_DECIMATE_RATIOS = {
    "LOD0": 1.0,
    "LOD1": 0.5,
    "LOD2": 0.25,
    "LOD3": 0.1,
}
TEXTURE_RESOLUTIONS = (2048, 4096, 8192)  # 2K, 4K, 8K
DEFAULT_TEXTURE_RES = 4096

# ---------------------------------------------------------------------------
# Collections (Unity / game-asset style hierarchy)
# ---------------------------------------------------------------------------
COLLECTION_HIERARCHY: Dict[str, List[str]] = {
    "01_Architecture": ["Walls", "Floor", "Ceiling", "Roof", "Columns", "Trim", "Windows"],
    "02_Furniture": ["Tables", "Chairs", "Booths", "Sofas", "ReadingCorner"],
    "03_CoffeeBar": ["Counter", "Machines", "Display", "Props", "Menus"],
    "04_Decor": ["Plants", "Art", "Rugs", "Lamps", "Books", "Candles", "Signs"],
    "05_Exterior": ["Sidewalk", "Road", "Buildings", "StreetProps", "Vehicles", "LOD"],
    "06_Weather": ["Rain", "Puddles", "Wind", "Lightning", "Steam"],
    "07_Lighting": ["InteriorLights", "ExteriorLights", "Practicals", "Volume"],
    "08_Cameras": ["InteriorCams", "ExteriorCams", "Cinematic"],
    "09_Physics": ["Cloth", "RigidBodies", "SoftBodies", "Particles"],
    "10_Export": ["HighPoly", "MediumPoly", "LowPoly", "LODs"],
}

# ---------------------------------------------------------------------------
# Randomization
# ---------------------------------------------------------------------------
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Material name registry
# ---------------------------------------------------------------------------
MATERIAL_NAMES: Tuple[str, ...] = (
    "MAT_WoodOak",
    "MAT_WoodWalnut",
    "MAT_WoodFloor",
    "MAT_MetalBrushed",
    "MAT_MetalChrome",
    "MAT_MetalBlack",
    "MAT_LeatherBrown",
    "MAT_LeatherBlack",
    "MAT_CeramicWhite",
    "MAT_CeramicMug",
    "MAT_Concrete",
    "MAT_GlassClear",
    "MAT_GlassRain",
    "MAT_FabricLinen",
    "MAT_FabricUpholstery",
    "MAT_FabricCurtain",
    "MAT_PaperMenu",
    "MAT_PaperBook",
    "MAT_FoodPastry",
    "MAT_FoodCoffee",
    "MAT_PlasterWarm",
    "MAT_PaintWall",
    "MAT_RubberFloorMat",
    "MAT_AsphaltWet",
    "MAT_BrickExterior",
    "MAT_PlantLeaf",
    "MAT_CandleWax",
    "MAT_WaterPuddle",
)


def ensure_directories() -> None:
    """Create texture and export folder trees if missing."""
    TEXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    for category in TEXTURE_CATEGORIES:
        cat_dir = TEXTURE_ROOT / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        for source in TEXTURE_SOURCES:
            (cat_dir / source).mkdir(parents=True, exist_ok=True)
    # Placeholder readme so empty folders survive VCS
    readme = TEXTURE_ROOT / "README_TEXTURES.txt"
    if not readme.exists():
        readme.write_text(
            "Place AI-generated or library textures here.\n"
            "Naming: {category}_{variant}_basecolor.png, _roughness.png, "
            "_metallic.png, _normal.png, _displacement.png\n"
            "Sources: stable_diffusion/, flux/, midjourney/, local/\n",
            encoding="utf-8",
        )


def package_path(*parts: str) -> str:
    """Return an absolute path string under the package root."""
    return str(PACKAGE_ROOT.joinpath(*parts))
