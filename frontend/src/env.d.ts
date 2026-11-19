interface ImportMetaEnv {
  /** Trafiklab key (ResRobot v2.1), shared by all visitors. Set at build time; public in the built site. */
  readonly VITE_TRAFIKLAB_API_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
