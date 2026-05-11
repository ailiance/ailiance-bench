#!/usr/bin/env python3
"""
Parser pure-Python pour fichiers .kicad_sch (KiCad 6 -> KiCad 10 S-expression).

Pas de dependance externe (kicad-cli absent sur GrosMac).

Capacites :
  - balanced_parens(text)               -> bool : verifie equilibre parens hors strings
  - extract_components(text)            -> [{ref, value, footprint, uuid}]
  - extract_labels(text)                -> [str] : noms de labels (locaux + globaux + hierarchiques)
  - sexpr_outermost_blocks(text, head)  -> [str] : extrait blocs balances commencant par "(head ..."
  - parse_summary(text)                 -> resume structurel pour scoring (legacy)
  - parse_sch(filepath_or_text)         -> {components, nets, labels} avec connectivite pin-level

Connectivite pin-level :
  1. Parse `lib_symbols` (recursivement, sub-units inclus) -> offsets relatifs des pins
  2. Pour chaque (symbol) instance -> position absolue de chaque pin
     = symbol.at + rotate(pin.local, symbol.rotation)
  3. Parse (wire), (junction), (label/global_label/hierarchical_label) avec coords
  4. Union-find sur points : tolerance ±0.01 mm pour matching position
  5. Labels associes au cluster du point le plus proche (tolerance large ~1.5mm
     car certains generateurs placent le label avec un offset visuel)
  6. Sortie : nets = clusters avec liste de pins "REF.PIN_NUMBER"

Limitations :
  - Rotations symboles : 0/90/180/270 supportees ; autres -> warning + skip rotation
  - Symboles mirror -> warning, traites comme rotation simple
  - Multi-unit symbols : chaque unit traite comme une instance
  - lib_symbols externes (non embarques) : skip silencieux, nets sans pins
"""
from __future__ import annotations

import math
import re
import sys


_PROP_RE = re.compile(r'\(property\s+"([^"]+)"\s+"([^"]*)"', re.S)
_LABEL_RE = re.compile(r'\((?:label|global_label|hierarchical_label)\s+"([^"]+)"', re.S)
_NUMBER_RE = re.compile(r'\(number\s+"([^"]+)"')
_AT_RE = re.compile(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\s*\)')
_LIB_ID_RE = re.compile(r'\(lib_id\s+"([^"]+)"')
_UUID_RE = re.compile(r'\(uuid\s+"([^"]+)"')
_MIRROR_RE = re.compile(r'\(mirror\s+([xy]+)\s*\)')

# Tolerances (mm)
TOL_POS = 0.01           # union-find position matching
TOL_LABEL = 1.5          # label-to-cluster matching (KiCad text offset can be ~0.635mm)


# --------------------------------------------------------------------------- #
# S-expression utilities (legacy + reusable)
# --------------------------------------------------------------------------- #


def balanced_parens(s: str) -> bool:
    depth = 0
    in_str = False
    esc = False
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _iter_sexpr_blocks(text: str, head: str, start: int = 0, end: int | None = None):
    """Yield (start, end+1, block_str) for each top-level (head ...) balanced block."""
    needle = "(" + head
    i = start
    n = end if end is not None else len(text)
    while True:
        idx = text.find(needle, i, n)
        if idx == -1:
            return
        after = idx + len(needle)
        if after < n and not (text[after].isspace() or text[after] in "()"):
            i = idx + 1
            continue
        depth = 0
        in_str = False
        esc = False
        block_end = None
        for j in range(idx, n):
            ch = text[j]
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    block_end = j + 1
                    break
        if block_end is None:
            return
        yield idx, block_end, text[idx:block_end]
        i = block_end


def sexpr_outermost_blocks(text: str, head: str) -> list[str]:
    return [blk for _, _, blk in _iter_sexpr_blocks(text, head)]


