"""
OCPP 1.6 meter value processing.

Data model:
- Charger sends Energy.Active.Import.Register = CUMULATIVE lifetime Wh counter
- meter_register_kwh: raw cumulative value stored in TimescaleDB (audit)
- session_energy_kwh: register minus meterStart (billing/live display)
- _session_energy() is the SINGLE function that computes the session delta
"""
import logging
import math

from events.bus import EventBus
from events.types import Event, EventType
from state.postgres import db
from state.redis import redis_state
from utils import parse_timestamp

logger = logging.getLogger(__name__)


def session_energy(meter_register_kwh: float | None, meter_start_wh: float | None) -> float:
    """Compute session energy from cumulative meter register and session start.

    meter_register_kwh: current cumulative reading from charger (in kWh)
    meter_start_wh: meterStart from StartTransaction (in Wh, as OCPP sends it)

    Returns session energy in kWh rounded to 4 decimal places. Never negative.
    0 Wh is a valid starting reading (e.g. new charger, reset meter, or sub-meter).
    """
    if meter_register_kwh is None or meter_start_wh is None:
        return 0.0

    try:
        reg_kwh = float(meter_register_kwh)
        start_wh = float(meter_start_wh)
    except (ValueError, TypeError):
        return 0.0

    if math.isnan(reg_kwh) or math.isinf(reg_kwh) or math.isnan(start_wh) or math.isinf(start_wh):
        return 0.0

    # Negative meter readings are invalid
    if reg_kwh < 0 or start_wh < 0:
        return 0.0

    start_kwh = start_wh / 1000.0

    # Monotonicity check: cumulative register should not be less than start reading
    if reg_kwh < start_kwh:
        logger.warning(
            f"Cumulative meter register ({reg_kwh:.4f} kWh) is less than start reading "
            f"({start_kwh:.4f} kWh). Possible meter rollover, reset, or invalid reading."
        )
        return 0.0

    delta = reg_kwh - start_kwh
    return round(max(0.0, delta), 4)


def parse_sampled_values(sampled: list[dict]) -> dict:
    """Parse OCPP 1.6 SampledValue array into a flat dict.
    
    Adheres strictly to OCPP 1.6 specification Section 7.31:
    - Default measurand is Energy.Active.Import.Register
    - Default unit for Energy.Active.Import.Register is Wh
    - Default unit for Power.Active.Import is W
    """
    readings = {}
    voltages = [None, None, None]
    currents = [None, None, None]

    import logging as _log
    _log.getLogger('meter').info(f'SampledValues: {[{"m": sv.get("measurand"), "v": sv.get("value"), "u": sv.get("unit")} for sv in sampled]}')
    for sv in sampled:
        measurand = sv.get("measurand") or "Energy.Active.Import.Register"
        value = sv.get("value", "0")
        phase = sv.get("phase")
        unit = (sv.get("unit") or "").strip()

        try:
            val = float(value)
        except (ValueError, TypeError):
            continue

        if math.isnan(val) or math.isinf(val):
            continue

        unit_lower = unit.lower()

        # Handle cumulative register vs interval energy
        if measurand in ("Energy.Active.Import.Register", "Energy.Active.Import") or measurand.startswith("Energy.Active.Import.Register"):
            # Cumulative meter register — convert Wh to kWh if needed
            # This is the charger's lifetime counter, NOT session energy
            if unit_lower in ("wh", ""):
                kwh_val = val / 1000.0
            elif unit_lower == "kwh":
                kwh_val = val
            elif unit_lower == "mwh":
                kwh_val = val * 1000.0
            else:
                kwh_val = val / 1000.0
            readings["meter_register_kwh"] = round(kwh_val, 4)

        elif measurand == "Energy.Active.Import.Interval":
            if unit_lower in ("wh", ""):
                interval_kwh = val / 1000.0
            elif unit_lower == "kwh":
                interval_kwh = val
            else:
                interval_kwh = val / 1000.0
            readings["energy_interval_kwh"] = round(interval_kwh, 4)

        elif "Power.Active.Import" in measurand:
            # Default unit is W per OCPP 1.6 Section 7.31
            if unit_lower in ("w", ""):
                readings["power_kw"] = round(val / 1000.0, 3)
            elif unit_lower == "kw":
                readings["power_kw"] = round(val, 3)
            else:
                readings["power_kw"] = round(val / 1000.0, 3)

        elif measurand == "SoC":
            if 0 <= val <= 100:
                readings["soc_pct"] = int(val)

        elif measurand == "Temperature":
            readings["temperature_c"] = val

        elif "Voltage" in measurand:
            if phase == "L1":
                voltages[0] = val
            elif phase == "L2":
                voltages[1] = val
            elif phase == "L3":
                voltages[2] = val
            elif not phase:
                voltages[0] = val  # single phase

        elif "Current.Import" in measurand:
            if phase == "L1":
                currents[0] = val
            elif phase == "L2":
                currents[1] = val
            elif phase == "L3":
                currents[2] = val
            elif not phase:
                currents[0] = val

    if any(v is not None for v in voltages):
        readings["voltage_v"] = voltages
    if any(c is not None for c in currents):
        readings["current_a"] = currents

    # Calculate power from V×I if charger doesn't send Power.Active.Import
    # Profile-driven: some chargers send Power, some don't. Always calc as fallback.
    if "power_kw" not in readings and any(v is not None for v in voltages) and any(c is not None for c in currents):
        power_w = sum(
            (v or 0) * (c or 0)
            for v, c in zip(voltages, currents)
        )
        if power_w > 0:
            readings["power_kw"] = round(power_w / 1000, 3)
            logger.info(f"Calculated power from V×I: {readings['power_kw']:.1f} kW "
                        f"(V={[v for v in voltages if v]}, A={[c for c in currents if c]})")

    return readings


