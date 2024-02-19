import grequests
import logging
import time
import asyncio
from uvicorn.logging import ColourizedFormatter

from decimal import Decimal
from datetime import datetime
from fastapi import FastAPI
from src.util import connect_to_db, esi_call_itemwise, gather_generator
from src.tasks import (
    update_market_orders,
    update_contracts,
    update_contract_items,
    aggregate_market_orders,
    aggregate_bp_contracts,
    calculate_reprocess_price,
    calculate_manufacture_price,
)
from src.requests import (
    reprocess_trades_r,
)


app = FastAPI()
LOGGER = logging.getLogger("uvicorn.access")


class UpdateTasksFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:

        return record.getMessage().find("/update_tasks") == -1


LOGGER.addFilter(UpdateTasksFilter())


@app.on_event("startup")
async def startup_event():
    console_formatter = ColourizedFormatter(
        "{asctime} {levelprefix} {message}",
        style="{",
        use_colors=True,
        datefmt="[%H:%M:%S %d/%m/%y]",
    )
    LOGGER.handlers[0].setFormatter(console_formatter)


@app.get("/analyse")
async def analyse(items: str, rep_yield: float = 0.55, tax: float = 0.036):
    YIELD = Decimal(rep_yield)
    TAX = Decimal(tax)
    items_split = items.split("\t")
    items_split = [items_split[0]] + [
        item.split(" ", 1)[1] for item in items_split[1:-1]
    ]

    conn = await connect_to_db()
    type_ids = await conn.fetch("SELECT name, type_id from sde.type_ids")
    type_ids = dict(type_ids)

    rep_prices = await conn.fetch(
        "SELECT type_id, reprocess_value FROM market.reprocess"
    )
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
        reprocess_value = (
            0
            if rep_prices[type_id] is None
            else YIELD * rep_prices[type_id] * (1 - TAX)
        )
        buy_price = 0 if buy_prices[type_id] is None else buy_prices[type_id]
        sell_price = 0 if sell_prices[type_id] is None else sell_prices[type_id]
        buy_percent = round((buy_price - reprocess_value) / reprocess_value * 100, 2)
        sell_percent = round((sell_price - reprocess_value) / reprocess_value * 100, 2)
        print_list.append(
            (item, reprocess_value, buy_price, sell_price, buy_percent, sell_percent)
        )

    print(
        f"{'Item':<64} {'Buy':<15} {'Reprocess':<15} {'Sell':<15} {'Buy%':<15} {'Sell%':<15}"
    )
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


@app.get("/reprocess_trades")
async def reprocess_trades(
    rep_yield: float = 0.55,
    tax: float = 0.036,
    min_roi: float = 0.05,
    location_id: int = 60003760,
):
    rep_yield = Decimal(rep_yield)
    tax = Decimal(tax)
    min_roi = Decimal(min_roi)
    location_id = Decimal(location_id)
    return await reprocess_trades_r(rep_yield, tax, min_roi, location_id)


@app.get("/test_requests")
async def test_requests():
    conn = await connect_to_db()

    contract_ids = await conn.fetch("SELECT contract_id FROM esi.contracts LIMIT 100")

    start_time = time.perf_counter()

    # testing time to request items of these 10 contracts
    contract_item_lists = [
        gather_generator(
            esi_call_itemwise(f"/contracts/public/items/{contract['contract_id']}")
        )
        for contract in contract_ids
    ]
    contract_item_lists = await asyncio.gather(*contract_item_lists)

    time_taken = time.perf_counter() - start_time

    # # test with a_esi_call
    # contract_item_lists = [gather_generator(a_esi_call(f"/contracts/public/items/{contract['contract_id']}")) for contract in contract_ids]
    # contract_item_lists = await asyncio.gather(*contract_item_lists)

    # time_taken = time.perf_counter() - start_time

    return {"time_taken": time_taken}


# TODO: Fix this and turn it into a functioning recurring task
@app.post("/update_market_history")
async def update_market_history(args: str):
    region_id = int(args)

    conn = await connect_to_db()
    type_ids = await conn.fetch(
        "SELECT DISTINCT ON (1) type_id from market.aggregates WHERE region_id = $1",
        region_id,
    )
    type_ids = [type_id["type_id"] for type_id in type_ids]

    url = f"https://esi.evetech.net/latest/markets/{region_id}/history/"

    def param_gen(type_id):
        return {"datasource": "tranquility", "type_id": type_id}

    requests = (grequests.get(url, params=param_gen(type_id)) for type_id in type_ids)

    histories = []
    count = 0
    for i, response in grequests.imap_enumerated(requests, size=32):
        count += 1
        if count % 100 == 0:
            print(f"{count}/{len(type_ids)}")
        if response.status_code != 200:
            print(
                type_ids[i],
                {"successful": False, "reason": response.status_code},
                response.json(),
            )
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


@app.post("/add_task")
async def add_task(task_name: str, task_params: str):
    conn = await connect_to_db()
    await conn.execute(
        "INSERT INTO db_management.last_updated (task_name, task_params, last_updated, expiry) VALUES ($1, $2, $3, $4)",
        task_name,
        task_params,
        datetime.min,
        datetime.min,
    )
    await conn.close()
    return {"successful": True}


@app.get("/update_tasks")
async def update_tasks():
    # get tasks that need to be updated
    conn = await connect_to_db()
    tasks = await conn.fetch("SELECT * FROM db_management.last_updated")

    TASKS = {
        "market.aggregates": aggregate_market_orders,
        "market.bp_contracts": aggregate_bp_contracts,
        "market.reprocess": calculate_reprocess_price,
        "market.manufacture": calculate_manufacture_price,
        "esi.market_orders": update_market_orders,
        "esi.contracts": update_contracts,
        "esi.contract_items": update_contract_items,
    }
    task_status = []

    for task in tasks:
        # check if task needs to be updated
        if task["expiry"] > datetime.utcnow():
            continue
        # try:
        result = await TASKS[task["task_name"]](task["task_params"])
        # except Exception as e:
        #     print(f"Failed to update {task['task_name']} with params {task['task_params']}")
        #     print(e)
        #     task_status.append(
        #         {
        #             "task_name": task["task_name"],
        #             "task_params": task["task_params"],
        #             "successful": False,
        #         }
        #     )
        #     continue

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
