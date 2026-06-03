import { createContext, useContext, useEffect, useState } from "react";

const LanguageContext = createContext({ lang: "ar", setLang: () => {}, t: (ar, en) => ar });

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(() => localStorage.getItem("opscore_lang") || "ar");

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("dir", lang === "ar" ? "rtl" : "ltr");
    root.setAttribute("lang", lang);
    localStorage.setItem("opscore_lang", lang);
  }, [lang]);

  const setLang = (l) => setLangState(l);
  const t = (ar, en) => (lang === "ar" ? ar : en);
  const toggle = () => setLangState((l) => (l === "ar" ? "en" : "ar"));

  return (
    <LanguageContext.Provider value={{ lang, setLang, toggle, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export const useLang = () => useContext(LanguageContext);
