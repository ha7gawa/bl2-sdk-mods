"""
Dumps the states and the camera/menu related functions of the player controller and the main UI
classes into a text file, for figuring out which functions to hook.

Run it from the SDK console with: pyexec <path to this file>
"""

import os
import unrealsdk
from mods_base import get_pc

OUTPUT_FILE = os.path.abspath("player_full_states_and_methods.txt")

def inspect_uclass(uclass):
    fields = {
        "states": [],
        "functions": [],
        "camera_functions": [],
        "menu_functions": [],
        "properties": []
    }

    if not uclass:
        return fields

    cur = uclass.Children
    while cur:
        name = cur.Name
        cname = cur.Class.Name

        if cname == "State":
            fields["states"].append(name)
        elif cname == "Function":
            fields["functions"].append(name)
            lower_name = name.lower()
            if any(k in lower_name for k in ("cam", "view", "behind", "third", "first", "rotation")):
                fields["camera_functions"].append(name)
            if any(k in lower_name for k in ("menu", "shop", "status", "vendor", "inventory", "cinematic", "interact")):
                fields["menu_functions"].append(name)
        elif "Property" in cname:
            fields["properties"].append(f"{name} ({cname})")

        cur = cur.Next

    return fields

def run_dump():
    pc = get_pc()
    if not pc:
        print("[DUMP_ERR] PlayerController not found!")
        return

    lines = []
    lines.append("=" * 80)
    lines.append("BORDERLANDS 2: PLAYER CONTROLLER AND UI STATES AND METHODS")
    lines.append("=" * 80 + "\n")

    # Live values of the controller
    lines.append("--- STATE AT THE TIME OF THE DUMP ---")
    lines.append(f"PC Class                  : {pc.Class.Name}")
    lines.append(f"PC StateName              : {getattr(pc, 'StateName', 'None')}")
    lines.append(f"bViewingThirdPersonMenu   : {getattr(pc, 'bViewingThirdPersonMenu', 'None')}")
    lines.append(f"CurrentThirdPersonMovie   : {getattr(pc, 'CurrentThirdPersonMovie', 'None')}")
    lines.append(f"ActiveShop                : {getattr(pc, 'ActiveShop', 'None')}")
    lines.append(f"bIsShopping               : {getattr(pc, 'bIsShopping', 'None')}")
    lines.append(f"BehindView                : {getattr(pc, 'bBehindView', 'None')}")
    lines.append(f"CalcViewActor             : {getattr(pc, 'CalcViewActor', 'None')}")
    lines.append(f"FocusObject               : {getattr(pc, 'FocusObject', 'None')}")
    lines.append("\n" + "=" * 80 + "\n")

    classes_to_dump = [
        ("WillowPlayerController", pc.Class),
        ("PlayerController", unrealsdk.find_class("PlayerController")),
        ("WillowPlayerPawn", getattr(pc.Pawn, "Class", unrealsdk.find_class("WillowPlayerPawn")) if getattr(pc, "Pawn", None) else unrealsdk.find_class("WillowPlayerPawn")),
        ("StatusMenuExGFxMovie", unrealsdk.find_class("StatusMenuExGFxMovie")),
        ("VendingMachineExGFxMovie", unrealsdk.find_class("VendingMachineExGFxMovie")),
        ("WillowGFxUIManager", unrealsdk.find_class("WillowGFxUIManager"))
    ]

    for label, ucls in classes_to_dump:
        if not ucls:
            continue
        info = inspect_uclass(ucls)
        lines.append(f"[{label.upper()}] (Super: {ucls.SuperField.Name if ucls.SuperField else 'None'})")

        lines.append(f"  > STATES ({len(info['states'])}):")
        for st in sorted(info["states"]):
            lines.append(f"      * {st}")
        if not info["states"]:
            lines.append("      (No own states, inherited from the parent)")

        lines.append(f"\n  > CAMERA / VIEW METHODS ({len(info['camera_functions'])}):")
        for fn in sorted(info["camera_functions"]):
            lines.append(f"      * {fn}")

        lines.append(f"\n  > MENU / SHOP / INTERACTION METHODS ({len(info['menu_functions'])}):")
        for fn in sorted(info["menu_functions"]):
            lines.append(f"      * {fn}")

        lines.append("\n" + "-" * 80 + "\n")

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[DUMP_SUCCESS] Dump saved to: {OUTPUT_FILE}")
    except Exception as e:
        print(f"[DUMP_ERR] Could not save the file: {e}")

run_dump()
