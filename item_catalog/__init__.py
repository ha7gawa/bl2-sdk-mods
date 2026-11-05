import unrealsdk
from mods_base import KeybindOption, SpinnerOption, build_mod, get_pc, hook
from unrealsdk.hooks import Block, Type
from ui_utils import show_chat_message

try:
    from custom_vendor import (
        show_vendor,
        close_vendor,
        update_vendor_items,
        update_vendor_labels,
        is_vendor_open,
    )
except ImportError:
    show_vendor = None
    is_vendor_open = lambda: False

CACHED_MASTER_ITEMS = []
IS_BUILDING_CACHE = False
CURRENT_PAGE = 1
ITEMS_PER_PAGE = 35

CATEGORIES_LIST = ["all", "weapons", "shields", "classmods", "gear", "quests"]
WEAPON_SUBS_LIST = ["all", "pistols", "shotguns", "snipers", "assault_rifles", "smgs", "launchers"]

CAT_LABELS = {
    "all": "ALL",
    "weapons": "WEAPONS",
    "shields": "SHIELDS",
    "classmods": "CLASS MODS",
    "gear": "GRENADES/RELICS",
    "quests": "QUEST REWARDS",
}

SUB_LABELS = {
    "all": "ALL",
    "pistols": "PISTOLS",
    "shotguns": "SHOTGUNS",
    "snipers": "SNIPERS",
    "assault_rifles": "ASSAULT RIFLES",
    "smgs": "SMGS",
    "launchers": "LAUNCHERS",
}

CURRENT_CAT_IDX = 0
CURRENT_SUBCAT_IDX = 0

open_key = KeybindOption(
    "Open Catalog Key",
    "F5",
    description=(
        "Opens the catalog while playing (not from other menus). Inside the catalog: Z/X - previous/next"
        " page, C - next category, V - next weapon type, click - take a copy, Esc - close."
    ),
)

CATEGORY_ORDER = {
    "weapons": 1,
    "shields": 2,
    "gear": 3,
    "classmods": 4,
    "quests": 5,
    "misc": 6,
}

SUBCAT_ORDER = {
    "pistols": 1,
    "shotguns": 2,
    "smgs": 3,
    "assault_rifles": 4,
    "snipers": 5,
    "launchers": 6,
    "grenades": 7,
    "artifacts": 8,
    "shields": 9,
    "classmods": 10,
    "other_weapons": 11,
    "other": 12,
}

CREATE_WEAPON_FROM_DEF = unrealsdk.find_class("WillowWeapon").ClassDefaultObject.CreateWeaponFromDef
CREATE_ITEM_FROM_DEF = unrealsdk.find_class("WillowItem").ClassDefaultObject.CreateItemFromDef

def log(msg: str) -> None:
    print(f"[ITEM_CATALOG] {msg}")

def classify_item(itm):
    if not itm or not hasattr(itm, "Class") or not itm.Class:
        return "misc", "other"

    class_name = itm.Class.Name.lower()
    full_path = str(itm.Class).lower()

    if "weapon" in class_name or "weapon" in full_path:
        if "pistol" in class_name or "pistol" in full_path:
            return "weapons", "pistols"
        elif "shotgun" in class_name or "shotgun" in full_path:
            return "weapons", "shotguns"
        elif "sniper" in class_name or "sniper" in full_path:
            return "weapons", "snipers"
        elif any(k in full_path for k in ("assault", "rifle", "ar_")):
            return "weapons", "assault_rifles"
        elif "smg" in class_name or "smg" in full_path:
            return "weapons", "smgs"
        elif "launcher" in class_name or "rl_" in full_path:
            return "weapons", "launchers"
        return "weapons", "other_weapons"

    elif "shield" in class_name or "shield" in full_path:
        return "shields", "shields"
    elif "classmod" in class_name or "classmod" in full_path:
        return "classmods", "classmods"
    elif "grenade" in class_name or "grenademod" in full_path or "gm_" in full_path:
        return "gear", "grenades"
    elif "artifact" in class_name or "artifact" in full_path or "a_item" in full_path:
        return "gear", "artifacts"

    return "misc", "other"

