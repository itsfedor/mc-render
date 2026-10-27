#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Region/anvil reader + terrain ASCII map for the future village area.

Reads .mca region files (live copy or test-server world), decodes:
 - Heightmaps (MOTION_BLOCKING, 9-bit packed, 1.18+ format)
 - block_states palettes per section (surface block classification)
 - biome palettes per section
and prints an ASCII height map + stats for the requested area.
"""
import io, os, sys, zlib, gzip, math, json
import numpy as np
import nbtlib

MASK64 = (1 << 64) - 1


def read_region_chunks(path):
    """Yield (cx, cz, nbt_root) for every chunk in the region file."""
    with open(path, 'rb') as fh:
        header = fh.read(8192)
    out = {}
    for i in range(1024):
        off = (header[i*4] << 16) | (header[i*4+1] << 8) | header[i*4+2]
        sectors = header[i*4+3]
        if off == 0 and sectors == 0:
            continue
        cx = i % 32
        cz = i // 32
        with open(path, 'rb') as fh:
            fh.seek(off * 4096)
            ln = int.from_bytes(fh.read(4), 'big')
            comp = fh.read(1)[0]
            data = fh.read(ln - 1)
        if comp == 1:
            data = gzip.decompress(data)
        elif comp == 2:
            data = zlib.decompress(data)
        elif comp == 3:
            pass
        elif comp == 4:
            import lz4.frame  # may be missing; only if needed
            data = lz4.frame.decompress(data)
        else:
            raise ValueError(f'unknown compression {comp}')
        root = nbtlib.File.parse(io.BytesIO(data))
        out[(cx, cz)] = root
    return out


def unpack_padded(data, bits, count):
    """Padded packing (DataVersion 4790 / MC 26.x observed): each long holds
    64//bits entries; values never cross long boundaries."""
    if data is None or len(data) == 0:
        return np.zeros(count, dtype=np.int64)
    u = np.asarray(data, dtype=np.int64).astype(np.uint64) & np.uint64(MASK64)
    per_long = 64 // bits
    need = math.ceil(count / per_long)
    u = u[:need]
    vals = np.zeros(count, dtype=np.int64)
    mask = (1 << bits) - 1
    for i in range(count):
        li = i // per_long
        off = (i % per_long) * bits
        vals[i] = (int(u[li]) >> off) & mask
    return vals


def unpack_compact(data, bits, count):
    """1.16+ compact packing: values may span long boundaries, no padding."""
    if data is None or len(data) == 0:
        return np.zeros(count, dtype=np.int64)
    u = np.asarray(data, dtype=np.int64).astype(np.uint64) & np.uint64(MASK64)
    per_long = 64 // bits
    need = math.ceil(count / per_long)
    u = u[:need]
    vals = np.zeros(count, dtype=np.int64)
    for i in range(count):
        start = i * bits
        li = start >> 6
        off = start & 63
        v = int(u[li]) >> off
        if off + bits > 64 and li + 1 < len(u):
            v |= int(u[li + 1]) << (64 - off)
        vals[i] = v & ((1 << bits) - 1)
    return vals


def infer_bits_from_len(data_len, count, min_bits=1, max_bits=12):
    """Padded packing: data_len = ceil(count / (64//bits)) -> unique for most bits."""
    cands = []
    for b in range(max_bits, min_bits - 1, -1):
        per_long = 64 // b
        if per_long == 0:
            continue
        if math.ceil(count / per_long) == data_len:
            cands.append(b)
    return cands


def decode_section_blocks(sec):
    bs = sec.get('block_states')
    if bs is None:
        return None
    pal = bs.get('palette')
    if pal is None:
        return None
    pal = [str(p.get('Name', p)) for p in pal]
    n = len(pal)
    if n == 1:
        return pal, None
    data = bs.get('data')
    if data is None or len(data) == 0:
        return pal, None
    cands = infer_bits_from_len(len(data), 4096, min_bits=1, max_bits=12)
    # 1.16+ rule: block states use at least 4 bits; keep candidates >= needed for palette
    need = max(1, (n - 1).bit_length())
    good = [b for b in cands if b >= need]
    order = sorted(good if good else cands, key=lambda b: abs(b - max(4, need)))
    for b in order:
        vals = unpack_padded(data, b, 4096)
        if vals.max() < n:
            return pal, vals
    return pal, unpack_padded(data, max(4, need), 4096)


