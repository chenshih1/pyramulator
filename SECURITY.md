# Security Policy

## Reporting a vulnerability

Please do **not** open a public issue for security vulnerabilities. Report
them privately:

- Open a security advisory on GitHub:
  https://github.com/chenshih1/pyramulator/security/advisories/new
- Or email the maintainers directly.

You will receive a response within 5 business days. Please include a
description of the issue, affected versions, and a minimal reproduction if
possible.

## Scope

pyramulator is a simulation library; it does not process untrusted input
from network or user-controlled data in production deployments. However,
defects in the pybind11 binding layer (memory safety, GIL handling, crash
on invalid input) are in scope and will be treated seriously.
