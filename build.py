#!/usr/bin/env python3
"""Generates the PvP resource pack from vanilla Minecraft assets.

Vanilla assets are pulled from Mojang's official client jar (cached in .cache/)
so every texture in pack/ is reproducible from source instead of hand-edited.
"""

import colorsys
import json
import math
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

KEEP_ROWS = 6   # of 16 rows per fire frame kept at full opacity
FADE_ROWS = 2   # rows above that, kept faint so burning stays noticeable


def low_fire():
    """Keep only the bottom of each fire frame so flames stop covering the screen."""
    for name in ("fire_0", "fire_1"):
        src = van(f"textures/block/{name}.png")
        frames = src.height // 16
        out = Image.new("RGBA", src.size, (0, 0, 0, 0))
        px_src, px_out = src.load(), out.load()
        for f in range(frames):
            top = f * 16
            for y in range(16):
                if y >= 16 - KEEP_ROWS:
                    keep = 1.0
                elif y >= 16 - KEEP_ROWS - FADE_ROWS:
                    keep = 0.45
                else:
                    continue
                for x in range(16):
                    r, g, b, a = px_src[x, top + y]
                    px_out[x, top + y] = (r, g, b, round(a * keep))
        write_png(MC / f"textures/block/{name}.png", out)
        copy_vanilla(f"textures/block/{name}.png.mcmeta")


COBWEB_BORDER = (235, 235, 235, 255)


def border_frame(img, color, inset=0, alpha=1.0, textured=False):
    """Draw a one-pixel frame around the edge of a block texture.

    alpha < 1 blends the frame into the block's own edge pixels instead of
    flatly overwriting them, so the border reads as a tinted highlight
    rather than a solid sticker outline.

    textured=True additionally modulates each border pixel's brightness by
    its own original luminance (relative to the block's average), so the
    frame carries the same grain/noise as the underlying stone instead of
    being one flat colour.
    """
    out = img.copy()
    px = out.load()
    lo, hi_x, hi_y = inset, img.width - 1 - inset, img.height - 1 - inset

    avg_lum = 128.0
    if textured:
        total, n = 0, 0
        for r, g, b, a in img.getdata():
            if a:
                total += (r + g + b) / 3
                n += 1
        if n:
            avg_lum = total / n

    for y in range(lo, hi_y + 1):
        for x in range(lo, hi_x + 1):
            if x in (lo, hi_x) or y in (lo, hi_y):
                r, g, b, a = px[x, y]
                c = color
                if textured:
                    ratio = max(0.55, min(1.5, (r + g + b) / 3 / avg_lum))
                    c = tuple(min(255, ch * ratio) for ch in color)
                if alpha >= 1:
                    px[x, y] = (round(c[0]), round(c[1]), round(c[2]), 255)
                else:
                    px[x, y] = (
                        round(c[0] * alpha + r * (1 - alpha)),
                        round(c[1] * alpha + g * (1 - alpha)),
                        round(c[2] * alpha + b * (1 - alpha)),
                        255,
                    )
    return out


def outlined_cobweb():
    """Cage the cobweb in a wire box so traps read as a solid box from any angle.

    Vanilla's cobweb model is just the 2 diagonal cross planes. A border
    baked onto those only outlines an X, which disappears when viewed
    from certain angles. Add 6 more quads - one per cube face - using a
    transparent texture with just a 1px frame, so the outline forms a
    full box around the web from any viewing angle.
    """
    copy_vanilla("textures/block/cobweb.png")

    cage = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    write_png(PVP / "textures/block/cobweb_cage.png",
              border_frame(cage, COBWEB_BORDER))

    cross = json.loads((VANILLA / "models/block/cross.json").read_text())
    cage_faces = {face: {"uv": [0, 0, 16, 16], "texture": "#cage"}
                  for face in ("north", "south", "east", "west", "up", "down")}
    write_json(MC / "models/block/cobweb.json", {
        "ambientocclusion": False,
        "textures": {
            "particle": "minecraft:block/cobweb",
            "cross": "minecraft:block/cobweb",
            "cage": "pvp:block/cobweb_cage",
        },
        "elements": cross["elements"] + [
            {"from": [0, 0, 0], "to": [16, 16, 16], "faces": cage_faces},
        ],
    })


# ores whose mineral speckles give the frame its colour
ORES = [
    "copper_ore", "diamond_ore", "emerald_ore", "gold_ore",
    "iron_ore", "lapis_ore", "redstone_ore", "nether_gold_ore",
    "nether_quartz_ore", "deepslate_copper_ore",
    "deepslate_diamond_ore", "deepslate_emerald_ore", "deepslate_gold_ore",
    "deepslate_iron_ore", "deepslate_lapis_ore", "deepslate_redstone_ore",
]

# coal's speckles are almost neutral grey (saturation ~12/255), so the
# "most saturated pixel" the auto-detection picks is just noise - it comes
# out an arbitrary khaki/olive that has nothing to do with coal. Give both
# variants the same fixed coal-black instead.
FIXED_ORE_COLORS = {
    "coal_ore": (35, 33, 30, 255),
    "deepslate_coal_ore": (35, 33, 30, 255),
}

