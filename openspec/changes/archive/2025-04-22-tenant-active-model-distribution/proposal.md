## Why

The current models page lets an operator set the active LLM for the current
tenant only. There is no operator flow to distribute that tenant-scoped active
model to other tenants, even though the product already supports a similar
cross-tenant broadcast workflow for skill-pool content.

The requested first version is intentionally narrow:
- the distribution source is the current tenant's active model
- the payload includes the required provider configuration together with the
  active model switch
- conflicts use explicit overwrite semantics
- the UI should reuse the target-tenant picker pattern, but not reuse the
  skill broadcast modal itself

Without this flow, operators must switch tenant context repeatedly and manually
recreate the same provider/model setup for each tenant, which is slow and
error-prone.

## What Changes

- Add a cross-tenant active-model distribution API in the models domain.
- Let the models page open a tenant-target picker and distribute the current
  active model to multiple target tenants in one request.
- For each target tenant:
  - ensure tenant bootstrap/provider storage are available
  - copy the required provider configuration from the source tenant
  - activate the same `provider_id + model` pair for the target tenant
- Require `overwrite=true` for the first version instead of introducing
  conflict-resolution branches.
- Return per-tenant success and failure results instead of making the whole
  batch transactional.
- Reuse the existing tenant discovery/selection interaction pattern from the
  skill-pool broadcast flow, but extract it into a models-appropriate UI
  surface rather than coupling to the skill modal.

## Capabilities

### New Capabilities
- `cross-tenant-active-model-distribution`: The system can distribute the
  current tenant active model, together with the required provider
  configuration, to multiple target tenants with additive overwrite semantics.

### Modified Capabilities
- None.

## Impact

- Affected backend modules:
  - `src/swe/app/routers/providers.py`
  - `src/swe/providers/provider_manager.py`
- Affected frontend modules:
  - `console/src/pages/Settings/Models/components/sections/ModelsSection.tsx`
  - `console/src/api/modules/provider.ts`
  - `console/src/api/types/provider.ts`
  - shared tenant picker extraction from the current skill-pool broadcast UI
- Affected behavior:
  - operators can distribute the current tenant active model to multiple target
    tenants from the models page
  - distribution copies required provider state before switching the target
    tenant active model
- Unchanged behavior:
  - model configuration remains tenant-scoped, not agent-scoped
  - ordinary tenant-local provider CRUD and active-model switching remain
    unchanged
  - the skill-pool broadcast modal remains a separate workflow
- Testing impact:
  - cross-tenant distribution backend coverage
  - provider-copy and target activation coverage
  - frontend tenant picker reuse and result display coverage
