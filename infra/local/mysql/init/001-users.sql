CREATE USER IF NOT EXISTS 'veritymesh_migration'@'%' IDENTIFIED BY 'veritymesh-migration-local';
CREATE USER IF NOT EXISTS 'veritymesh_app'@'%' IDENTIFIED BY 'veritymesh-app-local';

GRANT ALL PRIVILEGES ON `veritymesh`.* TO 'veritymesh_migration'@'%';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'veritymesh_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON `veritymesh`.* TO 'veritymesh_app'@'%';

FLUSH PRIVILEGES;
