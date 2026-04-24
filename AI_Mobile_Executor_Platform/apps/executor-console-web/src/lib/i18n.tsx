import {
  createContext,
  type PropsWithChildren,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { MESSAGES, type AppLanguage, type MessageBundle } from "./messages";

const STORAGE_KEY = "executor-console-language";

function normalizeLanguage(value: string | null | undefined): AppLanguage {
  const lowered = value?.toLowerCase();
  if (lowered?.startsWith("zh")) {
    return "zh";
  }
  return "en";
}

function getInitialLanguage(): AppLanguage {
  if (typeof window === "undefined") {
    return "en";
  }

  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === "en" || saved === "zh") {
    return saved;
  }

  return normalizeLanguage(window.navigator.language);
}

interface I18nContextValue {
  language: AppLanguage;
  setLanguage: (language: AppLanguage) => void;
  messages: MessageBundle;
}

const defaultValue: I18nContextValue = {
  language: "en",
  setLanguage: () => undefined,
  messages: MESSAGES.en,
};

const I18nContext = createContext<I18nContextValue>(defaultValue);

export function I18nProvider({ children }: PropsWithChildren) {
  const [language, setLanguage] = useState<AppLanguage>(getInitialLanguage);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, language);
  }, [language]);

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      messages: MESSAGES[language],
    }),
    [language],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}

export function formatMappedValue(
  map: Record<string, string>,
  rawValue: string | null | undefined,
  fallback: string,
) {
  if (!rawValue) {
    return fallback;
  }

  const localized = map[rawValue];
  return localized ? `${localized} | ${rawValue}` : rawValue;
}
