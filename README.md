# bl2-sdk-mods

Borderlands 2 mods for the [Python SDK](https://github.com/bl-sdk/willow2-mod-manager) (SDK 3.x, `mods_base`).

| Mod | What it does | Default key |
|---|---|---|
| [Paced Loot Multiplier](#paced-loot-multiplier) | Multiplies enemy loot without lag spikes or co-op desync | – |
| [Item Editor](#item-editor) | Edit parts and level of any item, clone it | F9 in the inventory |
| [Item Catalog](#item-catalog) | Vendor menu with one of every item in the game | F5 |
| [No Visual Clutter](#no-visual-clutter) | Shrink or fade particle effects by category | – |
| [Custom Vendor](#custom-vendor) | Library used by the vendor-menu mods | – |

All keys can be rebound in the mod's options (Mods menu → select the mod → Options).

## Installation

1. Install the [Python SDK](https://github.com/bl-sdk/willow2-mod-manager/releases).
2. Download the `.sdkmod` files you want from the [Releases](https://github.com/ha7gawa/bl2-sdk-mods/releases) page.
   Item Editor and Item Catalog also need `custom_vendor.sdkmod`.
3. Put them into `Borderlands 2/sdk_mods/` and start the game.
4. Enable the mods in the Mods menu.

## Mods

### Paced Loot Multiplier

Every enemy drops its loot the chosen number of times.

Based on [Drop Chance Multiplier](https://github.com/juso40/bl2sdk_Mods/tree/master/DropChanceMultiplier) by **juso40**.
The original is a legacy (ModMenu) mod that calls `DropLootOnDeath` N times inside the hook, so with high multipliers
everything spawns in a single frame: the game stutters and co-op clients desync or miss items. This version:

- is ported to SDK 3 (`mods_base`);
- queues the extra drops and releases them a few per network tick (both configurable);
- only generates loot on the host;
- clears the queue on map change and when disabled.

It got a new name so it isn't confused with juso40's mod, which still exists and works differently.

### Item Editor

Open the inventory, hover over a weapon or item and press **F9**. A vendor menu opens with:

- **LEVEL** – pick a new level (your level or ±5);
- **CLONE** – put a copy of the current version into the backpack;
- one entry per part slot – click to see every part the item can roll in that slot, click a part to install it.

**Esc** goes back one screen; Esc on the slot list saves the item and returns to the inventory.

Only parts the item's balance can roll are offered, so edited items should pass the game's sanity check.
The part-list logic and the "dummy item" trick used for the slot entries follow
[Vendor Edit](https://github.com/apple1417/willow2-sdk-mods/tree/master/vendor_edit) by **apple1417**.
Item Editor shows all slots and actions on one screen, applies changes without closing the menu and
has a clone action.

### Item Catalog

Press **F5** while playing to open a vendor menu with one of every weapon, shield, class mod, grenade,
relic and quest reward at your level. Click an item to get a copy.

| Key | Action |
|---|---|
| Z / X | Previous / next page |
| C | Next category |
| V | Next weapon type |
| Esc | Close |

The first open after loading a map takes a few seconds while the catalog is built.

### No Visual Clutter

Sliders (0–100 %) for the size and opacity of: grenades, shields, tracers and E-Tech beams, surface impacts,
explosions, muzzle flashes and smoke, floating loot icons, loot light beams, on-screen elemental effects and
action skills. Damage numbers and scopes are never touched.

Changes apply instantly. Effects that only load with a new area may need **Re-Scan Packages**.
Disabling the mod restores the original effects. Purely client-side.

### Custom Vendor

A library, not a mod you use directly. Opens the black market vendor menu with any list of items and
lets other mods react to clicks, key presses and closing:

```python
import custom_vendor

custom_vendor.show_vendor(
    items=[...],
    on_select=lambda item, movie: ...,
    on_close=lambda: ...,
    key_handler=lambda movie, key, event: False,  # return True to consume the key
    title="TITLE",  # the only label the vendor menu reliably shows, put controls here
    hint="[Esc] Close",  # set on VisitLabel_BlackMarket, not visible in the default layout
)
custom_vendor.update_vendor_items(new_items, title="...", hint="...")
custom_vendor.close_vendor()
```

Derived from `vendor_movie.py` of [Vendor Edit](https://github.com/apple1417/willow2-sdk-mods/tree/master/vendor_edit)
by **apple1417**. Changes: a reusable public API, callbacks for selection, keys and closing instead of
purchase/cancel, no item of the day, and sorting disabled so items stay in the given order.

## Building

```
python tools/build_sdkmods.py
```

Creates `dist/<mod>.sdkmod` for every mod.

`tools/dump_player_states.py` is a development helper that dumps the player controller and UI classes'
states and functions to a text file (run it with `pyexec` from the SDK console).

## Credits

- **juso40** – [Drop Chance Multiplier](https://github.com/juso40/bl2sdk_Mods), MIT. The license is kept in
  [`paced_loot_multiplier/LICENSE.juso40`](paced_loot_multiplier/LICENSE.juso40).
- **apple1417** – [Vendor Edit](https://github.com/apple1417/willow2-sdk-mods), GPL-3.0. The vendor menu code
  in Custom Vendor and the part-list/dummy-item approach in Item Editor are based on it.
- The [bl-sdk](https://github.com/bl-sdk) team for the Python SDK.

## License

GPL-3.0, see [LICENSE](LICENSE). Custom Vendor and Item Editor are derived from GPL-3.0 code, so the whole
collection uses the same license.

---

## Кратко по-русски

Моды для Borderlands 2 на Python SDK 3.x. Установка: положить нужные `.sdkmod` из Releases в
`Borderlands 2/sdk_mods/` и включить в меню Mods. Item Editor и Item Catalog
требуют `custom_vendor.sdkmod`.

- **Paced Loot Multiplier** – множитель лута, основан на Drop Chance Multiplier (juso40), но выдаёт
  дропы порциями, без фризов и рассинхрона в коопе.
- **Item Editor** – F9 на предмете в инвентаре: смена деталей, уровня, клонирование.
- **Item Catalog** – F5: магазин со всеми предметами игры (Z/X – страницы, C – категория, V – тип оружия).
- **No Visual Clutter** – ползунки размера и прозрачности эффектов.

Клавиши меняются в настройках мода.
