import grequests
import requests
import datetime

from src.util import connect_to_db

async def update_market_orders(args: str) -> bool:
    print(f"Updating orders for region {args}.")
    region_id = int(args)
    
    url = f"https://esi.evetech.net/latest/markets/{region_id}/orders/"
    param_gen = lambda page_id: {"datasource": "tranquility", "order_type": "all", "region_id": region_id, "page": page_id}
    response = requests.get(url, params=param_gen(1))
    
    if response.status_code != 200:
        return {"successful": False}
    
    other_pages = (grequests.get(url, params=param_gen(i)) for i in range(2, int(response.headers["x-pages"]) + 1))
    completed_orders = [response] + grequests.map(other_pages)
    
    for response in completed_orders:
        if response.status_code == 200:
            continue
        return {"successful": False}
        
    orders = []
    for response in completed_orders:
        for order in response.json():
            orders.append((
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
                order["duration"]
            ))
    
    conn = await connect_to_db()
    await conn.execute("DELETE FROM market.orders WHERE region_id = $1", region_id)
    await conn.copy_records_to_table("orders", records=orders, schema_name="market")
    await conn.close()
    
    print(f"Updated {len(orders)} orders for region {args}.")
    return {"successful": True, "expiry": datetime.datetime.strptime(response.headers["expires"], '%a, %d %b %Y %H:%M:%S %Z')}