def build_master_cache():
    global CACHED_MASTER_ITEMS, IS_BUILDING_CACHE
    if CACHED_MASTER_ITEMS:
        return CACHED_MASTER_ITEMS

    if IS_BUILDING_CACHE:
        return []

    pc = get_pc()
    if not pc or not pc.Pawn:
        return []

    IS_BUILDING_CACHE = True
    try:
        CACHED_MASTER_ITEMS = collect_catalog(pc.Pawn)
    finally:
        # Reset even on errors, otherwise the catalog could never be built again
        IS_BUILDING_CACHE = False
    log(f"Catalog ready. Items: {len(CACHED_MASTER_ITEMS)}")
    return CACHED_MASTER_ITEMS

def collect_catalog(pawn):
    player_level = pawn.GetExpLevel() if hasattr(pawn, "GetExpLevel") else 72
    item_pool_cdo = unrealsdk.find_class("ItemPool").ClassDefaultObject

    log("Building item catalog...")
    collected = []
    seen = set()

    balance_classes = ("WeaponBalanceDefinition", "InventoryBalanceDefinition", "ClassModBalanceDefinition")
    all_defs = []
    for b_cls in balance_classes:
        try:
            all_defs.extend(list(unrealsdk.find_all(b_cls)))
        except Exception:
            pass

    for b_def in all_defs:
        if not b_def:
            continue
        b_name = b_def.Name.lower()
        if any(w in b_name for w in ("dummy", "test", "currency", "ammo", "money", "vehicle")):
            continue

        try:
            _, items = item_pool_cdo.SpawnBalancedInventoryFromInventoryBalanceDefinition(
                InvBalanceDefinition=b_def,
                Quantity=1,
                GameStage=player_level,
                AwesomeLevel=5,
                ContextSource=pawn,
                SpawnedInventory=()
            )
            if items:
                for itm in items:
                    if not itm:
                        continue
                    if hasattr(pawn, "InvManager") and pawn.InvManager:
                        try:
                            pawn.InvManager.RemoveFromInventory(itm)
                        except Exception:
                            pass

                    name = itm.GetHumanReadableName() if hasattr(itm, "GetHumanReadableName") else str(itm)
                    if name and name not in seen:
                        seen.add(name)
                        cat, subcat = classify_item(itm)
                        collected.append((itm, cat, subcat, name))
        except Exception:
            pass

    missions = list(unrealsdk.find_all("MissionDefinition"))
    for m in missions:
        if not m:
            continue
        for r_name in ("Reward", "AlternativeReward"):
            rew = getattr(m, r_name, None)
            if not rew:
                continue
            r_items = getattr(rew, "RewardItems", []) or []
            for r_item in r_items:
                if not r_item:
                    continue
                try:
                    _, items = item_pool_cdo.SpawnBalancedInventoryFromInventoryBalanceDefinition(
                        InvBalanceDefinition=r_item,
                        Quantity=1,
                        GameStage=player_level,
                        AwesomeLevel=5,
                        ContextSource=pawn,
                        SpawnedInventory=()
                    )
                    if items:
                        for itm in items:
                            if not itm:
                                continue
                            if hasattr(pawn, "InvManager") and pawn.InvManager:
                                try:
                                    pawn.InvManager.RemoveFromInventory(itm)
                                except Exception:
                                    pass
                            name = itm.GetHumanReadableName() if hasattr(itm, "GetHumanReadableName") else str(itm)
                            if name and name not in seen:
                                seen.add(name)
                                cat, subcat = classify_item(itm)
                                collected.append((itm, "quests", subcat, name))
                except Exception:
                    pass

    collected.sort(key=lambda x: (
        CATEGORY_ORDER.get(x[1], 99),
        SUBCAT_ORDER.get(x[2], 99),
        x[3]
    ))

    return [(item, cat, subcat) for item, cat, subcat, _ in collected]