def decode_section_biomes(sec):
    bio = sec.get('biomes')
    if bio is None:
        return None
    pal = bio.get('palette')
    if pal is None:
        return None
    pal = [str(p) for p in pal]
    n = len(pal)
    if n == 0:
        return None
    if n == 1:
        return pal, None
    data = bio.get('data')
    if data is None or len(data) == 0:
        return pal, None
    cands = infer_bits_from_len(len(data), 64, min_bits=1, max_bits=8)
    need = max(1, (n - 1).bit_length())
    good = [b for b in cands if b >= need]
    for b in sorted(good if good else cands):
        vals = unpack_padded(data, b, 64)
        if vals.max() < n:
            return pal, vals
    return pal, unpack_padded(data, need, 64)


def decode_heightmap(root, which='MOTION_BLOCKING'):
    hm = root.get('Heightmaps')
    if hm is None:
        return None
    arr = hm.get(which) or hm.get('WORLD_SURFACE') or hm.get('MOTION_BLOCKING_NO_LEAVES')
    if arr is None:
        return None
    data = arr
    cands = infer_bits_from_len(len(data), 256, min_bits=8, max_bits=11)
    order = sorted(cands, key=lambda b: abs(b - 9))
    best = None
    for b in order:
        vals = unpack_padded(data, b, 256).reshape(16, 16)
        if vals.max() <= 384:  # -64..320 world, heightmap value = y+1
            if best is None or abs(b - 9) < abs(best[0] - 9):
                best = (b, vals)
    if best is None:
        return unpack_padded(data, 9, 256).reshape(16, 16)
    return best[1]


class WorldView:
    def __init__(self, region_paths):
        self.chunks = {}
        for p in region_paths:
            base = os.path.basename(p)
            parts = base.replace('.mca', '').split('.')
            rx, rz = int(parts[1]), int(parts[2])
            ch = read_region_chunks(p)
            for (lcx, lcz), root in ch.items():
                self.chunks[(rx * 32 + lcx, rz * 32 + lcz)] = root
        self.sections = {}
        self.dec_cache = {}

    def _decoded(self, cx, cz, sy, kind):
        key = (cx, cz, sy, kind)
        if key not in self.dec_cache:
            sec = self.section(cx, cz, sy)
            if sec is None:
                self.dec_cache[key] = None
            elif kind == 'blocks':
                self.dec_cache[key] = decode_section_blocks(sec)
            else:
                self.dec_cache[key] = decode_section_biomes(sec)
        return self.dec_cache[key]

    def chunk(self, cx, cz):
        return self.chunks.get((cx, cz))

    def section(self, cx, cz, sy):
        key = (cx, cz, sy)
        if key in self.sections:
            return self.sections[key]
        root = self.chunk(cx, cz)
        sec = None
        if root is not None:
            for s in root.get('sections', []):
                if int(s.get('Y', 9999)) == sy:
                    sec = s
                    break
        self.sections[key] = sec
        return sec

    def height_at(self, x, z):
        cx, cz = x >> 4, z >> 4
        root = self.chunk(cx, cz)
        if root is None:
            return None
        hm = decode_heightmap(root)
        if hm is None:
            return None
        return int(hm[z & 15][x & 15])

    def biome_at(self, x, z, y):
        cx, cz = x >> 4, z >> 4
        dec = self._decoded(cx, cz, y >> 4, 'biomes')
        if dec is None:
            return None
        pal, vals = dec
        if vals is None:
            return pal[0]
        lx, ly, lz = x & 15, y & 15, z & 15
        idx = ((ly >> 2) << 4) | ((lz >> 2) << 2) | (lx >> 2)
        if idx >= len(vals):
            idx = ((lx >> 2) << 4) | ((lz >> 2) << 2) | (ly >> 2)
        return pal[int(vals[idx])]

    def block_at(self, x, z, y):
        cx, cz = x >> 4, z >> 4
        dec = self._decoded(cx, cz, y >> 4, 'blocks')
        if dec is None:
            return None
        pal, vals = dec
        if vals is None:
            return pal[0]
        lx, ly, lz = x & 15, y & 15, z & 15
        idx = (ly << 8) | (lz << 4) | lx
        return pal[int(vals[idx])]

    def status(self, cx, cz):
        root = self.chunk(cx, cz)
        if root is None:
            return None
        return str(root.get('Status', '?'))


