# Assemble by Face (Blender extension)

Assemble mesh parts by their faces. This is the sister project to Assemble by Points, kept as a separate repository and extension package.

## Use

Open the **Assemble by Face** tab in the 3D Viewport sidebar (**N**) and tick its checkbox. While it's off, the add-on draws nothing and its tools are disabled.

1. Click **Select Faces** (**Shift+Alt+F**).
   - Click a face on the object that should **stay put**. It's highlighted in orange, and the corner nearest your click gets a dot labelled **1**.
   - Click a face on the object that should **move**. It's highlighted the same way, with its chosen corner labelled **2**.
   - Esc, right-click, or clicking empty space cancels.
2. Click **Assemble** (**Shift+Alt+A**). It stays disabled until both faces are picked. Then:
   - The second object turns so the two faces point straight at each other, using the smallest turn that does it, so it keeps as much of its orientation as possible.
   - It moves so the two chosen corners sit at the same spot.
   - Both objects' origins are set to that corner.
   - The highlights disappear.
   - It's one undo step.
3. **✕** forgets the picked faces without assembling.

## Merge Into New Object

After assembling, select both parts and click **Merge Into New Object** in the **Merge** panel. The result is a **new** object made of one closed outer shell with no internal geometry, ready for 3D printing.
The originals are hidden, never modified. This is the same merge as in the sister add-on, Assemble by Points.

The three settings are **percentages of the assembled size**, which is the largest dimension of the selected parts' combined bounding box. For parts 25 m across, 1% is 0.25 m. With two parts selected, the panel shows what each setting comes to.

| Option | Default | Meaning |
|---|---|---|
| **Merge Distance** | 1% | The vertex spacing target for the seam area. Merge never subdivides finer than this, and it collapses crowded seam vertices without thinning the seam below the density of the mesh around it. Away from the seam, nothing is ever merged. |
| **Fill Gaps Up To** | 1% | Gaps between the assembled parts up to this wide are closed, measured across the joined faces. Gaps up to 1.5× this are partly closed, and wider ones are left alone. 0 turns gap closing off. |
| **Smooth Seam** | 1% | The width of the band on each side of the seam that gets blended, so the two parts flow into each other. 0 turns smoothing off. |

What it does, on copies of the parts:
1. **Closes gaps across the joined faces.** Assemble remembers which way the faces were joined. Every vertex on each part's mating surface measures how far the other part is in that direction, and both sides move halfway across, plus a little so they overlap. Coarse faces are subdivided first so they have vertices to move.
2. **Unions** the parts with a Boolean.
3. **Cleans up.** It removes internal voids (enclosed cavities) and slivers, and fills holes.
4. **Evens out and smooths the seam** within the Smooth Seam band. Nothing outside the band changes.

If the parts weren't joined with Assemble, Merge still unions them but doesn't close gaps, and the status bar says so.
**Check Manifold** reports problems on any selected meshes.

Notes:
- **Shortcuts** work in Object Mode and can be changed under **Preferences → Keymap → 3D View → Object Mode**. Neither clashes with Blender's own Object Mode shortcuts.
- **Modifiers:** faces are picked on each object's own mesh, ignoring modifiers.
- **Shared meshes:** an object whose mesh is shared with other objects is refused, because setting its origin would move the others too. Make it single-user first.

Works on Blender 4.2 and later. Developed on 5.2.

## Layout

```
assemble_by_face/          the extension package (this is what gets built and installed)
  blender_manifest.toml    id, version, name, Blender version
  __init__.py              register/unregister, plus reloading for F3 > Reload Scripts
  properties.py            scene settings (scene.assemble_by_face)
  operators.py             Select Faces, Assemble, Clear Faces, Merge, and their shortcuts
  merge.py                 the merge (identical to Assemble by Points' merge.py)
  ui.py                    the sidebar panel and the face highlight in the viewport
tests/run_tests.py         headless tests
dist/                      built zips (not in git)
```

## Develop

The extension folder `%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\assemble_by_face` is a directory junction (a Windows folder link) pointing to `assemble_by_face/` here.
That means Blender loads the code straight from this repo.

To pick up code changes, press **F3 → Reload Scripts** in Blender.

**Don't uninstall the extension from Preferences while the junction exists.** Delete the junction itself instead.

## Test

```
blender --background --factory-startup --python tests/run_tests.py
```

Set `ONLY=<part of a test name>` to run a subset.

## Build

```
blender --command extension build --source-dir assemble_by_face --output-dir dist
```

Bump `version` in `blender_manifest.toml` for each release.

## License

GPL-3.0-or-later, the same as Blender. See [LICENSE](LICENSE).