# ancient debris has no distinct mineral fleck to sample a colour from - its
# most-saturated pixel is just its own dark rock, so it gets a fixed warm
# ember colour instead of the auto-detected one every other ore uses.
DEBRIS_TEXTURES = ["ancient_debris_side", "ancient_debris_top"]
DEBRIS_COLOR = (216, 120, 55, 255)


def ore_colour(img):
    """Pick the most saturated colour in the texture - that is the mineral.

    Earlier versions scaled this straight up to full brightness, which
    washed pale flecks (e.g. iron's tan) out into a neon pastel. Instead,
    widen the colour's saturation around its own mean and cap the peak
    brightness below pure white, then guarantee a minimum brightness so
    dark ores like coal still stand out against the stone.
    """
    best, best_sat = (255, 255, 255), -1
    for r, g, b, a in img.getdata():
        if not a:
            continue
        sat = max(r, g, b) - min(r, g, b)
        if sat > best_sat:
            best, best_sat = (r, g, b), sat

    mean = sum(best) / 3
    boosted = [mean + (c - mean) * 1.5 for c in best]
    boosted = [max(0, c) for c in boosted]

    peak = max(boosted)
    if peak > 225:
        boosted = [c * 225 / peak for c in boosted]
    peak = max(boosted)
    if peak < 150:
        boosted = [c * 150 / peak for c in boosted]

    return (*(min(255, round(c)) for c in boosted), 255)


def bordered_ores():
    """Frame every ore in its own mineral colour so it pops out of the stone."""
    for name in ORES:
        rel = f"textures/block/{name}.png"
        src = van(rel)
        write_png(MC / rel,
                  border_frame(src, ore_colour(src), alpha=0.85, textured=True))
    for name, color in FIXED_ORE_COLORS.items():
        rel = f"textures/block/{name}.png"
        src = van(rel)
        write_png(MC / rel, border_frame(src, color, alpha=0.85, textured=True))
    for name in DEBRIS_TEXTURES:
        rel = f"textures/block/{name}.png"
        src = van(rel)
        write_png(MC / rel,
                  border_frame(src, DEBRIS_COLOR, alpha=0.85, textured=True))


def louder_hit_sounds():
    """Boost the crit and sweep hit sounds - vanilla mixes both at 0.7 volume,
    which makes them easy to miss under other combat noise. Re-declare the
    same vanilla sound files with a higher volume; the actual .ogg files
    still resolve from vanilla since this pack ships no audio of its own.
    """
    write_json(MC / "sounds.json", {
        "entity.player.attack.crit": {
            "subtitle": "subtitles.entity.player.attack.crit",
            "sounds": [
                {"name": f"entity/player/attack/crit{n}", "volume": 1.4}
                for n in (1, 2, 3)
            ],
        },
        "entity.player.attack.sweep": {
            "subtitle": "subtitles.entity.player.attack.sweep",
            "sounds": [
                {"name": f"entity/player/attack/sweep{n}", "volume": 1.1}
                for n in range(1, 8)
            ],
        },
    })


def low_shield():
    """Drop the shield out of the centre of the screen while blocking."""
    model = json.loads((VANILLA / "models/item/shield.json").read_text())
    model["display"]["firstperson_righthand"] = {
        "rotation": [0, 180, 5],
        "translation": [-14, -2.5, -12],
        "scale": [1.0, 1.0, 1.0],
    }
    model["display"]["firstperson_lefthand"] = {
        "rotation": [0, 180, 5],
        "translation": [14, -3.5, -12],
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

    # Vanilla's shield is drawn by a special renderer whose geometry sits around
    # the model origin, NOT inside the usual 0..16 item box. Building it centred
    # like a normal item model puts it metres off to the side in first person.
    write_json(PVP / "models/item/shield_cooldown_base.json", {
        "parent": "minecraft:item/shield",
        "textures": {
            "shield": "pvp:item/shield_cooldown_1",
            "particle": "minecraft:block/dark_oak_planks",
        },
        "elements": [
            {
                "name": "plate",
                "from": [-6, -11, 1],
                "to": [6, 11, 2],
                "faces": {
                    "north": {"uv": [3.5, 0.25, 6.5, 5.75], "texture": "#shield"},
                    "east": {"uv": [3.25, 0.25, 3.5, 5.75], "texture": "#shield"},
                    "south": {"uv": [0.25, 0.25, 3.25, 5.75], "texture": "#shield"},
                    "west": {"uv": [0, 0.25, 0.25, 5.75], "texture": "#shield"},
                    "up": {"uv": [0.25, 0, 3.25, 0.25], "texture": "#shield"},
                    "down": {"uv": [3.25, 0, 6.25, 0.25], "texture": "#shield"},
                },
            },
            {
                "name": "handle",
                "from": [-1, -3, -5],
                "to": [1, 3, 1],
                "faces": {
                    "north": {"uv": [10, 1.5, 10.5, 3], "rotation": 180, "texture": "#shield"},
                    "east": {"uv": [8.5, 1.5, 10, 3], "texture": "#shield"},
                    "south": {"uv": [8, 1.5, 8.5, 3], "texture": "#shield"},
                    "west": {"uv": [6.5, 1.5, 8, 3], "texture": "#shield"},
                    "up": {"uv": [8, 0, 8.5, 1.5], "texture": "#shield"},
                    "down": {"uv": [8.5, 0, 9, 1.5], "rotation": 180, "texture": "#shield"},
                },
            },
        ],
    })

    special = {"type": "minecraft:shield"}
    # Vanilla wraps its special-rendered shield in this mirroring transform -
    # without it, the special renderer's geometry comes out rotated 180°. Our
    # own element-based cooldown models don't go through that renderer, so
    # they don't need it (and already render correctly without it).
    special_transform = {
        "left_rotation": [0.0, 0.0, 0.0, 1.0],
        "right_rotation": [0.0, 0.0, 0.0, 1.0],
        "scale": [1.0, -1.0, -1.0],
        "translation": [0.0, 0.0, 0.0],
    }
    write_json(MC / "items/shield.json", {
        "model": {
            "type": "minecraft:condition",
            "property": "minecraft:using_item",
            "on_true": {
                "type": "minecraft:special",
                "base": "minecraft:item/shield_blocking",
                "model": special,
                "transformation": special_transform,
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
                    "transformation": special_transform,
                },
            },
        }
    })


