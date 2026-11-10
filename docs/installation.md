# Installation and portability

The repository uses Python's standard library so the launcher works immediately after cloning. Python 3.11.8 or later supplies safe TAR extraction; 3.12+ is recommended. Git is required for cloning, not for every tool operation. The installer downloads the exact Node release, then `npm ci` applies the committed dependency lock. Selected, version-pinned native dependency scripts are explicitly allowlisted in `package.json`.

| Host | Runtime catalog | Notes |
|---|---|---|
| Linux x64 | Node, JDK 8/17/21/25 | End-to-end validation on Linux x64; glibc distribution required for upstream binaries |
| Linux arm64 | Node, JDK 8/17/21/25 | Native host validation delegated to CI/user hardware; not emulated as x64 |
| macOS x64 | Node, JDK 8/17/21/25 | Distribution's JDK `Contents/Home` is detected |
| macOS arm64 | Node, JDK 17/21/25 | Temurin JDK 8 arm64 is absent from this catalog; supply a compatible external JDK or use an x64 environment |
| Windows x64 | Node ZIP, JDK 8/17/21/25 ZIP | PowerShell installer; Python invokes Node/Gradle directly without fragile shell quoting |

Windows arm64, 32-bit hosts and Alpine/musl are not in the supported download matrix. A missing platform artifact fails explicitly. Optional Ghidra native support depends on the native components included by that release. Official Bedrock Dedicated Server runs on Windows/Linux x64, not macOS; use a separate appropriate test host for native checks there.

All tools stay under `.runtime/tools/TOOL`, verified download archives under `.runtime/downloads`, Gradle caches under `.runtime/gradle-cache`, and DSH state under `.runtime/dsh`. npm packages are local `node_modules` in the checkout. Keep secrets and private inputs outside tracked paths. Model settings and keys are configured through DSH and stored in the isolated DSH directory. Clone a fresh checkout elsewhere and run setup to reproduce the suite; do not copy native runtimes between different OS/CPU types.

An external full JDK can be selected using `AERO_JAVA_21_HOME` (and 8/17/25 equivalents). For native REA analysis, `GHIDRA_INSTALL_DIR` points to an extracted release; `tools install ghidra` supplies the catalog-pinned release automatically to the suite launcher. Java 21 runs Ghidra independently of a mod project's JDK. Existing external REA providers can use their documented environment configuration.

Run `python aero.py setup` after updating the checkout. Setup installs the pinned Node release even when an older managed Node already exists, then applies the npm lockfile. Downloads are checked and extracted before publication. Replaced managed tools are retained under `.runtime/tool-backups/`, and a failed publication restores the previous directory. A tool directory without an installation receipt requires moving it aside first. An interrupted install lock reports its exact path. Remove that empty `.installing` directory only when no install is running. `doctor` reports installed receipts and npm versions.

Setup and harness startup synchronize the active `reverse-engineer-anything` skill with the installed REA package. Existing copies, including legacy copies and user edits, are retained under `.runtime/dsh/skill-backups/` before the matching instructions are activated. References removed upstream are removed from the active copy. An identical bundle is left in place. Restart the harness after setup so its REA server and instructions load together.

Proxy/certificate requirements remain those of Python, Node/npm and Gradle. A first Java build fetches substantial Minecraft and loader dependencies and can take minutes. The source tree and scripts are small; caches can grow to many GB. Keep the resolved locks under version control. Upstream release assets and registries must remain available for a fresh online install. After installation, cached tools can be used offline where the underlying build dependencies are already cached.
