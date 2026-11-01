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
  operators.py             Select Faces, Assemble, Clear Faces, and their shortcuts
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
