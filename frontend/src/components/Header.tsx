import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthProvider";
import { Button } from "./ui/Button";
import { ChangePassword } from "../features/account/ChangePassword";

export function Header() {
  const { t, i18n } = useTranslation();
  const { appUser, signOut } = useAuth();

  const switchLang = (lng: string) => {
    i18n.changeLanguage(lng);
    localStorage.setItem("lang", lng);
  };

  return (
    <header className="flex items-center justify-between border-b bg-white px-6 py-3 shadow-sm">
      <div className="flex items-center gap-3">
        <span className="text-xl">🥗</span>
        <div>
          <div className="text-sm font-semibold text-brand-dark">{t("app_title")}</div>
          <div className="text-xs text-gray-500">{t("welcome_brand")}</div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex gap-1 text-xs">
          {["ru", "en"].map((lng) => (
            <button
              key={lng}
              onClick={() => switchLang(lng)}
              className={`rounded px-2 py-1 ${
                i18n.resolvedLanguage === lng ? "bg-brand text-white" : "text-gray-600"
              }`}
            >
              {lng.toUpperCase()}
            </button>
          ))}
        </div>
        {appUser && (
          <span className="text-xs text-gray-500">
            {appUser.email} · {t(`roles.${appUser.role}`)}
          </span>
        )}
        {appUser && <ChangePassword />}
        <Button variant="outline" onClick={() => signOut()}>
          {t("nav.logout")}
        </Button>
      </div>
    </header>
  );
}
