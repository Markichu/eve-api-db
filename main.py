import grequests
import datetime
import decimal
import winsound

from fastapi import FastAPI
from src.util import connect_to_db
from src.tasks import (
    update_market_orders,
    aggregate_market_orders,
    calculate_reprocess_price,
    calculate_manufacture_price,
)

app = FastAPI()


@app.get("/analyse")
async def analyse(items: str, rep_yield: float = 0.55, tax: float = 0.036):
    YIELD = decimal.Decimal(rep_yield)
    TAX = decimal.Decimal(tax)
    items_split = items.split("\t")
    items_split = [items_split[0]] + [item.split(" ", 1)[1] for item in items_split[1:-1]]

    conn = await connect_to_db()
    type_ids = await conn.fetch("SELECT name, type_id from sde.type_ids")
    type_ids = dict(type_ids)

    rep_prices = await conn.fetch("SELECT type_id, reprocess_value FROM market.reprocess")
    rep_prices = dict(rep_prices)

    buy_prices = await conn.fetch(
        "SELECT type_id, MAX(buy_max) FROM market.aggregates WHERE region_id = 10000002 GROUP BY type_id"
    )
    buy_prices = dict(buy_prices)

    sell_prices = await conn.fetch(
        "SELECT type_id, MIN(sell_min) FROM market.aggregates WHERE region_id = 10000002 GROUP BY type_id"
    )
    sell_prices = dict(sell_prices)

    print_list = []
    for item in items_split:
        type_id = type_ids[item]
        reprocess_value = 0 if rep_prices[type_id] is None else YIELD * rep_prices[type_id] * (1 - TAX)
        buy_price = 0 if buy_prices[type_id] is None else buy_prices[type_id]
        sell_price = 0 if sell_prices[type_id] is None else sell_prices[type_id]
        buy_percent = round((buy_price - reprocess_value) / reprocess_value * 100, 2)
        sell_percent = round((sell_price - reprocess_value) / reprocess_value * 100, 2)
        print_list.append((item, reprocess_value, buy_price, sell_price, buy_percent, sell_percent))

    print(f"{'Item':<64} {'Buy':<15} {'Reprocess':<15} {'Sell':<15} {'Buy%':<15} {'Sell%':<15}")
    # print(print_list)
    for (
        item,
        reprocess_value,
        buy_price,
        sell_price,
        buy_percent,
        sell_percent,
    ) in print_list:
        if buy_percent < 0 and sell_percent > 0:
            continue
        print(
            f"{item:<64} {buy_price:<15} {reprocess_value:<15.2f} {sell_price:<15.2f} {buy_percent:<15.2f} {sell_percent:<15.2f}"
        )

    return {"message": "Hello World"}


@app.get("/test")
async def test(rep_yield: float = 0.55, tax: float = 0.036, roi: float = 0.05):
    YIELD = decimal.Decimal(rep_yield)
    TAX = decimal.Decimal(tax)
    ROI = decimal.Decimal(roi)

    location_id = 60003760

    conn = await connect_to_db()

    data = {}

    reprocess_prices = await conn.fetch("SELECT * FROM market.reprocess")
    orders = await conn.fetch(
        "SELECT * FROM market.orders WHERE location_id = $1 AND is_buy_order = False",
        location_id,
    )
    type_names = dict(await conn.fetch("SELECT type_id, name from sde.type_ids"))

    for row in reprocess_prices:
        data[row["type_id"]] = {
            "reprocess_value": row["reprocess_value"],
            "sell_orders": [],
        }

    for row in orders:
        if row["type_id"] not in data:
            continue
        data[row["type_id"]]["sell_orders"].append(row)

    purchase_orders = []

    for type_id, value in data.items():
        if len(value["sell_orders"]) == 0:
            continue

        breakeven_price = (YIELD * value["reprocess_value"]) * (1 - TAX)

        total_value = decimal.Decimal(0)
        total_volume = decimal.Decimal(0)
        for order in value["sell_orders"]:
            if order["price"] > breakeven_price / (1 + ROI):
                continue
            total_value += decimal.Decimal(order["price"]) * decimal.Decimal(order["volume_remain"])
            total_volume += decimal.Decimal(order["volume_remain"])

        total_reprocess_value = total_volume * decimal.Decimal(value["reprocess_value"]) * YIELD * (1 - TAX)
        if total_reprocess_value == 0:
            continue

        purchase_orders.append(
            {
                "item": type_names[type_id],
                "breakeven": round(breakeven_price / (1 + ROI), 2),
                "buy_vol": total_volume,
                "buy_value": total_value,
                "sell_value": round(total_reprocess_value, 4),
                "profit": round(total_reprocess_value - total_value, 4),
            }
        )

    # sort purchase_orders by profit
    purchase_orders = sorted(purchase_orders, key=lambda k: k["profit"], reverse=True)

    print("Multi-buy:")
    for order in purchase_orders:
        print(f"{order['item']} {order['buy_vol']}")

    need_to_notify = False
    max_profit = 0

    print(f"\n{'Item':<64} {'Break Even':<15} {'Buy Value':<15} {'Sell Value':<15} {'Profit':<15} {'ROI':<15}")
    for order in purchase_orders:
        if not need_to_notify and order["profit"] > 5e6:
            need_to_notify = True
            max_profit = order["profit"]
        print(
            f"{order['item']:<64} {order['breakeven']:<15} {order['buy_value']:<15} {order['sell_value']:<15} {order['profit']:<15} {round(order['profit'] / order['buy_value'] * 100, 2):<15}"
        )

    if need_to_notify:
        winsound.Beep(440, 100)
        # play a sound that changes dynamically based on the amount of profit
        winsound.Beep(440 + int(max_profit / decimal.Decimal(1e6)), 100)

    print(
        f"\n{'Total':<64} {sum([order['buy_value'] for order in purchase_orders]):<15} {sum([order['sell_value'] for order in purchase_orders]):<15} {sum([order['profit'] for order in purchase_orders]):<15}"
    )

    return


