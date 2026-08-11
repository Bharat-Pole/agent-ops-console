# A2A Handoff Design Pattern

This asset is the readiness and discovery layer for internal company agents. It does not run another agent, call another team service, or move artifacts at runtime.

## Readiness rule

An agent is discoverable only when all conditions are true:

- The agent card is `published`.
- The latest eligibility attestation says `a2a_enabled=true`.
- The attested `capability_tier` matches the card tier.
- The lifecycle status is `live`.
- `registry_ready`, `runtime_ready`, and `content_ready` are all true.

This follows the master spec rule that A2A appears only when the source agent is actually LIVE and ready.

## Card tiers

`standardized` cards are discovery-only:

- `discovery_only=true`
- `message_task_format=null`
- `artifact_exchange=false`
- `artifact_format=null`

`advanced` cards declare full exchange readiness:

- `discovery_only=false`
- `message_task_format` is required
- `artifact_exchange=true`
- `artifact_format` is required

## Handoff validation

`POST /a2a/v1/handoffs/validate` checks whether a future cross-agent handoff is allowed by design:

- Source and target must both be published and eligible.
- Target must declare the requested task in `supported_tasks`.
- A trace correlation ID is required and returned.
- Target timeout, failure behavior, artifact format, and auth methods are returned.
- If human approval is required, the first validation creates a pending approval request instead of returning ready.

## Human approval

When `handoff_rules.require_human_approval=true`, validation returns:

```json
{
  "status": "approval_required",
  "trace_correlation_id": "trc-...",
  "approval_request_id": "..."
}
```

A reviewer then calls:

```text
POST /a2a/v1/handoff-approval-requests/{approval_id}/decision
```

After approval, the same handoff validation can be retried with `approval_request_id`, and the service returns `ready_for_handoff`.

## Audit pattern

Every mutation creates an audit event:

- card create, update, publish, suspend, retire
- eligibility attestation
- handoff approval requested
- handoff approval approved or rejected
- handoff validated

This makes the A2A readiness layer reviewable before integration into the main console.
