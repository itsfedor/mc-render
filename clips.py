#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clips.py — GIF-клипы постройки прямо из региона мира.

  clips.py orbit  --world DIR --box "x0 x1 z0 z1" --y 60 82 --out orbit.gif
  clips.py growth --world DIR --box "x0 x1 z0 z1" --y 60 82 --script city.bk --out growth.gif

Орбита: камера облетает участок (азимут 0..360), elevation фиксированная.
Рост: блоки появляются в порядке команд .bk-скрипта (fill/setblock), затем по очереди
дома из списка --houses "имя:x0:x1:z0:z1,...".

Рендер собственный: проекция с поворотом по азимуту, куб рисуется тремя видимыми
гранями, порядок — по глубине. Ни Chunky, ни клиент не нужны.
"""
import argparse
import ast
import glob
import importlib.util
import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

VOXEL = os.environ.get('VOXEL_RENDER', os.path.join(HERE, 'voxel_render.py'))
ANALYZE = os.environ.get('MC_ANALYZE', os.path.join(HERE, 'lib', 'region.py'))
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def palette():
    tree = ast.parse(open(VOXEL).read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == 'COLORS':
            return ast.literal_eval(node.value)
    raise SystemExit('COLORS not found in %s' % VOXEL)


COLORS = palette()


def color_of(name):
    c = COLORS.get(name)
    if c is None:
        for k, v in COLORS.items():
            if name.startswith(k):
                c = v
                break
    if c is None:
        if any(k in name for k in ('leaves', 'grass', 'fern', 'bush', 'flower', 'moss')):
            c = (74, 128, 62)
        elif any(k in name for k in ('quartz', 'calcite', 'white_', 'diorite')):
            c = (228, 226, 218)
        elif any(k in name for k in ('_log', 'wood', 'planks', 'stairs', 'slab', 'fence', 'door')):
            c = (104, 80, 48)
        elif any(k in name for k in ('water', 'ice', 'sea')):
            c = (64, 112, 190)
        else:
            c = (128, 128, 124)
    return c


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


class Camera:
    """Изометрическая проекция с произвольным азимутом."""

    def __init__(self, az_deg, el_deg, scale, size, center):
        az, el = math.radians(az_deg), math.radians(el_deg)
        self.v = (math.cos(el) * math.sin(az), math.sin(el), math.cos(el) * math.cos(az))
        self.right = (math.cos(az), 0.0, -math.sin(az))
        self.up = (-math.sin(az) * math.sin(el), math.cos(el), -math.cos(az) * math.sin(el))
        self.s = scale
        self.w, self.h = size
        self.c = center

    def p(self, x, y, z):
        dx, dy, dz = x - self.c[0], y - self.c[1], z - self.c[2]
        sx = dx * self.right[0] + dz * self.right[2]
        sy = dx * self.up[0] + dy * self.up[1] + dz * self.up[2]
        return (self.w / 2 + sx * self.s, self.h / 2 - sy * self.s)

    def depth(self, x, y, z):
        dx, dy, dz = x - self.c[0], y - self.c[1], z - self.c[2]
        return dx * self.v[0] + dy * self.v[1] + dz * self.v[2]


FACES = {
    'top': ([(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)], (0, 1, 0), 1.0),
    'bottom': ([(0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0)], (0, -1, 0), 0.55),
    'east': ([(1, 1, 0), (1, 0, 0), (1, 0, 1), (1, 1, 1)], (1, 0, 0), 0.80),
    'west': ([(0, 1, 1), (0, 0, 1), (0, 0, 0), (0, 1, 0)], (-1, 0, 0), 0.66),
    'south': ([(1, 1, 1), (1, 0, 1), (0, 0, 1), (0, 1, 1)], (0, 0, 1), 0.72),
    'north': ([(0, 1, 0), (0, 0, 0), (1, 0, 0), (1, 1, 0)], (0, 0, -1), 0.60),
}


def draw_world(dr, cam, blocks, label=None, sub=None):
    order = sorted(blocks, key=lambda b: cam.depth(b[0], b[1], b[2]))  # дальние → ближние
    for x, y, z, name in order:
        c = color_of(name)
        for corners, normal, k in FACES.values():
            if normal[0] * cam.v[0] + normal[1] * cam.v[1] + normal[2] * cam.v[2] <= 0:
                continue
            pts = [cam.p(x + a, y + b, z + d) for a, b, d in corners]
            dr.polygon(pts, fill=shade(c, k))
    if label:
        try:
            f = ImageFont.truetype(FONT, 15)
        except Exception:
            f = ImageFont.load_default()
        dr.text((14, 10), label, fill=(238, 238, 244), font=f)
        if sub:
            dr.text((14, 30), sub, fill=(150, 160, 175), font=f)


def load_region(world, box):
    spec = importlib.util.spec_from_file_location('an02', ANALYZE)
    an = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(an)
    x0, x1, z0, z1 = box
    rx, rz = (x0 + x1) // 2 >> 9, (z0 + z1) // 2 >> 9
    path = os.path.join(world, 'region', 'r.%d.%d.mca' % (rx, rz))
    if not os.path.exists(path):
        cand = sorted(glob.glob(os.path.join(world, 'region', '*.mca')))
        if not cand:
            raise SystemExit('no region files in %s' % world)
        path = cand[0]
    return an.WorldView([path])


def snapshot(wv, box, yr):
    x0, x1, z0, z1 = box
    y0, y1 = yr
    out = []
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            for y in range(y0, y1 + 1):
                raw = wv.block_at(x, z, y)
                if not raw:
                    continue
                name = raw.replace('minecraft:', '').split('[')[0]
                if name in ('air', 'cave_air', 'void_air'):
                    continue
                out.append((x, y, z, name))
    return out


def gif(frames, out, duration=110):
    imgs = [Image.open(p).convert('RGB') for p in frames]
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=duration,
                 loop=0, optimize=True)


def cmd_orbit(a):
    wv = load_region(a.world, a.box)
    blocks = snapshot(wv, a.box, a.y)
    x0, x1, z0, z1 = a.box
    center = ((x0 + x1) / 2, sum(a.y) / 2, (z0 + z1) / 2)
    w, h = a.size
    os.makedirs(a.frames, exist_ok=True)
    files = []
    for i in range(a.frames_count):
        az = 360.0 * i / a.frames_count + 20
        img = Image.new('RGB', (w, h), (18, 19, 23))
        dr = ImageDraw.Draw(img)
        cam = Camera(az, a.elev, a.scale, (w, h), center)
        draw_world(dr, cam, blocks, a.label, 'азимут %d°' % (az % 360))
        p = os.path.join(a.frames, 'orbit_%02d.png' % i)
        img.save(p)
        files.append(p)
    gif(files, a.out, a.duration)
    print('OUT %s %d кадров %d KB' % (a.out, len(files), os.path.getsize(a.out) // 1024))


def parse_bk(path):
    """Команды fill/setblock из .bk-скрипта в порядке исполнения."""
    ops = []
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if parts[0] == 'fill' and len(parts) >= 8:
            x0, y0, z0, x1, y1, z1 = map(int, parts[1:7])
            ops.append(('fill', x0, y0, z0, x1, y1, z1, parts[7].replace('minecraft:', '')))
        elif parts[0] == 'setblock' and len(parts) >= 5:
            ops.append(('set', int(parts[1]), int(parts[2]), int(parts[3]),
                        parts[4].replace('minecraft:', '')))
    return ops


def cmd_growth(a):
    wv = load_region(a.world, a.box)
    x0, x1, z0, z1 = a.box
    y0, y1 = a.y
    base = {(x, y, z): n for x, y, z, n in snapshot(wv, a.box, a.y)}
    inside = lambda x, z: x0 <= x <= x1 and z0 <= z <= z1

    # база: всё вокруг участка + грунт внутри (y <= y0+1)
    world = {k: v for k, v in base.items() if not inside(k[0], k[2]) or k[1] <= y0 + 1}

    ops = parse_bk(a.script) if a.script else []
    houses = []
    for spec in (a.houses or '').split(','):
        if not spec.strip():
            continue
        name, hx0, hx1, hz0, hz1 = spec.split(':')
        houses.append((name, int(hx0), int(hx1), int(hz0), int(hz1)))

    AIR = ('air', 'cave_air', 'void_air')

    def put(x, y, z, name):
        if name in AIR:
            world.pop((x, y, z), None)
        else:
            world[(x, y, z)] = name

    # рамки кадров: после каждых N команд + по одному дому
    steps = []
    step = max(1, len(ops) // a.steps) if ops else 0
    for i, op in enumerate(ops):
        if op[0] == 'fill':
            _, fx0, fy0, fz0, fx1, fy1, fz1, name = op
            for x in range(min(fx0, fx1), max(fx0, fx1) + 1):
                for z in range(min(fz0, fz1), max(fz0, fz1) + 1):
                    for y in range(min(fy0, fy1), max(fy0, fy1) + 1):
                        put(x, y, z, name)
        else:
            _, sx, sy, sz, name = op
            put(sx, sy, sz, name)
        if step and (i + 1) % step == 0:
            steps.append(('скрипт %d/%d' % (i + 1, len(ops)), dict(world)))
    for idx, (name, hx0, hx1, hz0, hz1) in enumerate(houses, 1):
        for (x, y, z), n in base.items():
            if hx0 <= x <= hx1 and hz0 <= z <= hz1 and y0 <= y <= y1:
                world[(x, y, z)] = n
        steps.append(('дом %d/%d — %s' % (idx, len(houses), name), dict(world)))
    if not steps:
        steps.append(('финал', dict(world)))

    center = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    w, h = a.size
    os.makedirs(a.frames, exist_ok=True)
    files = []
    for i, (caption, state) in enumerate(steps):
        img = Image.new('RGB', (w, h), (18, 19, 23))
        dr = ImageDraw.Draw(img)
        cam = Camera(a.az, a.elev, a.scale, (w, h), center)
        draw_world(dr, cam, [(x, y, z, n) for (x, y, z), n in state.items()
                             if inside(x, z)], a.label, caption)
        p = os.path.join(a.frames, 'growth_%02d.png' % i)
        img.save(p)
        files.append(p)
    gif(files, a.out, a.duration)
    print('OUT %s %d кадров %d KB' % (a.out, len(files), os.path.getsize(a.out) // 1024))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p):
        p.add_argument('--world', required=True)
        p.add_argument('--box', nargs=4, type=int, required=True)
        p.add_argument('--y', nargs=2, type=int, default=[60, 82])
        p.add_argument('--scale', type=float, default=7.0)
        p.add_argument('--size', nargs=2, type=int, default=[720, 500])
        p.add_argument('--elev', type=float, default=26.0)
        p.add_argument('--out', required=True)
        p.add_argument('--frames', default='/tmp/clipframes')
        p.add_argument('--duration', type=int, default=110)
        p.add_argument('--label', default='')

    o = sub.add_parser('orbit')
    common(o)
    o.add_argument('--frames-count', type=int, default=20)
    o.set_defaults(func=cmd_orbit)

    g = sub.add_parser('growth')
    common(g)
    g.add_argument('--script', default='')
    g.add_argument('--houses', default='')
    g.add_argument('--az', type=float, default=35.0)
    g.add_argument('--steps', type=int, default=14)
    g.set_defaults(func=cmd_growth)

    a = ap.parse_args()
    a.func(a)


if __name__ == '__main__':
    main()