# bow charge: red while weak, green once the shot is fully charged
BOW_RAMP = [
    (0.0, (150, 28, 28)),
    (0.3, (165, 70, 20)),
    (0.5, (160, 120, 18)),
    (0.7, (140, 140, 25)),
    (0.9, (75, 140, 35)),
    (1.0, (30, 155, 50)),
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


ARROW_MIN_SHADE = 85   # vanilla's arrow pixels are grey 107-150; the string is a flat 68
ARROW_MAX_SHADE = 160  # the bow limb's tip highlight is a brighter grey, 177-255


def tint_arrow(img, color):
    """Recolour only the nocked arrow, not the (also grey) bowstring or limb highlight.

    Vanilla draws the string, arrow and a highlight on the limb tip all in
    greyscale, but at different brightness bands: the string is a flat, dim
    68/255 diagonal, the arrow (head + shaft) sits at 107-150, and the limb
    highlight is brighter still at 177-255. Those gaps are enough to isolate
    just the arrow.
    """
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if not a or max(r, g, b) - min(r, g, b) > 25:
                continue  # the wooden limbs are strongly tinted, leave them alone
            shade = (r + g + b) / 3
            if shade <= ARROW_MIN_SHADE or shade > ARROW_MAX_SHADE:
                continue  # the bowstring, or the limb tip's highlight
            shade /= 255
            px[x, y] = (round(color[0] * shade), round(color[1] * shade),
                        round(color[2] * shade), a)
    return out


def bow_gradient():
    """Colour the bowstring from red to green so full charge is visible at a glance."""
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
                  tint_arrow(stage_art(t), ramp_color(t)))
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


BOBBER_ALPHA = 249    # marker value the shader uses to recognise bobber pixels
BOBBER_CUTOFF = 0.55  # blocks - roughly "someone rodded you in the face"


def bobber():
    """Hide the bobber only once it is right in front of the camera.

    The bobber is an entity, so an item model cannot touch it. Its texture is
    instead marked with a slightly-transparent alpha, and the entity fragment
    shader discards exactly those pixels when they are close enough to cover
    your view. Your own cast stays visible at normal fishing distance.
    """
    src = van("textures/entity/fishing/fishing_hook.png")
    out = src.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a == 255:
                px[x, y] = (r, g, b, BOBBER_ALPHA)
    write_png(MC / "textures/entity/fishing/fishing_hook.png", out)

    glsl = (
        "// Bobber pixels are marked with alpha 249/255 so they can be told apart\n"
        "// from every other entity drawn by this shader. The band stays narrow so\n"
        "// genuinely translucent entities are never discarded.\n"
        "bool pvp_isBobber(float alpha) {\n"
        "    return alpha > 0.95 && alpha < 1.0;\n"
        "}\n\n"
        "void pvp_hideCloseBobber(float dist, float cutoff, float alpha) {\n"
        "    if (pvp_isBobber(alpha) && dist < cutoff) {\n"
        "        discard;\n"
        "    }\n"
        "}\n"
    )
    (MC / "shaders/include").mkdir(parents=True, exist_ok=True)
    (MC / "shaders/include/pvp_bobber.glsl").write_text(glsl)

    fsh = (VANILLA / "shaders/core/entity.fsh").read_text()
    fsh = fsh.replace(
        "#moj_import <minecraft:fog.glsl>",
        "#moj_import <minecraft:fog.glsl>\n#moj_import <minecraft:pvp_bobber.glsl>",
        1,
    )
    fsh = fsh.replace(
        "    vec4 color = texture(Sampler0, texCoord0);",
        "    vec4 color = texture(Sampler0, texCoord0);\n"
        f"    pvp_hideCloseBobber(sphericalVertexDistance, {BOBBER_CUTOFF}, color.a);",
        1,
    )
    (MC / "shaders/core").mkdir(parents=True, exist_ok=True)
    (MC / "shaders/core/entity.fsh").write_text(fsh)


