from copy import copy
import time
import unrealsdk
from mods_base import KeybindOption, build_mod, get_pc, hook
from unrealsdk.hooks import Block, Type
from ui_utils import show_chat_message

try:
    import custom_vendor
except ImportError:
    custom_vendor = None

EPartReplacementMode = unrealsdk.find_enum("EPartReplacementMode")

CREATE_WEAPON_FROM_DEF = unrealsdk.find_class("WillowWeapon").ClassDefaultObject.CreateWeaponFromDef
CREATE_ITEM_FROM_DEF = unrealsdk.find_class("WillowItem").ClassDefaultObject.CreateItemFromDef
SPAWN_FROM_BAL_DEF = unrealsdk.find_class("ItemPool").ClassDefaultObject.SpawnBalancedInventoryFromInventoryBalanceDefinition

STATE_IDLE = 0
STATE_SLOTS = 1
STATE_PARTS = 2
STATE_LEVELS = 3

current_state = STATE_IDLE
original_item = None
current_def_data = None
current_replacements = []
current_slot_info = None
pending_inventory_return = False
last_esc_time = 0.0

_dummy_to_slot_map = {}
_item_to_part_map = {}
_level_options_map = {}
_slot_dummy_objects = {}

edit_key = KeybindOption(
    "Edit Item Key",
    "F9",
    description="Open the inventory, hover over a weapon or item and press this key to edit it.",
)

def log(msg: str) -> None:
    print(f"[ITEM_EDITOR] {msg}")

def is_weapon() -> bool:
    global original_item
    return original_item.Class._inherits(unrealsdk.find_class("WillowWeapon"))

def get_part_friendly_name(part) -> str:
    if not part:
        return "NONE / DEFAULT"
    name = getattr(part, "PartName", "")
    if name:
        return str(name)
    prefixes = getattr(part, "PrefixList", None)
    if prefixes and len(prefixes) > 0:
        p_name = getattr(prefixes[0], "PartName", "")
        if p_name:
            return str(p_name)
    parts = part.Name.split("_")
    return parts[-1] if len(parts) > 1 else part.Name

# --- Slot mappings, following the balance part lists (see Vendor Edit's replacement_lists) ---

WEAPON_SLOTS_SCHEMA = [
    ("BodyPartDefinition", "BodyPartData", "BODY"),
    ("GripPartDefinition", "GripPartData", "GRIP"),
    ("BarrelPartDefinition", "BarrelPartData", "BARREL"),
    ("SightPartDefinition", "SightPartData", "SIGHT"),
    ("StockPartDefinition", "StockPartData", "STOCK"),
    ("ElementalPartDefinition", "ElementalPartData", "ELEMENT"),
    ("Accessory1PartDefinition", "Accessory1PartData", "ACCESSORY"),
    ("Accessory2PartDefinition", "Accessory2PartData", "ALT ACCESSORY"),
    ("MaterialPartDefinition", "MaterialPartData", "MATERIAL"),
]

ITEM_PARTS_KEYS = [
    ("AlphaItemPartDefinition", "AlphaPartData", "AlphaParts", "ALPHA"),
    ("BetaItemPartDefinition", "BetaPartData", "BetaParts", "BETA"),
    ("GammaItemPartDefinition", "GammaPartData", "GammaParts", "GAMMA"),
    ("DeltaItemPartDefinition", "DeltaPartData", "DeltaParts", "DELTA"),
    ("EpsilonItemPartDefinition", "EpsilonPartData", "EpsilonParts", "EPSILON"),
    ("ZetaItemPartDefinition", "ZetaPartData", "ZetaParts", "ZETA"),
    ("EtaItemPartDefinition", "EtaPartData", "EtaParts", "ETA"),
    ("ThetaItemPartDefinition", "ThetaPartData", "ThetaParts", "THETA"),
    ("MaterialItemPartDefinition", "MaterialPartData", "MaterialParts", "MATERIAL"),
]

