# mod-creations

Procedural Blender generators and printable collectibles.

## Funko Pop–style cat figurine

`funko_pop_cat_figurine.py` — Blender **5.2.0** Python script that builds a 3D-printable Funko Pop–inspired cat figurine (oversized head, stubby body, geometric fluff, snaggle-teeth, circular base).

### Run in Blender

1. Open Blender 5.2.0 → **Scripting** workspace.
2. Open `funko_pop_cat_figurine.py` → **Run Script**.
3. Outputs appear in `output_funko_cat/`:
   - `funko_pop_cat_preview.png` — studio preview render
   - `funko_pop_cat_figurine.stl` — manifold mesh for 3D printing
   - `funko_pop_cat_figurine.blend` — saved scene

### Run from the terminal

```bash
blender --background --python funko_pop_cat_figurine.py
```

### Adjust proportions

Edit the `CONFIG` dict at the top of the script (head/body scale, fur clump sizes, voxel remesh resolution, colors, camera, render engine).