def fullbright():
    """Light everything at maximum, so caves and dark corners read like daylight.

    The lightmap is generated by the game, but every shader reads it through
    this one include - returning a constant makes the sample a no-op.
    """
    (MC / "shaders/include").mkdir(parents=True, exist_ok=True)
    (MC / "shaders/include/sample_lightmap.glsl").write_text(
        "#version 330\n\n"
        "vec4 sample_lightmap(sampler2D lightMap, ivec2 uv) {\n"
        "    return vec4(1.0);\n"
        "}\n"
    )


def no_pumpkin_blur():
    """Wearing a carved pumpkin no longer blurs the screen."""
    src = van("textures/misc/pumpkinblur.png")
    write_png(MC / "textures/misc/pumpkinblur.png",
              Image.new("RGBA", src.size, (0, 0, 0, 0)))
    copy_vanilla("textures/misc/pumpkinblur.png.mcmeta")


PARTICLE_ALPHA = {
    "critical_hit": 0.0,
    "enchanted_hit": 0.0,
    "damage": 0.3,
    "flash": 0.0,                                # crystal/TNT detonation flash
    **{f"sweep_{i}": 0.0 for i in range(8)},
    **{f"glitter_{i}": 0.2 for i in range(8)},   # totem of undying
    **{f"effect_{i}": 0.2 for i in range(8)},    # potion effect clouds
    **{f"spell_{i}": 0.2 for i in range(8)},
    # explosion clouds and their smoke otherwise cover the whole screen
    **{f"explosion_{i}": 0.0 for i in range(16)},
    **{f"big_smoke_{i}": 0.0 for i in range(12)},
}


def reduced_particles():
    """Fade down the particles that spam the screen mid-fight."""
    for name, factor in PARTICLE_ALPHA.items():
        rel = f"textures/particle/{name}.png"
        write_png(MC / rel, scale_alpha(van(rel), factor))


GLINT_FACTOR = 0.62


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
# reuse that mechanism but generate our own stage textures from the vanilla
# artwork: per-item bites that leave bones, cores and rinds behind for solid
# food, a draining top-down erosion for liquids.
# --------------------------------------------------------------------------

EAT_SCALE = 0.03
EAT_THRESHOLDS = [0.3, 0.55, 0.8]  # matches vanilla's ~32-tick eat/drink duration
DRAIN_FRACTIONS = [0.3, 0.65, 1.0]   # liquids: top-down erosion, fully empty by the last sip

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


# Solid food is eaten the way it would be in real life: the flesh goes, but
# what nobody eats stays behind - an apple's stem and core, a melon's rind,
# a fish's head, tail and skeleton, the bone out of a drumstick. Vanilla only
# draws each item's outside, so every food states that itself:
#   flesh   - colour of the cut surface, so a bite isn't a hole in the sprite
#   anchors - (x, y, delay) points the bites come from; delay holds one side
#             back, so an apple goes round one flank before the other
#   stages  - share of the edible pixels gone at each animation stage
#   keep    - pixels that are never eaten (rind, stem, leaves, head, fins)
#   core    - (pixels, colour) uncovered once the flesh around them is gone
# Coordinates refer to the item's 16x16 vanilla sprite.

BONE = (236, 230, 212)
APPLE_SEED = (86, 54, 30)
TOOTH = 0.9  # ripple on the bite front, in pixels, so it leaves tooth marks


def seg(a, b):
    """Pixels on the straight line from a to b, both ends included."""
    (x0, y0), (x1, y1) = a, b
    steps = max(abs(x1 - x0), abs(y1 - y0))
    if not steps:
        return [a]
    return [(round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps))
            for i in range(steps + 1)]


def hue_class(r, g, b):
    """Coarse colour name of a pixel, to pick rind, leaves or fins out of a sprite."""
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h *= 360
    if v < 0.22:
        return "dark"
    if s < 0.18:
        return "grey"
    if 70 <= h < 170:
        return "green"
    if 170 <= h < 250:
        return "cyan"
    if 250 <= h < 340:
        return "purple"
    if h < 15 or h >= 340:
        return "red"
    if h < 45:
        return "orange" if v > 0.6 else "brown"
    return "yellow"


def plain_bite(flesh):
    return {"flesh": flesh, "anchors": [(16, -1, 0)], "stages": (0.2, 0.42, 0.68)}


# stem, plus the skin left at the top and bottom of a finished core
APPLE_KEEP = {(9, 1), (8, 2), (9, 2), (8, 3),
              (6, 4), (7, 4), (8, 4), (9, 4), (7, 5), (8, 5),
              (6, 13), (7, 13), (8, 13), (9, 13), (6, 14), (7, 14), (8, 14)}


