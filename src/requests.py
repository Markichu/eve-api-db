from decimal import Decimal
from src.util import connect_to_db


async def reprocess_trades_r(
    rep_yield: float, tax: float, min_roi: float, location_id: int
):
    conn = await connect_to_db()

    item_reprocess_data = {}

    # fetch required data from database
    reprocess_prices = await conn.fetch("SELECT * FROM market.reprocess")
    orders = await conn.fetch(
        "SELECT * FROM esi.market_orders WHERE location_id = $1 AND is_buy_order = False",
        location_id,
    )
    type_names = dict(await conn.fetch("SELECT type_id, name from sde.type_ids"))

    # create entries for each repressible item
    for row in reprocess_prices:
        item_reprocess_data[row["type_id"]] = {
            "reprocess_value": row["reprocess_value"],
            "sell_orders": [],
        }

    # populate entries with orders selling repressible items
    for row in orders:
        if row["type_id"] not in item_reprocess_data:
            continue
        item_reprocess_data[row["type_id"]]["sell_orders"].append(row)

    purchase_orders = []

    # construct purchase orders for each repressible item
    for type_id, value in item_reprocess_data.items():
        if len(value["sell_orders"]) == 0:
            continue

        reprocess_value = value["reprocess_value"] * rep_yield * (1 - tax)

        total_value = Decimal(0)
        total_volume = Decimal(0)
        for order in value["sell_orders"]:
            if order["price"] > reprocess_value / (1 + min_roi):
                continue
            total_value += order["price"] * order["volume_remain"]
            total_volume += order["volume_remain"]

        if total_volume == 0:
            continue

        total_reprocess_value = total_volume * reprocess_value

        purchase_orders.append(
            {
                "item": type_names[type_id],
                "breakeven": round(reprocess_value, 2),
                "buy_vol": total_volume,
                "buy_value": total_value,
                "sell_value": round(total_reprocess_value, 2),
                "profit": round(total_reprocess_value - total_value, 2),
            }
        )

    # sort purchase_orders by profit
    purchase_orders = sorted(purchase_orders, key=lambda k: k["profit"], reverse=True)

    return purchase_orders
