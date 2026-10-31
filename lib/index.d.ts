/** Cordis plugin name. */
export declare const name: string

/** Services required by this plugin. */
export declare const inject: readonly string[]

/** Absolute directory holding the bundled `SKILL.md` trees. */
export declare const SKILLS_DIR: string

/** Frontmatter attributes; `metadata` keeps one nesting level. */
export interface SkillAttributes {
  [key: string]: string | Record<string, string>
}

/** Parsed `SKILL.md` content. */
export interface ParsedSkillMarkdown {
  attributes: SkillAttributes
  content: string
}

/**
 * Parse the YAML frontmatter that precedes a skill body.
 *
 * @param raw - complete `SKILL.md` file content.
 */
export declare function parseSkillMarkdown(raw: string): ParsedSkillMarkdown

/** One skill directory discovered under {@link SKILLS_DIR}. */
export interface BundledSkill {
  name: string
  description: string
  dir: string
  file: string
  metadata?: Record<string, string>
}

/** Read every skill directory under {@link SKILLS_DIR}. */
export declare function scanSkills(): Promise<BundledSkill[]>

/** Read-only provider serving the plugin's bundled skill bodies. */
export declare class WechatMpSkillProvider {
  name: string
  list(): Promise<unknown[]>
  get(candidate: { name?: string } | undefined): Promise<unknown | undefined>
}

/** Everything this plugin needs from the Cordis context. */
export interface PluginContext {
  skills: {
    registerProvider(factory: (control?: unknown) => WechatMpSkillProvider): unknown
  }
}

/**
 * Register the bundled provider on `ctx.skills`.
 *
 * @param ctx - Cordis context that mounts the skill registry.
 */
export declare function apply(ctx: PluginContext): void
