#!/usr/bin/env python3
"""Generates the PvP resource pack from vanilla Minecraft assets.

Vanilla assets are pulled from Mojang's official client jar (cached in .cache/)
so every texture in pack/ is reproducible from source instead of hand-edited.
"""

import json
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

MC_VERSION = "26.2"
PACK_FORMAT = 88

ROOT = Path(__file__).parent
CACHE = ROOT / ".cache"
VANILLA = CACHE / "vanilla" / "assets" / "minecraft"
PACK = ROOT / "pack"
MC = PACK / "assets" / "minecraft"
PVP = PACK / "assets" / "pvp"

MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


# --------------------------------------------------------------------------
# vanilla assets
# --------------------------------------------------------------------------

def fetch_vanilla():
    if VANILLA.exists():
        return
    CACHE.mkdir(exist_ok=True)
    jar = CACHE / f"client-{MC_VERSION}.jar"
    if not jar.exists():
        print(f"downloading vanilla {MC_VERSION} client jar ...")
        with urllib.request.urlopen(MANIFEST) as f:
            versions = json.load(f)["versions"]
        entry = next(v for v in versions if v["id"] == MC_VERSION)
        with urllib.request.urlopen(entry["url"]) as f:
            meta = json.load(f)
        urllib.request.urlretrieve(meta["downloads"]["client"]["url"], jar)
    print("extracting vanilla assets ...")
    with zipfile.ZipFile(jar) as z:
        for name in z.namelist():
            if name.startswith("assets/minecraft/") and not name.endswith("/"):
                z.extract(name, CACHE / "vanilla")


def van(rel):
    return Image.open(VANILLA / rel).convert("RGBA")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def write_png(path, img):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def copy_vanilla(rel):
    dst = MC / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(VANILLA / rel, dst)


def tint(img, color, strength):
    """Blend every non-transparent pixel towards color."""
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            px[x, y] = (
                round(r + (color[0] - r) * strength),
                round(g + (color[1] - g) * strength),
                round(b + (color[2] - b) * strength),
                a,
            )
    return out


def scale_alpha(img, factor):
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a:
                px[x, y] = (r, g, b, round(a * factor))
    return out


# --------------------------------------------------------------------------
# features
# --------------------------------------------------------------------------

KEEP_ROWS = 2  # of 16 rows per fire frame - a thin, fully opaque strip at the base


def low_fire():
    """Keep only the bottom of each fire frame so flames stop covering the screen."""
    for name in ("fire_0", "fire_1"):
        src = van(f"textures/block/{name}.png")
        frames = src.height // 16
        out = Image.new("RGBA", src.size, (0, 0, 0, 0))
        px_src, px_out = src.load(), out.load()
        for f in range(frames):
            top = f * 16
            for y in range(16 - KEEP_ROWS, 16):
                for x in range(16):
                    px_out[x, top + y] = px_src[x, top + y]
        write_png(MC / f"textures/block/{name}.png", out)
        copy_vanilla(f"textures/block/{name}.png.mcmeta")


OUTLINE = (120, 255, 255, 255)


