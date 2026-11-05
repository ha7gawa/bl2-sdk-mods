from typing import Any, Dict, List, Tuple
import unrealsdk
from mods_base import SliderOption, ButtonOption, build_mod

def log(msg: str) -> None:
    print(f"[CLEAN_FX] {msg}")

GROUPS: Dict[str, Dict[str, List[Tuple[Any, List[float]]]]] = {
    "screen_dots": {"size": [], "alpha": []}, # Огонь, кислота, шлак на экране
    "explosions":  {"size": [], "alpha": []}, # Взрывы, сплэш ракетниц, бочки
    "impacts":     {"size": [], "alpha": []}, # Попадания в землю, скалы, металл, пыль
    "tracers":     {"size": [], "alpha": []}, # Следы пуль, эридианские лучи (E-Tech), плазма
    "muzzle":      {"size": [], "alpha": []}, # Дульные вспышки и дым ствола
    "grenades":    {"size": [], "alpha": []}, # Гранаты, шлейфы полета, сингулярности
    "shields":     {"size": [], "alpha": []}, # Щиты персонажа, шипы, нова-вспышки
    "skills":      {"size": [], "alpha": []}, # Шизострел, Бор, скиллы сирены
    "loot_beams":  {"size": [], "alpha": []}, # Столбы света выпавшего лута
    "loot_icons":  {"size": [], "alpha": []}, # Парящие 3D-иконки оружия над лутом
}

def get_path(obj: Any) -> str:
    try:
        if hasattr(obj, "PathName") and callable(obj.PathName):
            return str(obj.PathName(obj))
        return str(getattr(obj, "Name", ""))
    except Exception:
        return ""

def scan_and_route_vfx() -> None:
    for g in GROUPS.values():
        g["size"].clear()
        g["alpha"].clear()

    try:
        all_ps = list(unrealsdk.find_all("ParticleSystem"))
    except Exception as e:
        log(f"Ошибка find_all: {e}")
        return

    log(f"Сортировка {len(all_ps)} систем частиц...")

    for ps in all_ps:
        if not ps:
            continue

        raw_path = get_path(ps)
        path = raw_path.lower()
        if not path:
            continue

        # Прицелы и урон в цифрах не трогаем
        if any(w in path for w in ("scopes", "reticle", "dynamic_number", "part_dynamic_mission")):
            continue

        target_group = None

        # 1. Экранные эффекты урона
        if "fx_int_screen" in path or "elemental_damage" in path:
            target_group = "screen_dots"

        # 2. Лут: разделяем иконки и лучевые столбы
        elif any(p in path for p in ("itemicons", "itemcard", "iconoff")):
            target_group = "loot_icons"
        elif any(p in path for p in ("fx_shared_items", "itemlocator", "lootablelocator", "locatorstick")):
            target_group = "loot_beams"

        # 3. Гранаты (изолированная группа)
        elif any(p in path for p in ("fx_wep_grenades", "grenade_tracer", "singularity", "bouncingbetty")):
            target_group = "grenades"

        # 4. Щиты (изолированная группа)
        elif any(p in path for p in ("fx_char_shared_shield", "spikeshields", "shieldnova", "part_shield")):
            target_group = "shields"

        # 5. Следы пуль и эридианских лучей
        elif any(p in path for p in ("fx_wep_trails", "trails_alien", "tracer", "bullet_projectile", "twister", "gyrojet")):
            target_group = "tracers"

        # 6. Попадания в поверхности и окружение
        elif any(p in path for p in ("bulletimpacts", "bullet_impacts", "groundimpact", "kickup", "scrape")):
            target_group = "impacts"

        # 7. Навыки персонажей
        elif any(p in path for p in ("fx_char_merc", "fx_char_assassin", "fx_char_siren", "fx_characterabilities")):
            target_group = "skills"

        # 8. Взрывы и сплэши
        elif any(p in path for p in ("fx_wep_explosions", "fx_shared_explosions", "fx_wep_launchers", "rl_nuke", "explo_barrel")):
            target_group = "explosions"

        # 9. Дульные вспышки и дым ствола
        elif any(p in path for p in ("fx_wep_alien", "fx_wep_pistol", "fx_wep_smg", "fx_wep_assault", "fx_wep_shotgun", "fx_wep_sniper", "muzzleflash")):
            target_group = "muzzle"

        if not target_group:
            continue

        try:
            emitters = getattr(ps, "Emitters", None)
            if not emitters:
                continue

            for em in emitters:
                if not em:
                    continue
                lods = getattr(em, "LODLevels", None)
                if not lods:
                    continue

                for lod in lods:
                    if not lod:
                        continue
                    modules = getattr(lod, "Modules", None)
                    if not modules:
                        continue

                    for mod in modules:
                        if not mod:
                            continue
                        m_class = getattr(mod, "Class", None)
                        if not m_class:
                            continue

                        curr = getattr(m_class, "Children", None)
                        while curr:
                            try:
                                f_name = curr.Name
                                val = getattr(mod, f_name, None)

                                if val is not None and hasattr(val, "LookupTable"):
                                    tbl = val.LookupTable
                                    if tbl and len(tbl) > 0:
                                        data = [float(x) for x in tbl]
                                        fn_lower = f_name.lower()

                                        if any(k in fn_lower for k in ("alpha", "color", "opacity", "fade")):
                                            GROUPS[target_group]["alpha"].append((val, data))
                                        else:
                                            GROUPS[target_group]["size"].append((val, data))
                            except Exception:
                                pass
                            curr = getattr(curr, "Next", None)
        except Exception:
            continue

    log("=== ИТОГИ МАРШРУТИЗАЦИИ ===")
    for k, v in GROUPS.items():
        log(f"  * {k.upper().ljust(14)} -> Размер: {str(len(v['size'])).ljust(5)} | Альфа: {len(v['alpha'])}")

