# Security

## Reporting a vulnerability

Do not publish vulnerabilities or sensitive data in a public issue.

Use GitHub private security advisories when available. Otherwise, contact the maintainer privately before making any disclosure.

## Sensitive data

This project may process confidential Jira issues. Never commit:

- a `.env` file or password;
- a SQLite database or issue export;
- a report containing identifiers or internal descriptions;
- an API key, token, or private certificate.

Local pipeline output is excluded by `.gitignore`.

