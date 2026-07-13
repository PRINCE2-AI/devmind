# Security Policy

## Scope

DevMind includes path validation, command checks, input limits, and log scrubbing. These are application guardrails, not an operating-system sandbox. Treat all model-generated commands and file edits as untrusted until reviewed.

For stronger isolation, run DevMind in a disposable repository, virtual machine, or container with the minimum credentials and filesystem access required.

## Secrets

Never commit Anthropic API keys or a populated `.env` file. If a key is exposed, revoke it immediately in the Anthropic Console, review recent usage, and replace the credential locally.

## Reporting a vulnerability

Do not disclose credential leaks or exploitable vulnerabilities in a public issue. Contact the maintainer through the `PRINCE2-AI` GitHub profile or use GitHub private vulnerability reporting when it is enabled.

Include reproduction steps, affected files, expected impact, and a suggested mitigation. Remove all real credentials, private source code, and personal data from the report.
