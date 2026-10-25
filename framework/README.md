# Framework Extensions

The framework changes support independent agent interaction with applications and reduce UI execution and rendering overhead. This directory contains patches for Android's `frameworks/base` and `frameworks/native`, based on **AOSP `android-16.0.0_r3`**.

## Design

**Second UI.** The framework creates a separate UI instance with its own view hierarchy and navigation state in the application's existing process. User and agent interactions use separate displays while sharing the application's account and business services. The launch changes are in `ActivityStarter` and `ActivityTaskManagerService`. Control over requests submitted between application layers is **pending release**.

**On-demand updates.** `ViewRootImpl` and `Choreographer` let the agent advance UI work when an action or observation requires it. A bounded update processes pending UI changes, records the resulting drawing commands and then pauses further agent traversals. This avoids continuous UI updates while the agent is waiting for inference.

**Piggyback traversal.** When user and agent UI instances share the main thread, agent traversal uses the time between foreground callbacks. Checkpoints in `View`, `ViewRootImpl` and `Choreographer` dispatch due foreground callbacks before continuing the agent traversal.

**DisplayList and rendering control.** A DisplayList records drawing commands before they become pixels. The HWUI changes export these records and let an observation stop after recording and RenderThread synchronization, skipping application rasterization. The native compositor patch can also bypass composition for the agent display. Normal pixel rendering can be restored when a screenshot is needed. Video and other separately rendered content still require pixel observations when their contents matter to the task.

On-demand updates and rendering control also apply when the agent is the only party using the target application. Piggyback handles the additional case of a shared application main thread.

## Source repositories and versions

| Component | Source repository / development branch | Implementation commit |
| --- | --- | --- |
| Android framework and HWUI | [aosp-frameworks-base](https://github.com/LiShengkai01/aosp-frameworks-base), [`exp_agent_gpu_bypass_eval`](https://github.com/LiShengkai01/aosp-frameworks-base/tree/exp_agent_gpu_bypass_eval) | [`3784ce34643f4b0d06b0dc7489c94e8bbb004378`](https://github.com/LiShengkai01/aosp-frameworks-base/commit/3784ce34643f4b0d06b0dc7489c94e8bbb004378) |
| System compositor | [aosp-frameworks-native](https://github.com/LiShengkai01/aosp-frameworks-native), [`exp_agent_ondemand_sched`](https://github.com/LiShengkai01/aosp-frameworks-native/tree/exp_agent_ondemand_sched) | [`4c01c486e1317e5773548e7f44eb4c72997f6d2d`](https://github.com/LiShengkai01/aosp-frameworks-native/commit/4c01c486e1317e5773548e7f44eb4c72997f6d2d) |

Each patch contains the changes from its baseline commit to the implementation commit above. Use these commits to reproduce this version; the development branches may advance.

| Patch | AOSP `android-16.0.0_r3` baseline commit |
| --- | --- |
| [frameworks-base.patch](frameworks-base.patch) | `33b96ce8a122757002e5040ac59824bd7a262e00` |
| [frameworks-native.patch](frameworks-native.patch) | `e4004c59925e0d212cb0823f3434966b9d41693b` |

## Apply and build

Apply each patch to the corresponding AOSP repository at the baseline revision listed above:

```bash
BIFACIAL_ROOT=/absolute/path/to/Bifacial-OS
BIFACIAL_AOSP=/absolute/path/to/aosp

git -C "$BIFACIAL_AOSP/frameworks/base" apply \
  "$BIFACIAL_ROOT/framework/frameworks-base.patch"
git -C "$BIFACIAL_AOSP/frameworks/native" apply \
  "$BIFACIAL_ROOT/framework/frameworks-native.patch"
```

The patches are `git diff` output and use `git apply`. Checking out the implementation commits directly gives the same source changes. Other Android releases and vendor branches require adapting the changes to their source trees.

Build the changes with the target device's normal AOSP build. The affected modules include `framework-minus-apex`, `services`, `libhwui` and `surfaceflinger`. Both the base and native changes are needed for the full rendering-control path.

The base patch carries an older README from the implementation repository. Use this document for current setup instructions. If a target tree already has its own README, add `--exclude=README.md` to the base patch command to leave that file in place.

## Usage examples

The [example guide](examples/README.md) covers display creation, input, on-demand updates, raw DisplayList export and restoring normal rendering.

| Example | Role |
| --- | --- |
| [AgentDisplay.java](examples/AgentDisplay.java) | Own the agent display, launch an application and report the display ID and compositor layer stack |
| [framework_ctl.py](examples/framework_ctl.py) | Send input and control UI updates, rasterization and composition |

The examples run on a privileged development build with these patches. DisplayList output contains raw drawing records; screenshot capture and semantic decoding are outside the examples.

The current controls use non-default displays to identify agent UI instances and apply settings through package-level `dumpsys gfxinfo` commands. Input uses a logical `displayId`; compositor bypass uses a `layerStack`. The display helper reports both identifiers. See the [interface reference](examples/README.md#interface-reference) for commands and the [restore procedure](examples/README.md#restore-and-stop) for returning to normal rendering.
