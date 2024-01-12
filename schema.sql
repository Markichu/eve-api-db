CREATE SCHEMA IF NOT EXISTS esi;

DROP TABLE IF EXISTS esi.contracts;

-- TODO: Remove unnecessary region_id column since it can be derived from the start_location_id/end_location_id
CREATE TABLE esi.contracts (
    contract_id BIGINT PRIMARY KEY,
    date_issued TIMESTAMP NOT NULL,
    date_expired TIMESTAMP NOT NULL,
    issuer_id BIGINT NOT NULL,
    issuer_corporation_id BIGINT NOT NULL,
    for_corporation BOOLEAN NOT NULL,
    type VARCHAR(32) NOT NULL,
    start_location_id BIGINT NOT NULL,
    end_location_id BIGINT NOT NULL,
    region_id BIGINT NOT NULL,
    collateral DECIMAL(20,2),              -- not present for auctions
    reward DECIMAL(20,2) NOT NULL,
    buyout DECIMAL(20,2),                  -- only present for auctions
    days_to_complete BIGINT NOT NULL,
    price DECIMAL(20,2) NOT NULL,
    title VARCHAR(100) NOT NULL,
    volume DECIMAL(100,2) NOT NULL
);

DROP TABLE IF EXISTS esi.contract_items;

CREATE TABLE esi.contract_items (
    contract_id BIGINT NOT NULL,
    record_id BIGINT NOT NULL,
    type_id INT NOT NULL,
    quantity BIGINT NOT NULL,
    is_included BOOLEAN NOT NULL,
    item_id BIGINT,
    is_blueprint_copy BOOLEAN,
    material_efficiency INT,
    time_efficiency INT,
    runs INT,
    PRIMARY KEY (contract_id, record_id)
);

CREATE SCHEMA IF NOT EXISTS market;

DROP TABLE IF EXISTS market.orders;

CREATE TABLE market.orders (
    order_id BIGINT PRIMARY KEY,
    type_id INT NOT NULL,
    location_id BIGINT NOT NULL,
    system_id INT NOT NULL,
    region_id INT NOT NULL,
    volume_total BIGINT NOT NULL,
    volume_remain BIGINT NOT NULL,
    min_volume INT NOT NULL,
    price DECIMAL(20,2) NOT NULL,
    range VARCHAR(11) NOT NULL,
    is_buy_order BOOLEAN NOT NULL,
    issued TIMESTAMP NOT NULL,
    duration INT NOT NULL
);

DROP TABLE IF EXISTS market.history;

CREATE TABLE market.history (
    type_id INT NOT NULL,
    date TIMESTAMP NOT NULL,
    highest DECIMAL(20,2) NOT NULL,
    lowest DECIMAL(20,2) NOT NULL,
    average DECIMAL(20,2) NOT NULL,
    volume BIGINT NOT NULL,
    order_count INT NOT NULL,
    PRIMARY KEY (type_id, date)
);

DROP TABLE IF EXISTS market.aggregates;

CREATE TABLE market.aggregates (
    location_id BIGINT NOT NULL,
    type_id INT NOT NULL,
    sell_min DECIMAL(20,2),
    buy_max DECIMAL(20,2),
    sell_volume BIGINT NOT NULL,
    buy_volume BIGINT NOT NULL,
    sell_orders INT NOT NULL,
    buy_orders INT NOT NULL,
    region_id BIGINT NOT NULL,
    PRIMARY KEY (location_id, type_id)
);

DROP TABLE IF EXISTS market.reprocess;

CREATE TABLE market.reprocess (
    type_id INT NOT NULL PRIMARY KEY,
    reprocess_value DECIMAL(22,4) NOT NULL
);

DROP TABLE IF EXISTS market.manufacture;

CREATE TABLE market.manufacture (
    type_id INT NOT NULL PRIMARY KEY,
    manufacture_value DECIMAL(22,4) NOT NULL
);

-- SDE schema, for storing data related to the static data export
CREATE SCHEMA IF NOT EXISTS sde;

DROP TABLE IF EXISTS sde.blueprints;

CREATE TABLE sde.blueprints (
    blueprint_type_id INT PRIMARY KEY,
    max_production_limit INT NOT NULL,
    copying_time INT,
    invention_time INT,
    manufacturing_time INT,
    research_material_time INT,
    research_time_time INT,
    reaction_time INT
);

DROP TABLE IF EXISTS sde.blueprint_materials;

CREATE TABLE sde.blueprint_materials (
    blueprint_type_id INT NOT NULL,
    activity VARCHAR(32) NOT NULL,
    material_type_id INT NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (blueprint_type_id, activity, material_type_id)
);

DROP TABLE IF EXISTS sde.blueprint_products;

CREATE TABLE sde.blueprint_products (
    blueprint_type_id INT NOT NULL,
    activity VARCHAR(32) NOT NULL,
    product_type_id INT NOT NULL,
    quantity INT NOT NULL,
    probability DECIMAL(10,2),
    PRIMARY KEY (blueprint_type_id, activity, product_type_id)
);

DROP TABLE IF EXISTS sde.blueprint_skills;

CREATE TABLE sde.blueprint_skills (
    blueprint_type_id INT NOT NULL,
    activity VARCHAR(32) NOT NULL,
    skill_type_id INT NOT NULL,
    level INT NOT NULL,
    PRIMARY KEY (blueprint_type_id, activity, skill_type_id)
);

DROP TABLE IF EXISTS sde.market_groups;

CREATE TABLE sde.market_groups (
    market_group_id INT PRIMARY KEY,
    has_types BOOLEAN NOT NULL,
    icon_id INT,
    name_id VARCHAR(100) NOT NULL,
    parent_group_id INT
);

DROP TABLE IF EXISTS sde.type_ids;

CREATE TABLE sde.type_ids (
    type_id INT PRIMARY KEY,
    base_price DECIMAL(100,2),
    capacity DECIMAL(100,2),
    faction_id INT,
    graphic_id INT,
    group_id INT NOT NULL,
    icon_id INT,
    market_group_id INT,
    mass DECIMAL(100,2),
    meta_group_id INT,
    name VARCHAR(100) NOT NULL,
    portion_size INT NOT NULL,
    published BOOLEAN NOT NULL,
    race_id INT,
    radius DECIMAL(100,2),
    sof_faction_name VARCHAR(100),
    sof_material_set_id INT,
    variation_parent_type_id INT,
    sound_id INT,
    volume DECIMAL(100,2)
);

DROP TABLE IF EXISTS sde.type_materials;

CREATE TABLE sde.type_materials (
    type_id INT NOT NULL,
    material_type_id INT NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (type_id, material_type_id)
);

-- DB management schema, for storing data related to the management of data in the database
CREATE SCHEMA IF NOT EXISTS db_management;

DROP TABLE IF EXISTS db_management.last_updated;

CREATE TABLE db_management.last_updated (
    task_name VARCHAR(100) NOT NULL,
    task_params VARCHAR(100) NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    expiry TIMESTAMP NOT NULL
);

ALTER TABLE db_management.last_updated ADD CONSTRAINT last_updated_pk PRIMARY KEY (task_name, task_params);

