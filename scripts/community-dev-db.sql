-- Dedicated development role/databases; does not modify existing databases.
SELECT 'CREATE ROLE community LOGIN PASSWORD ''community'''
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'community')\gexec
SELECT 'CREATE DATABASE community_dev OWNER community'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'community_dev')\gexec
SELECT 'CREATE DATABASE community_test OWNER community'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'community_test')\gexec
