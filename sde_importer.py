import asyncio
import asyncpg
import yaml

from src.util import connect_to_db

SDE_LOCATION = "./sde"


async def import_blueprints(conn: asyncpg.connection.Connection):
    print("Importing blueprints.yaml")
    with open(f"{SDE_LOCATION}/fsd/blueprints.yaml", "r", encoding="utf-8") as stream:
        blueprints = yaml.safe_load(stream)
        print("Loaded blueprints.yaml")

        potential_activities = [
            "research_time",
            "invention",
            "reaction",
            "manufacturing",
            "research_material",
            "copying",
        ]

        sde_blueprints = []
        sde_materials = []
        sde_products = []
        sde_skills = []

        for blueprint_id, value in blueprints.items():
            activities = value["activities"]

            sde_blueprints.append(
                (
                    blueprint_id,
                    value["maxProductionLimit"],
                    activities["copying"]["time"] if "copying" in activities else None,
                    activities["invention"]["time"] if "invention" in activities else None,
                    activities["manufacturing"]["time"] if "manufacturing" in activities else None,
                    activities["research_material"]["time"] if "research_material" in activities else None,
                    activities["research_time"]["time"] if "research_time" in activities else None,
                    activities["reaction"]["time"] if "reaction" in activities else None,
                )
            )

            for activity in potential_activities:
                if activity not in activities:
                    continue

                for material in activities[activity].get("materials", []):
                    sde_materials.append(
                        (
                            blueprint_id,
                            activity,
                            material["typeID"],
                            material["quantity"],
                        )
                    )

                for product in activities[activity].get("products", []):
                    sde_products.append(
                        (
                            blueprint_id,
                            activity,
                            product["typeID"],
                            product["quantity"],
                            product["probability"] if "probability" in product else None,
                        )
                    )

                for skill in activities[activity].get("skills", []):
                    sde_skills.append(
                        (
                            blueprint_id,
                            activity,
                            skill["typeID"],
                            skill["level"],
                        )
                    )

        # TODO: Wait for them to fix this then remove this junk
        # print(f"{len(set(sde_blueprints))}/{len(sde_blueprints)} blueprints are published.")
        # print(f"{len(set(sde_materials))}/{len(sde_materials)} materials are published.")
        # print(f"{len(set(sde_products))}/{len(sde_products)} products are published.")
        # print(f"{len(set(sde_skills))}/{len(sde_skills)} skills are published.")

        # skill_set = set(sde_skills)
        # for skill in sde_skills:
        #     if skill in skill_set:
        #         skill_set.remove(skill)
        #     else:
        #         print(skill)

        duplicate_skills = [
            (20344, "copying", 11442, 1),
            (20352, "copying", 11442, 1),
            (20354, "copying", 11442, 1),
            (27022, "invention", 3402, 1),
            (27022, "invention", 3402, 1),
        ]
        for skill in duplicate_skills:
            sde_skills.remove(skill)

        await conn.execute("TRUNCATE TABLE sde.blueprints")
        await conn.copy_records_to_table("blueprints", records=sde_blueprints, schema_name="sde")

        await conn.execute("TRUNCATE TABLE sde.blueprint_materials")
        await conn.copy_records_to_table("blueprint_materials", records=sde_materials, schema_name="sde")

        await conn.execute("TRUNCATE TABLE sde.blueprint_products")
        await conn.copy_records_to_table("blueprint_products", records=sde_products, schema_name="sde")

        await conn.execute("TRUNCATE TABLE sde.blueprint_skills")
        await conn.copy_records_to_table("blueprint_skills", records=sde_skills, schema_name="sde")


async def import_market_groups(conn: asyncpg.connection.Connection):
    print("Importing marketGroups.yaml")
    with open(f"{SDE_LOCATION}/fsd/marketGroups.yaml", "r", encoding="utf-8") as stream:
        market_groups = yaml.safe_load(stream)
        print("Loaded marketGroups.yaml")

        sde_market_groups = []

        for group_id, value in market_groups.items():
            sde_market_groups.append(
                (
                    group_id,
                    value["hasTypes"],
                    value["iconID"] if "iconID" in value else None,
                    value["nameID"]["en"],
                    value["parentGroupID"] if "parentGroupID" in value else None,
                )
            )

        await conn.execute("TRUNCATE TABLE sde.market_groups")
        await conn.copy_records_to_table("market_groups", records=sde_market_groups, schema_name="sde")


async def import_type_ids(conn: asyncpg.connection.Connection):
    print("Importing typeIDs.yaml")
    with open(f"{SDE_LOCATION}/fsd/typeIDs.yaml", "r", encoding="utf-8") as stream:
        type_ids = yaml.safe_load(stream)
        print("Loaded typeIDs.yaml")

        sde_type_ids = []

        for type_id, value in type_ids.items():
            sde_type_ids.append(
                (
                    type_id,
                    value["basePrice"] if "basePrice" in value else None,
                    value["capacity"] if "capacity" in value else None,
                    value["factionID"] if "factionID" in value else None,
                    value["graphicID"] if "graphicID" in value else None,
                    value["groupID"] if "groupID" in value else None,
                    value["iconID"] if "iconID" in value else None,
                    value["marketGroupID"] if "marketGroupID" in value else None,
                    value["mass"] if "mass" in value else None,
                    value["metaGroupID"] if "metaGroupID" in value else None,
                    value["name"]["en"],
                    value["portionSize"],
                    value["published"],
                    value["raceID"] if "raceID" in value else None,
                    value["radius"] if "radius" in value else None,
                    value["sofFactionName"] if "sofFactionName" in value else None,
                    value["sofMaterialSetID"] if "sofMaterialSetID" in value else None,
                    value["variationParentTypeID"] if "variationParentTypeID" in value else None,
                    value["soundID"] if "soundID" in value else None,
                    value["volume"] if "volume" in value else None,
                )
            )

        await conn.execute("TRUNCATE TABLE sde.type_ids")
        await conn.copy_records_to_table("type_ids", records=sde_type_ids, schema_name="sde")


async def import_type_materials(conn: asyncpg.connection.Connection):
    print("Importing typeMaterials.yaml")
    with open(f"{SDE_LOCATION}/fsd/typeMaterials.yaml", "r", encoding="utf-8") as stream:
        type_materials = yaml.safe_load(stream)
        print("Loaded typeMaterials.yaml")

        sde_type_materials = []

        for type_id, value in type_materials.items():
            for material in value["materials"]:
                sde_type_materials.append(
                    (
                        type_id,
                        material["materialTypeID"],
                        material["quantity"],
                    )
                )

        await conn.execute("TRUNCATE TABLE sde.type_materials")
        await conn.copy_records_to_table("type_materials", records=sde_type_materials, schema_name="sde")


async def main():
    conn = await connect_to_db()

    # await import_blueprints(conn)
    await import_market_groups(conn)
    # await import_type_ids(conn)
    # await import_type_materials(conn)

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
