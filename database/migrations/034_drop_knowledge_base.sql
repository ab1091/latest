-- Drops the RAG knowledge base (see migration 028). RAG was removed from the
-- product — unnecessary for an insurance-only CRM and was adding latency to
-- every SMS reply / outbound call / inbound Vapi assistant-request (a local
-- sentence-transformers embedding computed synchronously on every turn). No
-- other feature reads kb_documents/kb_chunks or the `vector` extension
-- (verified: grep for "vector(" across schema.pg.sql + migrations/*.sql
-- returns only 028_knowledge_base.sql).
DROP TABLE IF EXISTS kb_chunks CASCADE;
DROP TABLE IF EXISTS kb_documents CASCADE;
DROP EXTENSION IF EXISTS vector;