async def handle_meter_values(
    cp_id: str,
    event_bus: EventBus,
    simulated: bool,
    payload: dict,
) -> dict:
    """Meter readings during a session.

    Data model:
    - Charger sends cumulative Energy.Active.Import.Register (lifetime Wh)
    - We store the RAW register reading in TimescaleDB (unchanged, for audit)
    - Session energy = latest_register - meter_start (computed, not stored in meter_values)
    - Session energy is updated in ocpp.sessions and Redis (for live display)
    """
    connector_id = payload.get("connectorId", 0)
    transaction_id = payload.get("transactionId")
    meter_values = payload.get("meterValue", [])

    for mv in meter_values:
        timestamp = parse_timestamp(mv.get("timestamp"))
        sampled = mv.get("sampledValue", [])
        readings = parse_sampled_values(sampled)

        # Live charger state: write power/SoC to charger Redis hash (always, regardless of session)
        power_kw = readings.get("power_kw", 0) or 0
        charger_update = {}
        if power_kw > 0:
            charger_update[f"connector_{connector_id}_power_kw"] = str(round(power_kw, 2))
        if readings.get("soc_pct"):
            charger_update[f"connector_{connector_id}_soc_pct"] = str(readings["soc_pct"])
        if charger_update:
            await redis_state.set_charger(cp_id, charger_update)

        # Look up session context (meter_start for energy delta)
        session_id = None
        meter_start_wh = 0.0
        if transaction_id:
            async with db.read() as conn:
                row = await conn.fetchrow(
                    "SELECT id::text as session_id, COALESCE(meter_start, 0) as meter_start "
                    "FROM ocpp.sessions WHERE charge_point = $1 AND transaction_id = $2 AND status = 'active'",
                    cp_id, transaction_id,
                )
                if row:
                    session_id = row["session_id"]
                    meter_start_wh = float(row["meter_start"])

        # Derive session energy from cumulative register
        # meter_register_kwh = raw charger value (cumulative, in kWh)
        # session_energy_kwh = meter_register - meter_start (what this session delivered)
        meter_register_kwh = readings.get("meter_register_kwh")
        if meter_register_kwh is not None:
            session_energy_kwh = session_energy(meter_register_kwh, meter_start_wh)
        else:
            session_energy_kwh = None

        # 1. TimescaleDB: store RAW register reading (audit trail, immutable)
        async with db.write() as conn:
            await conn.execute("""
                INSERT INTO ocpp.meter_values
                    (time, charge_point, connector_id, session_id,
                     energy_kwh, power_kw, soc_pct, voltage_v, current_a, temperature_c)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
                timestamp, cp_id, connector_id, session_id,
                meter_register_kwh,  # RAW cumulative register, NOT session delta
                readings.get("power_kw"),
                readings.get("soc_pct"),
                readings.get("voltage_v"),
                readings.get("current_a"),
                readings.get("temperature_c"),
            )

        if session_id:
            # 2. Redis: live session state (consumers read this for dashboards)
            redis_meter_update = {
                "power_kw": readings.get("power_kw"),
                "soc_pct": readings.get("soc_pct"),
                "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
            }
            if session_energy_kwh is not None:
                redis_meter_update["energy_kwh"] = session_energy_kwh
            await redis_state.update_session_meter(session_id, redis_meter_update)

            # 3. Sessions table: running session energy + peak power (single source of truth)
            power_kw = readings.get("power_kw", 0) or 0
            if session_energy_kwh is not None or power_kw > 0:
                async with db.write() as conn:
                    if session_energy_kwh is not None:
                        await conn.execute(
                            "UPDATE ocpp.sessions SET "
                            "energy_kwh = GREATEST(COALESCE(energy_kwh, 0), $1), "
                            "peak_power_kw = GREATEST(COALESCE(peak_power_kw, 0), $3) "
                            "WHERE id::text = $2 AND LOWER(status) = 'active'",
                            session_energy_kwh, session_id, power_kw,
                        )
                    else:
                        await conn.execute(
                            "UPDATE ocpp.sessions SET "
                            "peak_power_kw = GREATEST(COALESCE(peak_power_kw, 0), $2) "
                            "WHERE id::text = $1 AND LOWER(status) = 'active'",
                            session_id, power_kw,
                        )

        # 4. Public sessions (charge app): same derived energy
        if transaction_id and session_energy_kwh is not None and session_energy_kwh > 0:
            async with db.write() as conn:
                await conn.execute(
                    "UPDATE ocpp.public_sessions SET kwh_delivered = $1 WHERE ocpp_transaction_id = $2",
                    session_energy_kwh, transaction_id,
                )

        # Publish event (consumers get both raw register and session energy)
        event_data = {
            **readings,
            "energy_kwh": session_energy_kwh if session_energy_kwh is not None else 0.0,
            "meter_register_kwh": meter_register_kwh if meter_register_kwh is not None else 0.0,
        }
        await event_bus.publish(Event(
            type=EventType.SESSION_METER,
            charge_point=cp_id,
            connector=connector_id,
            session_id=session_id or "",
            simulated=simulated,
            data=event_data,
        ))

    return {}
