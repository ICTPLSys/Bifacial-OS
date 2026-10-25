# Minimal framework examples

These examples use the patches and fixed revisions in [../README.md](../README.md). They are self-contained and require no model service or API credentials.

| File | Purpose |
| --- | --- |
| [AgentDisplay.java](AgentDisplay.java) | Create and hold an agent display, launch an activity there, report its display ID and compositor layer stack, and consume rendering buffers |
| [framework_ctl.py](framework_ctl.py) | Send input, select rendering modes, request a bounded update, inspect state, export raw DisplayList data, and restore normal rendering |

The examples return raw DisplayList records. Screenshot capture and glyph decoding are not included.

## Requirements

Use an Android 16 development device with both supplied patches and a root `adbd`. The host needs Android SDK platform 36 and build-tools, JDK 17, and Python 3.8 or later. The display helper runs through `app_process` and uses hidden framework APIs.

Use one controller and one agent display per target application: the current `dumpsys gfxinfo` controls apply to the application's roots together.

## Build and launch a display

Run the build commands from the Bifacial-OS repository root. Adjust the SDK/build-tools paths for your installation. Build output stays outside the repository.

```bash
BIFACIAL_SDK="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
BIFACIAL_ANDROID_JAR="$BIFACIAL_SDK/platforms/android-36/android.jar"
BIFACIAL_D8="$BIFACIAL_SDK/build-tools/36.1.0/d8"
BIFACIAL_BUILD=$(mktemp -d /tmp/bifacial-example.XXXXXX)
mkdir -p "$BIFACIAL_BUILD/classes" "$BIFACIAL_BUILD/dex"
javac -source 17 -target 17 -classpath "$BIFACIAL_ANDROID_JAR" \
  -d "$BIFACIAL_BUILD/classes" framework/examples/AgentDisplay.java
"$BIFACIAL_D8" --lib "$BIFACIAL_ANDROID_JAR" --min-api 36 \
  --output "$BIFACIAL_BUILD/dex" \
  "$BIFACIAL_BUILD/classes/org/bifacial/example/AgentDisplay.class"
```

In terminal A, set your device serial and an installed application's launch component. Replace the placeholders before running. For example, `com.example.app/.MainActivity` is a component, while `com.example.app` is its package. Resolve the actual component for your device with `cmd package resolve-activity --brief` or inspect the application's manifest.

```bash
BIFACIAL_SERIAL='YOUR_DEVICE_SERIAL'
BIFACIAL_COMPONENT='YOUR_PACKAGE/YOUR_LAUNCH_ACTIVITY'
BIFACIAL_REMOTE="/data/local/tmp/bifacial-example-$(date +%s)-$$"
adb -s "$BIFACIAL_SERIAL" root
adb -s "$BIFACIAL_SERIAL" wait-for-device
adb -s "$BIFACIAL_SERIAL" shell mkdir -p "$BIFACIAL_REMOTE"
adb -s "$BIFACIAL_SERIAL" push "$BIFACIAL_BUILD/dex/classes.dex" "$BIFACIAL_REMOTE/classes.dex"
adb -s "$BIFACIAL_SERIAL" shell app_process -cp "$BIFACIAL_REMOTE/classes.dex" / \
  org.bifacial.example.AgentDisplay "$BIFACIAL_COMPONENT" "$BIFACIAL_REMOTE/stop" 1800
```

Leave terminal A running. The helper holds a 1080 × 1920, 320-dpi virtual display for up to 1,800 seconds and prints `READY displayId=... layerStack=...`. It keeps the display on and consumes its rendered buffers. Wait for the application to load before sending input.

## Control the agent UI

In terminal B, from the repository root, set the same serial and target package. Copy the two identifiers printed by the helper; **do not infer the layer stack from the display ID**. The identifiers below are placeholders.