def apple(flesh):
    return {
        "flesh": flesh,
        "anchors": [(14, 8, 0), (0, 9, 2.5)],  # right flank first, then the left
        "stages": (0.28, 0.6, 0.93),
        "keep": lambda x, y, rgb: (x, y) in APPLE_KEEP,
        "core": [(seg((7, 6), (7, 12)) + seg((8, 6), (8, 12)), flesh),
                 ([(7, 8), (8, 10)], APPLE_SEED)],
    }


# cod, cooked cod and tropical fish share one outline - head bottom-left,
# tail fin top-right - so the spine runs corner to corner with ribs off it
COD_BONES = seg((5, 10), (11, 4)) + [(5, 8), (7, 10), (7, 6), (9, 8), (9, 4), (11, 6)]


def cod_like(flesh, tail):
    return {
        "flesh": flesh,
        "anchors": [(3, 4, 0), (12, 11, 2)],  # strip the back, then the belly
        "stages": (0.3, 0.62, 0.95),
        "keep": lambda x, y, rgb: ((x <= 4 and y >= 10) or y <= 3 or y == 14
                                   or (x, y) in tail),
        "core": [(COD_BONES, BONE)],
    }


# the salmon's green head reaches further in than the cod's, so its spine
# starts later
SALMON_BONES = seg((7, 9), (12, 4)) + [(7, 7), (9, 9), (8, 6), (10, 8), (9, 5)]
SALMON_FINS = {(3, 11), (5, 12), (5, 13), (6, 13), (4, 14), (5, 14), (13, 4), (14, 4)}


def salmon_like(flesh):
    return {
        "flesh": flesh,
        "anchors": [(4, 3, 0), (13, 11, 2)],
        "stages": (0.3, 0.62, 0.95),
        "keep": lambda x, y, rgb: (hue_class(*rgb) == "green" or y <= 3
                                   or (x, y) in SALMON_FINS),
        "core": [(SALMON_BONES, BONE)],
    }


# A whole roast chicken is eaten down to its carcass: the ribcage where the
# breast was, and two drumstick bones running from the pelvis out to the two
# knuckles that already poke out of vanilla's sprite at the bottom-left.
CHICKEN_KNUCKLES = {(2, 11), (2, 12), (5, 13), (4, 14)}
CHICKEN_RIBCAGE = [(7, 2), (8, 2), (9, 2), (10, 2), (6, 3), (11, 3),
                   (5, 4), (7, 4), (8, 4), (9, 4), (10, 4), (12, 4),
                   (5, 5), (12, 5),
                   (5, 6), (7, 6), (8, 6), (9, 6), (10, 6), (12, 6),
                   (6, 7), (11, 7), (7, 8), (8, 8), (9, 8), (10, 8)]
CHICKEN_LEGS = [(6, 8), (5, 8), (4, 9), (3, 10),    # out to the knuckle at (2, 11)
                (7, 9), (7, 10), (6, 11), (5, 12)]  # out to the knuckle at (5, 13)
# vanilla's own knuckle colours, so the new bones match the ones already drawn
CHICKEN_BONE = (238, 202, 172)
CHICKEN_BONE_SHADE = (222, 170, 131)


def chicken(flesh):
    lit = [(x, y) for x, y in CHICKEN_RIBCAGE if x + y <= 14]  # lower-right half is in shadow
    return {
        "flesh": flesh,
        "anchors": [(15, 1, 0), (15, 11, 1)],  # the breast first, the drumsticks last
        "stages": (0.3, 0.62, 1.0),
        "keep": lambda x, y, rgb: (x, y) in CHICKEN_KNUCKLES,
        "core": [(CHICKEN_RIBCAGE, CHICKEN_BONE_SHADE), (lit + CHICKEN_LEGS, CHICKEN_BONE)],
    }


def rabbit(flesh):
    return {
        "flesh": flesh,
        "anchors": [(8, 0, 0), (7, 14, 1.5)],
        "stages": (0.3, 0.62, 0.93),
    }


def mutton(flesh):
    return {
        "flesh": flesh,
        "anchors": [(2, 4, 0), (15, 11, 1), (6, 17, 1.5)],
        "stages": (0.3, 0.62, 0.92),
    }


def porkchop(flesh):
    return {
        "flesh": flesh,
        "anchors": [(1, 14, 0), (4, 1, 2.5)],  # the meaty end first, the rib end last
        "stages": (0.3, 0.62, 0.9),
    }


# the leaf stalk on top
BEETROOT_KEEP = {(9, 2), (10, 2), (10, 3), (11, 3), (12, 3), (10, 4), (11, 4)}


def glow_berry_vine(x, y, rgb):
    kind = hue_class(*rgb)
    return (kind == "green"
            or (kind == "yellow" and x >= 10)  # lit leaf edges, not berry highlights
            or (kind == "brown" and y <= 11 and 5 <= x <= 9))  # the stem


