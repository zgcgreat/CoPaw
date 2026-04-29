## 1. Backend API surface

- [x] 1.1 Add request/response models for active-model distribution in `src/swe/app/routers/providers.py`
- [x] 1.2 Add `POST /api/models/distribution/active-llm` with required `overwrite=true`
- [x] 1.3 Reuse the existing discovered-tenant listing route for the frontend picker in v1, or add a models-domain alias only if needed for API clarity

## 2. Backend orchestration

- [x] 2.1 Resolve the current tenant source active model from `ProviderManager`
- [x] 2.2 Validate the source provider and source model exist before target fan-out begins
- [x] 2.3 Add target-tenant bootstrap/provider-storage preparation before applying writes
- [x] 2.4 Implement target provider overwrite using `ProviderManager`-aligned persistence for both built-in and custom providers
- [x] 2.5 Activate the source `provider_id + model` on each successful target tenant
- [x] 2.6 Return per-tenant success/failure results without whole-batch rollback

## 3. Frontend models page

- [x] 3.1 Extract a reusable tenant picker component from the existing skill-pool broadcast interaction pattern
- [x] 3.2 Add provider API types and client methods for active-model distribution
- [x] 3.3 Add a models-specific distribution modal or drawer wired from `ModelsSection`
- [x] 3.4 Show overwrite/provider-copy warning copy in the models distribution UI
- [x] 3.5 Submit tenant selections and present per-tenant result feedback

## 4. Verification

- [x] 4.1 Add backend tests for distributing to an already bootstrapped tenant
- [x] 4.2 Add backend tests for distributing to a not-yet-bootstrapped tenant
- [x] 4.3 Add backend tests for built-in provider overwrite plus active-model switch
- [x] 4.4 Add backend tests for custom provider overwrite plus active-model switch
- [x] 4.5 Add backend tests for per-tenant partial success behavior
- [x] 4.6 Add frontend coverage for tenant picker reuse, overwrite warning copy, and result display
