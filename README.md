# Procedural Rainy Coffee Shop

`coffee_shop_generator.py` is a self-contained Blender 5.2 scene generator for
a playable-scale, stormy Scandinavian coffee shop and the surrounding street.

## Run

1. Open Blender 5.2 and switch to the **Scripting** workspace.
2. Open `coffee_shop_generator.py` in the Text Editor.
3. Save the `.blend` file to choose where relative paths will resolve.
4. Click **Run Script** once.

The script builds the scene, configures Cycles, creates a 30-second animation,
generates LOD collections, and writes FBX, GLB, and a source `.blend` to
`//UnityExport/`.

Artist controls are in `CoffeeShopConfig` near the top of the script. Set
`auto_export=False` while iterating if generation should stop before export.

## Optional AI/PBR maps

On first run, the generator creates this source hierarchy beside the `.blend`:

```text
Textures/
├── wood/{stable_diffusion,flux,midjourney,local}
├── leather/{stable_diffusion,flux,midjourney,local}
├── fabric/{stable_diffusion,flux,midjourney,local}
├── concrete/{stable_diffusion,flux,midjourney,local}
├── metal/{stable_diffusion,flux,midjourney,local}
├── food/{stable_diffusion,flux,midjourney,local}
├── decals/{stable_diffusion,flux,midjourney,local}
└── weather/{stable_diffusion,flux,midjourney,local}
```

Name maps with their asset and channel, for example
`Oak_Wood_4K_basecolor.png`, `Oak_Wood_4K_roughness.png`,
`Oak_Wood_4K_normal.png`, and `Oak_Wood_4K_height.exr`. Missing maps fall back
to procedural micro-surface detail, so external files are optional.

For Unity, import the FBX or GLB at scale 1, group `_LOD0` through `_LOD3`
objects in `LODGroup` components, and recreate Blender-only rain/steam effects
with Unity VFX Graph for runtime performance.
