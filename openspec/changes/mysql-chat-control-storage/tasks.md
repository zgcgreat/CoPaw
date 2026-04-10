## 1. Add durable chat repositories

- [x] 1.1 Introduce MySQL-backed repositories for chat metadata
- [x] 1.2 Introduce durable interactive run record storage
- [x] 1.3 Add schema and repository wiring for tenant-scoped chat reads and writes

## 2. Migrate chat control paths

- [x] 2.1 Update chat creation, update, delete, and list paths to use the MySQL repositories
- [x] 2.2 Add backfill or import support for existing `chats.json` data
- [x] 2.3 Add dual-read or parity checks during rollout until cutover is complete

## 3. Verify durable behavior

- [x] 3.1 Add tests for concurrent multi-instance chat mutations
- [x] 3.2 Add tests for consistent chat reads across instances after mutation
- [x] 3.3 Add tests for durable run fact persistence after runtime coordination expires
