import grequests
import requests
import math
import decimal

from fastapi import FastAPI
from psycopg2 import sql
from utils import connect_to_db
from collections import defaultdict

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/reprocess")
async def reprocess(location_id: int = 60003760):
    conn = connect_to_db()
    cur = conn.cursor()
    item_data = {}
    YIELD = decimal.Decimal("0.5")
    TAX = decimal.Decimal("0.036")
    
    # get all items that are published
    cur.execute("SELECT type_id, portion_size FROM sde.type_ids")
    for type_id, portion_size in cur.fetchall():
        item_data[type_id] = {
            "portion_size": portion_size,
            "materials": {}
        }
    
    # get materials for every item that is published
    cur.execute("SELECT type_id, material_type_id, quantity FROM sde.type_materials")
    for type_id, material_type_id, quantity in cur.fetchall():
        if type_id not in item_data:
            continue
        item_data[type_id]["materials"][material_type_id] = quantity * YIELD
        
    # trim items that dont have materials
    item_data = {type_id: value for type_id, value in item_data.items() if len(value["materials"]) > 0}
    
    # double items that require .5 of an item
    for type_id, value in item_data.items():
        if any([quantity % 1 != 0 for quantity in value["materials"].values()]):
            value["portion_size"] *= 2
            for material_type_id, quantity in value["materials"].items():
                value["materials"][material_type_id] = quantity * 2
        
    # get all sell orders for the location
    sell_orders = defaultdict(list)
    cur.execute("SELECT type_id, volume_remain, price FROM market.orders WHERE location_id = %s AND is_buy_order = FALSE", (location_id,))
    for type_id, volume_remain, price in cur.fetchall():
        if type_id not in item_data:
            continue
        sell_orders[type_id].append((volume_remain, price))
            
    # trim items that you can't buy
    item_data = {type_id: value for type_id, value in item_data.items() if len(sell_orders[type_id]) > 0}
    
    # get all materials for every item
    all_materials = set()
    for type_id, value in item_data.items():
        for material_type_id in value["materials"]:
            all_materials.add(material_type_id)
    
    # get all buy orders for the location
    buy_orders = defaultdict(list)
    cur.execute("SELECT type_id, volume_remain, price FROM market.orders WHERE location_id = %s AND is_buy_order = TRUE", (location_id,))
    for type_id, volume_remain, price in cur.fetchall():
        if type_id not in all_materials:
            continue
        buy_orders[type_id].append((volume_remain, price))
        
    # calculate the prices for every item
    for type_id, value in item_data.items():
        # calculate price to purchase the original item
        buy_vol = 0
        buy_price = 0
        for volume_remain, price in sorted(sell_orders[type_id], key=lambda x: x[1]):
            buy_price += min(value["portion_size"] - buy_vol, volume_remain) * price
            buy_vol += min(value["portion_size"] - buy_vol, volume_remain)
            if buy_vol == value["portion_size"]:
                break
            
        if buy_vol < value["portion_size"]:
            continue
        
        # calculate price we can get from selling materials
        sell_price = 0
        failed_to_sell = False
        for material_type_id, quantity in value["materials"].items():
            sell_vol = 0
            for volume_remain, price in sorted(buy_orders[material_type_id], key=lambda x: x[1], reverse=True):
                sell_price += min(quantity - sell_vol, volume_remain) * price
                sell_vol += min(quantity - sell_vol, volume_remain)
                if sell_vol == quantity:
                    break
            if sell_vol < quantity:
                failed_to_sell = True
                break
        
        if failed_to_sell:
            continue
        
        if buy_price == 0 or sell_price == 0:
            continue
        
        item_data[type_id]["unit_price"] = buy_price / value["portion_size"]
        item_data[type_id]["buy_price"] = buy_price
        item_data[type_id]["sell_price"] = sell_price
        
    # trim items that don't have a buy and sell price
    item_data = {type_id: value for type_id, value in item_data.items() if "buy_price" in value and "sell_price" in value}
    
    # calculate profit for every item
    for type_id, value in item_data.items():
        value["profit"] = value["sell_price"] * (1 - TAX) - value["buy_price"]
        value["roi"] = value["profit"] / value["buy_price"]
        
    # trim items that are not profitable
    item_data = {type_id: value for type_id, value in item_data.items() if value["profit"] > 0}
    
    # add names to items
    cur.execute("SELECT type_id, name FROM sde.type_ids")
    for type_id, name in cur.fetchall():
        if type_id not in item_data:
            continue
        item_data[type_id]["name"] = name
        
    # return items sorted by profit
    item_data = sorted(item_data.items(), key=lambda x: x[1]["profit"], reverse=True)
    
    conn.commit()
    cur.close()
    conn.close()
    
    return item_data



@app.get("/update")
async def update(region_id: int = 10000002):
    url = "https://esi.evetech.net/latest/markets/10000002/orders/"
    params = {"datasource": "tranquility", "order_type": "all", "region_id": region_id, "page": 1}
    response = requests.get(url, params=params)
    
    other_pages = (grequests.get(url, params={"datasource": "tranquility", "order_type": "all", "region_id": region_id, "page": i}) for i in range(2, int(response.headers["x-pages"]) + 1))
    completed_orders = [response] + grequests.map(other_pages)
    
    for response in completed_orders:
        if response.status_code == 200:
            continue
        print(f"Error: {response.status_code} {response.reason}")
        return {"message": "Error", "status_code": response.status_code, "reason": response.reason}
        
    conn = connect_to_db()
    cur = conn.cursor()
    
    cur.execute("TRUNCATE TABLE market.orders")
    
    for response in completed_orders:
        for order in response.json():
            cur.execute(
                sql.SQL("INSERT INTO market.orders (order_id, type_id, location_id, system_id, region_id, volume_total, volume_remain, min_volume, price, range, is_buy_order, issued, duration) VALUES ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})").format(
                    sql.Literal(order["order_id"]),
                    sql.Literal(order["type_id"]),
                    sql.Literal(order["location_id"]),
                    sql.Literal(region_id),
                    sql.Literal(order["system_id"]),
                    sql.Literal(order["volume_total"]),
                    sql.Literal(order["volume_remain"]),
                    sql.Literal(order["min_volume"]),
                    sql.Literal(order["price"]),
                    sql.Literal(order["range"]),
                    sql.Literal(order["is_buy_order"]),
                    sql.Literal(order["issued"]),
                    sql.Literal(order["duration"])
                )
            )
    print(f"Added {sum([len(response.json()) for response in completed_orders])} orders to database.")
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {"message": "Updated Orders", "expires": response.headers["expires"]}