FOOD_SPEC = {
    "apple": apple((243, 233, 208)),
    "golden_apple": apple((250, 240, 205)),
    "enchanted_golden_apple": apple((250, 240, 205)),
    "melon_slice": {
        "flesh": (232, 74, 82),
        # far off the cut face, so the bites advance on the rind in even rows
        "anchors": [(-4, -4, 0)],
        "stages": (0.3, 0.62, 0.96),
        "keep": lambda x, y, rgb: hue_class(*rgb) != "red",
    },
    "cod": cod_like((234, 220, 198), {(13, 4), (14, 4), (11, 5), (12, 5), (13, 5), (14, 5)}),
    "cooked_cod": cod_like((238, 228, 208), {(14, 4), (13, 5), (14, 5)}),
    "tropical_fish": cod_like((242, 224, 212), {(13, 4), (14, 4), (12, 5)}),
    "salmon": salmon_like((238, 134, 106)),
    "cooked_salmon": salmon_like((240, 158, 108)),
    "pufferfish": {
        "flesh": (238, 228, 178),
        "anchors": [(7, 0, 0), (7, 16, 1.5)],
        "stages": (0.3, 0.62, 0.93),
        # only the tail fin on the left - the top fin would be left floating
        "keep": lambda x, y, rgb: x <= 3 and hue_class(*rgb) == "cyan",
        "core": [(seg((3, 9), (12, 9))
                  + [(6, 8), (6, 10), (8, 8), (8, 10), (10, 8), (10, 10)], BONE)],
    },
    "chicken": chicken((240, 194, 184)),
    "cooked_chicken": chicken((233, 204, 158)),
    "rabbit": rabbit((238, 190, 180)),
    "cooked_rabbit": rabbit((163, 110, 72)),
    "mutton": mutton((170, 62, 58)),
    "cooked_mutton": mutton((154, 98, 64)),
    "porkchop": porkchop((242, 172, 164)),
    "cooked_porkchop": porkchop((219, 168, 112)),
    "carrot": {
        "flesh": (243, 156, 62),
        "anchors": [(1, 15, 0)],  # from the root tip up to the greens
        "stages": (0.28, 0.58, 0.88),
        "keep": lambda x, y, rgb: hue_class(*rgb) == "green",
    },
    "golden_carrot": {
        "flesh": (250, 205, 96),
        "anchors": [(1, 15, 0)],
        "stages": (0.28, 0.58, 0.88),
        "keep": lambda x, y, rgb: y <= 4 or (y <= 9 and hue_class(*rgb) in ("brown", "dark")),
    },
    "beetroot": {
        "flesh": (144, 30, 62),
        "anchors": [(14, 9, 0), (2, 15, 1.5)],  # the bulb, then the root tail
        "stages": (0.28, 0.6, 0.9),
        "keep": lambda x, y, rgb: (x, y) in BEETROOT_KEEP,
    },
    "glow_berries": {
        "flesh": (255, 202, 96),
        "anchors": [(0, 12, 0), (11, 15, 1)],
        "stages": (0.3, 0.62, 0.95),
        "keep": glow_berry_vine,
    },
    "sweet_berries": {
        "flesh": (202, 48, 72),
        "anchors": [(7, 1, 0), (15, 5, 0.5), (7, 14, 1), (0, 12, 1.5)],  # one per berry
        "stages": (0.3, 0.62, 0.95),
        "keep": lambda x, y, rgb: hue_class(*rgb) in ("green", "dark"),
    },
    "baked_potato": plain_bite((235, 205, 135)),
    "potato": plain_bite((226, 202, 148)),
    "poisonous_potato": plain_bite((206, 208, 138)),
    "beef": plain_bite((168, 58, 58)),
    "cooked_beef": plain_bite((146, 92, 58)),
    "rotten_flesh": plain_bite((112, 102, 74)),
    "bread": plain_bite((228, 199, 148)),
    "cookie": plain_bite((188, 137, 86)),
    # bitten from below, so the pale sprout stays attached to what's left
    "chorus_fruit": {**plain_bite((206, 178, 214)), "anchors": [(16, 16, 0)]},
    "dried_kelp": plain_bite((62, 88, 52)),
    "pumpkin_pie": plain_bite((236, 172, 78)),
    "spider_eye": plain_bite((116, 36, 48)),
}