def outlined_cobweb():
    """Ring every web strand with a bright outline so traps read instantly."""
    src = van("textures/block/cobweb.png")
    out = src.copy()
    px_src, px_out = src.load(), out.load()
    for y in range(src.height):
        for x in range(src.width):
            if px_src[x, y][3] > 0:
                continue
            neighbours = [
                (x + dx, y + dy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if 0 <= x + dx < src.width and 0 <= y + dy < src.height
            ]
            if any(px_src[nx, ny][3] > 0 for nx, ny in neighbours):
                px_out[x, y] = OUTLINE
    write_png(MC / "textures/block/cobweb.png", out)


def tiny_tools():
    """Shrink every handheld tool/weapon so it stops covering the target."""
    write_json(MC / "models/item/handheld.json", {
        "parent": "item/generated",
        "display": {
            "thirdperson_righthand": {
                "rotation": [0, -90, 55],
                "translation": [0, 4.0, 0.5],
                "scale": [0.6, 0.6, 0.6],
            },
            "thirdperson_lefthand": {
                "rotation": [0, 90, -55],
                "translation": [0, 4.0, 0.5],
                "scale": [0.6, 0.6, 0.6],
            },
            "firstperson_righthand": {
                "rotation": [0, -90, 25],
                "translation": [2.2, 4.6, 2.2],
                "scale": [0.42, 0.42, 0.42],
            },
            "firstperson_lefthand": {
                "rotation": [0, 90, -25],
                "translation": [2.2, 4.6, 2.2],
                "scale": [0.42, 0.42, 0.42],
            },
        },
    })


def low_shield():
    """Drop the shield out of the centre of the screen while blocking."""
    model = json.loads((VANILLA / "models/item/shield.json").read_text())
    model["display"]["firstperson_righthand"] = {
        "rotation": [0, 180, 5],
        "translation": [-14, -4, -12],
        "scale": [1.0, 1.0, 1.0],
    }
    model["display"]["firstperson_lefthand"] = {
        "rotation": [0, 180, 5],
        "translation": [14, -5, -12],
        "scale": [1.0, 1.0, 1.0],
    }
    write_json(MC / "models/item/shield.json", model)


# shield cooldown: 5 stages, stage 5 = just disabled (most red)
SHIELD_STAGES = 5
SHIELD_RED = (225, 45, 45)


def shield_cooldown():
    """Tint the shield red while it is axe-disabled, fading back as it recovers."""
    base = van("textures/entity/shield/shield_base_nopattern.png")
    for stage in range(1, SHIELD_STAGES + 1):
        strength = 0.15 + 0.15 * stage  # 0.30 .. 0.90
        write_png(PVP / f"textures/item/shield_cooldown_{stage}.png",
                  tint(base, SHIELD_RED, strength))
        write_json(PVP / f"models/item/shield_cooldown_{stage}.json", {
            "parent": "pvp:item/shield_cooldown_base",
            "textures": {"shield": f"pvp:item/shield_cooldown_{stage}"},
        })

    # Geometry mirrors vanilla ShieldModel: plate 12x22x1, handle 2x6x3.
    # UVs are the vanilla shield unwrap scaled from a 64px texture into model space.
    u = 16 / 64
    write_json(PVP / "models/item/shield_cooldown_base.json", {
        "gui_light": "front",
        "textures": {"particle": "block/dark_oak_planks"},
        "elements": [
            {
                "from": [2, -3, 9],
                "to": [14, 19, 10],
                "faces": {
                    "north": {"uv": [1 * u, 1 * u, 13 * u, 23 * u], "texture": "#shield"},
                    "south": {"uv": [14 * u, 1 * u, 26 * u, 23 * u], "texture": "#shield"},
                    "west": {"uv": [0 * u, 1 * u, 1 * u, 23 * u], "texture": "#shield"},
                    "east": {"uv": [13 * u, 1 * u, 14 * u, 23 * u], "texture": "#shield"},
                    "up": {"uv": [1 * u, 0 * u, 13 * u, 1 * u], "texture": "#shield"},
                    "down": {"uv": [13 * u, 0 * u, 25 * u, 1 * u], "texture": "#shield"},
                },
            },
            {
                "from": [7, 5, 6],
                "to": [9, 11, 9],
                "faces": {
                    "north": {"uv": [29 * u, 3 * u, 31 * u, 9 * u], "texture": "#shield"},
                    "south": {"uv": [34 * u, 3 * u, 36 * u, 9 * u], "texture": "#shield"},
                    "west": {"uv": [26 * u, 3 * u, 29 * u, 9 * u], "texture": "#shield"},
                    "east": {"uv": [31 * u, 3 * u, 34 * u, 9 * u], "texture": "#shield"},
                    "up": {"uv": [29 * u, 0 * u, 31 * u, 3 * u], "texture": "#shield"},
                    "down": {"uv": [31 * u, 0 * u, 33 * u, 3 * u], "texture": "#shield"},
                },
            },
        ],
        "display": json.loads((VANILLA / "models/item/shield.json").read_text())["display"],
    })

    special = {"type": "minecraft:shield"}
    write_json(MC / "items/shield.json", {
        "model": {
            "type": "minecraft:condition",
            "property": "minecraft:using_item",
            "on_true": {
                "type": "minecraft:special",
                "base": "minecraft:item/shield_blocking",
                "model": special,
            },
            "on_false": {
                "type": "minecraft:range_dispatch",
                "property": "minecraft:cooldown",
                "scale": SHIELD_STAGES,
                "entries": [
                    {
                        "threshold": threshold,
                        "model": {
                            "type": "minecraft:model",
                            "model": f"pvp:item/shield_cooldown_{stage}",
                        },
                    }
                    for stage, threshold in zip(
                        range(SHIELD_STAGES, 0, -1),
                        [4, 3, 2, 1, 0.01],
                    )
                ],
                "fallback": {
                    "type": "minecraft:special",
                    "base": "minecraft:item/shield",
                    "model": special,
                },
            },
        }
    })


# bow charge: red while weak, green once the shot is fully charged
BOW_RAMP = [
    (0.0, (255, 55, 55)),
    (0.3, (255, 120, 40)),
    (0.5, (255, 190, 40)),
    (0.7, (240, 230, 60)),
    (0.9, (150, 240, 80)),
    (1.0, (55, 255, 95)),
]


def ramp_color(t):
    for i in range(len(BOW_RAMP) - 1):
        t0, c0 = BOW_RAMP[i]
        t1, c1 = BOW_RAMP[i + 1]
        if t0 <= t <= t1:
            f = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(round(c0[j] + (c1[j] - c0[j]) * f) for j in range(3))
    return BOW_RAMP[-1][1]


BOW_STEPS = 10  # thresholds 0.1 .. 1.0, plus the untinted-ish fallback below 0.1


def bow_gradient():
    """Colour the bow from red to green so full charge is visible at a glance."""
    art = {
        0: van("textures/item/bow_pulling_0.png"),
        1: van("textures/item/bow_pulling_1.png"),
        2: van("textures/item/bow_pulling_2.png"),
    }

    def stage_art(t):
        # keep vanilla's string-pull artwork, only recolour it
        if t >= 0.9:
            return art[2]
        if t >= 0.65:
            return art[1]
        return art[0]

    entries = []
    for step in range(BOW_STEPS + 1):
        t = step / BOW_STEPS
        name = f"bow_pulling_{step}"
        write_png(PVP / f"textures/item/{name}.png",
                  tint(stage_art(t), ramp_color(t), 0.55))
        # parenting item/bow keeps vanilla's in-hand display transforms
        write_json(PVP / f"models/item/{name}.json", {
            "parent": "minecraft:item/bow",
            "textures": {"layer0": f"pvp:item/{name}"},
        })
        if step > 0:
            entries.append({
                "threshold": round(t, 2),
                "model": {"type": "minecraft:model", "model": f"pvp:item/{name}"},
            })

    write_json(MC / "items/bow.json", {
        "model": {
            "type": "minecraft:condition",
            "property": "minecraft:using_item",
            "on_false": {"type": "minecraft:model", "model": "minecraft:item/bow"},
            "on_true": {
                "type": "minecraft:range_dispatch",
                "property": "minecraft:use_duration",
                "scale": 0.05,
                "entries": entries,
                "fallback": {"type": "minecraft:model", "model": "pvp:item/bow_pulling_0"},
            },
        }
    })


def bobber():
    """Make the fishing bobber invisible.

    The bobber is an entity, so it cannot be switched off by an item model -
    but blanking its texture is enough. The line is drawn by a separate
    render type and stays visible, so a cast is still readable.
    """
    src = van("textures/entity/fishing/fishing_hook.png")
    write_png(MC / "textures/entity/fishing/fishing_hook.png",
              Image.new("RGBA", src.size, (0, 0, 0, 0)))


def no_pumpkin_blur():
    """Wearing a carved pumpkin no longer blurs the screen."""
    src = van("textures/misc/pumpkinblur.png")
    write_png(MC / "textures/misc/pumpkinblur.png",
              Image.new("RGBA", src.size, (0, 0, 0, 0)))
    copy_vanilla("textures/misc/pumpkinblur.png.mcmeta")


PARTICLE_ALPHA = {
    "critical_hit": 0.3,
    "enchanted_hit": 0.3,
    "damage": 0.3,
    "flash": 0.0,                                # crystal/TNT detonation flash
    **{f"sweep_{i}": 0.25 for i in range(8)},
    **{f"glitter_{i}": 0.2 for i in range(8)},   # totem of undying
    **{f"effect_{i}": 0.2 for i in range(8)},    # potion effect clouds
    **{f"spell_{i}": 0.2 for i in range(8)},
    # explosion clouds otherwise cover the whole screen in a crystal fight
    **{f"explosion_{i}": 0.0 for i in range(16)},
    # the smoke an explosion leaves behind lingers just as long
    **{f"big_smoke_{i}": 0.08 for i in range(12)},
}


def reduced_particles():
    """Fade down the particles that spam the screen mid-fight."""
    for name, factor in PARTICLE_ALPHA.items():
        rel = f"textures/particle/{name}.png"
        write_png(MC / rel, scale_alpha(van(rel), factor))


GLINT_FACTOR = 0.4


def unobtrusive_glint():
    """Dim the enchantment glint so it stops washing out item/armor textures."""
    for name in ("enchanted_glint_item", "enchanted_glint_armor"):
        rel = f"textures/misc/{name}.png"
        src = van(rel)
        out = src.copy()
        px = out.load()
        for y in range(out.height):
            for x in range(out.width):
                r, g, b, a = px[x, y]
                px[x, y] = (round(r * GLINT_FACTOR), round(g * GLINT_FACTOR), round(b * GLINT_FACTOR), a)
        write_png(MC / rel, out)
        copy_vanilla(rel + ".mcmeta")


def no_vignette():
    """Stop the screen edges from darkening (matches the VanillaTweaks technique)."""
    write_png(MC / "textures/misc/vignette.png", Image.new("RGBA", (1, 1), (0, 0, 0, 255)))


# --------------------------------------------------------------------------
# eating / drinking animation
#
# Vanilla already swaps the bow and shield model while an item is in use via
# the item-model `range_dispatch` on `minecraft:use_duration` - the same
# mechanism used by packs like "PvP For Cuties" for eating animations. We
# reuse that mechanism but generate our own stage textures (a growing bite
# notch for solid food, a draining top-down erosion for liquids) instead of
# hand-drawn art, so every food/drink is covered without per-item painting.
# --------------------------------------------------------------------------

EAT_SCALE = 0.03
EAT_THRESHOLDS = [0.3, 0.55, 0.8]  # matches vanilla's ~32-tick eat/drink duration
BITE_FRACTIONS = [0.22, 0.42, 0.62]   # solid food: growing corner bite
DRAIN_FRACTIONS = [0.22, 0.45, 0.7]   # liquids: top-down erosion

FOOD_SOLID = [
    "apple", "baked_potato", "beef", "beetroot", "bread", "carrot", "chicken",
    "chorus_fruit", "cod", "cooked_beef", "cooked_chicken", "cooked_cod",
    "cooked_mutton", "cooked_porkchop", "cooked_rabbit", "cooked_salmon",
    "cookie", "dried_kelp", "glow_berries", "golden_apple", "golden_carrot",
    "melon_slice", "mutton", "poisonous_potato", "porkchop", "potato",
    "pufferfish", "pumpkin_pie", "rabbit", "rotten_flesh", "salmon",
    "spider_eye", "sweet_berries", "tropical_fish", "enchanted_golden_apple",
]
# item id -> source texture, for items that reuse another item's artwork
FOOD_TEXTURE_OVERRIDE = {"enchanted_golden_apple": "golden_apple"}
FOOD_DRAIN = [
    "honey_bottle", "milk_bucket", "ominous_bottle",
    "beetroot_soup", "mushroom_stew", "rabbit_stew", "suspicious_stew",
]


def bite_erode(img, fraction):
    """Clear a circular notch from a corner of the opaque silhouette."""
    bbox = img.getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    cx, cy = x1, y0  # bite from the top-right
    diag = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    radius = diag * fraction
    out = img.copy()
    px = out.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            if px[x, y][3] and (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                px[x, y] = (0, 0, 0, 0)
    return out


def drain_erode(img, fraction):
    """Clear the top `fraction` of the opaque bounding box, as if drunk down."""
    bbox = img.getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    cutoff = y0 + (y1 - y0) * fraction
    out = img.copy()
    px = out.load()
    for y in range(y0, round(cutoff)):
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if a:
                px[x, y] = (r, g, b, 0)
    return out


def food_item_json(vanilla_model_id, stage_models, tints=None):
    def with_tints(model):
        return {**model, "tints": tints} if tints else model

    return {
        "model": {
            "type": "minecraft:condition",
            "property": "minecraft:using_item",
            "on_false": with_tints({"type": "minecraft:model", "model": vanilla_model_id}),
            "on_true": {
                "type": "minecraft:range_dispatch",
                "property": "minecraft:use_duration",
                "scale": EAT_SCALE,
                "entries": [
                    {
                        "threshold": t,
                        "model": with_tints({"type": "minecraft:model", "model": m}),
                    }
                    for t, m in zip(EAT_THRESHOLDS, stage_models)
                ],
                "fallback": with_tints({"type": "minecraft:model", "model": vanilla_model_id}),
            },
        }
    }


def eating_animation_solid():
    for name in FOOD_SOLID:
        tex = van(f"textures/item/{FOOD_TEXTURE_OVERRIDE.get(name, name)}.png")
        stage_models = []
        for i, frac in enumerate(BITE_FRACTIONS):
            write_png(PVP / f"textures/item/food/{name}/{name}{i}.png", bite_erode(tex, frac))
            model_id = f"pvp:item/food/{name}/{name}{i}"
            write_json(PVP / f"models/item/food/{name}/{name}{i}.json", {
                "parent": "minecraft:item/generated",
                "textures": {"layer0": f"pvp:item/food/{name}/{name}{i}"},
            })
            stage_models.append(model_id)
        write_json(MC / f"items/{name}.json",
                    food_item_json(f"minecraft:item/{name}", stage_models))


def eating_animation_drain():
    for name in FOOD_DRAIN:
        tex = van(f"textures/item/{name}.png")
        stage_models = []
        for i, frac in enumerate(DRAIN_FRACTIONS):
            write_png(PVP / f"textures/item/food/{name}/{name}{i}.png", drain_erode(tex, frac))
            model_id = f"pvp:item/food/{name}/{name}{i}"
            write_json(PVP / f"models/item/food/{name}/{name}{i}.json", {
                "parent": "minecraft:item/generated",
                "textures": {"layer0": f"pvp:item/food/{name}/{name}{i}"},
            })
            stage_models.append(model_id)
        write_json(MC / f"items/{name}.json",
                    food_item_json(f"minecraft:item/{name}", stage_models))


def eating_animation_potion():
    """Potion is two layers (tinted liquid + untinted glass) - only drain the liquid."""
    overlay = van("textures/item/potion_overlay.png")
    tints = [{"type": "minecraft:potion", "default": -13083194}]
    stage_models = []
    for i, frac in enumerate(DRAIN_FRACTIONS):
        write_png(PVP / f"textures/item/food/potion/potion_overlay{i}.png", drain_erode(overlay, frac))
        model_id = f"pvp:item/food/potion/potion{i}"
        write_json(PVP / f"models/item/food/potion/potion{i}.json", {
            "parent": "minecraft:item/generated",
            "textures": {
                "layer0": f"pvp:item/food/potion/potion_overlay{i}",
                "layer1": "minecraft:item/potion",
            },
        })
        stage_models.append(model_id)
    write_json(MC / "items/potion.json",
               food_item_json("minecraft:item/potion", stage_models, tints=tints))


def pack_meta():
    write_json(PACK / "pack.mcmeta", {
        "pack": {
            "description": [
                {"text": "PvP Pack ", "color": "white"},
                {"text": "V1", "color": "green"},
                {"text": "\nvanilla-kompatibel · ", "color": "gray"},
                {"text": MC_VERSION, "color": "dark_green"},
            ],
            "pack_format": PACK_FORMAT,
            "min_format": PACK_FORMAT,
            "max_format": PACK_FORMAT,
        }
    })
    icon = tint(van("textures/entity/shield/shield_base_nopattern.png")
                .crop((1, 1, 13, 23)), SHIELD_RED, 0.25).resize((48, 88), Image.NEAREST)
    canvas = Image.new("RGBA", (128, 128), (24, 26, 30, 255))
    canvas.paste(icon, (40, 20), icon)
    write_png(PACK / "pack.png", canvas)


def make_zip():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    target = dist / f"pvp-pack-v1-mc{MC_VERSION}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(PACK.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(PACK))
    print(f"zipped -> {target.relative_to(ROOT)} "
          f"({target.stat().st_size / 1024:.0f} KB)")


def main():
    fetch_vanilla()
    if PACK.exists():
        shutil.rmtree(PACK)
    print("building pack ...")
    pack_meta()
    low_fire()
    outlined_cobweb()
    tiny_tools()
    low_shield()
    shield_cooldown()
    bow_gradient()
    bobber()
    no_pumpkin_blur()
    no_vignette()
    unobtrusive_glint()
    reduced_particles()
    eating_animation_solid()
    eating_animation_drain()
    eating_animation_potion()
    files = sum(len(f) for _, _, f in os.walk(PACK))
    print(f"done - {files} files in {PACK.relative_to(ROOT)}/")
    make_zip()


if __name__ == "__main__":
    main()