def _iter_sexpr_blocks_anywhere(text: str, head: str):
    """Yield ALL (head ...) balanced blocks, even nested. Walk char by char."""
    needle = "(" + head
    n = len(text)
    i = 0
    while i < n:
        idx = text.find(needle, i)
        if idx == -1:
            return
        after = idx + len(needle)
        if after < n and not (text[after].isspace() or text[after] in "()"):
            i = idx + 1
            continue
        depth = 0
        in_str = False
        esc = False
        block_end = None
        for j in range(idx, n):
            ch = text[j]
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    block_end = j + 1
                    break
        if block_end is None:
            return
        yield idx, block_end, text[idx:block_end]
        i = idx + len(needle)  # advance past head only, allows nested matches


def _extract_lib_symbols_block(text: str) -> str:
    blocks = sexpr_outermost_blocks(text, "lib_symbols")
    return blocks[0] if blocks else ""


# --------------------------------------------------------------------------- #
# Legacy API (preserved)
# --------------------------------------------------------------------------- #


def extract_components(text: str) -> list[dict]:
    """Extract instance components: ref, value, footprint, uuid (uuid optional)."""
    lib_block = _extract_lib_symbols_block(text)
    lib_span = (text.find(lib_block), text.find(lib_block) + len(lib_block)) if lib_block else (-1, -1)

    out = []
    seen_refs = set()
    for start, end, block in _iter_sexpr_blocks(text, "symbol"):
        if lib_block and lib_span[0] <= start < lib_span[1]:
            continue
        if "(lib_id" not in block[:200] and "(at " not in block[:300]:
            continue
        props = dict(_PROP_RE.findall(block))
        ref = props.get("Reference", "")
        if not ref or not any(c.isdigit() for c in ref):
            continue
        if ref in seen_refs:
            continue
        seen_refs.add(ref)
        # First top-level uuid in the block (the symbol's own uuid)
        m_uuid = _UUID_RE.search(block)
        out.append({
            "ref": ref,
            "value": props.get("Value", ""),
            "footprint": props.get("Footprint", ""),
            "uuid": m_uuid.group(1) if m_uuid else "",
        })
    return out


def extract_labels(text: str) -> list[str]:
    """Extract every label / global_label / hierarchical_label name (deduped, ordered)."""
    seen = set()
    out = []
    for m in _LABEL_RE.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def parse_summary(text: str) -> dict:
    """Return a structural summary used by phase2 scoring (legacy)."""
    has_kicad_sch = text.lstrip().startswith("(kicad_sch")
    n_symbols_total = len(sexpr_outermost_blocks(text, "symbol"))
    has_lib_symbols = bool(_extract_lib_symbols_block(text))
    components = extract_components(text)
    labels = extract_labels(text)
    has_uuid = "(uuid " in text
    has_version = bool(re.search(r"\(version\s+\d", text))
    parens_ok = balanced_parens(text)
    return {
        "balanced_parens": parens_ok,
        "starts_with_kicad_sch": has_kicad_sch,
        "has_version": has_version,
        "has_lib_symbols": has_lib_symbols,
        "has_uuid": has_uuid,
        "n_symbols_total": n_symbols_total,
        "n_components": len(components),
        "n_labels": len(labels),
        "components": components,
        "labels": labels,
    }


# --------------------------------------------------------------------------- #
# Connectivity (NEW)
# --------------------------------------------------------------------------- #


_WARNINGS: list[str] = []


def _warn(msg: str) -> None:
    _WARNINGS.append(msg)


def _parse_at(block: str) -> tuple[float, float, float] | None:
    """Find the FIRST (at x y [rot]) inside a block (typically the head's own at)."""
    m = _AT_RE.search(block)
    if not m:
        return None
    x = float(m.group(1))
    y = float(m.group(2))
    r = float(m.group(3)) if m.group(3) is not None else 0.0
    return (x, y, r)