ITEM_SLOT_LABELS = {
    "WillowShield": {
        "DeltaItemPartDefinition": "ACCESSORY (Delta)",
        "BetaItemPartDefinition": "BATTERY (Beta)",
        "AlphaItemPartDefinition": "BODY (Alpha)",
        "GammaItemPartDefinition": "CAPACITOR (Gamma)",
        "MaterialItemPartDefinition": "MATERIAL",
    },
    "WillowGrenadeMod": {
        "DeltaItemPartDefinition": "ACCESSORY (Delta)",
        "ZetaItemPartDefinition": "BLAST RADIUS (Zeta)",
        "EtaItemPartDefinition": "CHILD COUNT (Eta)",
        "EpsilonItemPartDefinition": "DAMAGE (Epsilon)",
        "BetaItemPartDefinition": "DELIVERY (Beta)",
        "AlphaItemPartDefinition": "PAYLOAD (Alpha)",
        "ThetaItemPartDefinition": "STATUS DAMAGE (Theta)",
        "GammaItemPartDefinition": "TRIGGER (Gamma)",
        "MaterialItemPartDefinition": "MATERIAL",
    },
    "WillowClassMod": {
        "AlphaItemPartDefinition": "SPECIALIZATION (Alpha)",
        "BetaItemPartDefinition": "PRIMARY (Beta)",
        "GammaItemPartDefinition": "SECONDARY (Gamma)",
        "MaterialItemPartDefinition": "PENALTY (Material)",
    },
    "WillowArtifact": {
        "EtaItemPartDefinition": "BODY (Eta)",
        "ThetaItemPartDefinition": "UPGRADE (Theta)",
        "MaterialItemPartDefinition": "ELEMENT / MATERIAL",
    },
}

def get_item_slot_title(cls, def_field: str, default_label: str) -> str:
    for base_cls_name, mapping in ITEM_SLOT_LABELS.items():
        base_cls = unrealsdk.find_class(base_cls_name)
        if base_cls and cls._inherits(base_cls):
            if def_field in mapping:
                return mapping[def_field]
    return default_label

# --- Collect the parts the balance actually allows ---

def collect_native_slots(inv, def_data):
    slots = []
    balance = getattr(def_data, "BalanceDefinition", None)
    if not balance:
        return slots

    if is_weapon():
        part_col = getattr(balance, "RuntimePartListCollection", None) or getattr(balance, "PartListCollection", None)
        if not part_col:
            return slots

        for def_field, col_attr, label in WEAPON_SLOTS_SCHEMA:
            p_data = getattr(part_col, col_attr, None)
            if p_data and getattr(p_data, "bEnabled", True):
                w_parts = getattr(p_data, "WeightedParts", [])
                parts = [wp.Part for wp in w_parts if getattr(wp, "Part", None) is not None]
                if parts:
                    slots.append((def_field, parts, label))
        return slots

    # Items (shields, grenades, class mods, relics)
    definition = getattr(balance, "InventoryDefinition", None)
    part_col = getattr(balance, "RuntimePartListCollection", None) or getattr(balance, "PartListCollection", None)
    rep_mode = getattr(part_col, "PartReplacementMode", None) if part_col else None

    for def_field, col_attr, def_attr, default_label in ITEM_PARTS_KEYS:
        parts_set = []

        # 1. Parts from the base InventoryDefinition
        if definition:
            def_part_list = getattr(definition, def_attr, None)
            if def_part_list:
                for wp in getattr(def_part_list, "WeightedParts", []):
                    p = getattr(wp, "Part", None)
                    if p is not None and p not in parts_set:
                        parts_set.append(p)

        # 2. Apply the balance's part collection according to PartReplacementMode
        if part_col:
            col_part_list = getattr(part_col, col_attr, None)
            if col_part_list and getattr(col_part_list, "bEnabled", True):
                new_parts = []
                for wp in getattr(col_part_list, "WeightedParts", []):
                    p = getattr(wp, "Part", None)
                    if p is not None and p not in new_parts:
                        new_parts.append(p)

                if rep_mode == EPartReplacementMode.EPRM_Complete:
                    parts_set = new_parts
                elif rep_mode == EPartReplacementMode.EPRM_Additive:
                    for np in new_parts:
                        if np not in parts_set:
                            parts_set.append(np)
                elif rep_mode == EPartReplacementMode.EPRM_Selective:
                    if new_parts:
                        parts_set = new_parts

        if parts_set:
            label = get_item_slot_title(inv.Class, def_field, default_label)
            slots.append((def_field, parts_set, label))

    return slots