def surface_column(wv, x, z):
    """Return dict with terrain surface y (from MOTION_BLOCKING_NO_LEAVES),
    top block, biome, tree-canopy flag (MB > MB_NO_LEAVES), water flag.
    Stored heightmap value = surface_block_y + 65 (world bottom = -64)."""
    root = wv.chunk(x >> 4, z >> 4)
    if root is None:
        return None
    hm = root.get('Heightmaps')
    mbnl = decode_heightmap(root, 'MOTION_BLOCKING_NO_LEAVES')
    if mbnl is None:
        return None
    terrain_y = int(mbnl[z & 15][x & 15]) - 65
    mb = decode_heightmap(root, 'MOTION_BLOCKING')
    mb_val = int(mb[z & 15][x & 15]) if mb is not None else None
    tree = (mb_val is not None and mb_val > int(mbnl[z & 15][x & 15]))
    blk = wv.block_at(x, z, terrain_y)
    biome = wv.biome_at(x, z, max(0, terrain_y))
    water = blk is not None and 'water' in blk
    return {'y': terrain_y, 'block': blk, 'biome': biome, 'tree': tree, 'water': water}


BLOCK_ABBR = {
    'minecraft:water': '~', 'minecraft:grass_block': 'g', 'minecraft:snow_block': 's',
    'minecraft:sand': 'S', 'minecraft:red_sand': 'S', 'minecraft:coarse_dirt': 'd',
    'minecraft:dirt': 'd', 'minecraft:podzol': 'p', 'minecraft:stone': '#',
    'minecraft:gravel': 'G', 'minecraft:sandstone': 'S', 'minecraft:ice': 'i',
    'minecraft:grass': 'g', 'minecraft:oak_leaves': 'T', 'minecraft:spruce_leaves': 'T',
    'minecraft:birch_leaves': 'T', 'minecraft:jungle_leaves': 'T', 'minecraft:acacia_leaves': 'T',
    'minecraft:dark_oak_leaves': 'T', 'minecraft:oak_log': 'L', 'minecraft:spruce_log': 'L',
    'minecraft:birch_log': 'L', 'minecraft:acacia_log': 'L',
    'minecraft:snow': 's', 'minecraft:andesite': '#', 'minecraft:granite': '#',
    'minecraft:diorite': '#', 'minecraft:tuff': '#', 'minecraft:clay': 'c',
    'minecraft:mossy_cobblestone': '#', 'minecraft:cobblestone': '#',
    'minecraft:smooth_basalt': '#', 'minecraft:basalt': '#',
}


def abbr(block, biome):
    """symbol for the top block; unknown -> first letter of name upper/lower."""
    if block is None:
        return '?'
    if block in BLOCK_ABBR:
        return BLOCK_ABBR[block]
    if 'leaves' in block:
        return 'T'
    if 'log' in block:
        return 'L'
    if 'water' in block:
        return '~'
    if 'snow' in block:
        return 's'
    if 'sand' in block:
        return 'S'
    name = block.split(':')[-1]
    return name[0].upper() if name else '?'


HEIGHT_LEVELS = "0123456789ABCDEFGHIJ"  # y = 60 + idx*2 roughly


def hchar(y):
    if y is None:
        return '?'
    idx = int((y - 60) / 2)
    idx = max(0, min(len(HEIGHT_LEVELS) - 1, idx))
    return HEIGHT_LEVELS[idx]


