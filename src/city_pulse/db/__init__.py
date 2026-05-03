"""Database access."""

from city_pulse.db.pool import create_pool
from city_pulse.db.vehicle_counts import insert_vehicle_count

__all__ = ["create_pool", "insert_vehicle_count"]
