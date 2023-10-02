import yaml

from psycopg2 import sql, extensions
from src.util import connect_to_db

SDE_LOCATION = "./sde"

def import_type_materials(cur: extensions.cursor):
    print("Importing typeMaterials.yaml")
    with open(f"{SDE_LOCATION}/fsd/typeMaterials.yaml", 'r', encoding="utf-8") as stream:
        type_materials = yaml.safe_load(stream)
        
        cur.execute("TRUNCATE TABLE sde.type_materials")
        
        for type_id, value in type_materials.items():
            materials = value["materials"]
            for material in materials:
                cur.execute(
                    sql.SQL("INSERT INTO sde.type_materials (type_id, material_type_id, quantity) VALUES ({}, {}, {})").format(
                        sql.Literal(type_id),
                        sql.Literal(material["materialTypeID"]),
                        sql.Literal(material["quantity"])
                    )
                )
    print("Importing typeMaterials.yaml complete")
                
                
def import_type_ids(cur: extensions.cursor):
    print("Importing typeIDs.yaml")
    with open(f"{SDE_LOCATION}/fsd/typeIDs.yaml", 'r', encoding="utf-8") as stream:
        type_ids = yaml.safe_load(stream)
        
        cur.execute("TRUNCATE TABLE sde.type_ids")
        
        for type_id, value in type_ids.items():
            cur.execute(
                sql.SQL("INSERT INTO sde.type_ids (type_id, name, published, base_price, mass, volume, portion_size) VALUES ({}, {}, {}, {}, {}, {}, {})").format(
                    sql.Literal(type_id),
                    sql.Literal(value["name"]['en']),
                    sql.Literal(value["published"]),
                    sql.Literal(value["basePrice"] if "basePrice" in value else None),
                    sql.Literal(value["mass"] if "mass" in value else None),
                    sql.Literal(value["volume"] if "volume" in value else None),
                    sql.Literal(value["portionSize"]),
                )
            )
    print("Importing typeIDs.yaml complete")
        

if __name__ == '__main__':
    conn = connect_to_db()
    cur = conn.cursor()
    
    import_type_materials(cur)
    import_type_ids(cur)
    
    conn.commit()
    cur.close()
    conn.close()