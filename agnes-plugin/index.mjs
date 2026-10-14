// Verisolv as an AGH backend plugin.
//
// AGH owns the agent loop, the tool records and the approvals; this plugin gives
// the agent four capabilities that connect the runtime to a real structural
// analysis program.  Every tool shells out to the Python package and returns its
// JSON contract unchanged, so the tool record in the Trace view is the evidence.
//
// Environment:
//   VERISOLV_ROOT    project root containing the verisolv/ package
//   VERISOLV_PYTHON  python interpreter to use (default: python)
//
// The plugin is read-only with respect to the user's workspace: it computes and
// reports, it never writes files.

import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

const Kind = Symbol.for('TypeBox.Kind')

const PYTHON = process.env.VERISOLV_PYTHON || 'python'
const CLI_TIMEOUT_MS = Number(process.env.VERISOLV_TIMEOUT_MS || 180000)

function resolveRoot() {
  const candidates = [process.env.VERISOLV_ROOT, process.env.AGH_WORKSPACE, process.cwd()]
  for (const candidate of candidates) {
    if (candidate && existsSync(join(candidate, 'verisolv', 'cli.py'))) return candidate
  }
  return null
}

function runCli(args) {
  const root = resolveRoot()
  if (!root) {
    return Promise.reject(
      new Error(
        'verisolv project not found. Set VERISOLV_ROOT to the directory that contains ' +
          'the verisolv/ package (looked in VERISOLV_ROOT, AGH_WORKSPACE and the current ' +
          'working directory).',
      ),
    )
  }
  return new Promise((resolve, reject) => {
    execFile(
      PYTHON,
      ['-m', 'verisolv', ...args],
      { cwd: root, timeout: CLI_TIMEOUT_MS, maxBuffer: 16 * 1024 * 1024, windowsHide: true },
      (error, stdout, stderr) => {
        // The CLI uses exit code 1 for "ran fine, answer is not trustworthy".
        // That is a result, not a failure, so parse stdout whenever it is JSON.
        if (stdout && stdout.trim().startsWith('{')) {
          try {
            resolve(JSON.parse(stdout))
            return
          } catch (parseError) {
            reject(new Error(`could not parse verisolv output: ${parseError.message}`))
            return
          }
        }
        if (error) {
          reject(
            new Error(
              `verisolv command failed (${error.message})` +
                (stderr ? `\nstderr: ${stderr.slice(0, 2000)}` : ''),
            ),
          )
          return
        }
        reject(new Error('verisolv produced no JSON output'))
      },
    )
  })
}

// ---------------------------------------------------------------------------
// parameter schemas
// ---------------------------------------------------------------------------

const str = (description) => ({ [Kind]: 'String', type: 'string', description })
const num = (description) => ({ [Kind]: 'Number', type: 'number', description })
const int = (description) => ({ [Kind]: 'Integer', type: 'integer', description })
const bool = (description) => ({ [Kind]: 'Boolean', type: 'boolean', description })

const COMMON = {
  model: str('Reference structure: von_mises_truss or cantilever_truss.'),
  control: { [Kind]: 'Union', type: 'string', enum: ['load', 'displacement'],
    description: 'Control variable. Load control cannot pass a limit point; displacement control can.' },
  n_steps: int('Number of increments along the path (default 10).'),
  max_iter: int('Newton iterations allowed per increment (default 30).'),
  adaptive: bool('Halve the increment and retry after a failed iteration (default true).'),
  line_search: bool('Backtracking damping on the Newton update (default false).'),
  control_dof: int('Free DOF to prescribe when control is displacement.'),
  target_displacement: num('Displacement target for displacement control.'),
  path_points: int('How many equilibrium-path samples to return (default 12).'),
}

const parameters = (properties, required) => ({
  [Kind]: 'Object',
  type: 'object',
  properties,
  required,
  additionalProperties: false,
})

const meta = {
  isReadOnly: true,
  isDestructive: false,
  isConcurrencySafe: true,
  isOpenWorld: false,
  replay: 'safe',
  costHint: undefined,
  deferLoading: false,
  requiresApproval: 'never',
}

function toArgs(input) {
  const args = []
  if (input.model) args.push('--model', String(input.model))
  if (input.control) args.push('--control', String(input.control))
  if (input.n_steps != null) args.push('--n-steps', String(input.n_steps))
  if (input.max_iter != null) args.push('--max-iter', String(input.max_iter))
  if (input.adaptive != null) args.push(input.adaptive ? '--adaptive' : '--no-adaptive')
  if (input.line_search != null) args.push(input.line_search ? '--line-search' : '--no-line-search')
  if (input.control_dof != null) args.push('--control-dof', String(input.control_dof))
  if (input.target_displacement != null) args.push('--target-displacement', String(input.target_displacement))
  if (input.path_points != null) args.push('--path-points', String(input.path_points))
  return args
}

