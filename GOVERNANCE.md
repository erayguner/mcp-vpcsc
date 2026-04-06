# Governance

## Overview

VPC-SC MCP Server is maintained by [@erayguner](https://github.com/erayguner). This document describes how decisions are made and how contributions are accepted.

## Roles

### Maintainer

The maintainer is responsible for:

- Reviewing and merging pull requests
- Triaging issues
- Making release decisions
- Setting project direction and priorities
- Enforcing the [Code of Conduct](CODE_OF_CONDUCT.md)

### Contributors

Anyone who submits a pull request, opens an issue, or participates in discussions is a contributor. Contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md) and [Contributing Guide](CONTRIBUTING.md).

## Decision-making

- **Small changes** (bug fixes, documentation, minor improvements): reviewed and merged by the maintainer.
- **Significant changes** (new tools, architecture changes, security model modifications): discussed in a GitHub issue before implementation. The maintainer makes the final decision after considering community input.
- **Breaking changes**: require a deprecation notice in the changelog and a major version bump following [Semantic Versioning](https://semver.org/).

## Releases

- Releases follow [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH).
- The maintainer decides when to cut releases.
- All changes are documented in [CHANGELOG.md](CHANGELOG.md).

## Becoming a maintainer

As the project grows, additional maintainers may be invited based on sustained, high-quality contributions and alignment with project goals. There is no formal process yet — this will evolve with the community.

## Changes to governance

This governance model may be updated as the project and community evolve. Changes will be proposed via pull request and discussed openly.