def _parse_lib_symbols(text: str) -> dict[str, list[dict]]:
    """Parse lib_symbols section -> {lib_id: [{number, x, y, angle, length}]}.

    Recursively descends into sub-symbols (sub-units like FOO_0_1, FOO_1_1).
    A pin's (at x y angle) gives the pin's CONNECTION point and direction.
    """
    lib_block = _extract_lib_symbols_block(text)
    if not lib_block:
        return {}

    # Top-level symbols inside lib_symbols are the master lib defs
    # Their first quoted token is "libname:symname"
    out: dict[str, list[dict]] = {}
    # Walk the lib_block's CONTENT, not the wrapper
    inner_start = lib_block.find("(symbol")
    if inner_start < 0:
        return {}
    # We need to iterate top-level (symbol "...") inside lib_block
    for s, e, blk in _iter_sexpr_blocks(lib_block, "symbol"):
        # extract first quoted string after "symbol"
        m = re.match(r'\(symbol\s+"([^"]+)"', blk)
        if not m:
            continue
        lib_id = m.group(1)
        pins = _collect_pins_recursive(blk)
        if pins:
            out[lib_id] = pins
    return out


def _collect_pins_recursive(block: str) -> list[dict]:
    """Find every (pin ...) block inside `block` and extract number/at/length."""
    pins: list[dict] = []
    for s, e, pblk in _iter_sexpr_blocks_anywhere(block, "pin"):
        # skip the (pin "N" (uuid ...)) shortform used in instance symbols (no inner content)
        # those instance pins do NOT have (at ...) — they're just refs to lib pins
        m_at = _AT_RE.search(pblk)
        m_num = _NUMBER_RE.search(pblk)
        m_len = re.search(r'\(length\s+([\d.]+)\)', pblk)
        if not m_at or not m_num:
            continue
        try:
            x = float(m_at.group(1))
            y = float(m_at.group(2))
            angle = float(m_at.group(3)) if m_at.group(3) is not None else 0.0
        except ValueError:
            continue
        length = float(m_len.group(1)) if m_len else 0.0
        pins.append({
            "number": m_num.group(1),
            "x": x,
            "y": y,
            "angle": angle,
            "length": length,
        })
    # dedupe by number (lib symbol may define same pin in multiple sub-bodies)
    seen = set()
    deduped = []
    for p in pins:
        if p["number"] in seen:
            continue
        seen.add(p["number"])
        deduped.append(p)
    return deduped


def _rotate_local(px: float, py: float, srot: float) -> tuple[float, float]:
    """Rotate local pin pos by symbol rotation (degrees, CCW in math = CW in screen)."""
    r = int(round(srot)) % 360
    if r == 0:
        return (px, py)
    if r == 90:
        return (-py, px)
    if r == 180:
        return (-px, -py)
    if r == 270:
        return (py, -px)
    # exotic: fall back to math rotation
    _warn(f"non-cardinal symbol rotation {srot}, using math rotation")
    a = math.radians(srot)
    c, s = math.cos(a), math.sin(a)
    return (px * c - py * s, px * s + py * c)


