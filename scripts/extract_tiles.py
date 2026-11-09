"""Protomaps のベースマップ (PMTiles) から指定範囲だけを切り出してローカル用ファイルを作る。

    python scripts/extract_tiles.py --out maps/tiles/kyobashi.pmtiles

- Protomaps の公開ビルド (https://build.protomaps.com/<日付>.pmtiles, 全世界 約 140GB) に
  HTTP Range リクエストを送り、範囲内のタイルだけを取得する (全体はダウンロードしない)
- 一度作ったファイルはアプリがローカルで配信するため、実行時に外部 API へは一切アクセスしない
- データ: © OpenStreetMap contributors (ODbL)、Protomaps basemap
"""

from __future__ import annotations

import argparse
import math
import sys
import urllib.request
from pathlib import Path

from pmtiles.tile import Compression, deserialize_directory, deserialize_header, find_tile, zxy_to_tileid
from pmtiles.writer import write

DEFAULT_BUILD = "https://build.protomaps.com/20261108.pmtiles"
# 大阪府 京橋付近 (JR 京橋駅・大阪ビジネスパーク・大阪城北側を含む範囲)
DEFAULT_BBOX = (135.5150, 34.6800, 135.5500, 34.7080)
USER_AGENT = "mikke-tile-extract/1.0"


class RangeSource:
    def __init__(self, url: str):
        self.url = url
        self.requests = 0
        self.bytes = 0

    def __call__(self, offset: int, length: int) -> bytes:
        req = urllib.request.Request(self.url, headers={  # noqa: S310 (main() で https のみに制限)
            "Range": f"bytes={offset}-{offset + length - 1}", "User-Agent": USER_AGENT,
        })
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (https 固定の公開ビルド)
            if resp.status != 206:
                raise RuntimeError(f"Range リクエストに対応していない応答です: {resp.status}")
            data = resp.read()
        self.requests += 1
        self.bytes += len(data)
        return data


class CachedReader:
    def __init__(self, source: RangeSource):
        self.src = source
        self.header = deserialize_header(source(0, 127))
        self._dirs: dict[tuple[int, int], list] = {}

    def _directory(self, offset: int, length: int):
        key = (offset, length)
        if key not in self._dirs:
            self._dirs[key] = deserialize_directory(self.src(offset, length))
        return self._dirs[key]

    def metadata(self) -> dict:
        import gzip
        import json

        h = self.header
        raw = self.src(h["metadata_offset"], h["metadata_length"])
        if h["internal_compression"] == Compression.GZIP:
            raw = gzip.decompress(raw)
        return json.loads(raw)

    def locate(self, tile_id: int):
        h = self.header
        off, length = h["root_offset"], h["root_length"]
        for _ in range(4):
            entry = find_tile(self._directory(off, length), tile_id)
            if entry is None:
                return None
            if entry.run_length == 0:
                off, length = h["leaf_directory_offset"] + entry.offset, entry.length
                continue
            return h["tile_data_offset"] + entry.offset, entry.length
        return None


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=DEFAULT_BUILD)
    ap.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_BBOX, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    ap.add_argument("--maxzoom", type=int, default=15)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if not args.url.startswith("https://"):
        print("URL は https:// のみ対応します", file=sys.stderr)
        return 2

    src = RangeSource(args.url)
    reader = CachedReader(src)
    h = reader.header
    maxz = min(args.maxzoom, h["max_zoom"])
    minlon, minlat, maxlon, maxlat = args.bbox

    tiles: list[tuple[int, int, int, int]] = []
    for z in range(0, maxz + 1):
        x0, y0 = lonlat_to_tile(minlon, maxlat, z)
        x1, y1 = lonlat_to_tile(maxlon, minlat, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                tiles.append((zxy_to_tileid(z, x, y), z, x, y))
    tiles.sort()
    print(f"対象タイル: {len(tiles)} 枚 (z0-{maxz})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with write(str(args.out)) as w:
        for tile_id, _z, _x, _y in tiles:
            loc = reader.locate(tile_id)
            if loc is None:
                continue
            w.write_tile(tile_id, src(*loc))
            written += 1
        meta = reader.metadata()
        meta["description"] = "Protomaps basemap extract: 大阪府 京橋付近 (mikke ローカル用)"
        header = dict(h)
        header.update(
            min_lon_e7=int(minlon * 1e7), min_lat_e7=int(minlat * 1e7),
            max_lon_e7=int(maxlon * 1e7), max_lat_e7=int(maxlat * 1e7),
            center_zoom=15, center_lon_e7=int((minlon + maxlon) / 2 * 1e7),
            center_lat_e7=int((minlat + maxlat) / 2 * 1e7),
        )
        w.finalize(header, meta)
    print(f"書き込み: {written} 枚 → {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")
    print(f"HTTP リクエスト {src.requests} 回 / 受信 {src.bytes / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
