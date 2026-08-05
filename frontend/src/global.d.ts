declare global {
  interface Window {
    pywebview?: {
      api?: {
        pick_folder: (initial: string) => string | null;
      };
    };
  }
}

export {};
