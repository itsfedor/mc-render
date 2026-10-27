#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quarter_shots.py — все кадры постройки одним вызовом, с коротким выводом.

Делает: рендер N углов воксельным рендерером (он читает реальные блоки региона
и не зависит от текстур Chunky), затем сжимает PNG для чата через chatimg.
Выводит только строки IMG/SRC/UNKNOWN/FAIL — без логов, без прогресса.

Пример (квартал 54x38, два угла + площадь):
  quarter_shots.py --world /home/fedor/mcwork/quarter2/live_world \
      --box "-60 -4 -779 -739" --y 60 82 --scale 14 \
      --out /home/fedor/mcwork/quarter2 --label "Квартал у реки" \
      --angles 0,1 --closeup "-37 -25 -763 -751 60 77 26 Площадь с колодцем"

Ключи:
  --world DIR        папка мира (регион берётся по центру box)
  --region FILE      либо сразу файл .mca
  --box "x0 x1 z0 z1"  границы участка в блоках (включительно)
  --y Y0 Y1          высоты (по умолчанию 60 82)
  --scale N          пикселей на блок (14 — общий вид, 22-26 — крупный план)
  --angles "0,1"     ракурсы: 0 = с юго-востока, 1 = с северо-запада
  --out DIR          куда класть PNG (WebP для чата кэшируется автоматически)
  --label TEXT       подпись, к ней добавляется ракурс
  --closeup "x0 x1 z0 z1 y0 y1 scale label"   дополнительный кадр (можно повторять)
  --max N --quality N  параметры chatimg (по умолчанию 1200 / 86)
  --no-shrink        не звать chatimg
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOXEL = os.environ.get('VOXEL_RENDER', os.path.join(HERE, 'voxel_render.py'))
CHATIMG = os.environ.get('CHATIMG', os.path.expanduser('~/.hermes/bin/chatimg'))
PY = os.environ.get('VOXEL_PYTHON', sys.executable)
ANGLES = {0: 'ЮВ', 1: 'СЗ'}


def region_for(world, x0, x1, z0, z1):
    cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
    return os.path.join(world, 'region', 'r.%d.%d.mca' % (cx >> 9, cz >> 9))


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def render(region, box, y, scale, out, angle, label):
    x0, x1, z0, z1 = box
    y0, y1 = y
    r = run([PY, VOXEL, region] + [str(v) for v in (x0, x1, z0, z1, y0, y1, scale, out, angle, label)])
    if r.returncode != 0 or not os.path.exists(out):
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ['no output']
        print('FAIL %s rc=%s %s' % (out, r.returncode, tail[0][:160]))
        return None
    unknown = re.search(r'unknown-blocks (\d+): ?(.*)', r.stderr or '')
    size = re.search(r'\((\d+), (\d+)\)', (r.stdout or '').strip().splitlines()[-1] if r.stdout else '')
    wh = '%sx%s' % size.groups() if size else '?'
    return {'out': out, 'wh': wh, 'unknown': unknown}


def shrink(path, max_px, quality):
    r = run([CHATIMG, '--max', str(max_px), '--quality', str(quality), path])
    lines = [l for l in (r.stdout or '').splitlines() if l.strip()]
    return lines[-1] if lines and os.path.exists(lines[-1]) else path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--world')
    ap.add_argument('--region')
    ap.add_argument('--box', nargs=4, type=int, required=True)
    ap.add_argument('--y', nargs=2, type=int, default=[60, 82])
    ap.add_argument('--scale', type=int, default=14)
    ap.add_argument('--angles', default='0,1')
    ap.add_argument('--out', required=True)
    ap.add_argument('--label', default='')
    ap.add_argument('--closeup', action='append', default=[])
    ap.add_argument('--max', type=int, default=1200)
    ap.add_argument('--quality', type=int, default=86)
    ap.add_argument('--no-shrink', action='store_true')
    a = ap.parse_args()

    if not a.region:
        if not a.world:
            ap.error('нужен --world или --region')
        a.region = region_for(a.world, *a.box)
    if not os.path.exists(a.region):
        print('FAIL region not found: %s' % a.region)
        return 1
    os.makedirs(a.out, exist_ok=True)

    jobs = []
    for ang in [int(v) for v in a.angles.split(',') if v.strip() != '']:
        name = 'shot_%s%d.png' % ('iso' if a.scale >= 10 else 'small', ang)
        label = ('%s — вид с %s' % (a.label, ANGLES.get(ang, ang))).strip(' —')
        jobs.append((list(a.box), list(a.y), a.scale, os.path.join(a.out, name), ang, label))
    for i, spec in enumerate(a.closeup):
        parts = spec.split()
        if len(parts) < 8:
            print('FAIL closeup needs: x0 x1 z0 z1 y0 y1 scale label')
            return 1
        x0, x1, z0, z1, y0, y1, sc = [int(v) for v in parts[:7]]
        label = ' '.join(parts[7:])
        jobs.append(([x0, x1, z0, z1], [y0, y1], sc, os.path.join(a.out, 'shot_close%d.png' % (i + 1)), 0, label))

    done, unknown = [], {}
    for box, y, sc, out, ang, label in jobs:
        res = render(a.region, box, y, sc, out, ang, label)
        if not res:
            return 1
        done.append(res)
        if res['unknown']:
            n, names = res['unknown'].groups()
            for nm in names.split():
                unknown[nm] = int(n)

    for res in done:
        shown = res['out'] if a.no_shrink else shrink(res['out'], a.max, a.quality)
        kb = max(1, os.path.getsize(shown) // 1024)
        print('IMG %s %s (%d KB)' % (shown, res['wh'], kb))
        if shown != res['out']:
            print('SRC %s' % res['out'])
    if unknown:
        print('UNKNOWN %d: %s' % (len(unknown), ' '.join(sorted(unknown)[:12])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
