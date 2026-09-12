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
    "coal_ore", "copper_ore", "diamond_ore", "emerald_ore", "gold_ore",
    "iron_ore", "lapis_ore", "redstone_ore", "nether_gold_ore",
    "nether_quartz_ore", "deepslate_coal_ore", "deepslate_copper_ore",
    "deepslate_diamond_ore", "deepslate_emerald_ore", "deepslate_gold_ore",
    "deepslate_iron_ore", "deepslate_lapis_ore", "deepslate_redstone_ore",
]

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


# Which pixels of a drinkable item are the liquid rather than the container.
# Draining the whole sprite would eat the glass bottle or the bucket along
# with its contents, so each one is matched on the colour of its filling.
LIQUID_MASK = {
    # amber honey; the glass around it is blue-tinted
    "honey_bottle": lambda r, g, b: r > 140 and r > b + 60,
    # dark purple brew; the bottle itself is bright teal
    "ominous_bottle": lambda r, g, b: g < r and r + g + b < 260,
    # only the white milk surface, not the grey bucket
    "milk_bucket": lambda r, g, b: min(r, g, b) > 230,
    # stew fillings sit on a dark brown bowl
    "mushroom_stew": lambda r, g, b: b > 55 and r > 150,
    "beetroot_soup": lambda r, g, b: g * 3 < r and r > 80,
    "rabbit_stew": lambda r, g, b: b > 35 and r > 140,
    "suspicious_stew": lambda r, g, b: b > 55 and r > 140,
}


def drain_erode(img, fraction, is_liquid=None):
    """Lower the liquid level by `fraction`, leaving the container untouched."""
    px_in = img.load()
    liquid = [
        (x, y)
        for y in range(img.height)
        for x in range(img.width)
        if px_in[x, y][3] and (is_liquid is None or is_liquid(*px_in[x, y][:3]))
    ]
    if not liquid:
        return img
    top = min(y for _, y in liquid)
    bottom = max(y for _, y in liquid)
    cutoff = top + (bottom + 1 - top) * fraction
    out = img.copy()
    px = out.load()
    for x, y in liquid:
        if y < cutoff:
            r, g, b, _ = px[x, y]
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
            write_png(PVP / f"textures/item/food/{name}/{name}{i}.png",
                      drain_erode(tex, frac, LIQUID_MASK.get(name)))
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
    files = sum(len(f) for _, _, f in os.walk(PACK))
    print(f"done - {files} files in {PACK.relative_to(ROOT)}/")
    make_zip()


if __name__ == "__main__":
    main()