def _parse_instances(text: str, lib_pins: dict[str, list[dict]]) -> list[dict]:
    """Parse instance (symbol ...) blocks (those NOT in lib_symbols).

    Returns: [{ref, lib_id, x, y, rot, mirror, abs_pins: [{number, x, y}], uuid}]
    """
    lib_block = _extract_lib_symbols_block(text)
    lib_span = (text.find(lib_block), text.find(lib_block) + len(lib_block)) if lib_block else (-1, -1)

    out = []
    seen_refs = set()
    for start, end, block in _iter_sexpr_blocks(text, "symbol"):
        if lib_block and lib_span[0] <= start < lib_span[1]:
            continue
        if "(lib_id" not in block[:300]:
            continue
        m_lib = _LIB_ID_RE.search(block)
        if not m_lib:
            continue
        lib_id = m_lib.group(1)
        # symbol's own (at) is the first one in the block (after lib_id usually)
        # Use the at after lib_id to be safe (skip the (at) inside (property "..." (at ...)))
        # Strategy: find first (at ...) NOT inside a (property block. Easier: take the
        # at IMMEDIATELY following lib_id.
        sub_after_libid = block[m_lib.end():]
        m_at = _AT_RE.search(sub_after_libid)
        if not m_at:
            continue
        sx = float(m_at.group(1))
        sy = float(m_at.group(2))
        srot = float(m_at.group(3)) if m_at.group(3) is not None else 0.0

        m_mirror = _MIRROR_RE.search(block[:m_lib.end() + 200])
        mirror = m_mirror.group(1) if m_mirror else None
        if mirror:
            _warn(f"symbol with mirror={mirror} at ({sx},{sy}) — mirror not fully handled")

        props = dict(_PROP_RE.findall(block))
        ref = props.get("Reference", "")
        if not ref or not any(c.isdigit() for c in ref):
            continue
        if ref in seen_refs:
            continue
        seen_refs.add(ref)

        m_uuid = _UUID_RE.search(block)
        uuid = m_uuid.group(1) if m_uuid else ""

        # Compute absolute pin positions
        abs_pins = []
        pins_for_lib = lib_pins.get(lib_id, [])
        for p in pins_for_lib:
            rx, ry = _rotate_local(p["x"], p["y"], srot)
            ax = sx + rx
            ay = sy + ry
            # Apply mirror (best-effort): mirror "x" flips x around symbol center,
            # mirror "y" flips y. Already-rotated coords -> negate component.
            if mirror == "x":
                ax = sx - rx
            elif mirror == "y":
                ay = sy - ry
            abs_pins.append({
                "number": p["number"],
                "x": ax,
                "y": ay,
            })

        out.append({
            "ref": ref,
            "lib_id": lib_id,
            "value": props.get("Value", ""),
            "footprint": props.get("Footprint", ""),
            "uuid": uuid,
            "x": sx,
            "y": sy,
            "rot": srot,
            "mirror": mirror,
            "abs_pins": abs_pins,
        })
    return out


_XY_RE = re.compile(r'\(xy\s+(-?[\d.]+)\s+(-?[\d.]+)\)')