def apply_group_scale(group: str, sub_type: str, percent: int, min_val: float = 0.0) -> None:
    factor = percent / 100.0
    tables = GROUPS.get(group, {}).get(sub_type, [])
    count = 0
    for st, orig_values in tables:
        try:
            tbl = st.LookupTable
            for i, base in enumerate(orig_values):
                if base != 0.0:
                    val = base * factor
                    if val < min_val and base >= min_val:
                        val = min_val
                    tbl[i] = val
            count += 1
        except Exception:
            pass
    log(f"[{group}::{sub_type}] = {percent}% (обновлено {count})")

# 1. Гранаты (Отдельно)
@SliderOption("1. Grenades: Size (%)", 100, 0, 100, 10, description="Размер эффектов гранат, шлейфов и вортексов.")
def opt_gr_sz(s: SliderOption, val: int) -> None:
    apply_group_scale("grenades", "size", val)

@SliderOption("1. Grenades: Alpha (%)", 100, 0, 100, 10, description="Прозрачность эффектов гранат.")
def opt_gr_al(s: SliderOption, val: int) -> None:
    apply_group_scale("grenades", "alpha", val)

# 2. Щиты (Отдельно)
@SliderOption("2. Shields: Size (%)", 100, 0, 100, 10, description="Размер эффектов новы, шипов и вспышек щитов.")
def opt_sh_sz(s: SliderOption, val: int) -> None:
    apply_group_scale("shields", "size", val)

@SliderOption("2. Shields: Alpha (%)", 100, 0, 100, 10, description="Прозрачность барьеров, вспышек урона и щитов.")
def opt_sh_al(s: SliderOption, val: int) -> None:
    apply_group_scale("shields", "alpha", val)

# 3. Следы пуль и эридианских лучей (Tracers)
@SliderOption("3. Tracers & E-Tech: Size (%)", 100, 0, 100, 10, description="Толщина линий полета пуль, лазеров и плазмы.")
def opt_tr_sz(s: SliderOption, val: int) -> None:
    apply_group_scale("tracers", "size", val)

