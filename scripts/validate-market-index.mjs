/**
 * Offline check of `market/index.json` against the format-1 rules DSH enforces.
 *
 * The rules mirror the shipped validator `@deepseek-ai/dsh-plugin-market-index`
 * (the package DSH itself uses to read an index). It is a mirror rather than an
 * import because that package lives inside the DSH application bundle, not in a
 * plugin's dependency graph. DSH still re-validates the real index on read; this
 * exits non-zero before a bad index ever reaches GitHub Pages.
 */

import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const indexPath = join(root, 'market/index.json')
const indexUrl = process.env.MARKET_INDEX_URL ?? 'https://example.github.io/dsh/market/index.json'

const LANGUAGE_ID = /^[a-z]{2,8}(?:-[a-z0-9]{1,8})*$/u
const PACKAGE_NAME = /^(?:@[a-z0-9][a-z0-9._~-]*\/)?[a-z0-9][a-z0-9._~-]*$/u
const SEMVER =
  /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-(?:(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$/u
const COMMIT = /^[0-9a-f]{40}$/u

const problems = []
const fail = (path, reason) => problems.push(`${path} ${reason}`)
const isObject = (value) => typeof value === 'object' && value !== null && !Array.isArray(value)

function requireObject(value, path) {
  if (!isObject(value)) fail(path, 'must be an object')
  return isObject(value) ? value : {}
}

function requireString(value, path) {
  if (typeof value !== 'string' || value.trim() === '') fail(path, 'must be a non-empty string')
  return typeof value === 'string' ? value : ''
}

function localized(value, path) {
  if (typeof value === 'string') {
    requireString(value, path)
    return
  }
  requireObject(value, path)
  if (!isObject(value)) return
  for (const [language, text] of Object.entries(value)) {
    if (!LANGUAGE_ID.test(language)) fail(`${path}.${language}`, 'must be keyed by a lowercase language id')
    requireString(text, `${path}.${language}`)
  }
  if (!Object.hasOwn(value, 'en')) fail(path, 'must contain en')
}

function url(value, path, protocols) {
  requireString(value, path)
  if (typeof value !== 'string') return undefined
  let parsed
  try {
    parsed = new URL(value)
  } catch {
    fail(path, 'must be an absolute URL')
    return undefined
  }
  if (!protocols.includes(parsed.protocol)) fail(path, `must use ${protocols.join(' or ')}`)
  if (parsed.username !== '' || parsed.password !== '') fail(path, 'must not contain credentials')
  if (value.includes('?') || value.includes('#')) fail(path, 'must not contain a query or fragment')
  return parsed
}

/** npm `homepage` values legitimately carry a `#readme` fragment, so this is looser than {@link url}. */
function homepage(value, path) {
  requireString(value, path)
  if (typeof value !== 'string') return
  let parsed
  try {
    parsed = new URL(value)
  } catch {
    fail(path, 'must be an absolute URL')
    return
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') fail(path, 'must use https: or http:')
}

function icon(value, path, base) {
  requireString(value, path)
  if (typeof value !== 'string') return
  if (value.startsWith('data:')) {
    if (!/^data:(?:image\/svg\+xml|image\/png|image\/jpeg|image\/webp);base64,[A-Za-z0-9+/]*={0,2}$/u.test(value)) {
      fail(path, 'must be a base64 SVG, PNG, JPEG, or WebP data URL')
    }
    return
  }
  let resolved
  try {
    resolved = new URL(value, base)
  } catch {
    fail(path, 'must be a URL reference')
    return
  }
  if (resolved.protocol !== 'https:' && resolved.origin !== base.origin) {
    fail(path, 'must resolve to https or the index origin')
  }
}

const raw = await readFile(indexPath, 'utf8')
let document
try {
  document = JSON.parse(raw)
} catch (error) {
  console.error(`market/index.json is not valid JSON: ${error.message}`)
  process.exit(1)
}

const base = new URL(indexUrl)
const index = requireObject(document, '$')
if (index.format !== 1) fail('$.format', 'must be 1')
localized(index.title, '$.title')
if (index.description !== undefined) localized(index.description, '$.description')

const declared = { categories: {}, labels: {}, sortKeys: {} }
const meta = index.metadata === undefined ? {} : requireObject(index.metadata, '$.metadata')
for (const group of ['categories', 'labels', 'sortKeys']) {
  if (meta[group] === undefined) continue
  const entries = requireObject(meta[group], `$.metadata.${group}`)
  for (const [id, declaration] of Object.entries(entries)) {
    if (id === '') fail(`$.metadata.${group}`, 'must not declare an empty id')
    const declaredItem = requireObject(declaration, `$.metadata.${group}.${id}`)
    localized(declaredItem.title, `$.metadata.${group}.${id}.title`)
    if (group === 'sortKeys' && declaredItem.order !== 'asc' && declaredItem.order !== 'desc') {
      fail(`$.metadata.${group}.${id}.order`, 'must be "asc" or "desc"')
    }
    declared[group][id] = declaredItem
  }
}

if (!Array.isArray(index.plugins)) fail('$.plugins', 'must be an array')
const names = new Set()
for (const [position, entry] of (Array.isArray(index.plugins) ? index.plugins : []).entries()) {
  const at = `$.plugins[${position}]`
  const plugin = requireObject(entry, at)

  const name = requireString(plugin.name, `${at}.name`)
  if (name.length > 214 || !PACKAGE_NAME.test(name)) fail(`${at}.name`, 'must be a valid npm package name')
  if (names.has(name)) fail(`${at}.name`, `duplicates ${name}`)
  names.add(name)

  if (plugin.title !== undefined) localized(plugin.title, `${at}.title`)
  if (plugin.description !== undefined) localized(plugin.description, `${at}.description`)
  if (plugin.icon !== undefined) icon(plugin.icon, `${at}.icon`, base)
  if (plugin.author !== undefined) requireString(plugin.author, `${at}.author`)
  if (plugin.homepage !== undefined) homepage(plugin.homepage, `${at}.homepage`)

  if (plugin.repository !== undefined) {
    const repository = requireObject(plugin.repository, `${at}.repository`)
    url(repository.url, `${at}.repository.url`, ['https:', 'http:'])
    if (repository.directory !== undefined) {
      const directory = requireString(repository.directory, `${at}.repository.directory`)
      if (directory.split('/').some((segment) => segment === '.' || segment === '..' || !/^[A-Za-z0-9._@+-]+$/u.test(segment))) {
        fail(`${at}.repository.directory`, 'must be a relative directory of safe segments')
      }
    }
  }

  const pluginMeta = plugin.metadata === undefined ? {} : requireObject(plugin.metadata, `${at}.metadata`)
  if (pluginMeta.category !== undefined) {
    const category = requireString(pluginMeta.category, `${at}.metadata.category`)
    if (!Object.hasOwn(declared.categories, category)) fail(`${at}.metadata.category`, `references undeclared id "${category}"`)
  }
  if (pluginMeta.labels !== undefined) {
    if (!Array.isArray(pluginMeta.labels)) fail(`${at}.metadata.labels`, 'must be an array')
    else for (const [i, label] of pluginMeta.labels.entries()) {
      const id = requireString(label, `${at}.metadata.labels[${i}]`)
      if (!Object.hasOwn(declared.labels, id)) fail(`${at}.metadata.labels[${i}]`, `references undeclared id "${id}"`)
    }
  }
  if (pluginMeta.keywords !== undefined) {
    if (!Array.isArray(pluginMeta.keywords)) fail(`${at}.metadata.keywords`, 'must be an array')
    else for (const [i, keyword] of pluginMeta.keywords.entries()) requireString(keyword, `${at}.metadata.keywords[${i}]`)
  }

  if (!Array.isArray(plugin.versions) || plugin.versions.length === 0) {
    fail(`${at}.versions`, 'must be a non-empty array')
    continue
  }
  const seen = new Set()
  for (const [i, item] of plugin.versions.entries()) {
    const versionAt = `${at}.versions[${i}]`
    const version = requireObject(item, versionAt)
    const text = requireString(version.version, `${versionAt}.version`)
    if (!SEMVER.test(text)) fail(`${versionAt}.version`, 'must be an exact SemVer version')
    if (seen.has(text)) fail(`${versionAt}.version`, `duplicates ${text}`)
    seen.add(text)
    if (!Number.isInteger(version.publishTimestamp) || version.publishTimestamp < 0 || version.publishTimestamp >= 1e11) {
      fail(`${versionAt}.publishTimestamp`, 'must be an integer number of Unix seconds in [0, 10^11)')
    }
    const source = requireObject(version.source, `${versionAt}.source`)
    if (source.type === 'npm') {
      if (source.registry !== undefined) url(source.registry, `${versionAt}.source.registry`, ['https:', 'http:'])
    } else if (source.type === 'git') {
      const gitUrl = url(source.url, `${versionAt}.source.url`, ['https:'])
      if (gitUrl !== undefined && !/^(?:\/[^/]+){2,}$/u.test(gitUrl.pathname)) {
        fail(`${versionAt}.source.url`, 'must name a repository with at least two path segments')
      }
      if (typeof source.commit !== 'string' || !COMMIT.test(source.commit)) {
        fail(`${versionAt}.source.commit`, 'must be a lowercase 40-hex-digit commit SHA')
      }
    } else {
      fail(`${versionAt}.source.type`, 'must be "npm" or "git"')
    }
  }
}

if (problems.length > 0) {
  console.error(`market index is invalid against format 1 (${problems.length} problem(s)):`)
  for (const problem of problems) console.error(`  - ${problem}`)
  process.exit(1)
}

console.log(`market/index.json OK: ${names.size} plugin(s), base ${pathToFileURL(indexPath).href}`)
