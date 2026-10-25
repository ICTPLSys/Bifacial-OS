#!/usr/bin/env python3
"""Minimal CLI for the pinned framework patches; Python standard library only.

Requires an explicitly selected device with a root adbd. Controls are package-wide,
not per-window RPCs. Use one caller and one agent display per target application.
"""
import argparse
import json
import re
import shlex
import subprocess
import sys
import time

MODES = {
    'continuous': ('undecouple', 'nogpubypass', 'traversalunfreeze'),
    'on-demand': ('decouple', 'nogpubypass', 'traversalfreeze'),
    'displaylist': ('decouple', 'gpubypass', 'traversalfreeze'),
}


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError('must be non-negative')
    return number


class Device:
    def __init__(self, args):
        self.args = args

    def shell(self, *words, timeout=15):
        # Quote the remote command too: adb shell invokes a device-side shell.
        command = ' '.join(shlex.quote(str(word)) for word in words)
        result = subprocess.run([self.args.adb, '-s', self.args.serial, 'shell', command],
                                capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'adb failed')
        return result.stdout

    def gfx(self, *words):
        return self.shell('dumpsys', 'gfxinfo', self.args.package, 'displaylist', *words,
                          timeout=45)

    def control(self, *words):
        self.gfx('agentctl', *words)

    def states(self):
        states = []
        for line in self.gfx('agentstate').splitlines():
            line = line.strip()
            if line.startswith('{'):
                state = json.loads(line)
                if 'display' in state:
                    states.append(state)
        if not states:
            raise RuntimeError('No agent state: check the patched build, package and launched UI')
        # The debug interface applies to every root in the application's processes.
        if any(s.get('agent_ui') and s['display'] != self.args.display for s in states):
            raise RuntimeError('Another agent display belongs to this package; control is not isolated')
        return [s for s in states if s['display'] == self.args.display and s.get('agent_ui')]

    def visible(self):
        return [s for s in self.states() if s.get('host_visibility') == 0
                and s.get('added') and s.get('has_view')]

    def compose(self, enabled, layer_stack):
        result = self.shell('service', 'call', 'SurfaceFlinger', '1050',
                            'i32', layer_stack, 'i32', int(enabled))
        if any(error in result.lower() for error in ['permission', 'exception', 'error', 'denied']):
            raise RuntimeError(result.strip())
        print(result.strip())  # Keep the Binder reply for inspection; verify compositor state.

    def update(self, wait_ms):
        before = self.visible()
        if not before or any(s.get('observe_active') for s in before):
            raise RuntimeError('Need visible, inactive agent roots before starting an update')
        # A reset/read fence prevents accepting a previous terminal observation.
        # This resets diagnostic counters and must not be used during profiling.
        self.control('reset')
        reset = self.visible()
        if not reset or any(s.get('observe_result') != 'idle' or s.get('last_sync_valid')
                            for s in reset):
            raise RuntimeError('Could not verify the observation reset; update was not requested')
        self.control('fresh', 'nodraw', 'asyncsettle', 'readysettle', 'readywait' + str(wait_ms))
        deadline = time.monotonic() + wait_ms / 1000 + 6
        last = []
        while time.monotonic() < deadline:
            last = self.visible()
            if last and all(not s.get('observe_active')
                            and s.get('observe_result') in ('readiness', 'timeout')
                            and s.get('last_sync_valid') and s.get('last_sync_result') == 0
                            and s.get('phase2_traversals', 0) > 0 and s.get('frozen') for s in last):
                if any(s['observe_result'] == 'timeout' for s in last):
                    print('Update budget expired: output may show an intermediate state.', file=sys.stderr)
                return last
            if any(s.get('observe_result') in ('sync_failed', 'detached') for s in last):
                break
            time.sleep(0.1)
        raise RuntimeError('Update did not reach a valid synchronized state: ' + json.dumps(last))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', default='adb')
    p.add_argument('--serial', required=True, help='explicit adb device serial')
    p.add_argument('--package', required=True)
    p.add_argument('--display', required=True, type=positive, help='agent logical display ID')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('state', help='print agent-root states for this display')
    mode = sub.add_parser('mode', help='change UI/rendering mode; does not change composition bypass')
    mode.add_argument('mode', choices=MODES)
    update = sub.add_parser('update', help='run one bounded update, synchronize, then freeze traversals')
    update.add_argument('--wait-ms', type=positive, default=2000)
    sub.add_parser('dump', help='print raw package-wide DisplayList data; does not trigger an update')
    tap = sub.add_parser('tap')
    tap.add_argument('x', type=nonnegative)
    tap.add_argument('y', type=nonnegative)
    swipe = sub.add_parser('swipe')
    for coordinate in ('x1', 'y1', 'x2', 'y2'):
        swipe.add_argument(coordinate, type=nonnegative)
    swipe.add_argument('--duration-ms', type=positive, default=350)
    sub.add_parser('back')
    compose = sub.add_parser('compose', help='toggle agent-display composition bypass')
    compose.add_argument('bypass', choices=('on', 'off'))
    compose.add_argument('--layer-stack', required=True, type=positive)
    restore = sub.add_parser('restore', help='disable bypass and resume continuous UI updates')
    restore.add_argument('--layer-stack', required=True, type=positive)
    return p


def main():
    p = parser()
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+', args.package):
        p.error('invalid package name')
    if args.command == 'update' and args.wait_ms > 30000:
        p.error('--wait-ms must not exceed 30000')
    device = Device(args)
    if device.shell('id', '-u').strip() != '0':
        raise RuntimeError('Use a development device with root adbd; see README.md')
    if args.command == 'state':
        print(json.dumps(device.states(), indent=2))
        return
    if args.command != 'restore' and not device.visible():
        raise RuntimeError('No visible agent UI on the selected display; inspect the launch')
    if args.command == 'mode':
        device.control('nohashstable', 'nodlprofile', *MODES[args.mode])
        print(json.dumps(device.states(), indent=2))
    elif args.command == 'update':
        print(json.dumps(device.update(args.wait_ms), indent=2))
    elif args.command == 'dump':
        print(device.gfx(), end='')
    elif args.command == 'tap':
        device.shell('input', '-d', args.display, 'tap', args.x, args.y)
    elif args.command == 'swipe':
        device.shell('input', '-d', args.display, 'swipe', args.x1, args.y1,
                     args.x2, args.y2, args.duration_ms)
    elif args.command == 'back':
        device.shell('input', '-d', args.display, 'keyevent', 'KEYCODE_BACK')
    elif args.command == 'compose':
        device.compose(args.bypass == 'on', args.layer_stack)
    elif args.command == 'restore':
        device.compose(False, args.layer_stack)
        device.control('nohashstable', 'nodlprofile', *MODES['continuous'])
        print('Composition restore and normal UI rendering requested.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('error: ' + str(error), file=sys.stderr)
        sys.exit(1)
