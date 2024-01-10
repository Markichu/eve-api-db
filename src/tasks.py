import datetime
import decimal

from src.util import connect_to_db, esi_call
from collections import defaultdict


async def aggregate_market_orders(args: str):
    print(f"Aggregating orders for region {args}.")
    region_id = int(args)
    conn = await connect_to_db()
    market_updated = await conn.fetch(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'market.orders'",
        str(region_id),
    )
    agg_updated = await conn.fetch(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'market.aggregates'",
        args,
    )

    if market_updated[0]["last_updated"] <= agg_updated[0]["last_updated"]:
        return {"successful": False, "reason": "No new orders to aggregate."}

    aggs = await conn.fetch(
        """
        SELECT
            location_id,
            type_id,
            min(CASE WHEN is_buy_order = false THEN price END) as sell_min,
            max(CASE WHEN is_buy_order = true THEN price END) as buy_max,
            COALESCE(sum(CASE WHEN is_buy_order = false THEN volume_remain END), 0) as sell_volume,
            COALESCE(sum(CASE WHEN is_buy_order = true THEN volume_remain END), 0) as buy_volume,
            count(CASE WHEN is_buy_order = false THEN 1 END) as sell_orders,
            count(CASE WHEN is_buy_order = true THEN 1 END) as buy_orders,
            region_id
        FROM market.orders
        WHERE region_id = $1
        GROUP BY type_id, location_id, region_id
        """,
        region_id,
    )

    await conn.execute("DELETE FROM market.aggregates WHERE region_id = $1", region_id)
    await conn.copy_records_to_table("aggregates", records=aggs, schema_name="market")

    print(f"Aggregated {len(aggs)} orders for region {args}.")
    return {
        "successful": True,
        "last_updated": market_updated[0]["last_updated"],
        "expiry": market_updated[0]["expiry"],
    }


async def calculate_manufacture_price(args: str):
    print(f"Calculating manufacture cost prices for region {args}.")
    region_id, location_id = (int(arg) for arg in args.split(","))
    conn = await connect_to_db()
    market_updated = await conn.fetch(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'market.aggregates'",
        str(region_id),
    )
    manufacture_updated = await conn.fetch(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'market.manufacture'",
        args,
    )

    if market_updated[0]["last_updated"] <= manufacture_updated[0]["last_updated"]:
        return {"successful": False, "reason": "No new aggregates to manufacture."}

    sell_prices = dict(
        await conn.fetch(
            "SELECT type_id, sell_min FROM market.aggregates WHERE region_id = $1 AND location_id = $2",
            region_id,
            location_id,
        )
    )

    bp_materials = await conn.fetch(
        """
        SELECT blueprint_type_id, material_type_id, quantity 
        FROM sde.blueprint_materials bpm
        JOIN sde.type_ids ti ON bpm.material_type_id = ti.type_id
        WHERE activity = 'manufacturing'
        AND ti.published = true
        """,
    )

    bp_cost = defaultdict(decimal.Decimal)
    for blueprint_type_id, material_type_id, quantity in bp_materials:
        if material_type_id not in sell_prices or sell_prices[material_type_id] is None:
            continue
        bp_cost[blueprint_type_id] += quantity * sell_prices[material_type_id]

    manufacture = [(bp_type_id, manufacture_cost) for bp_type_id, manufacture_cost in bp_cost.items()]
    await conn.execute("TRUNCATE TABLE market.manufacture")
    await conn.copy_records_to_table("manufacture", records=manufacture, schema_name="market")

    return {
        "successful": True,
        "last_updated": market_updated[0]["last_updated"],
        "expiry": market_updated[0]["expiry"],
    }


async def calculate_reprocess_price(args: str):
    print(f"Calculating reprocess prices for region {args}.")
    region_id, location_id = (int(arg) for arg in args.split(","))
    conn = await connect_to_db()
    market_updated = await conn.fetch(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'market.aggregates'",
        str(region_id),
    )
    reprocess_updated = await conn.fetch(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'market.reprocess'",
        args,
    )

    if market_updated[0]["last_updated"] <= reprocess_updated[0]["last_updated"]:
        return {"successful": False, "reason": "No new aggregates to reprocess."}

    reprocess = await conn.fetch(
        """
        SELECT
            sde.type_materials.type_id,
            COALESCE(sum(quantity * buy_max) / sde.type_ids.portion_size, 0) as reprocess_value
        FROM
            (
                sde.type_materials
                JOIN (
                    SELECT
                        type_id,
                        buy_max
                    FROM
                        market.aggregates
                    WHERE
                        location_id = $1
                ) as prices ON sde.type_materials.material_type_id = prices.type_id
                JOIN sde.type_ids ON sde.type_materials.type_id = sde.type_ids.type_id
            )
        GROUP BY sde.type_materials.type_id, sde.type_ids.portion_size
        ORDER BY type_id ASC
        """,
        location_id,
    )

    await conn.execute("TRUNCATE TABLE market.reprocess")
    await conn.copy_records_to_table("reprocess", records=reprocess, schema_name="market")

    return {
        "successful": True,
        "last_updated": market_updated[0]["last_updated"],
        "expiry": market_updated[0]["expiry"],
    }


async def update_market_orders(args: str):
    print(f"Updating orders for region {args}.")
    region_id = int(args)

    url = f"/markets/{region_id}/orders/"
    params = {
        "datasource": "tranquility",
        "order_type": "all",
    }

    orders = []
    async for response in esi_call(url, params=params):
        if response.status_code != 200:
            return {"successful": False, "reason": response.status_code}
        for order in response.json():
            orders.append(
                (
                    order["order_id"],
                    order["type_id"],
                    order["location_id"],
                    order["system_id"],
                    region_id,
                    order["volume_total"],
                    order["volume_remain"],
                    order["min_volume"],
                    order["price"],
                    order["range"],
                    order["is_buy_order"],
                    datetime.datetime.strptime(order["issued"], "%Y-%m-%dT%H:%M:%SZ"),
                    order["duration"],
                )
            )

    conn = await connect_to_db()
    await conn.execute("DELETE FROM market.orders WHERE region_id = $1", region_id)
    await conn.copy_records_to_table("orders", records=orders, schema_name="market")
    await conn.close()

    print(f"Updated {len(orders)} orders for region {args}.")
    return {
        "successful": True,
        "last_updated": datetime.datetime.strptime(response.headers["last-modified"], "%a, %d %b %Y %H:%M:%S %Z"),
        "expiry": datetime.datetime.strptime(response.headers["expires"], "%a, %d %b %Y %H:%M:%S %Z"),
    }
