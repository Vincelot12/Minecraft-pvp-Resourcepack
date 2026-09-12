# Minecraft PvP Resource Pack

Ein vanilla-kompatibles Java-Edition Resource Pack für **Minecraft 26.2** (pack_format 88), das mehrere PvP-Utility-Fixes in einem Pack bündelt. Kein OptiFine, kein Mod nötig — läuft auf Servern, die nur normale Resource Packs erlauben.

## Features (V1)

| Feature | Was es macht |
|---|---|
| **Low Fire** | Nur noch der untere Teil der Flammen wird gerendert — freie Sicht beim Brennen |
| **Tiny Tools** | Schwerter/Äxte/Spitzhacken deutlich kleiner in der Hand |
| **Outlined Cobwebs** | Helle Umrandung um Spinnennetze, Fallen sofort erkennbar |
| **Low Shield** | Schild sitzt tiefer und kleiner, blockiert die Sicht nicht mehr |
| **Shield Cooldown** | Schild färbt sich rot, wenn es von einer Axt disabled wurde, und verblasst in 5 Stufen zurück auf normal, sobald es wieder nutzbar ist |
| **Bogen-Ladeanzeige** | Der Bogen färbt sich beim Spannen rot → orange → gelb → grün; grün heißt voll aufgeladen (loslassen!) |
| **Bobber-Fix** | Der Schwimmer einer Angel verschwindet, sobald er direkt vor der Kamera hängt — die Schnur bleibt sichtbar |
| **Kein Kürbis-Blur** | Kürbis auf dem Kopf blockiert die Sicht nicht mehr |
| **Reduzierte Partikel** | Crit-, Sweep-, Totem- und Potion-Effect-Partikel stark abgeschwächt |

**Nicht im Pack:** "No Hurt Cam" ist kein Resource-Pack-Feature, sondern ein Vanilla-Setting:
Optionen → Bedienungshilfen → **Damage Tilt** ausschalten.

## Installation

```bash
python3 build.py
```

Erzeugt `pack/` (der fertige Pack als Ordner) und `dist/pvp-pack-v1-mc26.2.zip`.

Die Zip in den `resourcepacks`-Ordner legen:
- Linux: `~/.minecraft/resourcepacks`
- Windows: `%appdata%/.minecraft/resourcepacks`

Dann im Spiel unter Optionen → Resource Packs aktivieren.

## Wie das gebaut ist

`build.py` lädt beim ersten Lauf die offizielle Vanilla-Client-Jar von Mojang (nach `.cache/`, nicht im Repo) und leitet **alle** Texturen daraus ab — Low Fire, Cobweb-Outline, Bogen-Farbstufen, Shield-Cooldown-Stufen und die abgeschwächten Partikel werden programmatisch generiert, nicht von Hand gemalt. Dadurch ist der komplette Pack reproduzierbar und lässt sich mit einer geänderten Konstante neu abstimmen (z.B. `KEEP_ROWS` für die Feuerhöhe oder `PARTICLE_ALPHA` für die Partikelstärke).

Technisch interessant:
- **Shield/Bogen** nutzen das seit 1.21.4 datengetriebene Item-Model-Format (`assets/minecraft/items/*.json`) mit `range_dispatch` auf `minecraft:cooldown` bzw. `minecraft:use_duration`.
- **Der Bobber** ist eine Entity und lässt sich nicht per Item-Model ausblenden. Stattdessen werden seine Textur-Pixel mit Alpha 249/255 markiert und der Entity-Fragment-Shader verwirft genau diese Pixel, wenn sie näher als 0,42 Blöcke an der Kamera sind.

## Status

Getestet ist bisher nur, dass alle JSONs valide sind und die Texturen korrekt generiert werden — **im Spiel verifiziert ist noch nichts**. Besonders die Position des Shield-Cooldown-Modells in der Hand braucht einen Praxistest.

## Offen

- Ess-/Trink-Animation (Anforderung muss noch präzisiert werden)
- Crystal-PvP-Texturen (End-Kristall, Obsidian, Totem, Anker)
- V2 mit eigenem visuellen Stil