def get_current_filtered_pool():
    all_data = build_master_cache()
    if not all_data:
        return []

    cat = CATEGORIES_LIST[CURRENT_CAT_IDX]
    subcat = WEAPON_SUBS_LIST[CURRENT_SUBCAT_IDX]

    filtered = []
    for itm, item_cat, item_subcat in all_data:
        match_cat = (cat == "all" or cat == item_cat)
        if match_cat:
            if cat == "weapons" and subcat != "all" and item_subcat != subcat:
                match_cat = False
            elif cat != "weapons" and subcat != "all" and item_subcat != subcat:
                match_cat = False

        if match_cat:
            filtered.append(itm)
    return filtered

def get_ui_strings(max_pages: int, total_items: int) -> tuple[str, str]:
    cat_key = CATEGORIES_LIST[CURRENT_CAT_IDX]
    sub_key = WEAPON_SUBS_LIST[CURRENT_SUBCAT_IDX]

    cat_label = CAT_LABELS.get(cat_key, cat_key.upper())
    sub_label = SUB_LABELS.get(sub_key, sub_key.upper())

    weapon_label = sub_label if cat_key == "weapons" else "WEAPONS"

    # The vendor movie never displays the hint label, so the controls have to go into the title
    panel_title = f"[Z/X] Page {CURRENT_PAGE}/{max_pages}  [C] {cat_label}  [V] {weapon_label}"
    hint_text = "[Z/X] Page  [C] Category  [V] Weapon type  [Click] Take  [Esc] Close"
    return panel_title, hint_text

