CREATE TABLE customers (
  customer_id SERIAL PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL, signup_date DATE NOT NULL
);
CREATE TABLE products (
  product_id SERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, price NUMERIC(10,2) NOT NULL
);
CREATE TABLE orders (
  order_id SERIAL PRIMARY KEY, customer_id INT REFERENCES customers(customer_id), order_date DATE NOT NULL, status TEXT NOT NULL
);
CREATE TABLE order_items (
  order_item_id SERIAL PRIMARY KEY, order_id INT REFERENCES orders(order_id), product_id INT REFERENCES products(product_id), quantity INT NOT NULL, unit_price NUMERIC(10,2) NOT NULL
);
INSERT INTO customers(name,region,signup_date) VALUES
('Ava','East','2025-01-10'),('Ben','West','2025-02-15'),('Cara','East','2025-03-20'),('Dev','South','2025-04-05');
INSERT INTO products(name,category,price) VALUES
('Laptop','Electronics',1200),('Headphones','Electronics',150),('Desk','Furniture',400),('Chair','Furniture',250);
INSERT INTO orders(customer_id,order_date,status) VALUES
(1,'2026-01-05','completed'),(1,'2026-02-10','completed'),(2,'2026-02-12','completed'),(3,'2026-03-01','cancelled'),(4,'2026-03-15','completed');
INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES
(1,1,1,1200),(1,2,2,150),(2,3,1,400),(3,2,1,150),(4,4,2,250),(5,1,1,1200),(5,4,1,250);
DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='askdb_readonly') THEN CREATE ROLE askdb_readonly LOGIN PASSWORD 'readonly'; END IF;
END $$;
GRANT CONNECT ON DATABASE askdb TO askdb_readonly;
GRANT USAGE ON SCHEMA public TO askdb_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO askdb_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO askdb_readonly;