def make_maps(wv, cx0, cz0, half, title):
    """ASCII maps + stats around (cx0, cz0)."""
    import collections
    xs = range(cx0 - half, cx0 + half + 1)
    zs = range(cz0 - half, cz0 + half + 1)
    cols = {}
    for z in zs:
        for x in xs:
            cols[(x, z)] = surface_column(wv, x, z)
    # height map (symbol per height band)
    lines_h = [f'{title} HEIGHT map (terrain surface, MOTION_BLOCKING_NO_LEAVES). center=({cx0},{cz0})']
    lines_h.append('z\\x   ' + ''.join(str(abs(x) % 10) for x in xs))
    for z in zs:
        row = ''.join(hchar(cols[(x, z)]['y'] if cols[(x, z)] else None) for x in xs)
        lines_h.append(f'{z: 5d} {row}')
    lines_h.append('height legend: char idx = (y-60)//2 -> "0"=60-61 "1"=62-63 "2"=64-65 "3"=66-67 "4"=68-69 "5"=70-71 ... "9"=78-79 A=80-81 ...')
    # block map
    lines_b = [f'{title} TOP-BLOCK map  (center {cx0},{cz0})']
    lines_b.append('z\\x   ' + ''.join(str(abs(x) % 10) for x in xs))
    for z in zs:
        row = ''.join(abbr(cols[(x, z)]['block'], cols[(x, z)]['biome']) if cols[(x, z)] else '?' for x in xs)
        lines_b.append(f'{z: 5d} {row}')
    lines_b.append('block legend: g=grass_block d=dirt/coarse S=sand #=stone/rock ~=water s=snow i=ice T=leaves L=log G=gravel c=clay <=leaf_litter(l) etc')
    # tree canopy map
    lines_t = [f'{title} TREE-CANOPY map  (T = leaves/log above terrain = tree, t = leaf litter on ground)']
    lines_t.append('z\\x   ' + ''.join(str(abs(x) % 10) for x in xs))
    for z in zs:
        row = []
        for x in xs:
            c = cols[(x, z)]
            if not c:
                row.append('?')
            elif c['tree']:
                row.append('T')
            elif c['block'] and 'leaf_litter' in c['block']:
                row.append('t')
            elif c['water']:
                row.append('~')
            else:
                row.append('.')
        lines_t.append(f'{z: 5d} ' + ''.join(row))
    lines_t.append('T = canopy above (MOTION_BLOCKING > NO_LEAVES) -> tree/bush present; t = leaf litter block on ground')
    # stats
    yy = [c['y'] for c in cols.values() if c]
    blocks = collections.Counter(c['block'] for c in cols.values() if c)
    biomes = collections.Counter(c['biome'] for c in cols.values() if c and c['biome'])
    stats = {
        'area': f'{2*half+1}x{2*half+1} around ({cx0},{cz0})',
        'min_y': min(yy) if yy else None, 'max_y': max(yy) if yy else None,
        'avg_y': round(sum(yy) / len(yy), 2) if yy else None,
        'y_at_center': cols[(cx0, cz0)]['y'] if cols.get((cx0, cz0)) else None,
        'top_blocks': blocks.most_common(15),
        'biomes': biomes.most_common(10),
        'water_columns': sum(1 for c in cols.values() if c and c['water']),
        'tree_columns': sum(1 for c in cols.values() if c and c['tree']),
        'chunk_status_center': wv.status(cx0 >> 4, cz0 >> 4),
    }
    # cliff analysis: max |dy| between adjacent columns
    maxd, maxd_at = 0, None
    deltas = []
    for z in zs:
        for x in xs:
            a, b = cols.get((x, z)), cols.get((x + 1, z))
            if a and b:
                d = abs(a['y'] - b['y'])
                deltas.append(d)
                if d > maxd:
                    maxd, maxd_at = d, (x, z)
    stats['max_neighbor_delta'] = maxd
    stats['max_neighbor_delta_at'] = maxd_at
    stats['mean_neighbor_delta'] = round(sum(deltas) / len(deltas), 3) if deltas else None
    stats['deltas_gt4'] = sum(1 for d in deltas if d > 4)
    return '\n'.join(lines_h), '\n'.join(lines_b), '\n'.join(lines_t), stats


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--regions', nargs='+', required=True)
    ap.add_argument('--x', type=int, default=-54)
    ap.add_argument('--z', type=int, default=-773)
    ap.add_argument('--half', type=int, default=60)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    wv = WorldView(a.regions)
    hm, bm, tm, stats = make_maps(wv, a.x, a.z, a.half, a.out.split('/')[-1])
    txt = f'=== {a.out} ===\n' + hm + '\n\n' + bm + '\n\n' + tm + '\n\nSTATS: ' + json.dumps(stats, ensure_ascii=False, indent=1)
    with open(a.out, 'w') as fh:
        fh.write(txt)
    print(txt)
    print('chunks loaded:', len(wv.chunks))


if __name__ == '__main__':
    main()
