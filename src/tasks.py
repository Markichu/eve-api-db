import asyncio

from decimal import Decimal
from datetime import datetime, timedelta
from src.util import connect_to_db, esi_call, esi_call_itemwise, gather_generator
from collections import defaultdict


async def aggregate_market_orders(args: str):
    print(f"[aggregate_market_orders] Aggregating orders for region {args}.")
    region_id = int(args)
    conn = await connect_to_db()
    market_updated = await conn.fetch(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'esi.market_orders'",
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
        FROM esi.market_orders
        WHERE region_id = $1
        GROUP BY type_id, location_id, region_id
        """,
        region_id,
    )

    await conn.execute("DELETE FROM market.aggregates WHERE region_id = $1", region_id)
    await conn.copy_records_to_table("aggregates", records=aggs, schema_name="market")

    print(f"[aggregate_market_orders] Aggregated {len(aggs)} orders for region {args}.")
    return {
        "successful": True,
        "last_updated": market_updated[0]["last_updated"],
        "expiry": market_updated[0]["expiry"],
    }
    

async def aggregate_bp_contracts(args: str):
    print(f"[aggregate_bp_contracts] Aggregating BP contracts for region {args}.")
    region_id = int(args)
    
    conn = await connect_to_db()
    contracts_updated = await conn.fetchrow(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'esi.contract_items'",
        args,
    )
    agg_updated = await conn.fetchrow(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'market.bp_contracts'",
        args,
    )
    
    if contracts_updated["last_updated"] <= agg_updated["last_updated"]:
        return {"successful": False, "reason": "No new contract items to aggregate."}
    
    contracts_data = await conn.fetch(
        """
        SELECT *
        FROM esi.contracts
        WHERE region_id = $1
        """,
        region_id,
    )
    contract_items_data = await conn.fetch(
        """
        SELECT *
        FROM esi.contract_items
        """
    )
    contract_items = defaultdict(list)
    
    # add associated items for each contract to dict
    for contract_item in contract_items_data:
        contract_items[contract_item["contract_id"]].append(contract_item)
    
    bp_contracts = []
    # collect all contracts that are bpo or bpc
    for contract in contracts_data:
        if contract["type"] != "item_exchange":
            continue
        if len(contract_items[contract["contract_id"]]) != 1:
            continue
        contract_item = contract_items[contract["contract_id"]][0]
        if contract_item["is_included"] == False:
            continue
        if contract_item["material_efficiency"] == None:
            continue
        
        bp_contracts.append(
            (
                contract["contract_id"],
                region_id,
                contract_item["type_id"],
                contract["price"],
                contract_item["is_blueprint_copy"],
                contract_item["material_efficiency"],
                contract_item["time_efficiency"],
                contract_item["runs"],
            )
        )
    
    await conn.execute("DELETE FROM market.bp_contracts WHERE region_id = $1", region_id)
    await conn.copy_records_to_table("bp_contracts", records=bp_contracts, schema_name="market")
    await conn.close()
    print(f"[aggregate_bp_contracts] Aggregated {len(bp_contracts)} BP contracts for region {args}.")
    return {
        "successful": True,
        "last_updated": contracts_updated["last_updated"],
        "expiry": contracts_updated["expiry"],
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

    bp_cost = defaultdict(Decimal)
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
    print(f"[update_market_orders] Updating orders for region {args}.")
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
                    datetime.strptime(order["issued"], "%Y-%m-%dT%H:%M:%SZ"),
                    order["duration"],
                )
            )

    conn = await connect_to_db()
    await conn.execute("DELETE FROM esi.market_orders WHERE region_id = $1", region_id)
    await conn.copy_records_to_table("market_orders", records=orders, schema_name="esi")
    await conn.close()

    print(f"[update_market_orders] Updated {len(orders)} orders for region {args}.")
    return {
        "successful": True,
        "last_updated": datetime.strptime(response.headers["last-modified"], "%a, %d %b %Y %H:%M:%S %Z"),
        "expiry": datetime.strptime(response.headers["expires"], "%a, %d %b %Y %H:%M:%S %Z"),
    }
    

async def update_contracts(args: str):
    print(f"[update_contracts] Updating contracts for region {args}.")
    region_id = int(args)
    
    last_updated = datetime.utcnow()
    data_expiry = datetime.utcnow() + timedelta(hours=1)
    contracts = []
    async for item in esi_call_itemwise(f"/contracts/public/{region_id}/"):
        if item.get("is_headers", False):
            last_updated = datetime.strptime(item["last-modified"], "%a, %d %b %Y %H:%M:%S %Z")
            data_expiry = datetime.strptime(item["expires"], "%a, %d %b %Y %H:%M:%S %Z")
            continue
        
        contracts.append((
            item["contract_id"],
            datetime.strptime(item["date_issued"], "%Y-%m-%dT%H:%M:%SZ"),
            datetime.strptime(item["date_expired"], "%Y-%m-%dT%H:%M:%SZ"),
            item["issuer_id"],
            item["issuer_corporation_id"],
            item.get("for_corporation", False),
            item["type"],
            item["start_location_id"],
            item["end_location_id"],
            region_id,
            item.get("collateral", None),
            item["reward"],
            item.get("buyout", None),
            item["days_to_complete"],
            item["price"],
            item["title"],
            item["volume"],
        ))
        
    conn = await connect_to_db()
    await conn.execute("DELETE FROM esi.contracts WHERE region_id = $1", region_id)
    await conn.copy_records_to_table("contracts", records=contracts, schema_name="esi")
    await conn.close()
    
    print(f"[update_contracts] Updated {len(contracts)} contracts for region {region_id}.")
    return {
        "successful": True,
        "last_updated": last_updated,
        "expiry": data_expiry,
    }
    
async def update_contract_items(args: str):
    print(f"[update_contract_items] Updating contract items")
    region_id = int(args)
    conn = await connect_to_db()

    removed_items = await conn.execute(
        """
        DELETE FROM esi.contract_items ci
        WHERE ci.contract_id NOT IN (SELECT contract_id FROM esi.contracts);
        """
    )
    print(f"[update_contract_items] {removed_items} items from contracts that no longer exist")

    contracts = await conn.fetch(
        """
        SELECT c.contract_id
        FROM esi.contracts c
        LEFT JOIN esi.contract_items ci USING (contract_id)
        WHERE ci.record_id IS NULL 
        AND c.type IN ('item_exchange', 'auction')
        AND c.region_id = $1;
        """,
        region_id,
    )
    print(f"[update_contract_items] Found {len(contracts)} contracts with missing items")
    incomplete_contracts = False
    
    contract_item_lists = [gather_generator(esi_call_itemwise(f"/contracts/public/items/{contract['contract_id']}")) for contract in contracts]
    contract_item_lists = await asyncio.gather(*contract_item_lists)

    for contract, item_list in zip(contracts, contract_item_lists):
        contract_items = []
        try:
            for item in item_list:
                if item.get("is_headers", False):
                    continue
                contract_items.append(
                    (
                        contract["contract_id"],
                        item["record_id"],
                        item["type_id"],
                        item["quantity"],
                        item["is_included"],
                        item.get("item_id", None),
                        item.get("is_blueprint_copy", False),
                        item.get("material_efficiency", None),
                        item.get("time_efficiency", None),
                        item.get("runs", None),
                    )
                )

            await conn.executemany(
                """
                INSERT INTO esi.contract_items (contract_id, record_id, type_id, quantity, is_included, item_id, is_blueprint_copy, material_efficiency, time_efficiency, runs)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                contract_items,
            )
        except Exception as e:
            print(f"[update_contract_items] Failed to retrieve items for contract {contract['contract_id']}")
            print(e)
            incomplete_contracts = True
            
    print("[update_contract_items] Finished updating contract items")
    contract_expiry = await conn.fetchrow(
        "SELECT * FROM db_management.last_updated WHERE task_params = $1 AND task_name = 'esi.contracts'",
        args,
    )
    
    await conn.close()
    return {
        "successful": True,
        "last_updated": datetime.utcnow(),
        "expiry": min(datetime.utcnow() + timedelta(minutes=5), contract_expiry["expiry"]) if incomplete_contracts else contract_expiry["expiry"]
    }