```bash
BIFACIAL_SERIAL='YOUR_DEVICE_SERIAL'
BIFACIAL_PACKAGE='YOUR_PACKAGE'
BIFACIAL_DISPLAY='DISPLAY_ID_FROM_READY'
BIFACIAL_LAYER_STACK='LAYER_STACK_FROM_READY'
ctl() {
  python3 framework/examples/framework_ctl.py \
    --serial "$BIFACIAL_SERIAL" --package "$BIFACIAL_PACKAGE" \
    --display "$BIFACIAL_DISPLAY" "$@"
}
ctl state
ctl mode displaylist
ctl update --wait-ms 2000
ctl dump > initial-displaylist.txt
```

`mode displaylist` enables on-demand updates and skips application rasterization. `update` advances the UI, records and synchronizes its DisplayList, then freezes further traversals. If its time budget expires, the result may show an intermediate loading state. The helper resets diagnostic counters for each update, so run performance profiling separately.

`dump` returns the existing records without triggering an update. Its output covers all windows in the package; use the window headers' `display` and visibility fields to select the agent UI.

### A short page-navigation sequence

Use a display viewer or pixel-observation client to locate an item that opens another page. Enter its coordinates below, navigate into the page and return with Back:

```bash
read -r -p 'Navigation item x y: ' BIFACIAL_X BIFACIAL_Y
ctl tap "$BIFACIAL_X" "$BIFACIAL_Y"
ctl update --wait-ms 2000
ctl dump > detail-displaylist.txt
ctl back
ctl update --wait-ms 2000
ctl dump > returned-displaylist.txt
```

For loading content, issue another `update` without new input. Complete login and dismiss setup dialogs before the sequence. If navigation opens a different application, update the target package before continuing.

## Interface reference

The following are custom controls supplied by these patches, not standard Android APIs. `<package>`, `<display>` and `<layerStack>` below denote the resolved runtime identifiers.

| Operation | Device-side command / arguments | Effect |
| --- | --- | --- |
| Inspect roots | `dumpsys gfxinfo <package> displaylist agentstate` | Report per-root agent and observation state |
| Continuous rendering | `dumpsys gfxinfo <package> displaylist agentctl undecouple nogpubypass traversalunfreeze` | Restore normal frame-clock updates and application pixel rendering |
| On-demand UI service | `dumpsys gfxinfo <package> displaylist agentctl decouple nogpubypass traversalfreeze` | Hold traversals until an explicit update; leave persistent rasterization bypass off |
| DisplayList mode | `dumpsys gfxinfo <package> displaylist agentctl decouple gpubypass traversalfreeze` | Hold traversals and suppress application pixel drawing while retaining UI recording/synchronization |
| Bounded update | `dumpsys gfxinfo <package> displaylist agentctl fresh nodraw asyncsettle readysettle readywait2000` | Start an asynchronous update with a 2,000-ms budget; final record/sync is followed by traversal freezing |
| Raw observation | `dumpsys gfxinfo <package> displaylist` | Export recorded drawing data; does not by itself refresh the UI |
| Targeted input | `input -d <display> tap X Y` / `input -d <display> keyevent KEYCODE_BACK` | Route input to the logical display |
| Composition bypass | `service call SurfaceFlinger 1050 i32 <layerStack> i32 1` | Bypass composition for the selected agent output; use `0` to restore it |

The `mode` command leaves composition bypass unchanged. To also omit agent-display composition:

```bash
ctl compose on --layer-stack "$BIFACIAL_LAYER_STACK"
ctl update --wait-ms 2000
ctl dump > bypass-displaylist.txt
```

Transaction `1050` comes from the native patch and takes a compositor layer stack. Use the value reported by the display helper.

## Restore and stop

Restore while the application and display still exist, then stop the display owner. Set `BIFACIAL_REMOTE` in terminal B to the exact session path created in terminal A.

```bash
ctl restore --layer-stack "$BIFACIAL_LAYER_STACK"
adb -s "$BIFACIAL_SERIAL" shell touch "$BIFACIAL_REMOTE/stop"
```

`restore` resumes normal UI updates, rasterization and composition. Wait for a new rendered buffer before taking a screenshot. Restore these settings after a failed update as well: stopping the display helper releases its display but does not reset controls in the application. The restore command also works when the agent UI is no longer visible.

## Example status

The helpers are adapted from the project's GPU-bypass experiments. They have been compiled and checked offline; this standalone version has not yet been run on a device.
