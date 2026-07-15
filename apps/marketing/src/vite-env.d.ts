/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Optional Loops (https://loops.so) newsletter-form id for the beta waitlist.
   * When unset, WaitlistForm falls back to the `REPLACE_WITH_LOOPS_FORM_ID`
   * placeholder and the form stays inert (validates but does not POST).
   */
  readonly VITE_LOOPS_FORM_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
