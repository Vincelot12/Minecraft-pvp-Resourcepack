# Minecraft PvP Resource Pack

Ein vanilla-kompatibles Java-Edition Resource Pack für **Minecraft 26.2** (pack_format 88), das mehrere PvP-Utility-Fixes in einem Pack bündelt. Kein OptiFine, kein Mod nötig — läuft auf Servern, die nur normale Resource Packs erlauben.

## Features (V1)

| Feature | Was es macht |
|---|---|
| **Low Fire** | Flammen sind nur noch 2 Pixel hoch am Boden — freie Sicht beim Brennen |
| **Tiny Tools** | Schwerter/Äxte/Spitzhacken deutlich kleiner in der Hand |
| **Outlined Cobwebs** | Helle Umrandung um Spinnennetze, Fallen sofort erkennbar |
| **Low Shield** | Schild sitzt tiefer und kleiner, blockiert die Sicht nicht mehr |
| **Shield Cooldown** | Schild färbt sich rot, wenn es von einer Axt disabled wurde, und verblasst in 5 Stufen zurück auf normal, sobald es wieder nutzbar ist |
| **Bogen-Ladeanzeige** | Der Bogen färbt sich beim Spannen rot → orange → gelb → grün; grün heißt voll aufgeladen (loslassen!) |
| **Kein Bobber** | Der Schwimmer einer Angel ist komplett unsichtbar — die Schnur bleibt sichtbar |
| **Kein Kürbis-Blur** | Kürbis auf dem Kopf blockiert die Sicht nicht mehr |
| **Kein Vignette** | Bildschirmränder verdunkeln sich nicht mehr bei wenig Leben/Hunger |
| **Dezenter Verzauberungs-Glanz** | Enchantment-Glint auf Items/Rüstung deutlich abgeschwächt statt grell |
| **Reduzierte Partikel** | Crit-, Sweep-, Totem- und Potion-Effect-Partikel stark abgeschwächt |
| **Explosions-Sicht** | Explosions- und Flash-Partikel fast unsichtbar — im Crystal-Fight wird der Bildschirm nicht mehr zugeballert |
| **Ess-/Trink-Animation** | Essen zeigt einen wachsenden "Biss" in 3 Stufen, Getränke/Suppen einen sinkenden Flüssigkeitsstand — für alle Vanilla-Foods und -Drinks |

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
- **Shield/Bogen/Essen** nutzen das seit 1.21.4 datengetriebene Item-Model-Format (`assets/minecraft/items/*.json`) mit `range_dispatch` auf `minecraft:cooldown` bzw. `minecraft:use_duration`. Die Ess-Animation ist exakt dasselbe Prinzip, das z.B. [PvP For Cuties](https://modrinth.com/resourcepack/pvp-for-cuties) für seine Eating-Animation nutzt (3 Texturstufen bei `use_duration`-Schwellen 0.3/0.55/0.8) — nur mit eigenen, programmatisch erodierten Texturen statt deren Artwork.
- **Der Bobber** ist eine Entity und lässt sich nicht per Item-Model ausblenden — seine Textur wird deshalb komplett transparent gemacht. Die Angelschnur läuft über einen eigenen Render-Type und bleibt sichtbar, ein Wurf ist also weiterhin erkennbar. Das Pack kommt damit ganz ohne Shader-Overrides aus.
- **Ess-/Trink-Animation**: feste Nahrung bekommt einen wachsenden kreisförmigen "Biss" aus einer Ecke der Textur, Getränke/Suppen einen von oben sinkenden Füllstand (`bite_erode`/`drain_erode` in `build.py`). Beim Trank wird nur die tint-fähige Flüssigkeits-Textur (`potion_overlay`) geleert, das Glas bleibt unverändert.
- **Kein Vignette**: `vignette.png` wird durch ein 1×1 schwarzes Pixel ersetzt (dieselbe Technik wie bei VanillaTweaks/PvP For Cuties) statt des vanilla Radial-Gradienten.

## Status

Getestet ist bisher nur, dass alle JSONs valide sind und die Texturen korrekt generiert werden — **im Spiel verifiziert ist noch nichts**. Besonders die Position des Shield-Cooldown-Modells in der Hand braucht einen Praxistest.

## Was ein Resource Pack *nicht* kann

Die End-Kristall-Textur lässt sich nicht sinnvoll "entschlacken" — sie besteht
schon in Vanilla zu über der Hälfte aus vollständig transparenten Pixeln, die
Glasflächen sind nur gepunktete Umrandungen. Die Durchsichtigkeit kommt vom
Render-Type, nicht von der Textur.

Auch die *Anzahl* der Partikel und Entities ist Spiellogik und für ein Resource
Pack unerreichbar. Was geht, ist die bemalte Fläche zu verkleinern (siehe
Explosions-Partikel oben) — das entlastet die Fill-Rate und vor allem die
Übersicht, ersetzt aber keine FPS-Mod wie Sodium.

## Offen

- Obsidian/Totem/Respawn-Anker klarer erkennbar machen
- V2 mit eigenem visuellen Stil
