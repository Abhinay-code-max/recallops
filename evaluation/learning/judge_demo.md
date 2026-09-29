# Judge demo (<60 seconds)

Here is what RecallOps believed before feedback: for recurring `payments-api` pool exhaustion, pool resize ranked first at 0.6598. Killing idle connections ranked second at 0.4358, with one Worked and one Partial outcome.

The engineer reports one outcome: on `INC-023`, killing idle connections worked. Exactly one feedback event was submitted.

RecallOps immediately updated it to Worked=2, score 0.7000, and rank #1 on the same context. On the next similar incident it recalled `INC-023` and retained Worked=2. Different recall similarity left it #2 at 0.4338; we did not add feedback to force a rank change.

After resolution, future recall returned `INC-024`, proving retention.

No LLM weights were retrained. The change came from Hindsight/live feedback memory, a structured outcome-count overlay, and the existing deterministic scoring formula.