def create_fresh_item(def_data, pawn, b_readied: bool = False, custom_level: int = None):
    new_def = copy(def_data)
    new_def.UniqueId = int(time.time() * 1000) % 2147483647
    if custom_level is not None:
        new_def.ManufacturerGradeIndex = custom_level
        new_def.GameStage = custom_level

    try:
        if is_weapon():
            item = CREATE_WEAPON_FROM_DEF(NewWeaponDef=new_def, PlayerOwner=pawn, bForceSelectNameParts=True)
        else:
            item = CREATE_ITEM_FROM_DEF(NewItemDef=new_def, PlayerOwner=pawn, NewQuantity=1, bForceSelectNameParts=True)
        if item:
            item.Owner = pawn
            setattr(item, "bReadied", b_readied)
            if hasattr(item, "InitializeInternal"):
                try:
                    item.InitializeInternal()
                except Exception:
                    pass
            return item
    except Exception as e:
        log(f"CreateFreshItem error: {e}")
    return None

def get_slot_dummy_item(slot_key: str, display_title: str, pawn):
    global _slot_dummy_objects

    base_bal = unrealsdk.find_object("InventoryBalanceDefinition", "GD_CustomItems.Items.CustomItem_SDU_Bank")
    engine_pkg = unrealsdk.find_object("Package", "Engine")
    if not base_bal or not engine_pkg:
        return None

    try:
        if slot_key not in _slot_dummy_objects:
            new_bal = unrealsdk.construct_object(base_bal.Class, engine_pkg, f"DBal_{abs(hash(slot_key)) % 1000000}", 0x4000, base_bal)
            base_part_list = new_bal.PartListCollection
            new_part_list = unrealsdk.construct_object(base_part_list.Class, engine_pkg, f"DCol_{abs(hash(slot_key)) % 1000000}", 0, base_part_list)
            new_bal.PartListCollection = new_part_list

            alpha_data = new_part_list.AlphaPartData.WeightedParts[0]
            base_part = alpha_data.Part
            new_part = unrealsdk.construct_object(base_part.Class, engine_pkg, f"DPart_{abs(hash(slot_key)) % 1000000}", 0, base_part)
            alpha_data.Part = new_part
            new_part_list.MaterialPartData.WeightedParts[0].Part = new_part

            new_part.CustomPresentations.clear()

            base_prefix = base_part.PrefixList[0]
            new_prefix = unrealsdk.construct_object(base_prefix.Class, engine_pkg, f"DPfx_{abs(hash(slot_key)) % 1000000}", 0, base_prefix)
            new_prefix.PartName = display_title
            new_part.PrefixList = (new_prefix,)

            _, spawned = SPAWN_FROM_BAL_DEF(
                InvBalanceDefinition=new_bal,
                Quantity=1,
                GameStage=1,
                AwesomeLevel=0,
                ContextSource=pawn,
                SpawnedInventory=(),
            )
            if spawned:
                _slot_dummy_objects[slot_key] = (spawned[0], new_prefix)
        else:
            item, prefix_obj = _slot_dummy_objects[slot_key]
            prefix_obj.PartName = display_title

        return _slot_dummy_objects[slot_key][0]
    except Exception as e:
        log(f"Dummy error for {slot_key}: {e}")
        return None

