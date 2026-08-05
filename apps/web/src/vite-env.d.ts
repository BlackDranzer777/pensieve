/// <reference types="vite/client" />

/**
 * Typed environment variables.
 *
 * Without this, `import.meta.env.X` is `any`, which quietly re-introduces
 * untyped values at the exact boundary the project is trying to keep typed.
 */
interface ImportMetaEnv {
  /** Absolute base URL for the API. Empty means same-origin (`/api/v1/...`). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
