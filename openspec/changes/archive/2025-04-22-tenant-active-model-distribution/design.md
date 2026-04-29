## Context

The runtime already treats model configuration as tenant-scoped. The current
tenant's active model is read and written through `ProviderManager` backed by
tenant-local provider files plus `providers/active_model.json`. The models page
also saves with tenant-global scope only.

That gives us a clear source of truth for the requested workflow:
- source active model: current tenant `ProviderManager.get_active_model()`
- source provider config: current tenant provider storage under
  `~/.swe.secret/{tenant}/providers/`
- target active model: target tenant `ProviderManager.activate_model(...)`

What is missing is a cross-tenant orchestration layer in the models domain.
The skill-pool broadcast implementation already proves two useful patterns:
- tenant selection can combine discovered tenant IDs with manual tenant entry
- cross-tenant fan-out should isolate failures per target tenant

The requested first version does not introduce new model scopes or agent-level
configuration. It only adds an operator workflow to copy the current tenant's
active model setup to other tenants.

## Goals / Non-Goals

**Goals:**
- Distribute the current tenant active model to multiple target tenants.
- Copy the required provider configuration before activating the model in each
  target tenant.
- Support both discovered tenants and manually entered tenant IDs.
- Use explicit overwrite semantics in v1.
- Return per-tenant results.

**Non-Goals:**
- Per-agent model distribution.
- Full provider catalog synchronization between tenants.
- Merge dialogs or rename flows for provider conflicts.
- A new tenant registry beyond current discovered-tenants filesystem behavior.
- Reusing the entire skill-pool broadcast modal in the models page.

## Decisions

### Decision 1: the distribution source is the current tenant active model only

**Choice:** The source payload is the current tenant's active model slot from
`ProviderManager`, not an arbitrary provider/model chosen outside that state.

**Rationale:**
- This exactly matches the approved first-version scope.
- It keeps the UX simple: distribute what is currently active.
- It avoids adding a second model-selection surface just for distribution.

**Alternatives considered:**
- Let users choose any provider/model pair in the distribution modal:
  rejected because it duplicates the existing model selector and expands scope.

### Decision 2: distribution copies required provider configuration together with the active model switch

**Choice:** For each target tenant, the backend copies the source provider
configuration needed by the source active model, then activates the same model
on the target tenant.

**Rationale:**
- Writing only `active_model.json` is insufficient if the target tenant does
  not already have the provider config or model entry.
- The current provider storage already persists the exact provider payload
  needed for runtime and console behavior.
- This keeps distribution operationally useful instead of producing broken
  target active-model pointers.

**Alternatives considered:**
- Copy only `provider_id + model`: rejected because target tenants may not have
  the referenced provider/model available.
- Mirror the entire source tenant provider directory: rejected because v1 only
  needs the provider required by the current active model.

### Decision 3: distribution uses explicit overwrite semantics in v1

**Choice:** The request requires `overwrite=true`. When the target tenant
already has a same-ID provider config or an existing active model, the source
provider config replaces the target provider config and the target active model
is updated to the source slot.

**Rationale:**
- This matches the approved first-version behavior.
- It avoids adding ambiguous merge logic for provider fields such as
  `api_key`, `base_url`, `generate_kwargs`, `extra_models`, and custom-provider
  metadata.

**Alternatives considered:**
- Best-effort merge: rejected because field-level merge rules would be fragile.
- Skip-on-conflict: rejected because it would not satisfy the operator's
  distribution intent.

### Decision 4: custom providers are allowed and are replaced by same provider ID

**Choice:** If the active model uses a custom provider, the distribution flow
copies that custom provider to the target tenant by the same provider ID and
overwrites the target copy when `overwrite=true`.

**Rationale:**
- The approved payload includes required provider configuration, not only
  built-in providers.
- Keeping the provider ID stable is necessary because the active-model slot
  references that ID directly.

**Alternatives considered:**
- Exclude custom providers from v1: rejected because it makes the feature fail
  for a meaningful set of valid current active-model states.
- Rename imported custom providers on conflict: rejected because the active
  model would need additional remapping behavior and conflict UX.