@SliderOption("3. Tracers & E-Tech: Alpha (%)", 100, 0, 100, 10, description="Прозрачность следов пуль и лазеров.")
def opt_tr_al(s: SliderOption, val: int) -> None:
    apply_group_scale("tracers", "alpha", val)

# 4. Попадания в объекты и окружение
@SliderOption("4. Surface Impacts: Size (%)", 100, 0, 100, 10, description="Размер брызг грязи, искр от стен и осколков камня.")
def opt_imp_sz(s: SliderOption, val: int) -> None:
    apply_group_scale("impacts", "size", val)

@SliderOption("4. Surface Impacts: Alpha (%)", 100, 0, 100, 10, description="Прозрачность эффектов попадания в окружение.")
def opt_imp_al(s: SliderOption, val: int) -> None:
    apply_group_scale("impacts", "alpha", val)

# 5. Взрывы и ракеты
@SliderOption("5. Explosions: Size (%)", 100, 10, 100, 10, description="Размер взрывов, ракетниц и бочек.")
def opt_exp_sz(s: SliderOption, val: int) -> None:
    apply_group_scale("explosions", "size", val, min_val=2.0)

@SliderOption("5. Explosions: Alpha (%)", 100, 0, 100, 10, description="Прозрачность вспышек детонаций.")
def opt_exp_al(s: SliderOption, val: int) -> None:
    apply_group_scale("explosions", "alpha", val)

# 6. Дульные вспышки и дым выстрела
@SliderOption("6. Weapon Muzzle & Smoke: Size (%)", 100, 0, 100, 10, description="Размер пламени и дыма из ствола.")
def opt_muz_sz(s: SliderOption, val: int) -> None:
    apply_group_scale("muzzle", "size", val)

@SliderOption("6. Weapon Muzzle & Smoke: Alpha (%)", 100, 0, 100, 10, description="Прозрачность дульного дыма и вспышек.")
def opt_muz_al(s: SliderOption, val: int) -> None:
    apply_group_scale("muzzle", "alpha", val)

# 7. Иконки предметов над лутом
@SliderOption("7. Loot Floating Icons: Size (%)", 100, 20, 100, 10, description="Размер парящих 3D-иконок оружия/щитов над лутом.")
def opt_licon_sz(s: SliderOption, val: int) -> None:
    apply_group_scale("loot_icons", "size", val, min_val=0.5)

# 8. Столбы света лута
@SliderOption("8. Loot Light Beams: Size (%)", 100, 20, 100, 10, description="Высота и толщина световых столбов редкого лута.")
def opt_lbeam_sz(s: SliderOption, val: int) -> None:
    apply_group_scale("loot_beams", "size", val, min_val=1.0)

# 9. Эффекты урона на экране (огонь/кислота перед глазами)
@SliderOption("9. Screen DoT: Alpha (%)", 100, 0, 100, 10, description="Прозрачность огня и кислоты на экране игрока.")
def opt_scr_al(s: SliderOption, val: int) -> None:
    apply_group_scale("screen_dots", "alpha", val)

# 10. Навыки персонажей
@SliderOption("10. Action Skills: Alpha (%)", 100, 0, 100, 10, description="Прозрачность эффектов способностей (Шизострел, Инвиз).")
def opt_sk_al(s: SliderOption, val: int) -> None:
    apply_group_scale("skills", "alpha", val)

@ButtonOption("Re-Scan Packages", description="Пересканировать память игры.")
def opt_rescan(btn: ButtonOption) -> None:
    scan_and_route_vfx()

def on_enable() -> None:
    scan_and_route_vfx()

mod = build_mod(
    options=[
        opt_gr_sz, opt_gr_al,
        opt_sh_sz, opt_sh_al,
        opt_tr_sz, opt_tr_al,
        opt_imp_sz, opt_imp_al,
        opt_exp_sz, opt_exp_al,
        opt_muz_sz, opt_muz_al,
        opt_licon_sz,
        opt_lbeam_sz,
        opt_scr_al,
        opt_sk_al,
        opt_rescan,
    ],
    on_enable=on_enable,
)