def clone_current_item_to_backpack():
    global current_def_data
    if not current_def_data:
        return

    pc = get_pc()
    owner = pc.Pawn if pc else None
    inv_mgr = getattr(owner, "InvManager", None) if owner else None
    if not inv_mgr:
        return

    clone_def = copy(current_def_data)
    clone_def.UniqueId = int(time.time() * 1000) % 2147483647

    if is_weapon():
        inv_mgr.ClientAddWeaponToBackpack(DefinitionData=clone_def, Mark=0, bReadyAfterAdd=False)
    else:
        inv_mgr.ClientAddItemToBackpack(DefinitionData=clone_def, Quantity=1, Mark=0, bReadyAfterAdd=False)

    if hasattr(inv_mgr, "ForceNetUpdate"):
        inv_mgr.ForceNetUpdate()

    show_chat_message("★ Clone added to your backpack!", user="[Item Editor]")

# ================= SCREENS =================

def render_slots_view():
    global current_state, current_replacements
    current_state = STATE_SLOTS
    _dummy_to_slot_map.clear()
    _item_to_part_map.clear()
    _level_options_map.clear()

    pc = get_pc()
    pawn = pc.Pawn if pc else None

    # 1. Preview of the item being edited
    top_item = create_fresh_item(current_def_data, pawn, b_readied=True)
    display_items = [top_item] if top_item else []

    # 2. Level selector
    cur_lvl = current_def_data.ManufacturerGradeIndex
    lvl_dummy = get_slot_dummy_item("__LEVEL__", f"★ LEVEL: {cur_lvl}", pawn)
    if lvl_dummy:
        _dummy_to_slot_map[lvl_dummy] = "__LEVEL_SELECTOR__"
        display_items.append(lvl_dummy)

    # 3. Clone
    clone_dummy = get_slot_dummy_item("__CLONE__", "★ CREATE A COPY (CLONE)", pawn)
    if clone_dummy:
        _dummy_to_slot_map[clone_dummy] = "__CLONE_ACTION__"
        display_items.append(clone_dummy)

    # 4. Part slots from the balance
    slots_info = collect_native_slots(original_item, current_def_data)
    current_replacements = slots_info

    for def_field, parts, display_label in slots_info:
        cur_part = getattr(current_def_data, def_field, None)
        installed_name = get_part_friendly_name(cur_part)
        title = f"{display_label}: {installed_name}"
        dummy = get_slot_dummy_item(def_field, title, pawn)
        if dummy:
            _dummy_to_slot_map[dummy] = def_field
            display_items.append(dummy)

    item_name = top_item.GetHumanReadableName() if top_item else "Item"
    custom_vendor.update_vendor_items(
        display_items,
        title=f"EDITOR: {item_name}",
        hint="[Click] Open slot / change level / clone | [ESC] Save and back to inventory",
    )

def render_parts_view(slot_field: str, parts_list: list, slot_label: str):
    global current_state, current_slot_info
    current_state = STATE_PARTS
    current_slot_info = (slot_field, parts_list, slot_label)
    _dummy_to_slot_map.clear()
    _item_to_part_map.clear()
    _level_options_map.clear()

    pc = get_pc()
    pawn = pc.Pawn if pc else None

    top_item = create_fresh_item(current_def_data, pawn, b_readied=True)
    display_items = [top_item] if top_item else []

    cur_installed_part = getattr(current_def_data, slot_field, None)

    for p in parts_list:
        variant_def = copy(current_def_data)
        setattr(variant_def, slot_field, p)
        item_variant = create_fresh_item(variant_def, pawn, b_readied=False)
        if item_variant:
            _item_to_part_map[item_variant] = p
            display_items.append(item_variant)

    installed_name = get_part_friendly_name(cur_installed_part)
    title = f"{slot_label} (Installed: {installed_name})"
    hint = "[ESC] Back to slots | Click a part to install it"
    custom_vendor.update_vendor_items(display_items, title=title, hint=hint)

