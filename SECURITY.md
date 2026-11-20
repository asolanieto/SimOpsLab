# Security policy

SimOps runs installed backend plugins and may invoke Docker or simulator processes. Plugins are trusted code; an MCP backend allowlist limits selection but does not sandbox a malicious plugin. Keep MCP on local stdio, review adapters before enabling them, and do not mount secrets into simulation containers.

Please report suspected vulnerabilities privately to the repository owner through GitHub Security Advisories. Do not include credentials, private maps, bags, or robot logs in public issues.