// The text below IS the result as far as the model is concerned.
//
// This matters more than it looks. An earlier version summarised compactly and
// relied on the `structured` sidecar to carry the detail, ending with a line
// telling the model to "read the per-case rows in the structured result". The
// model could not: it sees the text, and only the text. So it reported summary
// totals while the rows sat unread beside them -- and when the numbers it needed
// were not in the text, it reconstructed plausible ones from what it had. That is
// precisely the failure this whole project exists to name, and the tool was
// doing it to its own caller.
//
// So: everything the caller needs goes in the text. No exceptions, no "see the
// structured field".
function summarise(command, payload) {
  if (command === 'solve') {
    const state = payload.converged ? 'converged' : `did NOT converge (${payload.failure})`
    const peak = payload.peak_load
    return [
      `verisolv solve: ${state}`,
      `model=${payload.model} control=${payload.control}`,
      `load factor ${Number(payload.load_factor).toFixed(6)}, ` +
        `accepted ${payload.accepted_steps} / rejected ${payload.rejected_steps} increments`,
      `max displacement ${Number(payload.max_displacement).toExponential(4)}`,
      peak
        ? `peak load reached on this path: ${Number(peak.absolute_load).toFixed(1)} N ` +
          `(load factor ${Number(peak.load_factor).toFixed(6)}` +
          `${peak.interior ? ', INSIDE the path: the structure lost stability there' : ''})`
        : '',
      !payload.converged && payload.path?.length
        ? `last stable point before failure: load factor ` +
          `${Number(payload.path[payload.path.length - 1].load_factor).toFixed(6)}`
        : '',
    ]
      .filter(Boolean)
      .join('\n')
  }
  if (command === 'verify') {
    const verdict = payload.verdict ?? 'not_converged'
    const gciCheck = (payload.verification?.checks ?? []).find((c) => c.name === 'gci')
    const gciLines = []
    if (gciCheck) {
      const results = gciCheck.evidence?.results ?? []
      for (const g of results) {
        if (g.status === 'pass' || g.status === 'conditional') {
          gciLines.push(
            `  GCI ${g.quantity}: ${g.status}  p=${g.p?.toFixed(3)}  ` +
              `GCI_fine=${g.gci_fine_pct?.toFixed(3)}%  ` +
              `GCI_coarse=${g.gci_coarse_pct?.toFixed(3)}%  ` +
              `asymptotic_ratio=${g.asymptotic_ratio?.toFixed(3)}`,
          )
        } else {
          gciLines.push(`  GCI ${g.quantity}: ${g.status}  (${g.detail?.slice(0, 90)})`)
        }
      }
    }
    return [
      `verisolv verify: ${verdict}`,
      `claim level: ${payload.claim_level ?? 'smoke'}`,  // which claim this result supports
      ...(gciCheck && gciLines.length === 0
        ? ['  GCI gate: see checks']
        : gciLines.map((l) => l)),
      payload.peak_load
        ? `peak load: ${Number(payload.peak_load.absolute_load).toFixed(1)} N`
        : '',
    ]
      .filter(Boolean)
      .join('\n')
  }
  if (command === 'repair') {
    const peak = payload.peak_load
    const gciCheck = (payload.verification?.checks ?? []).find((c) => c.name === 'gci')
    const gciLines = []
    if (gciCheck) {
      for (const g of gciCheck.evidence?.results ?? []) {
        if (g.status === 'pass' || g.status === 'conditional') {
          gciLines.push(
            `  GCI ${g.quantity}: ${g.status}  p=${g.p?.toFixed(3)}  ` +
              `GCI_fine=${g.gci_fine_pct?.toFixed(3)}%  ` +
              `GCI_coarse=${g.gci_coarse_pct?.toFixed(3)}%  ` +
              `asymptotic_ratio=${g.asymptotic_ratio?.toFixed(3)}`,
          )
        } else {
          gciLines.push(`  GCI ${g.quantity}: ${g.status}  (${g.detail?.slice(0, 90)})`)
        }
      }
    }
    return [
      `verisolv repair: solved=${payload.solved}, final verdict=${payload.verdict}, ` +
        `claim level=${payload.claim_level ?? 'smoke'}`,
      payload.conclusion ? `ANSWER: ${payload.conclusion}` : '',
      peak
        ? `peak load ${Number(peak.absolute_load).toFixed(2)} N ` +
          `(load factor ${Number(peak.load_factor).toFixed(6)}, ` +
          `reference load ${Number(peak.reference_load).toFixed(0)} N, ` +
          `control value ${Number(peak.at_control_value).toFixed(6)}` +
          `${peak.interior ? ', INTERIOR: a limit point lies inside the traced path' : ''})`
        : '',
      `diagnosis: ${payload.diagnosis?.kind} - ${payload.diagnosis?.summary}`,
      ...(payload.attempts ?? []).map(
        (a) => `  ${a.accepted ? 'ACCEPTED' : 'rejected'} ${a.strategy} (verdict=${a.verdict})`,
      ),
      ...((payload.verification?.checks ?? [])
        .filter((c) => !c.passed && c.name !== 'gci')
        .map((c) => `  FAILED CHECK ${c.name}: ${c.detail}`)),
      ...gciLines,
      ...(!gciLines.length && !(payload.verification?.checks ?? []).some((c) => !c.passed)
        ? ['  all verification checks passed']
        : []),
    ]
      .filter(Boolean)
      .join('\n')
  }
  if (command === 'cases') {
    const s = payload.summary ?? {}
    const rows = payload.cases ?? []
    const pad = (value, width) => String(value ?? '-').padEnd(width).slice(0, width)

    const table = rows.map((r, index) => {
      const caught = (r.caught_by ?? []).join('+') || 'NOTHING'
      const rep =
        r.repair_helped === null || r.repair_helped === undefined
          ? '-'
          : r.repair_helped
            ? 'yes'
            : 'no'
      return (
        `${String(index + 1).padStart(2)}  ${pad(r.name, 34)} ${pad(r.test_class, 9)} ` +
        `${pad(r.root_cause, 30)} ${pad(r.observed, 21)} ${pad(r.verdict ?? '-', 9)} ` +
        `${pad(rep, 7)} ${pad(r.model_check_verdict, 10)} ${caught}`
      )
    })

    const counts = {}
    for (const r of rows) counts[r.test_class] = (counts[r.test_class] ?? 0) + 1
    const classLine = Object.entries(counts)
      .map(([name, n]) => `${name} ${n}`)
      .join(', ')

    const reference = rows.filter((r) => r.analytical)
    const referenceLines = reference.length
      ? [
          '',
          'closed-form comparison -- the ONLY check here that can catch a wrong',
          'formulation rather than an inconsistent one, because every other gate either',
          'reuses the solver\'s own assembly or re-runs the same code:',
          ...reference.map((r) => {
            const a = r.analytical
            const rel = a.relative_error != null ? a.relative_error.toExponential(2) : 'n/a'
            return (
              `  ${pad(r.name, 40)} ${pad(a.quantity, 18)} ` +
              `${rel} rel.err  ${a.passed ? 'AGREES' : 'DISAGREES'}  (tol ${a.tolerance})`
            )
          }),
        ]
      : []

    return [
      `verisolv case library: ${s.total_cases} labelled cases run  [${classLine}]`,
      '',
      ' #  case                               class     ground truth                   observed              verdict   rep*    model-chk  caught by',
      ...table,
      ...referenceLines,
      '',
      ' rep* = did the repair chain rescue it? "-" means the first solve converged, so',
      '        there was nothing for the escalation to do.',
      `detectable errors caught : ${s.detected}/${s.detectable_errors}`,
      `undetectable by design   : ${s.undetectable_by_design}  ` +
        `${(s.undetectable_cases ?? []).join(', ') || 'none'}`,
      ...((s.unexpectedly_detected_anyway ?? []).length
        ? [
            `  of those, caught anyway: ${s.unexpectedly_detected_anyway.join(', ')} ` +
              `-- caught by scale_consistency once the load magnitude exceeds the small-strain regime; the *category* (a unit slip) remains undetectable in principle: a x10 slip of the same kind is measured silent`,
          ]
        : []),
      `positive controls clean  : ${s.controls_clean}/${s.positive_controls}`,
      `repair acted correctly   : ${s.repair_behaviour_correct}/${s.total_cases}`,
      `missed                   : ${(s.missed ?? []).join(', ') || 'none'}`,
      ...((s.controls_false_alarm ?? []).length
        ? [`FALSE ALARMS             : ${s.controls_false_alarm.join(', ')}`]
        : []),
    ].join('\n')
  }
  if (command === 'checkmodel') {
    return [
      `verisolv checkmodel: ${payload.verdict}`,
      `  rigid-body modes: ${payload.rigid_body_modes}, ` +
        `static indeterminacy: ${payload.static_indeterminacy}`,
      ...(payload.findings ?? [])
        .filter((f) => !f.passed)
        .map((f) => `  [${f.severity}] ${f.check}: ${f.detail}`),
      ...(payload.verdict === 'ok' ? ['  every model check passed'] : []),
    ].join('\n')
  }
  return JSON.stringify(payload)
}