def render_levels_view():
    global current_state
    current_state = STATE_LEVELS
    _dummy_to_slot_map.clear()
    _item_to_part_map.clear()
    _level_options_map.clear()

    pc = get_pc()
    pawn = pc.Pawn if pc else None
    pri = getattr(pc, "PlayerReplicationInfo", None) if pc else None
    char_level = int(getattr(pri, "ExpLevel", 50)) if pri else 50
    cur_lvl = current_def_data.ManufacturerGradeIndex

    top_item = create_fresh_item(current_def_data, pawn, b_readied=True)
    display_items = [top_item] if top_item else []

    target_levels = []
    if char_level != cur_lvl:
        target_levels.append(char_level)

    for offset in (5, 4, 3, 2, 1, -1, -2, -3, -4, -5):
        lvl = cur_lvl + offset
        if 1 <= lvl <= 90 and lvl not in target_levels and lvl != cur_lvl:
            target_levels.append(lvl)

    target_levels.sort(reverse=True)

    for lvl in target_levels:
        item_variant = create_fresh_item(current_def_data, pawn, b_readied=False, custom_level=lvl)
        if item_variant:
            _level_options_map[item_variant] = lvl
            display_items.append(item_variant)

    title = f"SELECT LEVEL (Current: {cur_lvl})"
    hint = "[ESC] Back to slots | Click a level to apply it"
    custom_vendor.update_vendor_items(display_items, title=title, hint=hint)

# ================= INPUT =================

def on_vendor_item_selected(selected_obj, _movie):
    global current_def_data

    if not selected_obj:
        return

    if current_state == STATE_SLOTS:
        slot_field = _dummy_to_slot_map.get(selected_obj)
        if slot_field == "__LEVEL_SELECTOR__":
            render_levels_view()
            return
        elif slot_field == "__CLONE_ACTION__":
            clone_current_item_to_backpack()
            return
        elif slot_field:
            for def_field, parts, slot_label in current_replacements:
                if def_field == slot_field:
                    render_parts_view(def_field, parts, slot_label)
                    return

    elif current_state == STATE_PARTS:
        chosen_part = _item_to_part_map.get(selected_obj)
        if chosen_part:
            slot_field, parts, slot_label = current_slot_info
            setattr(current_def_data, slot_field, chosen_part)
            current_def_data.UniqueId = int(time.time() * 1000) % 2147483647
            part_name = get_part_friendly_name(chosen_part)
            show_chat_message(f"Installed: {part_name}", user="[Item Editor]")
            render_parts_view(slot_field, parts, slot_label)

    elif current_state == STATE_LEVELS:
        new_lvl = _level_options_map.get(selected_obj)
        if new_lvl is not None:
            current_def_data.ManufacturerGradeIndex = new_lvl
            current_def_data.GameStage = new_lvl
            current_def_data.UniqueId = int(time.time() * 1000) % 2147483647
            show_chat_message(f"Level changed to: {new_lvl}", user="[Item Editor]")
            render_levels_view()

