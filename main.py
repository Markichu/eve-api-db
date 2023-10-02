import grequests
import requests
import datetime
import decimal

from fastapi import FastAPI
from src.util import connect_to_db
from src.tasks import update_market_orders

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}


# @app.get("/reprocess")
# async def reprocess(location_id: int = 60003760):
#     conn = await connect_to_db()
#     cur = conn.cursor()
#     item_data = {}
#     YIELD = decimal.Decimal("0.5")
#     TAX = decimal.Decimal("0.036")
    
#     # get all items that are published
#     cur.execute("SELECT type_id, portion_size FROM sde.type_ids")
#     for type_id, portion_size in cur.fetchall():
#         item_data[type_id] = {
#             "portion_size": portion_size,
#             "materials": {}
#         }
    
#     # get materials for every item that is published
#     cur.execute("SELECT type_id, material_type_id, quantity FROM sde.type_materials")
#     for type_id, material_type_id, quantity in cur.fetchall():
#         if type_id not in item_data:
#             continue
#         item_data[type_id]["materials"][material_type_id] = quantity * YIELD
        
#     # trim items that dont have materials
#     item_data = {type_id: value for type_id, value in item_data.items() if len(value["materials"]) > 0}
    
#     # double items that require .5 of an item
#     for type_id, value in item_data.items():
#         if any([quantity % 1 != 0 for quantity in value["materials"].values()]):
#             value["portion_size"] *= 2
#             for material_type_id, quantity in value["materials"].items():
#                 value["materials"][material_type_id] = quantity * 2
        
#     # get all sell orders for the location
#     sell_orders = defaultdict(list)
#     cur.execute("SELECT type_id, volume_remain, price FROM market.orders WHERE location_id = %s AND is_buy_order = FALSE", (location_id,))
#     for type_id, volume_remain, price in cur.fetchall():
#         if type_id not in item_data:
#             continue
#         sell_orders[type_id].append((volume_remain, price))
            
#     # trim items that you can't buy
#     item_data = {type_id: value for type_id, value in item_data.items() if len(sell_orders[type_id]) > 0}
    
#     # get all materials for every item
#     all_materials = set()
#     for type_id, value in item_data.items():
#         for material_type_id in value["materials"]:
#             all_materials.add(material_type_id)
    
#     # get all buy orders for the location
#     buy_orders = defaultdict(list)
#     cur.execute("SELECT type_id, volume_remain, price FROM market.orders WHERE location_id = %s AND is_buy_order = TRUE", (location_id,))
#     for type_id, volume_remain, price in cur.fetchall():
#         if type_id not in all_materials:
#             continue
#         buy_orders[type_id].append((volume_remain, price))
        
#     # calculate the prices for every item
#     for type_id, value in item_data.items():
#         # calculate price to purchase the original item
#         buy_vol = 0
#         buy_price = 0
#         for volume_remain, price in sorted(sell_orders[type_id], key=lambda x: x[1]):
#             buy_price += min(value["portion_size"] - buy_vol, volume_remain) * price
#             buy_vol += min(value["portion_size"] - buy_vol, volume_remain)
#             if buy_vol == value["portion_size"]:
#                 break
            
#         if buy_vol < value["portion_size"]:
#             continue
        
#         # calculate price we can get from selling materials
#         sell_price = 0
#         failed_to_sell = False
#         for material_type_id, quantity in value["materials"].items():
#             sell_vol = 0
#             for volume_remain, price in sorted(buy_orders[material_type_id], key=lambda x: x[1], reverse=True):
#                 sell_price += min(quantity - sell_vol, volume_remain) * price
#                 sell_vol += min(quantity - sell_vol, volume_remain)
#                 if sell_vol == quantity:
#                     break
#             if sell_vol < quantity:
#                 failed_to_sell = True
#                 break
        
#         if failed_to_sell:
#             continue
        
#         if buy_price == 0 or sell_price == 0:
#             continue
        
#         item_data[type_id]["unit_price"] = buy_price / value["portion_size"]
#         item_data[type_id]["buy_price"] = buy_price
#         item_data[type_id]["sell_price"] = sell_price
        
#     # trim items that don't have a buy and sell price
#     item_data = {type_id: value for type_id, value in item_data.items() if "buy_price" in value and "sell_price" in value}
    
#     # calculate profit for every item
#     for type_id, value in item_data.items():
#         value["profit"] = value["sell_price"] * (1 - TAX) - value["buy_price"]
#         value["roi"] = value["profit"] / value["buy_price"]
        
#     # trim items that are not profitable
#     item_data = {type_id: value for type_id, value in item_data.items() if value["profit"] > 0}
    
#     # add names to items
#     cur.execute("SELECT type_id, name FROM sde.type_ids")
#     for type_id, name in cur.fetchall():
#         if type_id not in item_data:
#             continue
#         item_data[type_id]["name"] = name
        
#     # return items sorted by profit
#     item_data = sorted(item_data.items(), key=lambda x: x[1]["profit"], reverse=True)
    
#     conn.commit()
#     cur.close()
#     conn.close()
    
#     return item_data

@app.post("/add_task")
async def add_task(task_name: str, task_params: str):
    conn = await connect_to_db()
    await conn.execute("INSERT INTO db_management.last_updated (task_name, task_params, last_updated, expiry) VALUES ($1, $2, $3, $4)", task_name, task_params, datetime.datetime.min, datetime.datetime.min)
    await conn.close()
    return {"successful": True}

@app.get("/update")
async def update():
    # get tasks that need to be updated
    conn = await connect_to_db()
    tasks = await conn.fetch("SELECT * FROM db_management.last_updated")
    
    TASKS = {
        "market.orders": update_market_orders,
    }
    task_status = []
    
    for task in tasks:
        # check if task needs to be updated
        if task["expiry"] > datetime.datetime.utcnow():
            continue
        
        result = await TASKS[task["task_name"]](task["task_params"])
        
        if result["successful"]:
            task_status.append({"task_name": task["task_name"], "task_params": task["task_params"], "successful": True, "expires": result["expiry"]})
            await conn.execute("UPDATE db_management.last_updated SET last_updated = $1, expiry = $2 WHERE task_name = $3 AND task_params = $4", datetime.datetime.utcnow(), result["expiry"], task["task_name"], task["task_params"])
        else:
            task_status.append({"task_name": task["task_name"], "task_params": task["task_params"], "successful": False})
    
    
    await conn.close()
    return task_status
