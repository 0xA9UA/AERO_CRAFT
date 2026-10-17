# Java mods and upgrades

Use `profiles` to choose a Minecraft/loader/JDK combination, then `new PATH --profile fabric-1.21.1 --id example_mod` (or the NeoForge, Forge or Java 25 Fabric profile). `build PATH` installs the selected JDK and Gradle, downloads loader/game dependencies through their official build plugins, and writes `build/libs/*.jar`. `gradle PATH -- runClient`, `runServer`, `genSources` (Fabric), or `wrapper` provide normal development tasks. The wrapper task can create conventional `gradlew`/`gradlew.bat` launchers for IDEs. Server EULA acceptance remains an explicit user action.

The JDK used to run Gradle, Java source level and class-file target are different constraints. The maintained suite profiles use Java 17 for Forge 1.20.1, Java 21 for 1.21.1, and Java 25 for Fabric 26.1. JDK 8 is available for analyzing and maintaining older 1.12 projects. Existing legacy projects should retain their compatible Gradle wrapper; do not run a modern profile's Gradle against ForgeGradle 2.x.

For an upgrade:

1. Build and test the old source with its original loader, mappings, JDK and Gradle. Preserve baseline JAR and world fixtures.
2. `inspect` source and JAR; `compare` old/new JARs records changed classes/resources and class-version requirements. Multi-release JAR entries and embedded dependency JARs need independent interpretation.
3. Generate a new target with the intended profile. Use `port OLD --to LOADER --minecraft VERSION --output assessment` to track API migration. Move one subsystem at a time. Do not simply change `sourceCompatibility` and call the mod upgraded.
4. Review registration events, mapping names, components/NBT, capabilities, networking payloads, tick events, rendering, worldgen codecs and recipe/data-pack format changes. Loader-specific JavaDocs and generated sources are the API authority for the chosen version.
5. Test server/client class separation. Preserve registry identifiers and migrate saves. Add real GameTests where useful; launch them using the loader's Gradle run configurations after defining fixtures.
6. Verify the built JAR metadata, resources and bytecode; then test actual game startup and gameplay. A bytecode-major match alone does not prove binary compatibility.

`AERO_JAVA_8_HOME`, `AERO_JAVA_17_HOME`, `AERO_JAVA_21_HOME` and `AERO_JAVA_25_HOME` select existing JDKs without editing global JAVA_HOME. Full JDKs include JVM runtimes, `javac`, `javap`, `jar`, `jarsigner`, `jcmd` and related tools; an additional JRE is unnecessary for this suite.
