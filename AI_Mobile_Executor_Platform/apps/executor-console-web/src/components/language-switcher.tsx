import { useI18n } from "../lib/i18n";

export function LanguageSwitcher() {
  const { language, setLanguage, messages } = useI18n();

  return (
    <section className="language-card" aria-label={messages.shell.language}>
      <span>{messages.shell.language}</span>
      <div className="language-toggle" role="group" aria-label={messages.shell.language}>
        {(["en", "zh"] as const).map((option) => (
          <button
            key={option}
            className={`language-button ${language === option ? "active" : ""}`}
            type="button"
            onClick={() => setLanguage(option)}
          >
            {messages.shell.languageOptions[option]}
          </button>
        ))}
      </div>
    </section>
  );
}
