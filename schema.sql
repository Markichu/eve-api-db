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

CREATE SCHEMA IF NOT EXISTS sde;

DROP TABLE IF EXISTS sde.type_materials;

CREATE TABLE sde.type_materials (
    type_id INT NOT NULL,
    material_type_id INT NOT NULL,
    quantity INT NOT NULL
);

DROP TABLE IF EXISTS sde.type_ids;

CREATE TABLE sde.type_ids (
    type_id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    published BOOLEAN NOT NULL,
    base_price DECIMAL(100,2),
    mass DECIMAL(100,2),
    volume DECIMAL(100,2),
    portion_size INT NOT NULL
);