def eat_stage(img, eaten, spec):
    """Eat `eaten` (0-1) of an item's edible pixels as its `spec` describes.

    Edible pixels go in order of distance from the nearest bite anchor, with
    a small angular ripple so the front leaves tooth marks rather than a
    clean arc. `keep` pixels are never touched. `core` pixels aren't removed
    either, but take their own colour once the front reaches or bares them.
    Edible pixels left beside a gap get the flesh colour, so the cut shows a
    cross-section instead of a hole through to the background.
    """
    src = img.load()
    solid = {(x, y) for y in range(img.height) for x in range(img.width) if src[x, y][3]}
    core = {}
    for pixels, colour in spec.get("core", ()):
        for p in pixels:
            if p in solid:
                core[p] = colour
    keep_fn = spec.get("keep")
    keep = {p for p in solid if p not in core and keep_fn and keep_fn(*p, src[p][:3])}
    edible = [p for p in solid if p not in core and p not in keep]

    def priority(p):
        return min(
            math.hypot(p[0] - ax, p[1] - ay)
            - TOOTH * math.sin(6 * math.atan2(p[1] - ay, p[0] - ax))
            + delay
            for ax, ay, delay in spec["anchors"]
        )

    edible.sort(key=lambda p: (priority(p), p))
    n = round(len(edible) * eaten)
    gone = set(edible[:n])
    reach = priority(edible[n - 1]) if n else float("-inf")

    def gaps_around(p):
        return sum((p[0] + ox, p[1] + oy) in gone for ox in (-1, 0, 1) for oy in (-1, 0, 1))

    out = img.copy()
    px = out.load()
    for p in gone:
        px[p] = (0, 0, 0, 0)
    for p, colour in core.items():
        if priority(p) <= reach or gaps_around(p):
            px[p] = (*colour, 255)

    # on a thin sprite a rim off every pixel touching the cut swallows the
    # whole remainder, so tighten it until it stays an edge, not a repaint
    left = [p for p in edible if p not in gone]
    rim = [p for p in left if gaps_around(p)]
    if left and len(rim) > 0.4 * len(left):
        rim = [p for p in left if gaps_around(p) >= 3]
    for p in rim:
        px[p] = (*spec["flesh"], 255)
    return out



# Which pixels of a stew bowl are the soup rather than the bowl. Draining the
# whole sprite would eat the bowl along with its contents, so each one is
# matched on the colour of its filling.
LIQUID_MASK = {
    # stew fillings sit on a dark brown bowl
    "mushroom_stew": lambda r, g, b: b > 55 and r > 150,
    "beetroot_soup": lambda r, g, b: g * 3 < r and r > 80,
    "rabbit_stew": lambda r, g, b: b > 35 and r > 140,
    "suspicious_stew": lambda r, g, b: b > 55 and r > 140,
}


def drain_erode(img, fraction, is_liquid):
    """Lower the soup in a bowl by `fraction`.

    Vanilla's flat icons never draw anything underneath the liquid fill, so
    clearing drained pixels would punch a hole through the container to the
    background. A bowl is opaque, so paint the drained area with a darkened
    shade of the bowl's own colour instead - an empty bottom.
    """
    px_in = img.load()
    liquid, container = [], []
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px_in[x, y]
            if a:
                (liquid if is_liquid(r, g, b) else container).append((x, y))
    if not liquid:
        return img
    floor = (tuple(round(sum(px_in[p][i] for p in container) / len(container) * 0.55)
                   for i in range(3))
             if container else (35, 35, 35))
    top = min(y for _, y in liquid)
    bottom = max(y for _, y in liquid)
    cutoff = top + (bottom + 1 - top) * fraction
    out = img.copy()
    px = out.load()
    for x, y in liquid:
        if y < cutoff:
            px[x, y] = (*floor, 255)
    return out


def is_cork(r, g, b, y):
    """A bottle's cork is warm brown; its glass is always cooler (blue/teal),
    and the cork only ever sits in the neck near the top of the sprite."""
    return y <= 4 and r > b


def uncork(img):
    out = img.copy()
    px = out.load()
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y][3] and is_cork(*px[x, y][:3], y):
                px[x, y] = (0, 0, 0, 0)
    return out


def drain_to_empty(img, fraction, is_contents, empty):
    """Drain a container top-down until it looks like `empty`, its vanilla
    empty counterpart.

    Painting the drained space with a flat colour reads as a container still
    full of something, so each drained pixel takes whatever the empty version
    has in that spot instead: clear glass or a highlight in a bottle, the
    shaded inside of a bucket. A bottle's cork is off from the first sip.
    """
    src = img.load()
    ref = empty.load()
    contents = [(x, y) for y in range(img.height) for x in range(img.width)
                if src[x, y][3] and is_contents(x, y, src[x, y][:3])]
    out = uncork(img)
    if not contents:
        return out
    px = out.load()
    top = min(y for _, y in contents)
    bottom = max(y for _, y in contents)
    cutoff = top + (bottom + 1 - top) * fraction
    for x, y in contents:
        if y < cutoff:
            px[x, y] = ref[x, y]
    return out


def ominous_brew(x, y, rgb):
    """Everything inside the teal bottle - purple band, dark brew, red eyes."""
    r, g, b = rgb
    return not (g > r and b > r) and not is_cork(r, g, b, y)


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
        spec = FOOD_SPEC[name]
        for i, eaten in enumerate(spec["stages"]):
            write_png(PVP / f"textures/item/food/{name}/{name}{i}.png",
                      eat_stage(tex, eaten, spec))
            model_id = f"pvp:item/food/{name}/{name}{i}"
            write_json(PVP / f"models/item/food/{name}/{name}{i}.json", {
                "parent": "minecraft:item/generated",
                "textures": {"layer0": f"pvp:item/food/{name}/{name}{i}"},
            })
            stage_models.append(model_id)
        write_json(MC / f"items/{name}.json",
                    food_item_json(f"minecraft:item/{name}", stage_models))