### Decision 5: target tenant selection reuses the existing picker pattern, not the whole skill broadcast modal

**Choice:** The frontend extracts a reusable tenant picker surface from the
skill-pool broadcast interaction pattern and uses it in a dedicated models
distribution modal or drawer.

**Rationale:**
- The tenant selection interaction is reusable.
- The full skill broadcast modal is not reusable because it is coupled to skill
  selection and skill-pool copy semantics.
- A models-specific surface can explain model/provider overwrite semantics
  clearly.

**Alternatives considered:**
- Embed the skill broadcast modal directly: rejected because it introduces the
  wrong primary object and wrong copy.
- Rebuild a second tenant picker from scratch: rejected because the current
  selection behavior already matches the needed operator flow.

### Decision 6: per-tenant partial success, but each tenant updates in ordered steps

**Choice:** The batch returns per-tenant results. For each tenant, the backend
executes:
1. validate target tenant ID
2. ensure target tenant bootstrap/provider storage
3. overwrite target provider config
4. activate target active model

If one target fails, other targets still proceed.

**Rationale:**
- This matches the already accepted skill broadcast batch model.
- Operationally, target tenants are independent failure domains.

**Alternatives considered:**
- Whole-batch rollback: rejected because it couples unrelated tenants.

## API Sketch

### `POST /api/models/distribution/active-llm`

Example request:

```json
{
  "target_tenant_ids": ["tenant-a", "tenant-b", "tenant-new"],
  "overwrite": true
}
```

Example response:

```json
{
  "source_active_llm": {
    "provider_id": "openai",
    "model": "gpt-5.4"
  },
  "results": [
    {
      "tenant_id": "tenant-a",
      "success": true,
      "bootstrapped": false,
      "provider_updated": "openai",
      "active_llm_updated": {
        "provider_id": "openai",
        "model": "gpt-5.4"
      }
    },
    {
      "tenant_id": "tenant-new",
      "success": false,
      "bootstrapped": true,
      "error": "..."
    }
  ]
}
```

Notes:
- `overwrite` is required to be `true` in v1.
- The source active model is resolved from the current request tenant.
- Tenant discovery can keep using the existing discovery route in v1, because
  the UI only needs a discovered-tenant list plus manual entry.

## Backend Flow

```text
read current tenant active model
  -> validate source provider and source model exist
  -> read source provider payload from current tenant ProviderManager
  -> for each target tenant:
       validate tenant id
       ensure tenant bootstrap/provider storage
       overwrite target provider config by provider_id
       reload/update target ProviderManager state
       activate_model(provider_id, model_id)
       collect per-tenant result
```

Implementation notes:
- The write path should use `ProviderManager` save/update behavior instead of
  raw file copying alone, so in-memory manager state and on-disk state remain
  aligned.
- Built-in provider distribution should carry configured fields plus
  `extra_models`.
- Custom provider distribution should persist the same custom provider payload
  under the same provider ID.

## Frontend Flow

```text
Models page
  -> read current active model
  -> user clicks "Distribute"
  -> open models-specific tenant modal
       -> discovered tenant list
       -> manual tenant entry
       -> overwrite warning copy
  -> submit distribution request
  -> show per-tenant success/failure results
```

Recommended placement:
- place the entry action near the current active-model save area in
  `ModelsSection`, because the distribution source is "what is active now"
  rather than a provider card or model-management action.

## Risks / Trade-offs

- [Secrets are copied across tenants]
  -> This is intentional in v1 because the approved payload includes required
  provider configuration. The UI and API copy should state this clearly.
- [Target tenant has a provider with the same ID but different intent]
  -> `overwrite=true` makes replacement explicit in v1.
- [Direct file writes could leave cached ProviderManager state stale]
  -> Route all target writes through target-tenant `ProviderManager` logic.
- [Discovered tenants are incomplete]
  -> Keep manual tenant entry in the UI.
- [Target bootstrap and provider initialization semantics drift]
  -> Reuse existing tenant bootstrap/provider initialization boundaries instead
  of inventing a second setup path.
