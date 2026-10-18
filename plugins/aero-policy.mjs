/** DSH 0.2.1-rc.2 integration: grounded port workflow and delivery verification. */
import { execFile } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import {
  createReadStream, existsSync, mkdirSync, readFileSync, realpathSync, renameSync, writeFileSync,
} from 'node:fs';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { promisify } from 'node:util';

export const name = 'aero-craft-policy';
export const inject = ['systemPrompt', 'tools'];
const executeFile = promisify(execFile);

const GUIDANCE = `You are developing Minecraft projects with AERO_CRAFT.
For a Java/Bedrock port, use mcp__aerocraft__start_port first to register the source and target project. Read the registered project's aero-port.json, follow the autonomous port workflow, and keep feature evidence and required acceptance tests current. A user-invoked /reverse-engineer-anything is the installed REA skill: load it through the skill tool before inspecting the supplied artifact. REA's archive evidence complements JVM decompilation through AERO_CRAFT; do not treat decompiled text as observed game behavior.
Implement and verify one playable vertical slice before expanding content counts. Never suppress missing Minecraft API members, retain placeholder mechanics, or replace meaningful tests to obtain a green build. API declarations, engine schemas and native tests determine support. Use the suite's server discovery and native verification tools; a missing PATH command is not proof that a server is unavailable. Failed web search must not be treated as version or API evidence.
Before presenting a .mcaddon or marking a port goal complete, run the project's verification workflow and gate. The gate is read-only and checks current evidence; it does not execute tests. Fix blockers and rerun the required tests rather than editing evidence to force approval. A structural validation result, generated content count or starter test does not establish working machines or parity. Full release delivery and goal completion require ready:true. When candidate_ready:true permits client testing, present only the exact verified artifact with every file description beginning TEST CANDIDATE: and clearly list unfinished features and client checks. This does not complete the port. Keep working when required features are unfinished. If a required connected-client check needs a person, state the exact unobserved check and leave the port incomplete; do not claim full parity.
This is the AERO_CRAFT suite installed with the npm release of DSH. The DSH package directory is not necessarily an upstream source checkout. Use the actual working directory and project paths returned by tools. Project-specific instructions and source files are separate from the installed harness. These checks do not change existing sandbox or approval policies.`;

/** Find the real project containing a delivered file or working directory. */
export function nearestProject(path, marker = 'aero-project.json') {
  let current = resolve(path);
  if (existsSync(current)) current = realpathSync(current);
  for (;;) {
    if (existsSync(join(current, marker))) return current;
    const parent = dirname(current);
    if (parent === current) return undefined;
    current = parent;
  }
}

function reasonText(report) {
  const values = report?.blockers ?? report?.reasons ?? report?.errors;
  if (!Array.isArray(values) || values.length === 0) return 'No current passing verification evidence.';
  return values.slice(0, 20).map(value => typeof value === 'string'
    ? value : JSON.stringify(value)).join('\n');
}

async function fileHash(path, signal) {
  const digest = createHash('sha256');
  for await (const chunk of createReadStream(path, { signal })) digest.update(chunk);
  return digest.digest('hex');
}

/** Run the read-only CLI through argv, without a shell or model-supplied command. */
export async function checkGate(config, project, signal) {
  let stdout;
  let failure;
  try {
    ({ stdout } = await executeFile(config.python,
      [config.cli, 'gate', project, '--json'], {
        cwd: config.workspace, encoding: 'utf8', timeout: 30000,
        maxBuffer: 1024 * 1024, windowsHide: true, signal,
      }));
  } catch (error) {
    if (signal?.aborted) throw error;
    failure = error;
    stdout = error.stdout;
  }
  let report;
  try { report = JSON.parse(stdout ?? ''); } catch { /* Deny unknown outcomes. */ }
  if (!failure && report?.ready === true) return { ready: true, report };
  const reason = report && typeof report === 'object'
    ? reasonText(report)
    : `Could not read the verification gate: ${failure?.message ?? 'invalid JSON output'}`;
  // Exit 1 is the CLI's deliberate not-ready verdict; crashes/timeouts cannot
  // turn a partial stdout object into an approved test candidate.
  const candidateReady = (!failure || failure.code === 1)
    && report?.candidate_ready === true;
  return { ready: false, candidateReady, reason, report };
}

