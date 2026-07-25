# mod-creations

## Realistic procedural cat for Blender 5.2.0

`create_realistic_cat.py` builds a complete, render-ready photoreal domestic
cat scene entirely from code — no external textures, models or HDRIs. It was
developed and verified against **Blender 5.2.0 LTS** (Cycles).

### What the script creates

- **Anatomy** – a full cat body (skull, brow ridges, cheeks, whisker pads,
  eyelids, muscle masses, legs, paws, tapered tail, ears) generated from a
  metaball armature, voxel-remeshed into one organic mesh, then refined with
  smoothing, procedural displacement and a geometry-nodes micro-detail
  modifier.
- **Separate mesh objects** for the body, eyeballs (sclera/iris), corneas,
  eye wet-lines, nose, whiskers, teeth, tongue and mouth cavity.
- **Fur** – three hair particle systems (undercoat, guard hairs, tactile
  whiskers) with interpolated children, clumping, kink, roughness and
  per-strand randomness, driven by procedurally painted vertex groups and
  shaded with the Principled Hair BSDF (melanin parametrization, mackerel
  tabby pattern, root-to-tip variation, agouti ticking).
- **Materials** – PBR skin with subsurface scattering, pore micro-normals,
  paw-pad/belly color zones and ear translucency; procedural iris with
  radial fibers, true displacement and a vertical slit pupil; IOR-1.376
  refractive cornea; pebbled nose leather; teeth/tongue/mouth shaders.
- **Lighting & render** – procedural multiple-scattering sky environment,
  soft key light, cool rim light, fill light, ground plane, DOF portrait
  camera, and Cycles configured for 2048 adaptive samples with
  OpenImageDenoise, light tree, thick 3D hair curves and caustics.

### Usage

```bash
# build the scene only (leaves a render-ready .blend state)
blender -b -P create_realistic_cat.py

# build and render to //cat_render.png (4K, 2048 samples)
blender -b -P create_realistic_cat.py -- --render

# or open interactively and press F12
blender -P create_realistic_cat.py
```

The final render is configured for maximum realism (3840x2160, 2048
samples); expect long render times on CPU. Reduce
`scene.cycles.samples` / resolution for previews.