def eating_animation_drain():
    glass_bottle = van("textures/item/glass_bottle.png")
    glass_px = glass_bottle.load()
    bucket = van("textures/item/bucket.png")
    bucket_px = bucket.load()
    nothing = Image.new("RGBA", glass_bottle.size, (0, 0, 0, 0))
    empties = {
        # the honey bottle is vanilla's glass bottle with honey drawn in, so
        # drained honey turns back into exactly that empty bottle
        "honey_bottle": (lambda x, y, rgb: (*rgb, 255) != glass_px[x, y], uncork(glass_bottle)),
        # likewise the milk bucket is the empty bucket with a milk surface on top
        "milk_bucket": (lambda x, y, rgb: (*rgb, 255) != bucket_px[x, y], bucket),
        # no vanilla empty version exists - only its teal glass is left over
        "ominous_bottle": (ominous_brew, nothing),
    }
    for name in FOOD_DRAIN:
        tex = van(f"textures/item/{name}.png")
        stage_models = []
        for i, frac in enumerate(DRAIN_FRACTIONS):
            if name in empties:
                stage = drain_to_empty(tex, frac, *empties[name])
            else:
                stage = drain_erode(tex, frac, LIQUID_MASK[name])
            write_png(PVP / f"textures/item/food/{name}/{name}{i}.png", stage)
            model_id = f"pvp:item/food/{name}/{name}{i}"
            write_json(PVP / f"models/item/food/{name}/{name}{i}.json", {
                "parent": "minecraft:item/generated",
                "textures": {"layer0": f"pvp:item/food/{name}/{name}{i}"},
            })
            stage_models.append(model_id)
        write_json(MC / f"items/{name}.json",
                    food_item_json(f"minecraft:item/{name}", stage_models))


def eating_animation_potion():
    """Potion is two layers: the tinted liquid under an untinted glass layer
    that is pixel-for-pixel vanilla's empty glass bottle. Draining the liquid
    to nothing therefore leaves precisely an empty bottle, minus the cork."""
    overlay = van("textures/item/potion_overlay.png")
    write_png(PVP / "textures/item/food/potion/potion_glass.png",
              uncork(van("textures/item/potion.png")))
    nothing = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    tints = [{"type": "minecraft:potion", "default": -13083194}]
    stage_models = []
    for i, frac in enumerate(DRAIN_FRACTIONS):
        write_png(PVP / f"textures/item/food/potion/potion_overlay{i}.png",
                  drain_to_empty(overlay, frac, lambda x, y, rgb: True, nothing))
        model_id = f"pvp:item/food/potion/potion{i}"
        write_json(PVP / f"models/item/food/potion/potion{i}.json", {
            "parent": "minecraft:item/generated",
            "textures": {
                "layer0": f"pvp:item/food/potion/potion_overlay{i}",
                "layer1": "pvp:item/food/potion/potion_glass",
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


def glow_pulse_frames(img, frames=16, low=0.85, high=1.3):
    """Build a looping sequence that breathes the texture's brightness up and down."""
    out = []
    for i in range(frames):
        factor = low + (high - low) * (0.5 - 0.5 * math.cos(2 * math.pi * i / frames))
        frame = img.copy()
        px = frame.load()
        for y in range(frame.height):
            for x in range(frame.width):
                r, g, b, a = px[x, y]
                if a:
                    px[x, y] = (min(255, round(r * factor)),
                                min(255, round(g * factor)),
                                min(255, round(b * factor)), a)
        out.append(frame)
    return out


def stack_vertical(frames):
    w, h = frames[0].size
    sheet = Image.new("RGBA", (w, h * len(frames)))
    for i, frame in enumerate(frames):
        sheet.paste(frame, (0, i * h))
    return sheet


def animated_items():
    """Give the totem and ender eye a subtle glow-pulse animation.

    Uses Minecraft's native item texture animation (frames stacked into one
    tall PNG plus a .mcmeta) rather than any third-party pack's art - the
    same vanilla-texture-in, procedurally-modified-out approach as the rest
    of this pack.
    """
    for name in ("totem_of_undying", "ender_eye"):
        rel = f"textures/item/{name}.png"
        src = van(rel)
        write_png(MC / rel, stack_vertical(glow_pulse_frames(src)))
        write_json(MC / f"{rel}.mcmeta", {"animation": {"frametime": 3}})


def main():
    fetch_vanilla()
    if PACK.exists():
        shutil.rmtree(PACK)
    print("building pack ...")
    pack_meta()
    low_fire()
    outlined_cobweb()
    bordered_ores()
    louder_hit_sounds()
    low_shield()
    shield_cooldown()
    bow_gradient()
    bobber()
    fullbright()
    no_pumpkin_blur()
    no_vignette()
    unobtrusive_glint()
    reduced_particles()
    eating_animation_solid()
    eating_animation_drain()
    eating_animation_potion()
    animated_items()
    files = sum(len(f) for _, _, f in os.walk(PACK))
    print(f"done - {files} files in {PACK.relative_to(ROOT)}/")
    make_zip()


if __name__ == "__main__":
    main()
