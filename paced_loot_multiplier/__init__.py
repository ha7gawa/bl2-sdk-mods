from dataclasses import dataclass
from typing import Any
import time
import unrealsdk
from mods_base import SliderOption, build_mod, get_pc, hook
from unrealsdk.unreal import BoundFunction, UObject, WeakPointer, WrappedStruct


@dataclass
class DropTask:
    caller: WeakPointer
    killer: Any
    damage_type: Any
    damage_def: Any
    remaining: int


drop_queue: list[DropTask] = []
_is_internal_drop: bool = False
_last_network_tick_time: float = 0.0


def is_host() -> bool:
    """Проверяет, является ли текущий игрок хостом."""
    try:
        pc = get_pc()
        if pc is not None and hasattr(pc, "WorldInfo") and pc.WorldInfo:
            world_info = pc.WorldInfo
            if hasattr(world_info, "NetMode"):
                # NM_Standalone (0), NM_DedicatedServer (1), NM_ListenServer (2)
                return world_info.NetMode in (0, 1, 2)
    except Exception:
        pass
    return True


@SliderOption(
    identifier="Drop Multiplier",
    value=3,
    min_value=1,
    max_value=100,
    step=1,
    description="Сколько раз повторить дроп с каждого врага.",
).set_on_change()
def multiplier_slider(opt: SliderOption, new_value: float) -> None:
    pass


@SliderOption(
    identifier="Drops Per Enemy Per Tick",
    value=1,
    min_value=1,
    max_value=3,
    step=1,
    description="Сколько дропов выдавать каждому врагу за один сетевой шаг.",
).set_on_change()
def batch_slider(opt: SliderOption, new_value: float) -> None:
    pass


@SliderOption(
    identifier="Network Tick Delay (ms)",
    value=40,
    min_value=15,
    max_value=200,
    step=5,
    description="Интервал сетевого шага в миллисекундах (35-50мс предотвращает рассинхрон в сети).",
).set_on_change()
def delay_slider(opt: SliderOption, new_value: float) -> None:
    pass


@hook("WillowGame.WillowPawn:DropLootOnDeath")
def drop_loot_hook(
    obj: UObject,
    args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    global _is_internal_drop

    if _is_internal_drop:
        return

    if not is_host():
        return

    mult = int(multiplier_slider.value)
    if mult <= 1:
        return

    drop_queue.append(
        DropTask(
            caller=WeakPointer(obj),
            killer=args.Killer,
            damage_type=args.DamageType,
            damage_def=args.DamageTypeDefinition,
            remaining=mult - 1,
        )
    )


@hook("WillowGame.WillowPlayerController:PlayerTick")
def player_tick_hook(
    obj: UObject,
    _args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    global drop_queue, _is_internal_drop, _last_network_tick_time
    if not drop_queue:
        return

    # Запускаем только от локального контроллера хоста
    try:
        local_pc = get_pc()
        if local_pc is not None and local_pc != obj:
            return
    except Exception:
        pass

    if not is_host():
        drop_queue.clear()
        return

    # Сетевой троттлинг
    now = time.time()
    interval_sec = float(delay_slider.value) / 1000.0
    if (now - _last_network_tick_time) < interval_sec:
        return

    _last_network_tick_time = now

    drops_per_enemy = int(batch_slider.value)

    # Параллельный обход всех активных врагов в очереди
    for item in drop_queue[:]:
        pawn = item.caller()

        # Если тело моба исчезло из памяти
        if pawn is None:
            drop_queue.remove(item)
            continue

        # Выдаем фиксированную порцию (1 дроп) текущему мобу в этом сетевом цикле
        for _ in range(min(drops_per_enemy, item.remaining)):
            _is_internal_drop = True
            try:
                pawn.DropLootOnDeath(
                    item.killer,
                    item.damage_type,
                    item.damage_def,
                )
            except Exception:
                item.remaining = 0
                break
            finally:
                _is_internal_drop = False

            item.remaining -= 1

        # Если у этого врага закончился лимит дропа — убираем его из очереди
        if item.remaining <= 0:
            if item in drop_queue:
                drop_queue.remove(item)


@hook("Engine.WorldInfo:PreExitMap")
def on_pre_exit_map(
    _obj: UObject,
    _args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    global drop_queue, _is_internal_drop
    drop_queue.clear()
    _is_internal_drop = False


def on_disable() -> None:
    global drop_queue, _is_internal_drop
    drop_queue.clear()
    _is_internal_drop = False


mod = build_mod(
    options=[multiplier_slider, batch_slider, delay_slider],
    on_disable=on_disable,
)