/** Session-scoped targets survive a harness restart, independent of compaction. */
export function createPolicy(config, currentDirectory = exec =>
  exec.agent?.session?.header?.cwd ?? config.workspace) {
  const cached = new Map();
  const identity = exec => String(exec.agent?.session?.header?.id ?? 'workspace');
  const stateFile = id => join(config.stateDirectory,
    createHash('sha256').update(id).digest('hex') + '.json');

  function targets(exec) {
    const id = identity(exec);
    if (!cached.has(id)) {
      let projects = [];
      const path = stateFile(id);
      if (existsSync(path)) {
        const saved = JSON.parse(readFileSync(path, 'utf8'));
        if (saved.version !== 1 || saved.session !== id || !Array.isArray(saved.projects)
          || saved.projects.some(p => typeof p !== 'string' || !isAbsolute(p))) {
          throw new Error('Invalid AERO_CRAFT session target state; restore the state or register the port again.');
        }
        projects = saved.projects;
      }
      cached.set(id, new Set(projects));
    }
    return cached.get(id);
  }

  function remember(exec, project) {
    const set = targets(exec);
    if (set.has(project)) return;
    set.add(project);
    const id = identity(exec);
    mkdirSync(config.stateDirectory, { recursive: true, mode: 0o700 });
    const temporary = stateFile(id) + '.' + randomUUID() + '.tmp';
    writeFileSync(temporary, JSON.stringify({ version: 1, session: id, projects: [...set] }),
      { encoding: 'utf8', mode: 0o600 });
    renameSync(temporary, stateFile(id));
  }

  function observe(exec, result) {
    if (exec.name !== 'mcp__aerocraft__start_port' || result.isError
      || result.value?.isError || typeof exec.arguments?.path !== 'string') return;
    // Prefer the authoritative returned path, including the MCP text envelope.
    // The fixed MCP workspace is the fallback for relative tool arguments.
    let returned = result.value?.structuredContent?.project ?? result.value?.project;
    for (const block of result.value?.content ?? result.content ?? []) {
      if (returned || block.type !== 'text') continue;
      try { returned = JSON.parse(block.text).project; } catch { /* Not a JSON result. */ }
    }
    const path = typeof returned === 'string' ? returned : exec.arguments.path;
    const project = nearestProject(resolve(config.workspace, path));
    if (project && existsSync(join(project, 'aero-port.json'))) remember(exec, project);
  }

  async function before(exec, next) {
    const completing = exec.name === 'update_goal' && exec.arguments?.action === 'complete';
    const files = exec.name === 'present' && Array.isArray(exec.arguments?.files)
      ? exec.arguments.files.filter(file => typeof file?.path === 'string'
        && /\.mcaddon$/i.test(file.path)) : [];
    const testCandidate = files.length > 0 && exec.arguments.files.every(file =>
      typeof file?.description === 'string' && file.description.startsWith('TEST CANDIDATE:'));
    if (!completing && files.length === 0) return next();
    try {
      const projects = new Set(completing ? targets(exec) : []);
      const presented = new Map();
      if (completing) {
        const project = nearestProject(currentDirectory(exec), 'aero-port.json');
        if (project) projects.add(project);
      }
      for (const file of files) {
        const path = resolve(currentDirectory(exec), file.path);
        const project = nearestProject(path);
        if (!project) return { kind: 'deny', reason: 'AERO_CRAFT could not locate the aero-project.json owning this .mcaddon. Present the verified artifact from its source project.' };
        projects.add(project);
        presented.set(project, [...(presented.get(project) ?? []), path]);
        // Retain the association even when the delivery gate rejects the file.
        remember(exec, project);
      }
      for (const project of projects) {
        const result = await checkGate(config, project, exec.signal);
        if (!result.ready && !(testCandidate && !completing && result.candidateReady)) return {
          kind: 'deny',
          reason: `AERO_CRAFT verification has not passed for ${project}.\n${result.reason}\nContinue implementing and verifying this project, then run aero.py gate PROJECT --json. Goal completion requires ready:true. Test delivery is allowed only after candidate_ready:true, with the verified artifact and every file description beginning TEST CANDIDATE:. A label cannot bypass failing technical checks.`,
        };
        for (const path of presented.get(project) ?? []) {
          const artifact = result.report?.artifact;
          if (typeof artifact?.path !== 'string' || !isAbsolute(artifact.path)
            || !/^[a-f0-9]{64}$/i.test(artifact.sha256 ?? '')) {
            return { kind: 'deny', reason: 'AERO_CRAFT gate did not identify a verified artifact. Rerun project verification before presenting this .mcaddon.' };
          }
          if (await fileHash(path, exec.signal) !== artifact.sha256.toLowerCase()) {
            return { kind: 'deny', reason: 'This .mcaddon does not match the artifact verified by AERO_CRAFT. Present the verified build or rebuild and rerun verification after changes.' };
          }
        }
      }
    } catch (error) {
      if (exec.signal?.aborted) return { kind: 'cancel' };
      return { kind: 'deny', reason: `AERO_CRAFT could not verify this delivery: ${error.message}` };
    }
    // Never return 'allow' directly: the rest of DSH's policy chain still runs.
    return next();
  }

  return { before, observe };
}

/** Cordis plugin entry point, using DSH's supported prompt and tool seams. */
export function apply(ctx, config) {
  for (const key of ['python', 'cli', 'workspace', 'stateDirectory']) {
    if (typeof config?.[key] !== 'string' || !isAbsolute(config[key])) {
      throw new Error(`AERO_CRAFT policy requires an absolute ${key} path.`);
    }
  }
  const workflow = config.guide && existsSync(config.guide)
    ? readFileSync(config.guide, 'utf8') : '';
  ctx.systemPrompt.section({
    name: 'aero-craft:port-workflow', order: 850, interpolate: false,
    text: GUIDANCE + (workflow ? '\n\n' + workflow : ''),
  });
  const policy = createPolicy(config, exec => {
    const directories = ctx.get?.('workingDirectory');
    return exec.agent && directories
      ? directories.get(exec.agent.session)
      : exec.agent?.session?.header?.cwd ?? config.workspace;
  });
  ctx.on('tools/pre-execute', policy.before);
  ctx.on('tools/result', policy.observe);
}
