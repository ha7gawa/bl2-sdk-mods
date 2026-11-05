from typing import Callable, Sequence
import unrealsdk
from mods_base import Game, get_pc, hook
from unrealsdk.hooks import Block, Type
from unrealsdk.unreal import UObject

__all__ = (
    "show_vendor",
    "close_vendor",
    "update_vendor_items",
    "update_vendor_labels",
    "is_vendor_open",
)

VENDOR_GFX_DEF_NAME = "custom_vendor_gfx_def"
vendor_gfx_def: UObject | None = None

REQUIRED_PACKAGES = {
    Game.BL2: ("Sanctuary_P", "Sanctuary_Dynamic"),
    Game.TPS: ("Spaceport_Combat",),
    Game.AoDK: ("Village_P",),
}

is_active: bool = False
active_movie: UObject | None = None
current_items: list[UObject] = []

on_select_callback: Callable[[UObject, UObject], None] | None = None
on_close_callback: Callable[[], None] | None = None
custom_key_handler: Callable[[UObject, str, int], bool] | None = None

EShopType = unrealsdk.find_enum("EShopType")

# Plain 0 since there is no IST_None, keeps the list in the order we pass it
SORT_CONFIG = unrealsdk.make_struct(
    "SortFilterConfiguration",
    SortType=0,
    SortTitleLookupKey="all",
)

def log(msg: str) -> None:
    print(f"[CUSTOM_VENDOR] {msg}")

def is_vendor_open() -> bool:
    return is_active and active_movie is not None

def get_or_create_gfx_def() -> UObject:
    global vendor_gfx_def
    if vendor_gfx_def is not None:
        return vendor_gfx_def

    curr_game = Game.get_current()
    if curr_game in REQUIRED_PACKAGES:
        for pkg in REQUIRED_PACKAGES[curr_game]:
            unrealsdk.load_package(pkg)

    black_market = unrealsdk.find_object(
        "VendingMachineExGFxDefinition",
        "UI_VendingMachine.VendingMachineDef_BlackMarket",
    )
    vendor_gfx_def = unrealsdk.construct_object(
        black_market.Class,
        unrealsdk.find_object("Package", "Engine"),
        VENDOR_GFX_DEF_NAME,
        0x4000,
        black_market,
    )
    vendor_gfx_def.bCustomStoragePanelTint = True
    vendor_gfx_def.bShouldAllowCompare = False
    vendor_gfx_def.bShouldShowAmmoPanel = False
    return vendor_gfx_def

def reset_state() -> None:
    global is_active, active_movie, current_items
    global on_select_callback, on_close_callback, custom_key_handler
    is_active = False
    active_movie = None
    current_items = []
    on_select_callback = None
    on_close_callback = None
    custom_key_handler = None

    _hook_start.disable()
    _hook_hide_iotd.disable()
    _hook_refresh_left.disable()
    _hook_block_scrolling_sort.disable()
    _hook_force_no_sell.disable()
    _hook_block_timer.disable()
    _hook_block_transient.disable()
    _hook_cell_pressed.disable()
    _hook_main_input.disable()
    _hook_cancel_pressed.disable()
    _hook_on_close.disable()

def close_vendor() -> None:
    global active_movie
    if active_movie is not None:
        try:
            active_movie.Close(False)
        except Exception as e:
            log(f"Close error: {e}")
    reset_state()

def update_vendor_labels(title: str = "", subtitle: str = "", hint: str = "") -> None:
    global active_movie
    if not active_movie:
        return
    try:
        if title:
            active_movie.BlackMarketTitle = title
            active_movie.StoragePanelLabel = title
            two_panel = getattr(active_movie, "TwoPanelInterface", None)
            if two_panel and hasattr(two_panel, "StoragePanel"):
                sp = two_panel.StoragePanel
                if hasattr(sp, "SetPanelTitle"):
                    sp.SetPanelTitle(title)
        if hint:
            active_movie.VisitLabel_BlackMarket = hint
    except Exception:
        pass

def update_vendor_items(items: Sequence[UObject], title: str = "", hint: str = "") -> None:
    global current_items, active_movie
    if not active_movie:
        return

    valid = [x for x in items if x is not None]
    current_items = list(valid)

    _hook_refresh_left.enable()
    _hook_block_scrolling_sort.enable()

    two_panel = getattr(active_movie, "TwoPanelInterface", None)
    if two_panel:
        storage_panel = getattr(two_panel, "StoragePanel", None)
        if storage_panel:
            storage_panel.SetList(tuple(current_items), SORT_CONFIG, 0)
            storage_panel.CurrentSelectedIndex = 0
            storage_panel.FixupSelectedIndex()
            two_panel.bLeftPanelRefreshed = True

    if title or hint:
        update_vendor_labels(title, "", hint)