@app.post("/add_task")
async def add_task(task_name: str, task_params: str):
    conn = await connect_to_db()
    await conn.execute(
        "INSERT INTO db_management.last_updated (task_name, task_params, last_updated, expiry) VALUES ($1, $2, $3, $4)",
        task_name,
        task_params,
        datetime.datetime.min,
        datetime.datetime.min,
    )
    await conn.close()
    return {"successful": True}


@app.post("/update_market_history")
async def update_market_history(args: str):
    region_id = int(args)

    conn = await connect_to_db()
    # type_ids = await conn.fetch("SELECT type_id from sde.type_ids WHERE published = true AND market_group_id IS NOT NULL")
    type_ids = await conn.fetch("SELECT DISTINCT ON (1) type_id from market.aggregates WHERE region_id = $1", region_id)
    type_ids = [type_id["type_id"] for type_id in type_ids]

    url = f"https://esi.evetech.net/latest/markets/{region_id}/history/"
    param_gen = lambda type_id: {
        "datasource": "tranquility",
        "type_id": type_id,
    }
    requests = (grequests.get(url, params=param_gen(type_id)) for type_id in type_ids)

    histories = []
    count = 0
    for i, response in grequests.imap_enumerated(requests, size=32):
        count += 1
        if count % 100 == 0:
            print(f"{count}/{len(type_ids)}")
        if response.status_code != 200:
            print(type_ids[i], {"successful": False, "reason": response.status_code}, response.json())
            break
        for history in response.json():
            histories.append(
                (
                    type_ids[i],
                    datetime.datetime.strptime(history["date"], "%Y-%m-%d").date(),
                    history["highest"],
                    history["lowest"],
                    history["average"],
                    history["volume"],
                    history["order_count"],
                )
            )
    await conn.executemany(
        """
        INSERT INTO market.history (type_id, date, highest, lowest, average, volume, order_count)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (type_id, date) DO UPDATE
        SET highest = $3, lowest = $4, average = $5, volume = $6, order_count = $7
        """,
        histories,
    )


@app.get("/update")
async def update():
    # get tasks that need to be updated
    conn = await connect_to_db()
    tasks = await conn.fetch("SELECT * FROM db_management.last_updated")

    TASKS = {
        "market.orders": update_market_orders,
        "market.aggregates": aggregate_market_orders,
        "market.reprocess": calculate_reprocess_price,
        "market.manufacture": calculate_manufacture_price,
    }
    task_status = []

    for task in tasks:
        # check if task needs to be updated
        if task["expiry"] > datetime.datetime.utcnow():
            continue
        try:
            result = await TASKS[task["task_name"]](task["task_params"])
        except Exception as e:
            print(f"Failed to update {task['task_name']} with params {task['task_params']}")
            print(e)
            task_status.append(
                {
                    "task_name": task["task_name"],
                    "task_params": task["task_params"],
                    "successful": False,
                }
            )
            continue

        if result["successful"]:
            task_status.append(
                {
                    "task_name": task["task_name"],
                    "task_params": task["task_params"],
                    "successful": True,
                    "expires": result["expiry"],
                }
            )
            await conn.execute(
                "UPDATE db_management.last_updated SET last_updated = $1, expiry = $2 WHERE task_name = $3 AND task_params = $4",
                result["last_updated"],
                result["expiry"],
                task["task_name"],
                task["task_params"],
            )
        else:
            task_status.append(
                {
                    "task_name": task["task_name"],
                    "task_params": task["task_params"],
                    "successful": False,
                }
            )

    await conn.close()
    return task_status
