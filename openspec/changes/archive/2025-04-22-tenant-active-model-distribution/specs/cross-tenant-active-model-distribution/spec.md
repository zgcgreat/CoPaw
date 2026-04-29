## ADDED Requirements

### Requirement: The models page can distribute the current tenant active model to multiple target tenants
The system SHALL let an operator distribute the current tenant active model to
multiple target tenant IDs from the models page.

#### Scenario: Distribution resolves the source from the current tenant active model
- **GIVEN** the current tenant active model is `provider_id=openai`,
  `model=gpt-5.4`
- **WHEN** the operator submits an active-model distribution request
- **THEN** the backend SHALL use the current tenant active model as the source
- **AND** the backend SHALL NOT require the request to restate the source
  `provider_id + model`

#### Scenario: Distribution accepts multiple target tenants
- **GIVEN** the current tenant has an active model configured
- **WHEN** the operator submits target tenants `tenant-a` and `tenant-b`
- **THEN** the backend SHALL process both target tenants in the same request

### Requirement: Distribution copies the required provider configuration before switching the target active model
For each successful target tenant, the system SHALL copy the provider
configuration required by the source active model before activating that model
for the target tenant.

#### Scenario: Built-in provider distribution updates provider state and active model
- **GIVEN** the source active model uses built-in provider `openai`
- **AND** the source tenant has configured `openai` settings and model entries
- **WHEN** the distribution succeeds for target tenant `tenant-a`
- **THEN** the target tenant provider config for `openai` SHALL be overwritten
  by the source tenant configuration
- **AND** the target tenant active model SHALL be set to `openai` with the
  source model ID

#### Scenario: Custom provider distribution preserves provider identity
- **GIVEN** the source active model uses custom provider `corp-gateway`
- **WHEN** the distribution succeeds for target tenant `tenant-a`
- **THEN** the target tenant SHALL store provider `corp-gateway` with the
  source tenant configuration under the same provider ID
- **AND** the target tenant active model SHALL reference `corp-gateway`

### Requirement: Distribution supports target tenants that are not bootstrapped yet
The system SHALL support target tenant IDs that do not yet have a complete
runtime scaffold by preparing the target tenant before provider/model writes.

#### Scenario: Distribution to a not-yet-bootstrapped tenant
- **GIVEN** target tenant `tenant-new` does not yet have a complete tenant
  scaffold
- **WHEN** the operator distributes the current tenant active model to
  `tenant-new`
- **THEN** the system SHALL prepare the target tenant scaffold and provider
  storage before writing provider config or active model state

### Requirement: Distribution uses explicit overwrite semantics in v1
The active-model distribution flow SHALL require explicit overwrite semantics
for the first version.

#### Scenario: Request omits overwrite
- **WHEN** the operator submits an active-model distribution request without
  `overwrite=true`
- **THEN** the backend SHALL reject the request

#### Scenario: Same-ID provider config is overwritten
- **GIVEN** target tenant `tenant-a` already has provider `openai`
- **WHEN** the operator submits distribution with `overwrite=true`
- **THEN** the target tenant provider `openai` SHALL be replaced by the source
  tenant provider configuration used for the current active model

### Requirement: Distribution results are reported per target tenant
The distribution flow SHALL isolate failures per target tenant and SHALL NOT
roll back already successful tenants because another target failed.

#### Scenario: One target tenant fails while another succeeds
- **GIVEN** target tenants `tenant-a` and `tenant-b` are selected
- **AND** `tenant-a` can be updated successfully
- **AND** `tenant-b` encounters a validation or write failure
- **WHEN** the distribution request completes
- **THEN** the response SHALL report success for `tenant-a`
- **AND** the response SHALL report failure details for `tenant-b`
- **AND** the successful updates already written for `tenant-a` SHALL remain in
  place

### Requirement: The models UI supports discovered tenant selection and manual tenant entry
The active-model distribution UI SHALL help operators choose discovered tenants
while also allowing explicit tenant IDs that are not yet bootstrapped.

#### Scenario: Discovered tenants are shown for selection
- **WHEN** the models page opens the active-model distribution UI
- **THEN** the UI SHALL fetch and display discovered tenant IDs from the
  backend tenant discovery route

#### Scenario: Operator enters a tenant ID that is not in the discovered list
- **GIVEN** tenant `tenant-new` is not yet present in the discovered tenant
  response
- **WHEN** the operator manually enters `tenant-new` as a distribution target
- **THEN** the UI SHALL include `tenant-new` in the distribution submission
