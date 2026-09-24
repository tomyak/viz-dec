# Releases

The package and both plugins share a semantic version. Public releases are Git tags `vMAJOR.MINOR.PATCH` on `tomyak/viz-dec`. Tags should be immutable.

1. Run `uv run python scripts/release.py --set-version MAJOR.MINOR.PATCH`. This updates Python/plugin metadata, launcher version, README examples, installer default tag, and lock metadata.
2. Add the matching CHANGELOG.md entry. Review dependency/model revision changes separately.
3. Run lint, format check, unit/integration tests, model tests on Apple Silicon, plugin validation, and `uv build`. Test `bash install.sh --agents both` from a clean installation directory, including a model-download failure and cached-model reuse. Check private files/credentials are excluded.
4. Commit, push, and verify CI. Run `uv run python scripts/release.py --check --tag vMAJOR.MINOR.PATCH`, then create and push that tag.
5. The Release workflow reruns checks, builds a wheel and sdist, archives the plugin and standalone skill, creates SHA256SUMS, and publishes a GitHub release. It does not publish to PyPI or include model weights.

The source archive contains the installer and locked project. The plugin ZIP contains metadata, the shared skill, MCP configuration, and MIT license. The skill ZIP contains only the portable skill, CLI launcher, references, and license, with no MCP manifest or machine-specific runtime binding. Neither ZIP alone provisions Python or weights; use the release's installer for a complete installation, choosing `--integration skill` for skill-only use. Release assets use GitHub permissions and work with private forks under the same process.

GPU correctness tests are intentionally opt-in; generic GitHub runners lack the supported model/Metal environment. CI checks the agent-independent core on Linux as well as macOS. Synthetic tests do not establish real-world accuracy. Document local model-test results in docs/VALIDATION.md before tagging.