def _parse_wires(text: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Parse all (wire ... (pts (xy ...) (xy ...) ...) ...) -> list of segments.

    A wire may have more than 2 points (polyline); we emit consecutive segment
    pairs so endpoints get unioned correctly.
    """
    out = []
    for s, e, blk in _iter_sexpr_blocks(text, "wire"):
        xys = _XY_RE.findall(blk)
        pts = [(float(x), float(y)) for x, y in xys]
        if len(pts) < 2:
            continue
        for i in range(len(pts) - 1):
            out.append((pts[i], pts[i + 1]))
    return out


def _parse_junctions(text: str) -> list[tuple[float, float]]:
    out = []
    for s, e, blk in _iter_sexpr_blocks(text, "junction"):
        at = _parse_at(blk)
        if at:
            out.append((at[0], at[1]))
    return out


def _parse_labels_with_pos(text: str) -> list[dict]:
    """Parse label/global_label/hierarchical_label with their (at x y) positions."""
    out = []
    for kind in ("label", "global_label", "hierarchical_label"):
        for s, e, blk in _iter_sexpr_blocks(text, kind):
            m_name = re.match(r'\(' + kind + r'\s+"([^"]+)"', blk)
            if not m_name:
                continue
            at = _parse_at(blk)
            if not at:
                continue
            out.append({
                "kind": kind,
                "name": m_name.group(1),
                "x": at[0],
                "y": at[1],
            })
    return out


# --------------------------------------------------------------------------- #
# Union-find on geometric points
# --------------------------------------------------------------------------- #


class _UF:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def add(self, x: int) -> None:
        if x not in self.parent:
            self.parent[x] = x

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.add(a)
        self.add(b)
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _qkey(x: float, y: float, tol: float = TOL_POS) -> tuple[int, int]:
    """Quantize a point to a grid of size `tol` for hash-based matching."""
    return (int(round(x / tol)), int(round(y / tol)))


def _build_clusters(
    wires: list[tuple[tuple[float, float], tuple[float, float]]],
    junctions: list[tuple[float, float]],
    pin_points: list[tuple[float, float, str]],  # (x, y, "REF.NUM")
) -> dict[int, dict]:
    """Run union-find on all geometric points.

    Returns: {cluster_root_id: {"points": [(x,y), ...], "pins": [refdes, ...]}}
    """
    uf = _UF()
    # Map quantized point key -> id
    key_to_id: dict[tuple[int, int], int] = {}
    id_to_xy: dict[int, tuple[float, float]] = {}
    next_id = [0]

    def get_id(x: float, y: float) -> int:
        k = _qkey(x, y)
        if k in key_to_id:
            return key_to_id[k]
        i = next_id[0]
        next_id[0] += 1
        key_to_id[k] = i
        id_to_xy[i] = (x, y)
        uf.add(i)
        return i

    # Wires: union endpoints AND mark every point along the path so labels/pins
    # can sit anywhere on the wire.
    # KiCad wires are straight segments; for now treat as connecting just the two
    # endpoints. Mid-wire connections require junctions.
    for (p1, p2) in wires:
        a = get_id(*p1)
        b = get_id(*p2)
        uf.union(a, b)

    # Pins: register; will be unioned to cluster on match
    for (x, y, label) in pin_points:
        get_id(x, y)

    # Junctions: union with anything within TOL_POS at same point
    for (x, y) in junctions:
        get_id(x, y)
        # additionally check tiny neighborhood (already collapsed via quantize)

    # Build cluster map
    clusters: dict[int, dict] = {}
    for i, (x, y) in id_to_xy.items():
        root = uf.find(i)
        clusters.setdefault(root, {"points": [], "pins": []})
        clusters[root]["points"].append((x, y))

    # Attach pin labels to their cluster
    pin_key_to_label: dict[tuple[int, int], list[str]] = {}
    for (x, y, lbl) in pin_points:
        k = _qkey(x, y)
        pin_key_to_label.setdefault(k, []).append(lbl)

    for k, lbls in pin_key_to_label.items():
        if k not in key_to_id:
            continue
        i = key_to_id[k]
        root = uf.find(i)
        clusters[root]["pins"].extend(lbls)

    return clusters


def _assign_labels_to_clusters(
    labels: list[dict],
    clusters: dict[int, dict],
) -> dict[int, str]:
    """For each label, find the nearest cluster point within TOL_LABEL.

    Returns: {cluster_root: net_name}.
    Multiple labels with same name on different clusters all win their cluster.
    Conflicts (different names on same cluster) -> first label wins, others noted.
    """
    name_for: dict[int, str] = {}
    if not clusters:
        return name_for

    # Flatten cluster points with root ids for quick nearest search
    pts: list[tuple[float, float, int]] = []
    for root, c in clusters.items():
        for (x, y) in c["points"]:
            pts.append((x, y, root))

    if not pts:
        return name_for

    for lab in labels:
        lx, ly, lname = lab["x"], lab["y"], lab["name"]
        best_d2 = None
        best_root = None
        for (px, py, root) in pts:
            d2 = (px - lx) ** 2 + (py - ly) ** 2
            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                best_root = root
        if best_d2 is None:
            continue
        if math.sqrt(best_d2) > TOL_LABEL:
            _warn(f"label {lname!r} at ({lx},{ly}) no cluster within {TOL_LABEL}mm "
                  f"(closest: {math.sqrt(best_d2):.3f}mm)")
            continue
        if best_root in name_for and name_for[best_root] != lname:
            _warn(f"cluster {best_root} got conflicting labels: "
                  f"{name_for[best_root]!r} vs {lname!r}")
            continue
        name_for[best_root] = lname

    return name_for


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def parse_sch(filepath_or_text: str) -> dict:
    """Parse a .kicad_sch file (or raw text) -> {components, nets, labels}.

    Returns:
        {
          "components": [{"ref","value","footprint","uuid"}, ...],
          "nets":       [{"name", "pins": ["REF.PIN_NUM", ...]}, ...],
          "labels":     ["VCC", "GND", ...],   # backward-compat: dedup label NAMES
          "warnings":   [...]
        }

    `pins` may be empty for clusters with no resolved pin geometry; the cluster is
    still emitted IFF it has a label name. Auto-named clusters ("auto-net-N") are
    only emitted for clusters that have at least one pin AND no label.
    """
    global _WARNINGS
    _WARNINGS = []

    # Allow filepath or raw text
    text = filepath_or_text
    looks_like_path = (
        len(filepath_or_text) < 4096
        and "\n" not in filepath_or_text
        and (filepath_or_text.endswith(".kicad_sch") or filepath_or_text.endswith(".sch"))
    )
    if looks_like_path:
        try:
            with open(filepath_or_text) as f:
                text = f.read()
        except OSError:
            # Treat as raw text
            text = filepath_or_text

    components = extract_components(text)
    label_names = extract_labels(text)

    # Connectivity
    lib_pins = _parse_lib_symbols(text)
    instances = _parse_instances(text, lib_pins)
    wires = _parse_wires(text)
    junctions = _parse_junctions(text)
    labels_pos = _parse_labels_with_pos(text)

    # Collect (x, y, "REF.NUM") for every absolute pin
    pin_points: list[tuple[float, float, str]] = []
    for inst in instances:
        for p in inst["abs_pins"]:
            pin_points.append((p["x"], p["y"], f"{inst['ref']}.{p['number']}"))

    clusters = _build_clusters(wires, junctions, pin_points)
    name_for = _assign_labels_to_clusters(labels_pos, clusters)

    # Build nets list
    nets: list[dict] = []
    auto_idx = 0
    for root, c in clusters.items():
        unique_pins = sorted(set(c["pins"]))
        name = name_for.get(root)
        if name is None:
            if not unique_pins:
                continue
            name = f"auto-net-{auto_idx}"
            auto_idx += 1
        nets.append({"name": name, "pins": unique_pins})

    # Group nets that share the same name (label appearing on multiple wire
    # clusters representing one logical net).
    by_name: dict[str, list[str]] = {}
    order: list[str] = []
    for net in nets:
        if net["name"] not in by_name:
            order.append(net["name"])
            by_name[net["name"]] = []
        for p in net["pins"]:
            if p not in by_name[net["name"]]:
                by_name[net["name"]].append(p)

    # Fallback: if NO nets emerged from geometry but labels exist, emit one
    # empty-pin net per unique label name. This keeps the legacy "name-only"
    # behavior so abstract/synthetic schematics without lib_symbols geometry
    # still produce a useful nets list (graceful degradation).
    if not by_name and label_names:
        for n in label_names:
            order.append(n)
            by_name[n] = []

    merged = [{"name": n, "pins": sorted(by_name[n])} for n in order]

    return {
        "components": components,
        "nets": merged,
        "labels": label_names,
        "warnings": list(_WARNINGS),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


if __name__ == "__main__":
    import json
    import pathlib

    if len(sys.argv) < 2:
        demo = '''(kicad_sch (version 20250114) (uuid "x")
  (lib_symbols (symbol "Device:R" (property "Reference" "R" (at 0 0 0))))
  (symbol (lib_id "Device:R") (at 1 1 0)
    (property "Reference" "R1" (at 1 1 0))
    (property "Value" "10k" (at 1 1 0))
    (property "Footprint" "Resistor_SMD:R_0603" (at 1 1 0)))
  (label "VCC" (at 0 0 0))
  (global_label "GND" (at 0 0 0))
)'''
        print(json.dumps(parse_sch(demo), indent=2))
        sys.exit(0)
    p = pathlib.Path(sys.argv[1])
    text = p.read_text()
    res = parse_sch(text)
    print(json.dumps(res, indent=2, ensure_ascii=False))
