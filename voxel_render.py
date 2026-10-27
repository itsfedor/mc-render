#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""voxel_render.py — полноценный воксельный изо-рендер участка мира.

Рисует ВСЕ блоки (не только поверхность), с отсечением скрытых граней,
формами для ступеней/плит/заборов/стен/панелей/дверей/фонарей/цепей/кроватей.
CLI: voxel_render.py REGION X0 X1 Z0 Z1 Y0 Y1 SCALE OUT [angle 0|1] [label]
"""
import os, sys, math, importlib.util
from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
ANALYZE = os.environ.get('MC_ANALYZE', os.path.join(_HERE, 'lib', 'region.py'))
spec = importlib.util.spec_from_file_location('an', ANALYZE)
an = importlib.util.module_from_spec(spec); spec.loader.exec_module(an)

REGION, X0, X1, Z0, Z1, Y0, Y1, S = sys.argv[1], *map(int, sys.argv[2:9])
OUT = sys.argv[9]
ANGLE = int(sys.argv[10]) if len(sys.argv) > 10 else 0
LABEL = sys.argv[11] if len(sys.argv) > 11 else os.path.basename(OUT)

COS, SIN = 0.8660254, 0.5
CX = (X1 - X0) + (Z1 - Z0)
CY = (Y1 - Y0)
W = int(CX * COS * S) + 60
H = int((CX * SIN + CY) * S) + 60

COLORS = {
 'calcite': (228, 224, 214), 'spruce_planks': (122, 92, 58), 'stripped_spruce_log': (176, 140, 92),
 'deepslate_tiles': (58, 58, 64), 'deepslate_tile_stairs': (64, 64, 70), 'deepslate_tile_slab': (70, 70, 76),
 'stone_bricks': (140, 140, 134), 'stone_brick_slab': (140, 140, 134), 'stone_brick_wall': (140, 140, 134),
 'glass_pane': (150, 205, 225), 'spruce_door': (104, 74, 42), 'lantern': (250, 205, 110),
 'spruce_fence': (100, 74, 44), 'spruce_stairs': (126, 96, 60), 'spruce_slab': (118, 90, 56),
 'bricks': (154, 90, 74), 'dirt_path': (154, 124, 78), 'grass_block': (104, 158, 76),
 'water': (64, 112, 190), 'sand': (222, 206, 140), 'cobblestone': (128, 128, 124),
 'cobblestone_wall': (128, 128, 124), 'oak_planks': (176, 138, 74), 'barrel': (140, 108, 66),
 'campfire': (220, 150, 70), 'bookshelf': (150, 116, 70), 'lectern': (150, 112, 62),
 'crafting_table': (146, 108, 62), 'chest': (150, 112, 60), 'furnace': (128, 126, 122),
 'smoker': (110, 106, 100), 'blast_furnace': (116, 112, 108), 'anvil': (88, 88, 92),
 'grindstone': (130, 120, 110), 'smithing_table': (110, 86, 60), 'cauldron': (96, 96, 100),
 'note_block': (120, 90, 66), 'observer': (120, 116, 110), 'piston': (150, 140, 120),
 'redstone_lamp': (210, 130, 80), 'target': (220, 210, 190), 'quartz_block': (236, 232, 224),
 'light_blue_concrete': (90, 160, 210), 'iron_chain': (112, 112, 118),
 'oak_leaves': (48, 108, 54), 'spruce_leaves': (36, 92, 48), 'birch_leaves': (88, 136, 62),
 'oak_log': (112, 86, 52), 'spruce_log': (92, 70, 44), 'birch_log': (196, 190, 176),
 'gravel': (150, 145, 140), 'stone': (140, 140, 140), 'dirt': (134, 96, 67),
 'leaf_litter': (122, 112, 62), 'short_grass': (100, 152, 72), 'tall_grass': (96, 148, 68),
 'poppy': (200, 60, 60), 'dandelion': (220, 200, 60), 'blue_bell': (110, 130, 220),
 'hay_block': (206, 180, 72), 'farmland': (110, 80, 50), 'wheat': (200, 180, 80),
 'composter': (122, 92, 52), 'moss_block': (80, 122, 62), 'spruce_trapdoor': (110, 84, 50),
 'cobweb': (225, 225, 225), 'red_bed': (170, 60, 60), 'blue_bed': (60, 90, 170),
 'gray_bed': (110, 110, 110), 'lime_bed': (120, 180, 60), 'yellow_bed': (220, 190, 70),
 'ladder': (150, 112, 66), 'bell': (220, 190, 90), 'campfire_fire': (255, 170, 60),
 'birch_planks': (198, 182, 140), 'birch_stairs': (198, 182, 140), 'birch_slab': (198, 182, 140),
 'birch_log': (216, 212, 196), 'coarse_dirt': (120, 86, 60), 'seagrass': (64, 112, 190),
 'tall_seagrass': (64, 112, 190), 'coal_ore': (92, 92, 92), 'copper_ore': (140, 120, 100),
 'iron_ore': (172, 150, 130), 'diorite': (200, 200, 200), 'andesite': (136, 136, 136),
 'granite': (154, 110, 90),
 'dark_oak_planks': (76, 57, 32), 'dark_oak_stairs': (72, 54, 30), 'dark_oak_slab': (78, 59, 34),
 'dark_oak_log': (70, 52, 30), 'dark_oak_door': (84, 62, 36), 'dark_oak_fence': (74, 56, 32),
 'smooth_quartz': (232, 228, 220), 'polished_andesite': (154, 154, 150),
 'stripped_oak_log': (178, 142, 90), 'fern': (86, 140, 66), 'oxeye_daisy': (238, 238, 226),
 'cartography_table': (108, 84, 54), 'flowering_azalea_leaves': (120, 150, 80), 'bush': (60, 110, 50),
 'purple_bed': (140, 80, 180), 'brewing_stand': (120, 100, 80), 'oak_fence': (140, 110, 70),
 'cobblestone_stairs': (128, 128, 124), 'cobblestone_slab': (128, 128, 124), 'oak_stairs': (176, 138, 74),
 'oak_slab': (176, 138, 74), 'oak_door': (150, 116, 66), 'lever': (140, 130, 110),
 'stonecutter': (130, 130, 126), 'diorite_stairs': (200, 200, 200),
}
TRANSPARENT = {'air', 'cave_air', 'void_air', 'water', 'glass', 'glass_pane', 'spruce_door',
               'spruce_fence', 'cobblestone_wall', 'stone_brick_wall', 'lantern', 'iron_chain',
               'campfire', 'spruce_trapdoor', 'cobweb', 'ladder', 'bell', 'poppy', 'dandelion',
               'short_grass', 'tall_grass', 'fern', 'wheat', 'oak_sapling', 'spruce_sapling'}


def parse(block):
    if '[' in block:
        name, props = block[:-1].split('[', 1)
        p = {}
        for kv in props.split(','):
            k, v = kv.split('=', 1)
            p[k] = v
        return name.replace('minecraft:', ''), p
    return block.replace('minecraft:', ''), {}


def is_partial(name):
    return ('slab' in name or 'stairs' in name or 'fence' in name or 'wall' in name
            or 'pane' in name or 'door' in name or 'lantern' in name or 'chain' in name
            or 'campfire' in name or 'bed' in name or 'carpet' in name or 'trapdoor' in name)


def boxes(name, p):
    """Список боксов (x0,x1,y0,y1,z0,z1) в долях блока."""
    if 'slab' in name:
        top = p.get('type') == 'top'
        return [(0, 1, 0.5, 1, 0, 1)] if top else [(0, 1, 0, 0.5, 0, 1)]
    if 'stairs' in name:
        f = p.get('facing', 'north')
        half = 1 if p.get('half') == 'top' else 0
        base = [(0, 1, 0.5, 1, 0, 1)] if half else [(0, 1, 0, 0.5, 0, 1)]
        y0, y1 = (0, 0.5) if half else (0.5, 1)
        if f == 'north':   step = (0, 1, y0, y1, 0, 0.5)
        elif f == 'south': step = (0, 1, y0, y1, 0.5, 1)
        elif f == 'east':  step = (0.5, 1, y0, y1, 0, 1)
        else:              step = (0, 0.5, y0, y1, 0, 1)
        return base + [step]
    if 'fence' in name:
        return [(0.375, 0.625, 0, 1, 0.375, 0.625)]
    if 'wall' in name:
        return [(0.3, 0.7, 0, 1, 0.3, 0.7)]
    if 'pane' in name:
        if p.get('east') == 'true' or p.get('west') == 'true':
            return [(0, 1, 0, 1, 0.4375, 0.5625)]
        return [(0.4375, 0.5625, 0, 1, 0, 1)]
    if 'door' in name:
        f = p.get('facing', 'north')
        if f in ('north', 'south'):
            return [(0, 1, 0, 1, 0.375, 0.625)]
        return [(0.375, 0.625, 0, 1, 0, 1)]
    if 'trapdoor' in name:
        return [(0, 1, 0.8, 1, 0, 1)]
    if 'lantern' in name:
        return [(0.32, 0.68, 0.08, 0.72, 0.32, 0.68)]
    if 'chain' in name:
        return [(0.44, 0.56, 0, 1, 0.44, 0.56)]
    if 'campfire' in name:
        return [(0, 1, 0, 0.42, 0, 1)]
    if 'bed' in name:
        return [(0, 1, 0, 0.56, 0, 1)]
    if 'carpet' in name:
        return [(0, 1, 0, 0.06, 0, 1)]
    return [(0, 1, 0, 1, 0, 1)]


wv = an.WorldView([REGION])


def getb(x, y, z):
    return (wv.block_at(x, z, y) or 'minecraft:air').replace('minecraft:', '')


def opaque(name):
    return name not in TRANSPARENT and name != 'air'


blocks = []
for x in range(X0, X1 + 1):
    for z in range(Z0, Z1 + 1):
        for y in range(Y0, Y1 + 1):
            raw = wv.block_at(x, z, y)
            if not raw:
                continue
            name, p = parse(raw)
            if name in ('air', 'cave_air', 'void_air'):
                continue
            blocks.append((x, y, z, name, p))

if ANGLE == 0:
    key = lambda b: (b[0] + b[1] + b[2])
else:
    key = lambda b: (-b[0] + b[1] - b[2])
blocks.sort(key=key)

img = Image.new('RGB', (W, H), (26, 27, 32))
dr = ImageDraw.Draw(img)


def P(x, y, z):
    if ANGLE == 0:
        X, Z = x - X0, z - Z0
    else:
        X, Z = X1 - x, Z1 - z
    sx = (X - Z) * COS * S + W / 2
    sy = ((X + Z) * SIN - (y - Y0)) * S + CY * S + 26
    return sx, sy


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


UNKNOWN = set()


def _guess_color(name):
    """Цвет для блока, которого нет в палитре: по ключевому слову, а не лиловый фолбэк."""
    if any(k in name for k in ('leaves', 'sapling', 'fern', 'grass', 'bush', 'flower', 'azalea', 'vine', 'moss')):
        return (74, 128, 62)
    if any(k in name for k in ('quartz', 'calcite', 'white_', 'diorite', 'snow', 'birch', 'bone')):
        return (228, 226, 218)
    if any(k in name for k in ('_log', 'wood', 'planks', 'stairs', 'slab', 'fence', 'door', 'trapdoor')):
        return (104, 80, 48)
    if any(k in name for k in ('water', 'ice', 'sea')):
        return (64, 112, 190)
    if any(k in name for k in ('wool', 'concrete', 'terracotta', 'glass')):
        return (170, 170, 166)
    return (128, 128, 124)


def color_of(name):
    if name == 'water':
        return (64, 112, 190)
    c = COLORS.get(name)
    if c is None:
        for k, v in COLORS.items():
            if name.startswith(k):
                c = v; break
    if c is None:
        UNKNOWN.add(name)
        c = _guess_color(name)
    return c


drawn = 0
for x, y, z, name, p in blocks:
    c = color_of(name)
    if name == 'water':
        above = getb(x, y + 1, z)
        if above == 'water':
            continue
        yy = y + 0.88
        pts = [P(x, yy, z), P(x + 1, yy, z), P(x + 1, yy, z + 1), P(x, yy, z + 1)]
        dr.polygon(pts, fill=c)
        continue
    bx = boxes(name, p)
    partial = is_partial(name)
    above_op = opaque(getb(x, y + 1, z))
    if ANGLE == 0:
        xp_op = opaque(getb(x + 1, y, z)); zp_op = opaque(getb(x, y, z + 1))
    else:
        xp_op = opaque(getb(x - 1, y, z)); zp_op = opaque(getb(x, y, z - 1))
    for (ax0, ax1, ay0, ay1, az0, az1) in bx:
        # top
        if partial or not above_op:
            pts = [P(x + ax0, y + ay1, z + az0), P(x + ax1, y + ay1, z + az0),
                   P(x + ax1, y + ay1, z + az1), P(x + ax0, y + ay1, z + az1)]
            dr.polygon(pts, fill=shade(c, 1.0))
        # боковая грань по X
        if partial or not xp_op:
            xp = x + (ax1 if ANGLE == 0 else ax0)
            pts = [P(xp, y + ay0, z + az0), P(xp, y + ay1, z + az0),
                   P(xp, y + ay1, z + az1), P(xp, y + ay0, z + az1)]
            dr.polygon(pts, fill=shade(c, 0.74))
        # боковая грань по Z
        if partial or not zp_op:
            zp = z + (az1 if ANGLE == 0 else az0)
            pts = [P(x + ax0, y + ay0, zp), P(x + ax0, y + ay1, zp),
                   P(x + ax1, y + ay1, zp), P(x + ax1, y + ay0, zp)]
            dr.polygon(pts, fill=shade(c, 0.56))
    drawn += 1

try:
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 15)
except Exception:
    font = ImageFont.load_default()
dr.text((12, 10), LABEL, fill=(238, 238, 244), font=font)
img.save(OUT)
print(OUT, img.size, 'blocks', drawn)
if UNKNOWN:
    sys.stderr.write('unknown-blocks %d: %s\n' % (len(UNKNOWN), ' '.join(sorted(UNKNOWN)[:15])))