def show_vendor(
    items: Sequence[UObject],
    iotd: UObject | None = None,
    on_select: Callable[[UObject, UObject], None] | None = None,
    on_close: Callable[[], None] | None = None,
    key_handler: Callable[[UObject, str, int], bool] | None = None,
    title: str = "SHOP",
    hint: str = "",
) -> None:
    global is_active, active_movie, current_items
    global on_select_callback, on_close_callback, custom_key_handler

    valid = [x for x in items if x is not None]
    if not valid:
        if on_close:
            on_close()
        return

    is_active = True
    current_items = list(valid)
    on_select_callback = on_select
    on_close_callback = on_close
    custom_key_handler = key_handler

    _hook_start.enable()
    _hook_hide_iotd.enable()
    _hook_refresh_left.enable()
    _hook_block_scrolling_sort.enable()
    _hook_force_no_sell.enable()
    _hook_block_timer.enable()
    _hook_block_transient.enable()
    _hook_cell_pressed.enable()
    _hook_main_input.enable()
    _hook_cancel_pressed.enable()
    _hook_on_close.enable()

    pc = get_pc()
    movie = pc.GFxUIManager.PlayMovie(get_or_create_gfx_def())
    active_movie = movie
    movie.BlackMarketTitle = title
    movie.StoragePanelLabel = title
    movie.VisitLabel_BlackMarket = hint

@hook("WillowGame.VendingMachineExGFxMovie:Start", Type.POST)
def _hook_start(obj, _args, _ret, _func):
    _hook_start.disable()
    obj.ShopType = EShopType.SType_BlackMarket

@hook("WillowGame.VendingMachineExGFxMovie:extInitItemOfTheDayPanel")
def _hook_hide_iotd(obj, args, _ret, _func):
    _hook_hide_iotd.disable()
    try:
        iotd_panel = obj.GetVariableObject(
            args.ItemOfTheDayPanelPath,
            unrealsdk.find_class("ItemOfTheDayPanelGFxObject"),
        )
        if iotd_panel:
            iotd_panel.SetVisible(False)
    except Exception:
        pass
    return Block

# Block all sorting inside the scrolling list
@hook("WillowGame.WillowScrollingList:Sort", Type.PRE)
def _hook_block_scrolling_sort(_obj, _args, _ret, _func):
    return Block

@hook("WillowGame.TwoPanelInterfaceGFxObject:RefreshLeftPanel")
def _hook_refresh_left(obj, _args, _ret, _func):
    storage_panel = getattr(obj, "StoragePanel", None)
    if not storage_panel:
        return Block

    display = [x for x in current_items if x is not None]
    try:
        storage_panel.SetList(tuple(display), SORT_CONFIG, 0)
    except Exception as e:
        log(f"SetList error: {e}")

    try:
        storage_panel.CurrentSelectedIndex = 0
        storage_panel.FixupSelectedIndex()
    except Exception:
        pass

    obj.bLeftPanelRefreshed = True
    return Block

@hook("WillowGame.VendingMachineExGFxMovie:IsCurrentSelectionSell")
def _hook_force_no_sell(*_):
    return Block, False

@hook("WillowGame.VendingMachineExGFxMovie:SetVendingMachineRefreshTimer")
def _hook_block_timer(*_):
    _hook_block_timer.disable()
    return Block

@hook("WillowGame.VendingMachineExGFxMovie:RefreshTransientData")
def _hook_block_transient(*_):
    return Block

@hook("WillowGame.VendingMachineExGFxMovie:OnCellPressed", Type.PRE)
def _hook_cell_pressed(obj, _args, _ret, _func):
    two_panel = getattr(obj, "TwoPanelInterface", None)
    storage_panel = getattr(two_panel, "StoragePanel", None) if two_panel else None

    selection = getattr(obj, "CurrentSelectionItem", None)
    selected_idx = -1

    if storage_panel is not None:
        selected_idx = getattr(storage_panel, "CurrentSelectedIndex", -1)

    if selection is None and storage_panel is not None:
        if 0 <= selected_idx < len(current_items):
            selection = current_items[selected_idx]

    if selection is not None and on_select_callback is not None:
        try:
            on_select_callback(selection, obj)
        except Exception as e:
            log(f"Error in on_select_callback: {e}")

    return None

@hook("WillowGame.VendingMachineExGFxMovie:MainInputKey", Type.PRE)
def _hook_main_input(obj, args, _ret, _func):
    event = getattr(args, "uevent", getattr(args, "Event", None))
    key = str(getattr(args, "ukey", getattr(args, "Key", "")))

    if custom_key_handler is not None:
        if custom_key_handler(obj, key, event):
            return Block, True

    if event == 0 and key in ("Escape", "XboxTypeS_B"):
        close_vendor()
        return Block, True

    return None

@hook("WillowGame.VendingMachineExGFxMovie:extOnCancelPressed", Type.PRE)
def _hook_cancel_pressed(obj, _args, _ret, _func):
    if custom_key_handler is not None:
        if custom_key_handler(obj, "Escape", 0):
            return Block, True
    close_vendor()
    return Block, True

@hook("WillowGame.VendingMachineExGFxMovie:OnClose", Type.POST)
def _hook_on_close(*_):
    cb = on_close_callback
    reset_state()
    if cb:
        cb()