def refresh_shop_view():
    global CURRENT_PAGE
    filtered = get_current_filtered_pool()
    total_items = len(filtered)
    if total_items == 0:
        return

    max_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    CURRENT_PAGE = max(1, min(CURRENT_PAGE, max_pages))

    start_idx = (CURRENT_PAGE - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_items = filtered[start_idx:end_idx]

    panel_title, hint_text = get_ui_strings(max_pages, total_items)
    update_vendor_items(page_items, title=panel_title, hint=hint_text)

def handle_purchase(item, _movie):
    pc = get_pc()
    pawn = pc.Pawn if pc else None
    if not item or not pawn:
        return

    inv_mgr = getattr(pawn, "InvManager", None)
    if not inv_mgr:
        return

    def_data = getattr(item, "DefinitionData", None)
    new_item = None

    try:
        if def_data is not None:
            if item.Class._inherits(unrealsdk.find_class("WillowWeapon")):
                new_item = CREATE_WEAPON_FROM_DEF(
                    NewWeaponDef=def_data,
                    PlayerOwner=pawn,
                    bForceSelectNameParts=True,
                )
            else:
                new_item = CREATE_ITEM_FROM_DEF(
                    NewItemDef=def_data,
                    PlayerOwner=pawn,
                    NewQuantity=1,
                    bForceSelectNameParts=True,
                )
    except Exception as e:
        log(f"Clone error: {e}")

    if new_item is None:
        new_item = item

    if new_item is not None:
        new_item.Owner = pawn
        inv_mgr.AddInventoryToBackpack(new_item)

        if hasattr(inv_mgr, "ForceNetUpdate"):
            inv_mgr.ForceNetUpdate()
        if hasattr(pawn, "ForceNetUpdate"):
            pawn.ForceNetUpdate()

        final_name = new_item.GetHumanReadableName() if hasattr(new_item, "GetHumanReadableName") else str(new_item)
        log(f"Added: {final_name}")
        try:
            show_chat_message(f"Received: {final_name}", user="[Catalog]")
        except Exception:
            pass

def shop_key_handler(_movie, key: str, _event: int) -> bool:
    global CURRENT_PAGE, CURRENT_CAT_IDX, CURRENT_SUBCAT_IDX

    # Only react to key presses, not repeats or releases
    if _event != 0:
        return False

    if key in ("Z", "LeftBracket"):
        filtered = get_current_filtered_pool()
        max_pages = max(1, (len(filtered) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        CURRENT_PAGE = max(1, CURRENT_PAGE - 1)
        refresh_shop_view()
        return True

    elif key in ("X", "RightBracket"):
        filtered = get_current_filtered_pool()
        max_pages = max(1, (len(filtered) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        CURRENT_PAGE = min(max_pages, CURRENT_PAGE + 1)
        refresh_shop_view()
        return True

    elif key == "C":
        CURRENT_CAT_IDX = (CURRENT_CAT_IDX + 1) % len(CATEGORIES_LIST)
        CURRENT_SUBCAT_IDX = 0
        CURRENT_PAGE = 1
        category_spinner.value = CATEGORIES_LIST[CURRENT_CAT_IDX]
        weapon_sub_spinner.value = "all"
        refresh_shop_view()
        return True

    elif key == "V":
        if CATEGORIES_LIST[CURRENT_CAT_IDX] != "weapons":
            CURRENT_CAT_IDX = CATEGORIES_LIST.index("weapons")
            category_spinner.value = "weapons"
            CURRENT_SUBCAT_IDX = 1
        else:
            CURRENT_SUBCAT_IDX = (CURRENT_SUBCAT_IDX + 1) % len(WEAPON_SUBS_LIST)

        CURRENT_PAGE = 1
        weapon_sub_spinner.value = WEAPON_SUBS_LIST[CURRENT_SUBCAT_IDX]
        refresh_shop_view()
        return True

    return False

def open_master_shop():
    global CURRENT_PAGE
    if show_vendor is None:
        log("custom_vendor library not found!")
        return

    filtered = get_current_filtered_pool()
    total_items = len(filtered)
    if total_items == 0:
        return

    max_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    CURRENT_PAGE = 1

    start_idx = 0
    end_idx = ITEMS_PER_PAGE
    page_items = filtered[start_idx:end_idx]

    panel_title, hint_text = get_ui_strings(max_pages, total_items)

    show_vendor(
        items=page_items,
        on_select=handle_purchase,
        key_handler=shop_key_handler,
        title=panel_title,
        hint=hint_text,
    )

@SpinnerOption(
    identifier="Shop Category",
    value="all",
    choices=CATEGORIES_LIST,
    description="Main category."
)
def category_spinner(opt: SpinnerOption, val: str) -> None:
    global CURRENT_CAT_IDX
    if val in CATEGORIES_LIST:
        CURRENT_CAT_IDX = CATEGORIES_LIST.index(val)

@SpinnerOption(
    identifier="Weapon Subcategory",
    value="all",
    choices=WEAPON_SUBS_LIST,
    description="Weapon type."
)
def weapon_sub_spinner(opt: SpinnerOption, val: str) -> None:
    global CURRENT_SUBCAT_IDX
    if val in WEAPON_SUBS_LIST:
        CURRENT_SUBCAT_IDX = WEAPON_SUBS_LIST.index(val)

@hook("WillowGame.WillowUIInteraction:InputKey", Type.PRE)
def ui_interaction_input_key(_1, args, _3, _4):
    key = str(getattr(args, "Key", ""))
    event = getattr(args, "Event", None)

    if event == 0 and open_key.value and key == open_key.value:
        pc = get_pc()
        if not pc:
            return None

        # 1. Don't open twice
        if is_vendor_open():
            return Block, True

        # 2. Don't open while the inventory, pause or another menu is open
        mgr = getattr(pc, "GFxUIManager", None)
        if mgr and hasattr(mgr, "ScreenMovies"):
            # Any open screen besides the base HUD/Echo
            active_screens = [m for m in mgr.ScreenMovies if m and "EchoVersion" not in m.Class.Name]
            if active_screens:
                return Block, True

        # 3. Open the catalog and stop the game from handling the key
        open_master_shop()
        return Block, True

    return None

# The catalog items are actors in the current level and get destroyed with it
@hook("Engine.WorldInfo:PreExitMap")
def on_pre_exit_map(_obj, _args, _ret, _func):
    global CACHED_MASTER_ITEMS
    CACHED_MASTER_ITEMS = []

def on_enable() -> None:
    log(f"Loaded. [{open_key.value}] opens the catalog.")

mod = build_mod(
    options=[open_key, category_spinner, weapon_sub_spinner],
    on_enable=on_enable,
)
