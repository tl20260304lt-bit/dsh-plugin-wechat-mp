import assert from 'node:assert/strict'
import { access, readFile } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'
import test from 'node:test'

import {
  apply,
  inject,
  name,
  parseSkillMarkdown,
  scanSkills,
  SKILLS_DIR,
  WechatMpSkillProvider,
} from '../lib/index.js'

/** Mount the plugin on a minimal stand-in for the Cordis skill registry. */
function mount() {
  const registered = []
  const ctx = {
    skills: {
      registerProvider(factory) {
        registered.push(factory({ signal: new AbortController().signal, invalidate() {} }))
        return () => {}
      },
    },
  }
  apply(ctx)
  return registered
}

test('plugin contract: identity, injection, and provider registration', () => {
  assert.equal(name, 'skill-wechat-mp')
  assert.deepEqual(inject, ['skills'])

  const providers = mount()
  assert.equal(providers.length, 1)
  assert.ok(providers[0] instanceof WechatMpSkillProvider)
  assert.equal(providers[0].name, 'wechat-mp')
})

test('catalog advertises both bundled skills', async () => {
  const [provider] = mount()
  const candidates = await provider.list()

  assert.deepEqual(
    candidates.map((candidate) => candidate.name),
    ['wechat-mp-content', 'wechat-mp-corpus'],
  )
  for (const candidate of candidates) {
    assert.equal(candidate.provider, 'wechat-mp')
    assert.equal(candidate.source, 'bundled')
    assert.equal(candidate.rank, 600)
    assert.deepEqual(candidate.invocation, { modelInvocable: true, userInvocable: true })
    assert.ok(candidate.description.length > 40, `${candidate.name} needs a triggerable description`)
    assert.equal(candidate.resourceBase.kind, 'directory')
    assert.ok(isAbsolute(candidate.resourceBase.path))
    assert.equal(candidate.resourceBase.path, join(SKILLS_DIR, candidate.name))
  }
})

test('get returns the body without frontmatter', async () => {
  const [provider] = mount()
  for (const candidate of await provider.list()) {
    const skill = await provider.get(candidate)
    assert.ok(skill, `${candidate.name} should load`)
    assert.equal(skill.name, candidate.name)
    assert.equal(skill.description, candidate.description)
    assert.deepEqual(skill.invocation, candidate.invocation)
    assert.equal(skill.provider, 'wechat-mp')
    assert.equal(skill.source, 'bundled')
    assert.ok(skill.path.endsWith('SKILL.md'))
    assert.ok(skill.content.startsWith('# '), 'body should start with its heading')
    assert.ok(!skill.content.startsWith('---'), 'frontmatter must be stripped')
    assert.ok(!/^name: /m.test(skill.content), 'frontmatter keys must not leak into the body')
  }
})

test('get keeps one level of frontmatter metadata', async () => {
  const [provider] = mount()
  const [candidate] = await provider.list()
  const skill = await provider.get(candidate)
  if (candidate.name === 'wechat-mp-corpus') {
    assert.equal(skill.metadata['short-description'], '微信文章本地存档')
  }
})

test('unknown or stale candidates resolve to undefined', async () => {
  const [provider] = mount()
  assert.equal(await provider.get(undefined), undefined)
  assert.equal(await provider.get({ name: 'does-not-exist' }), undefined)
})

test('frontmatter parser handles quotes, nesting, and continuation lines', () => {
  const parsed = parseSkillMarkdown(
    ['---', 'name: demo-skill', 'description: "first line"', 'metadata:', '  short-description: x', '---', '', '# Body', '', 'text'].join('\n'),
  )
  assert.equal(parsed.attributes.name, 'demo-skill')
  assert.equal(parsed.attributes.description, 'first line')
  assert.deepEqual(parsed.attributes.metadata, { 'short-description': 'x' })
  assert.equal(parsed.content, '# Body\n\ntext')
})

test('a document without frontmatter keeps its whole body', () => {
  const parsed = parseSkillMarkdown('# Just a body\n')
  assert.deepEqual(parsed.attributes, {})
  assert.equal(parsed.content, '# Just a body')
})

test('bundled skills carry no machine-specific absolute paths', async () => {
  for (const skill of await scanSkills()) {
    const raw = await readFile(skill.file, 'utf8')
    assert.ok(!/(?<![A-Za-z])[A-Za-z]:[\\/]/.test(raw), `${skill.name} must not hardcode a Windows path`)
    assert.ok(!raw.includes('/Users/'), `${skill.name} must not hardcode a POSIX home path`)
    assert.ok(!raw.includes('.codex'), `${skill.name} must not point at a Codex installation`)
  }
})

test('every relative asset a skill references exists', async () => {
  for (const skill of await scanSkills()) {
    const raw = await readFile(skill.file, 'utf8')
    const refs = new Set(raw.match(/(?:scripts|references)\/[A-Za-z0-9._-]+/g) ?? [])
    assert.ok(refs.size > 0, `${skill.name} should reference its helpers`)
    for (const ref of refs) {
      await access(join(skill.dir, ref))
    }
  }
})

test('shipped Python helpers are present and non-empty', async () => {
  const expected = [
    'wechat-mp-content/scripts/wx_mp.py',
    'wechat-mp-corpus/scripts/probe_env.py',
    'wechat-mp-corpus/scripts/watch_corpus.py',
    'wechat-mp-corpus/scripts/build_index.py',
  ]
  for (const relative of expected) {
    const body = await readFile(join(SKILLS_DIR, relative), 'utf8')
    assert.ok(body.length > 1000, `${relative} looks truncated`)
  }
})