export const verisolvPlugin = {  inject: ['extension'],
  apply(ctx) {
    const agnes = ctx.extension()

    const register = (name, description, schema, command) => {
      agnes.registerTool({
        name,
        description,
        parameters: schema,
        meta,
        async execute(input = {}) {
          const payload = await runCli([command, ...toArgs(input)])
          return {
            content: [{ type: 'text', text: summarise(command, payload) }],
            structured: payload,
          }
        },
      })
    }

    register(
      'verisolv_models',
      'List the structural models available to the solver, with node and bar counts, free degrees ' +
        'of freedom, design-variable groups and the reference load magnitude. Call this once at the ' +
        'start if you do not already know which model to analyse.',
      parameters({}, []),
      'models',
    )

    register(
      'verisolv_solve',
      'Run ONE nonlinear structural analysis and report the raw outcome: whether the Newton ' +
        'iteration converged, the equilibrium path it traced, and any rejected increments. ' +
        'A non-converged result is information, not an error - it usually means the applied load ' +
        'passed a limit point. The reply includes peak_load (the largest load reached anywhere on ' +
        'the traced path) and, when nothing converged, limit_point_estimate. Use verisolv_repair ' +
        'instead if you want a trustworthy answer rather than a first look.',
      parameters(COMMON, []),
      'solve',
    )

    register(
      'verisolv_verify',
      'Solve and then independently re-derive the answer: rebuild the residual, check global force ' +
        'and moment balance, test the equilibrium path for discontinuities, and re-run with a ' +
        'refined step size. Returns verdict verified / suspect / rejected plus the individual ' +
        'checks. Use it when you already have a specific load case in mind and want to know ' +
        'whether the answer can be trusted.',
      parameters(COMMON, []),
      'verify',
    )

    register(
      'verisolv_repair',
      'The complete closed loop in a single call: solve, verify, diagnose why it failed, escalate ' +
        'through repair strategies (including switching from load control to displacement control), ' +
        'and verify again. Provides everything needed to answer "how much load can this carry": ' +
        'read the conclusion and peak_load fields. ' +
        'CALL THIS ONCE. It already searches the equilibrium path and reports the maximum load it ' +
        'carried; repeating the call with a different n_steps only re-samples the same curve and ' +
        'does not improve the answer. Do not read the solver source to understand the result - the ' +
        'conclusion, verdict and checks are the complete answer.',
      parameters(COMMON, []),
      'repair',
    )

    register(
      'verisolv_checkmodel',
      'Inspect a structural model WITHOUT running an analysis, and report whether it is well posed ' +
        'and physically plausible. Catches what numerical verification structurally cannot: a ' +
        'missing restraint (a mechanism), a Young\'s modulus or density typed with the wrong order ' +
        'of magnitude, a load with no restraint able to react it. These produce answers that are ' +
        'converged, self-consistent and about the wrong problem, so no amount of residual or ' +
        'equilibrium checking will find them. Call this when an analysis behaves inexplicably, or ' +
        'before reporting a result that will be acted on.',
      parameters(COMMON, []),
      'checkmodel',
    )

    register(
      'verisolv_cases',
      'Run the labelled case library: twenty cases (7 normal, 4 boundary, 9 failure) whose root '
        + 'cause is known by construction, each carrying a deterministic expected outcome. '
        + 'Returns, per case, the ground truth (root_cause), what the solver observed '
        + '(observed), the verification verdict, the model-check verdict, and whether the repair '
        + 'chain rescued it - plus a summary that separates errors something can detect from errors '
        + 'that are undetectable in principle (reversed load sign, unit slips): detectable_errors, '
        + 'detected, missed, undetectable_by_design, positive_controls, controls_clean, '
        + 'controls_false_alarm, repair_behaviour_correct, repair_mismatch. Use it to test a change '
        + 'to the solver, the diagnoser or the model checker, and to answer "how do you know your '
        + 'diagnosis is right?". The closed-form reference rows also print a per-case comparison '
        + 'against an analytical value - the only gate that can catch a wrong formulation, not '
        + 'just an inconsistent one.',
      parameters({}, []),
      'cases',
    )

    agnes.on('session_start', () => {
      const root = resolveRoot()
      agnes.ctx.log.info(
        root
          ? `verisolv tools ready (project root ${root})`
          : 'verisolv tools registered but project root unresolved; set VERISOLV_ROOT',
      )
    })
  },
}

// Exported so the text output can be tested without going through a live agent
// turn. The text IS the result as far as the model is concerned, so it deserves a
// test that does not depend on a model reading it correctly.
export const __summariseForTest = summarise
