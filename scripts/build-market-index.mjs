/**
 * Build the format-1 plugin-market index consumed by DSH's Plugins → Discover tab.
 *
 * The index is regenerated from package.json, so bumping the version only needs
 * `npm run market:build` after the release is published to npm.
 */

import { execFileSync } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const pkg = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'))

/** Unix seconds for the version's npm publish time, falling back to now. */
function publishTimestamp() {
  try {
    const windows = process.platform === 'win32'
    const raw = execFileSync(
      windows ? 'cmd.exe' : '/bin/sh',
      [windows ? '/c' : '-c', `npm view ${pkg.name} time --json`],
      { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
    )
    const times = JSON.parse(raw)
    const published = times[pkg.version]
    if (typeof published === 'string') {
      const seconds = Math.floor(Date.parse(published) / 1000)
      if (Number.isInteger(seconds) && seconds > 0) return seconds
    }
  } catch {
    // Not published yet, or offline: the index still has to be buildable.
  }
  return Math.floor(Date.now() / 1000)
}

/** Strip the `git+` prefix and `.git` suffix the format forbids on https repository URLs. */
function repositoryUrl(value) {
  if (typeof value !== 'string') return undefined
  const cleaned = value.replace(/^git\+/, '').replace(/\.git$/, '')
  return cleaned.startsWith('https://') || cleaned.startsWith('http://') ? cleaned : undefined
}

const repository = repositoryUrl(pkg.repository?.url)

const index = {
  format: 1,
  title: {
    en: 'WeChat & Chinese content tools for DSH',
    zh: 'DSH 公众号与中文内容工具',
  },
  description: {
    en: 'Community plugins that give DeepSeek Harness access to WeChat official-account content: article bodies, 留言/comments, and local archives.',
    zh: '给 DeepSeek Harness 补上微信公众号能力的社区插件：正文、留言、本地存档。',
  },
  metadata: {
    categories: {
      content: { title: { en: 'Content & publishing', zh: '内容与发布' } },
    },
    labels: {
      windows: { title: { en: 'Windows only', zh: '仅 Windows' } },
      skills: { title: { en: 'Bundled skills', zh: '纯技能包' } },
      wechat: { title: { en: 'WeChat', zh: '微信' } },
    },
  },
  plugins: [
    {
      name: pkg.name,
      title: { en: 'WeChat official-account skills', zh: '公众号工具箱' },
      description: {
        en: 'Read an article and its 留言/comments with the live WeChat session, and archive a whole 公众号 into an indexed local corpus.',
        zh: '用微信客户端的实时会话读取文章与留言，并把整个公众号存档成带索引的本地语料库。',
      },
      icon: '../icon.svg',
      author: 'TaoLiu',
      ...(pkg.homepage === undefined ? {} : { homepage: pkg.homepage }),
      ...(repository === undefined ? {} : { repository: { url: repository } }),
      metadata: {
        category: 'content',
        keywords: pkg.keywords,
        labels: ['windows', 'skills', 'wechat'],
      },
      versions: [
        {
          version: pkg.version,
          publishTimestamp: publishTimestamp(),
          source: { type: 'npm' },
        },
      ],
    },
  ],
}

await mkdir(join(root, 'market'), { recursive: true })
await writeFile(join(root, 'market/index.json'), `${JSON.stringify(index, null, 2)}\n`, 'utf8')
console.log(`wrote market/index.json for ${pkg.name}@${pkg.version}`)
