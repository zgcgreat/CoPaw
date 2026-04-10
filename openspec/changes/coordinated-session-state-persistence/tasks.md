## 1. Add authoritative session checkpoint metadata

- [x] 1.1 Introduce MySQL-backed session checkpoint metadata with tenant, session, user, and version identity
- [x] 1.2 Define how raw checkpoint payloads are stored and referenced from authoritative metadata
- [x] 1.3 Add version-aware write semantics so stale writers cannot silently overwrite newer checkpoints

## 2. Migrate session save and load paths

- [x] 2.1 Update session save paths to create coordinated checkpoints
- [x] 2.2 Update session load paths to resolve the latest checkpoint through authoritative metadata
- [x] 2.3 Add compatibility or migration handling for existing legacy session JSON files

## 3. Verify conflict-safe persistence

- [x] 3.1 Add tests for concurrent multi-instance session updates
- [x] 3.2 Add tests for durable latest-checkpoint resolution across instances
- [x] 3.3 Add tests for conflict and cleanup behavior when checkpoint writes partially fail
