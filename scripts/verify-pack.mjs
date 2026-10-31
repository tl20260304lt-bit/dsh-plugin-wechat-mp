/**
 * Prove the published tarball is self-contained: pack it, extract it away from
 * the checkout, then load the packaged plugin and read both skill bodies.
 *
 * This catches the failure mode a unit test cannot: a file that `files` omits
 * and that only the working tree happens to have.
 */

import { execFileSync } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))

/** Run npm through a shell: Node refuses to spawn the Windows `npm.cmd` shim directly. */
function runNpm(args) {
  const windows = process.platform === 'win32'
  return execFileSync(windows ? 'cmd.exe' : '/bin/sh', [windows ? '/c' : '-c', `npm ${args.join(' ')}`], {
    cwd: root,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
}

const packed = JSON.parse(runNpm(['pack', '--json']))
const [info] = packed
const workdir = await mkdtemp(join(tmpdir(), 'dsh-pack-verify-'))

try {
  execFileSync('tar', ['-xzf', join(root, info.filename), '-C', workdir])
  const entry = pathToFileURL(join(workdir, 'package', 'lib', 'index.js')).href
  const mod = await import(entry)

  if (mod.name !== 'skill-wechat-mp') throw new Error(`unexpected plugin name ${String(mod.name)}`)
  if (JSON.stringify(mod.inject) !== JSON.stringify(['skills'])) throw new Error('inject must be ["skills"]')

  const provider = new mod.WechatMpSkillProvider()
  const candidates = await provider.list()
  const names = candidates.map((candidate) => candidate.name).sort()
  if (JSON.stringify(names) !== JSON.stringify(['wechat-mp-content', 'wechat-mp-corpus'])) {
    throw new Error(`tarball lost a skill: ${JSON.stringify(names)}`)
  }

  for (const candidate of candidates) {
    const skill = await provider.get(candidate)
    if (skill === undefined || skill.content.length < 500) {
      throw new Error(`${candidate.name} body is missing or truncated in the tarball`)
    }
  }

  console.log(
    `tarball OK: ${info.filename} (${info.size} bytes, ${info.entryCount} files) → ${candidates.length} skills load from the extracted package`,
  )
} finally {
  await rm(join(root, info.filename), { force: true })
  await rm(workdir, { recursive: true, force: true })
}
