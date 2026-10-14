// Print exactly what a model will see from each verisolv tool.
//
// This exists because the model sees the text and nothing else. Testing the text
// by asking a model to read it is circular; testing it here is not.

import { spawnSync } from 'node:child_process'

import { __summariseForTest as summarise } from '../agnes-plugin/index.mjs'

const PY = process.env.VERISOLV_PYTHON || 'python'
const CWD = process.env.VERISOLV_ROOT || process.cwd()

function runCli(args) {
  const proc = spawnSync(PY, ['-m', 'verisolv', ...args], {
    cwd: CWD,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  })
  if (proc.status !== 0 && !proc.stdout.trim()) {
    throw new Error(`cli failed (${proc.status}): ${proc.stderr.slice(0, 400)}`)
  }
  return JSON.parse(proc.stdout)
}

const CASES = [
  ['checkmodel', ['checkmodel', '--model', 'von_mises_truss']],
  ['solve', ['solve', '--model', 'von_mises_truss', '--n-steps', '8']],
  ['repair', ['repair', '--model', 'von_mises_truss']],
  ['cases', ['cases']],
]

for (const [command, args] of CASES) {
  const payload = runCli(args)
  const text = summarise(command, payload)
  console.log('='.repeat(78))
  console.log(`TOOL verisolv_${command} — this is the entire result the model sees`)
  console.log('='.repeat(78))
  console.log(text)
  console.log(`[${text.length} chars]`)

  if (/structured result|see the structured|undefined/.test(text)) {
    console.log('*** REGRESSION: text refers to data the model cannot reach ***')
    process.exitCode = 1
  }
  console.log()
}
