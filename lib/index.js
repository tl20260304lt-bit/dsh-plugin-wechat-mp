/**
 * Bundled skill provider for WeChat official-account (公众号) workflows.
 *
 * Registers two read-only skills on `ctx.skills`:
 *   - `wechat-mp-content` — read an article, its 留言/comments, and search 公众号.
 *   - `wechat-mp-corpus`  — archive every article of one account from Share Data.
 *
 * Zero runtime dependencies: the skill bodies and their Python helpers ship in
 * `../assets/skills/`, and the provider only reads them from disk on demand.
 *
 * @module dsh-plugin-wechat-mp
 */

import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

/** Cordis plugin name. */
export const name = 'skill-wechat-mp'

/** Service required by this plugin. */
export const inject = ['skills']

/** Provider name shown in skill diagnostics. */
const PROVIDER_NAME = 'wechat-mp'

/** Standard precedence rank for packaged skill providers. */
const BUNDLED_SKILL_RANK = 600

/** Both skills are safe to advertise to the model and to invoke by hand. */
const INVOCATION = Object.freeze({ modelInvocable: true, userInvocable: true })

/** Absolute directory holding the bundled `SKILL.md` trees. */
export const SKILLS_DIR = fileURLToPath(new URL('../assets/skills/', import.meta.url))

/**
 * Parse the YAML frontmatter that precedes a skill body.
 *
 * Only the shape skill files actually use is supported: top-level `key: value`
 * pairs, one level of nesting (for `metadata`), quoted scalars, and indented
 * continuation lines for a multi-line description. Anything else is preserved
 * verbatim in the returned attributes instead of failing the load.
 *
 * @param raw - complete `SKILL.md` file content.
 * @returns the parsed attributes and the body with the frontmatter removed.
 */
export function parseSkillMarkdown(raw) {
  const text = raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw
  const match = /^---\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n)?/.exec(text)
  if (match === null) return { attributes: {}, content: text.trim() }

  const attributes = {}
  let parent
  let lastKey

  for (const line of match[1].split(/\r?\n/)) {
    const trimmed = line.trim()
    if (trimmed === '' || trimmed.startsWith('#')) continue

    if (/^[ \t]/.test(line)) {
      const nested = /^[ \t]+([A-Za-z0-9_.-]+):[ \t]*(.*)$/.exec(line)
      if (nested !== null && parent !== undefined) {
        attributes[parent][nested[1]] = unquote(nested[2])
      } else if (lastKey !== undefined && typeof attributes[lastKey] === 'string') {
        attributes[lastKey] = `${attributes[lastKey]} ${trimmed}`.trim()
      }
      continue
    }

    const pair = /^([A-Za-z0-9_.-]+):[ \t]*(.*)$/.exec(line)
    if (pair === null) continue
    const key = pair[1]
    const value = pair[2].trim()
    if (value === '') {
      parent = key
      attributes[key] = {}
    } else {
      parent = undefined
      attributes[key] = unquote(value)
      lastKey = key
    }
  }

  return { attributes, content: text.slice(match[0].length).trim() }
}

/**
 * Drop the surrounding quotes of a scalar when both ends carry the same one.
 *
 * @param value - raw scalar text.
 * @returns the unquoted text.
 */
function unquote(value) {
  if (value.length < 2) return value
  const first = value[0]
  if ((first !== '"' && first !== "'") || value[value.length - 1] !== first) return value
  return value.slice(1, -1)
}

/**
 * Read every skill directory under {@link SKILLS_DIR}.
 *
 * A missing or unreadable asset tree yields an empty catalog: a broken install
 * must never take down the profile that loaded it. A skill without a
 * frontmatter description is skipped because the registry cannot advertise it.
 *
 * @returns the discovered skills sorted by name.
 */
export async function scanSkills() {
  let entries
  try {
    entries = await readdir(SKILLS_DIR, { withFileTypes: true })
  } catch {
    return []
  }

  const skills = []
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const dir = join(SKILLS_DIR, entry.name)
    const file = join(dir, 'SKILL.md')
    let raw
    try {
      raw = await readFile(file, 'utf8')
    } catch {
      continue
    }
    const { attributes } = parseSkillMarkdown(raw)
    const skillName = typeof attributes.name === 'string' && attributes.name !== ''
      ? attributes.name
      : entry.name
    const description = typeof attributes.description === 'string' ? attributes.description : ''
    if (description === '') continue
    const metadata = attributes.metadata
    skills.push({
      name: skillName,
      description,
      dir,
      file,
      ...(metadata !== undefined && typeof metadata === 'object' && Object.keys(metadata).length > 0
        ? { metadata }
        : {}),
    })
  }
  return skills.sort((left, right) => left.name.localeCompare(right.name))
}

/**
 * Map one discovered skill to the provider-neutral candidate shape.
 *
 * @param skill - one entry from {@link scanSkills}.
 * @returns a candidate the registry can merge and resolve.
 */
function toCandidate(skill) {
  return {
    name: skill.name,
    description: skill.description,
    invocation: { ...INVOCATION },
    provider: PROVIDER_NAME,
    source: 'bundled',
    resourceBase: { kind: 'directory', path: skill.dir },
    rank: BUNDLED_SKILL_RANK,
    locator: { kind: 'bundled-skill-markdown', path: skill.file },
  }
}

/**
 * Read-only provider serving the plugin's bundled skill bodies.
 */
export class WechatMpSkillProvider {
  /** Provider label merged into the registry catalog. */
  name = PROVIDER_NAME

  /**
   * Report the bundled catalog.
   *
   * @returns every bundled skill candidate.
   */
  async list() {
    return (await scanSkills()).map(toCandidate)
  }

  /**
   * Load one bundled skill body on demand.
   *
   * The candidate is re-resolved by name so a renamed or removed asset yields
   * `undefined` instead of stale content the registry would have to reject.
   *
   * @param candidate - a candidate previously returned by {@link list}.
   * @returns the full skill definition, or `undefined` when it disappeared.
   */
  async get(candidate) {
    if (candidate === undefined || candidate === null || typeof candidate.name !== 'string') {
      return undefined
    }
    const skill = (await scanSkills()).find((entry) => entry.name === candidate.name)
    if (skill === undefined) return undefined

    let raw
    try {
      raw = await readFile(skill.file, 'utf8')
    } catch {
      return undefined
    }

    const parsed = parseSkillMarkdown(raw)
    return {
      name: skill.name,
      description: skill.description,
      invocation: { ...INVOCATION },
      provider: PROVIDER_NAME,
      source: 'bundled',
      resourceBase: { kind: 'directory', path: skill.dir },
      path: skill.file,
      ...(skill.metadata === undefined ? {} : { metadata: skill.metadata }),
      content: parsed.content,
    }
  }
}

/**
 * Register the bundled provider on `ctx.skills`.
 *
 * @param ctx - Cordis context that mounts the skill registry.
 */
export function apply(ctx) {
  ctx.skills.registerProvider(() => new WechatMpSkillProvider())
}
