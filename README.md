# mod-creations

## Blender Rainstorm Environment

`blender_rainstorm_environment.py` is a complete, procedural Blender **5.2.0** Python script that builds a cinematic rainstorm scene:

- Volumetric storm clouds
- High-performance Geometry Nodes rain (instanced drops)
- Splash crowns / droplets
- Reflective puddles and wet ground
- Wind / turbulence force fields
- Overcast lighting with optional lightning
- 300-frame animated sequence

### Run in Blender

1. Open Blender 5.2.0
2. Go to the **Scripting** workspace
3. Open `blender_rainstorm_environment.py`
4. Click **Run Script**

Or from the terminal:

```bash
blender --python blender_rainstorm_environment.py
```

### Tunable parameters

Edit the configuration block at the top of the script:

| Parameter | Role |
|---|---|
| `RAIN_INTENSITY` | Rain density |
| `DROP_SIZE_MIN` / `DROP_SIZE_MAX` | Drop scale range |
| `WIND_STRENGTH` | Rain wind drift |
| `SPLASH_SCALE` / `SPLASH_DENSITY` | Splash size / amount |
| `PUDDLE_COVERAGE` / `PUDDLE_DEPTH` | Wet ground puddles |
| `WIND_SPEED` / `WIND_TURBULENCE` / `GUST_FACTOR` | Force fields |
| `ENABLE_LIGHTNING` | Animated lightning flashes |