def commit_changes_to_inventory():
    global original_item, current_def_data
    if not original_item or not current_def_data:
        return

    owner = getattr(original_item, "Owner", None) or get_pc().Pawn
    inv_mgr = getattr(owner, "InvManager", None)
    if not inv_mgr:
        return

    is_weap = is_weapon()
    mark = getattr(original_item, "Mark", 0)
    was_ready = getattr(original_item, "bReadied", False)
    quick_slot = getattr(original_item, "QuickSelectSlot", 0) if is_weap else 0

    inv_mgr.RemoveFromInventory(original_item)
    if is_weap:
        inv_mgr.RemoveInventoryFromBackpack(original_item)
        inv_mgr.UpdateBackpackInventoryCount()

    created = None
    if is_weap:
        inv_mgr.ClientAddWeaponToBackpack(DefinitionData=current_def_data, Mark=mark, bReadyAfterAdd=False)
        if hasattr(inv_mgr, "Backpack"):
            for w in reversed(inv_mgr.Backpack):
                if w and getattr(w, "DefinitionData", None) == current_def_data:
                    created = w
                    break
    else:
        inv_mgr.ClientAddItemToBackpack(DefinitionData=current_def_data, Quantity=1, Mark=mark, bReadyAfterAdd=False)
        if hasattr(inv_mgr, "Backpack"):
            for itm in reversed(inv_mgr.Backpack):
                if itm and getattr(itm, "DefinitionData", None) == current_def_data:
                    created = itm
                    break

    if created:
        created.Owner = owner
        if was_ready and created.CanBeUsedBy(owner):
            inv_mgr.ReadyBackpackInventory(created, quick_slot)

    if hasattr(inv_mgr, "ForceNetUpdate"):
        inv_mgr.ForceNetUpdate()

def editor_key_handler(_movie, key: str, event: int) -> bool:
    global current_state, last_esc_time

    if key in ("Escape", "XboxTypeS_B"):
        now = time.time()
        if now - last_esc_time < 0.25:
            return True

        if event == 0:
            last_esc_time = now
            if current_state in (STATE_PARTS, STATE_LEVELS):
                render_slots_view()
                return True
            elif current_state == STATE_SLOTS:
                commit_changes_to_inventory()
                custom_vendor.close_vendor()
                return True

        return True

    return False

def on_editor_closed():
    global current_state, original_item, current_def_data, pending_inventory_return
    current_state = STATE_IDLE
    original_item = None
    current_def_data = None
    _dummy_to_slot_map.clear()
    _item_to_part_map.clear()
    _level_options_map.clear()
    pending_inventory_return = True

@hook("WillowGame.StatusMenuExGFxMovie:HandleInputKey", Type.PRE)
def _on_status_input_key(obj, args, _ret, _func):
    global original_item, current_def_data
    key = str(getattr(args, "ukey", getattr(args, "Key", "")))
    event = getattr(args, "uevent", getattr(args, "Event", None))

    if event == 0 and edit_key.value and key == edit_key.value:
        inv_panel = getattr(obj, "InventoryPanel", None)
        selected_item = inv_panel.GetSelectedThing() if inv_panel else None

        if selected_item and hasattr(selected_item, "DefinitionData"):
            original_item = selected_item
            current_def_data = copy(selected_item.DefinitionData)
            if hasattr(obj, "FinishClosing"):
                obj.FinishClosing()
            else:
                obj.Close(False)
            return Block, True
        else:
            show_chat_message("Hover over an item first!", user="[Item Editor]")
            return Block, True

    return None

@hook("WillowGame.StatusMenuExGFxMovie:OnClose", Type.POST)
def _on_status_closed(_obj, _args, _ret, _func):
    global original_item
    if original_item is not None and custom_vendor:
        item_name = original_item.GetHumanReadableName() if hasattr(original_item, "GetHumanReadableName") else "Item"
        custom_vendor.show_vendor(
            items=[original_item],
            iotd=None,
            on_select=on_vendor_item_selected,
            on_close=on_editor_closed,
            key_handler=editor_key_handler,
            title=f"EDITOR: {item_name}",
            hint="[ESC] Back to inventory",
        )
        render_slots_view()

@hook("WillowGame.EchoVersionGFxMovie:Start", Type.POST)
def _on_echo_started(_obj, _args, _ret, _func):
    global pending_inventory_return
    if pending_inventory_return:
        pending_inventory_return = False
        pc = get_pc()
        if pc:
            pc.ShowStatusMenu_Inventory()

def on_enable():
    log(f"Item editor ready. Open the inventory, hover over an item and press [{edit_key.value}].")

mod = build_mod(options=[edit_key], on_enable=on_enable)
